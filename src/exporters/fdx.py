"""FDX (Final Draft XML) exporters for the Script Notes-to-Outline Matrix Agent.

Two honest, format-interchange functions (NOT a live in-editor plugin — Final Draft has
no public plugin API). We write standard .fdx XML so a writer can open the result in
Final Draft and see the Draft-2 revision notes as **native, non-printing <ScriptNote>**
elements** — they appear in the margin / as collapsible note popups and do NOT alter
scene lengths or page count (unlike injecting Action paragraphs, which would).

- inject_matrix_notes_to_fdx: merge a revision checklist into an EXISTING .fdx script.
- generate_standalone_fdx_notes_summary: build a standalone .fdx holding only the notes
  (used when no source script is supplied).

Checklist contract — accepts EITHER shape:
  A) build_checklist output: [{"scene": "5"|"INT. ...", "items": [str], "conflicts": [str]}]
  B) rich note dict:        {"scene_num": 5, "category": "...", "conflict_flagged": bool,
                              "summary_note": "...", "action_item": "..."}
Scene matching uses the numeric scene key (e.g. "5") when present, else heading text.
"""
from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from datetime import datetime
from xml.dom import minidom


_FDX_NS = "http://www.screenwriting.io/2009/"


def _ns_of(root: ET.Element) -> str:
    tag = root.tag
    if isinstance(tag, str) and tag.startswith("{"):
        return tag[1:].split("}", 1)[0]
    return ""


def _q(ns: str, tag: str) -> str:
    return f"{{{ns}}}{tag}" if ns else tag


def _norm_scene_key(scene) -> str:
    """Normalize a checklist 'scene' value to a comparable token.

    '5'/'scene_num':5 -> '5'; 'Scene 5' -> '5'; 'INT. DINING ROOM' -> upper (text match only).
    """
    if scene is None:
        return ""
    s = str(scene).strip()
    m = re.search(r"(\d+)", s)
    if m and re.fullmatch(r"scenes?\s*\d+|scene\s*\d+|\d+", s, re.I):
        return m.group(1)
    return s.upper()


def _scene_number_from_heading(heading_text: str) -> str | None:
    m = re.match(r"\s*(\d+)\.?\s", heading_text or "")
    return m.group(1) if m else None


def _iter_scene_headings(root: ET.Element):
    """Yield (parent, paragraph, heading_text) for every Scene Heading."""
    ns = _ns_of(root)
    for parent in root.iter(_q(ns, "Content")):
        for p in parent.findall(_q(ns, "Paragraph")):
            ptype = p.find(_q(ns, "Type"))
            if ptype is not None and (ptype.text or "").strip().lower() == "scene heading":
                texts = [t.text or "" for t in p.iter(_q(ns, "Text")) if t.text]
                heading = " ".join(texts).strip()
                yield parent, p, heading


def _normalize_checklist(checklist) -> list[dict]:
    """Return [{'scene': str, 'items': [str], 'conflicts': [str], 'category': str}]."""
    out: list[dict] = []
    if not isinstance(checklist, list):
        return out
    for e in checklist:
        if not isinstance(e, dict):
            continue
        # Rich shape (B)
        if "scene_num" in e or "conflict_flagged" in e:
            scene = e.get("scene_num") or e.get("scene") or "General"
            conflicts = []
            if e.get("conflict_flagged"):
                conflicts.append(e.get("summary_note") or e.get("action_item") or "conflict flagged")
            items = []
            if e.get("summary_note") or e.get("action_item"):
                items.append(f"[{e.get('category','General')}] {e.get('summary_note','')}".strip())
            out.append({"scene": str(scene), "items": items, "conflicts": conflicts,
                        "category": str(e.get("category", "General"))})
        # build_checklist shape (A)
        elif "scene" in e or "items" in e or "conflicts" in e:
            out.append({
                "scene": str(e.get("scene", "General")),
                "items": [str(x) for x in (e.get("items") or [])],
                "conflicts": [str(x) for x in (e.get("conflicts") or [])],
                "category": "General",
            })
        # raw note dict from write_clickhouse
        elif e.get("raw_text"):
            out.append({
                "scene": str(e.get("scene_ref") or e.get("scene_id") or "General"),
                "items": [f"[{e.get('severity','med')}] {e.get('note_type','note')}: {e.get('raw_text','')}"],
                "conflicts": [],
                "category": str(e.get("note_type", "General")),
            })
    return out


def _build_script_note(ns: str, title: str, body: str) -> ET.Element:
    """Build a native, non-printing Final Draft <ScriptNote> element."""
    sn = ET.Element(_q(ns, "ScriptNote"))
    now = datetime.now()
    sn.set("Date", now.strftime("%m/%d/%Y"))
    sn.set("Time", now.strftime("%I:%M %p"))
    sn.set("Author", "Matrix AI Agent")
    p_title = ET.SubElement(sn, _q(ns, "Paragraph"))
    t_title = ET.SubElement(p_title, _q(ns, "Text"))
    t_title.text = title
    p_body = ET.SubElement(sn, _q(ns, "Paragraph"))
    t_body = ET.SubElement(p_body, _q(ns, "Text"))
    t_body.text = body
    return sn


def inject_matrix_notes_to_fdx(fdx_content: str, checklist) -> str:
    """Inject native <ScriptNote> elements into an existing .fdx, at matching scene headings.

    Unlike Action paragraphs, ScriptNote is non-printing: it does not change page count
    or script formatting. Returns the re-serialized .fdx XML string.
    """
    if not fdx_content or not fdx_content.strip():
        raise ValueError("fdx_content is empty; cannot inject into a non-existent script.")

    root = ET.fromstring(fdx_content)
    ns = _ns_of(root)
    entries = _normalize_checklist(checklist)

    numbered: dict[str, ET.Element] = {}
    by_text: list[tuple[str, ET.Element]] = []
    parent_of: dict[int, ET.Element] = {}
    for parent, p, heading in _iter_scene_headings(root):
        num = _scene_number_from_heading(heading)
        if num and num not in numbered:
            numbered[num] = p
        by_text.append((heading.upper(), p))
        parent_of[id(p)] = parent

    used_headings: set[int] = set()
    for e in entries:
        key = _norm_scene_key(e["scene"])
        target = numbered.get(key) if key.isdigit() else None
        if target is None:
            for htext, p in by_text:
                if key and key in htext and id(p) not in used_headings:
                    target = p
                    break
        if target is None:
            for htext, p in by_text:
                if id(p) not in used_headings:
                    target = p
                    break
        if target is None:
            continue

        prefix = "⚠ [FLAGGED CONFLICTS] " if e["conflicts"] else "[REVISION NOTE] "
        title = f"{prefix}Category: {e.get('category', 'General')}"
        body_lines = []
        if e["items"]:
            body_lines.append("Notes: " + " | ".join(e["items"]))
        if e["conflicts"]:
            body_lines.append("Conflicts: " + " | ".join(e["conflicts"]))
        body = "\n".join(body_lines) or "(no detail)"

        note = _build_script_note(ns, title, body)
        target.append(note)  # attach inside the Scene Heading paragraph (non-printing)
        used_headings.add(id(target))

    return _serialize(root, ns)


def generate_standalone_fdx_notes_summary(checklist) -> str:
    """Build a standalone .fdx whose notes live in native <ScriptNote> elements attached
    to placeholder Scene Heading paragraphs (one per checklist entry)."""
    entries = _normalize_checklist(checklist)
    ns = _FDX_NS
    root = ET.Element(_q(ns, "FinalDraft"), {"DocumentType": "Script", "Template": "No", "SchemaVersion": "1"})
    content = ET.SubElement(root, _q(ns, "Content"))

    if not entries:
        p = ET.SubElement(content, _q(ns, "Paragraph"))
        ET.SubElement(p, _q(ns, "Type")).text = "Action"
        ET.SubElement(p, _q(ns, "Text")).text = "DRAFT-2 REVISION MATRIX — (no notes in checklist)"
        return _serialize(root, ns)

    for e in entries:
        sh = ET.Element(_q(ns, "Paragraph"))
        ET.SubElement(sh, _q(ns, "Type")).text = "Scene Heading"
        ET.SubElement(sh, _q(ns, "Text")).text = f"SCENE {e['scene'].upper()}"
        content.append(sh)
        prefix = "⚠ [FLAGGED CONFLICTS] " if e["conflicts"] else "[REVISION NOTE] "
        title = f"{prefix}Category: {e.get('category', 'General')}"
        body_lines = []
        if e["items"]:
            body_lines.append("Notes: " + " | ".join(e["items"]))
        if e["conflicts"]:
            body_lines.append("Conflicts: " + " | ".join(e["conflicts"]))
        body = "\n".join(body_lines) or "(no detail)"
        sh.append(_build_script_note(ns, title, body))
    return _serialize(root, ns)


def _serialize(root: ET.Element, ns: str) -> str:
    raw = ET.tostring(root, encoding="unicode")
    try:
        pretty = minidom.parseString(raw).toprettyxml(indent="  ")
        pretty = "\n".join(line for line in pretty.splitlines() if line.strip())
        if ns:
            pretty = pretty.replace('<?xml version="1.0" ?>', '<?xml version="1.0" encoding="UTF-8"?>')
        return pretty
    except Exception:
        return '<?xml version="1.0" encoding="UTF-8"?>\n' + raw


def parse_agent_text_to_checklist(agent_text: str) -> list[dict]:
    """Lightweight regex extraction of 'Scene N: ...' blocks from the agent's free-text
    output into structured checklist dicts (rich shape B) for the export endpoint.

    Falls back to a single General entry if no scene markers are found.
    """
    if not agent_text:
        return []
    pattern = r"Scene\s+(\d+)[:\s\-]+(.*?)(?=(Scene\s+\d+|$))"
    matches = re.findall(pattern, agent_text, re.DOTALL | re.IGNORECASE)
    out = []
    for scene_num, content, _ in matches:
        c = content.strip()
        conflict = "conflict" in c.lower() or "contradict" in c.lower()
        out.append({
            "scene_num": int(scene_num),
            "category": "Narrative Revision",
            "conflict_flagged": conflict,
            "summary_note": c[:150],
            "action_item": c,
        })
    if not out:
        return [{"scene_num": 1, "category": "General", "conflict_flagged": False,
                 "summary_note": agent_text, "action_item": agent_text}]
    return out


# Backwards-friendly alias matching the endpoint the user sketched.
def export_fdx(checklist, fdx_content: str | None = None) -> str:
    if fdx_content:
        return inject_matrix_notes_to_fdx(fdx_content, checklist)
    return generate_standalone_fdx_notes_summary(checklist)
