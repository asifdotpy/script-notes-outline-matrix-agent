"""FDX (Final Draft XML) exporters for the Script Notes-to-Outline Matrix Agent.

Two honest, format-interchange functions (NOT a live in-editor plugin — Final Draft has
no public plugin API). We write standard .fdx XML so a writer can open the result in
Final Draft and see the Draft-2 revision notes embedded at the right scenes.

- inject_matrix_notes_to_fdx: merge a revision checklist into an EXISTING .fdx script.
- generate_standalone_fdx_notes_summary: build a standalone .fdx holding only the notes
  (used when no source script is supplied).

Checklist contract (matches src.agent.tools.note_tools.build_checklist output):
    [{"scene": "5" | "INT. DINING ROOM - NIGHT" | "General",
      "items": ["[high] structure: <raw note text>", ...],
      "conflicts": ["<reason>", ...]}, ...]
A `notes` list of raw-note dicts is also accepted and converted.
"""
from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from xml.dom import minidom

# Final Draft's standard namespace. Real .fdx files declare it on <FinalDraft>;
# some exports omit it. We detect the namespace from the parsed root so both work.
_FDX_NS = "http://www.screenwriting.io/2009/"


def _ns_of(root: ET.Element) -> str:
    """Return the XML namespace in use ('' if none), derived from the root tag."""
    tag = root.tag
    if isinstance(tag, str) and tag.startswith("{"):
        return tag[1:].split("}", 1)[0]
    return ""


def _q(ns: str, tag: str) -> str:
    return f"{{{ns}}}{tag}" if ns else tag


def _norm_scene_key(scene: str) -> str:
    """Normalize a checklist 'scene' value to a comparable token.

    '5' -> '5'; 'Scene 5' -> '5'; 'INT. DINING ROOM - NIGHT' -> full upper string
    (used only for heading-text matching, not number matching)."""
    if scene is None:
        return ""
    s = str(scene).strip()
    m = re.search(r"(\d+)", s)
    if m and re.fullmatch(r"scenes?\s*\d+|scene\s*\d+|\d+", s, re.I):
        return m.group(1)
    return s.upper()


def _scene_number_from_heading(heading_text: str) -> str | None:
    """Extract a scene number if the heading carries one, e.g. '5. INT. ...' or '5 INT.'."""
    m = re.match(r"\s*(\d+)\.?\s", heading_text or "")
    return m.group(1) if m else None


def _iter_scene_headings(root: ET.Element):
    """Yield (parent_element, paragraph_element, heading_text) for every Scene Heading."""
    ns = _ns_of(root)
    for parent in root.iter(_q(ns, "Content")):
        for p in parent.findall(_q(ns, "Paragraph")):
            ptype = p.find(_q(ns, "Type"))
            if ptype is not None and (ptype.text or "").strip().lower() == "scene heading":
                texts = [t.text or "" for t in p.iter(_q(ns, "Text")) if t.text]
                heading = " ".join(texts).strip()
                yield parent, p, heading


def _build_note_paragraph(ns: str, lines: list[str]) -> ET.Element:
    """Create a Final Draft Paragraph (Action type) containing the given note lines."""
    p = ET.Element(_q(ns, "Paragraph"))
    t = ET.SubElement(p, _q(ns, "Type"))
    t.text = "Action"
    for line in lines:
        text_el = ET.SubElement(p, _q(ns, "Text"))
        text_el.text = line
    return p


def _normalize_checklist(checklist) -> list[dict]:
    """Accept build_checklist shape or a raw notes list; always return
    [{'scene': str, 'items': [str], 'conflicts': [str]}]. Plain strings in items are kept."""
    out: list[dict] = []
    if not isinstance(checklist, list):
        return out
    for entry in checklist:
        if isinstance(entry, dict) and ("items" in entry or "conflicts" in entry or "scene" in entry):
            out.append({
                "scene": str(entry.get("scene", "General")),
                "items": [str(x) for x in (entry.get("items") or [])],
                "conflicts": [str(x) for x in (entry.get("conflicts") or [])],
            })
        elif isinstance(entry, dict):
            # raw note dict from write_clickhouse
            scene = entry.get("scene_ref") or entry.get("scene_id") or "General"
            raw = entry.get("raw_text") or ""
            if raw.strip():
                out.append({
                    "scene": str(scene),
                    "items": [f"[{entry.get('severity','med')}] {entry.get('note_type','note')}: {raw}"],
                    "conflicts": [],
                })
    return out


def inject_matrix_notes_to_fdx(fdx_content: str, checklist) -> str:
    """Inject Draft-2 revision notes into an existing .fdx script.

    For each checklist entry whose scene number matches a scene heading (or, failing that,
    any scene heading when the entry is 'General'/unmatched), insert an Action paragraph
    immediately after that heading carrying the categorized notes + flagged conflicts.
    Returns the re-serialized .fdx XML string.
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

        lines = []
        if e["items"]:
            lines.append("[MATRIX NOTES]")
            lines.extend(f"• {it}" for it in e["items"])
        if e["conflicts"]:
            lines.append("[FLAGGED CONFLICTS]")
            lines.extend(f"⚠ {c}" for c in e["conflicts"])
        if not lines:
            continue
        parent = parent_of[id(target)]
        idx = list(parent).index(target)
        parent.insert(idx + 1, _build_note_paragraph(ns, lines))
        used_headings.add(id(target))

    return _serialize(root, ns)


def generate_standalone_fdx_notes_summary(checklist) -> str:
    """Build a standalone .fdx document containing only the revision notes, grouped by scene."""
    entries = _normalize_checklist(checklist)
    ns = _FDX_NS
    root = ET.Element(_q(ns, "FinalDraft"), {"DocumentType": "Script", "Template": "No", "SchemaVersion": "1"})
    content = ET.SubElement(root, _q(ns, "Content"))

    title_p = _build_note_paragraph(ns, ["DRAFT-2 REVISION MATRIX — NOTES SUMMARY"])
    content.append(title_p)

    if not entries:
        content.append(_build_note_paragraph(ns, ["(no notes in checklist)"]))
        return _serialize(root, ns)

    for e in entries:
        sh = ET.Element(_q(ns, "Paragraph"))
        st = ET.SubElement(sh, _q(ns, "Type"))
        st.text = "Scene Heading"
        sh_text = ET.SubElement(sh, _q(ns, "Text"))
        sh_text.text = f"SCENE {e['scene'].upper()}"
        content.append(sh)
        lines = []
        if e["items"]:
            lines.extend(f"• {it}" for it in e["items"])
        if e["conflicts"]:
            lines.append("[FLAGGED CONFLICTS]")
            lines.extend(f"⚠ {c}" for c in e["conflicts"])
        if lines:
            content.append(_build_note_paragraph(ns, lines))
    return _serialize(root, ns)


def _serialize(root: ET.Element, ns: str) -> str:
    """Serialize with an XML declaration and pretty-printing."""
    raw = ET.tostring(root, encoding="unicode")
    try:
        pretty = minidom.parseString(raw).toprettyxml(indent="  ")
        pretty = "\n".join(line for line in pretty.splitlines() if line.strip())
        if ns:
            pretty = pretty.replace('<?xml version="1.0" ?>',
                                     '<?xml version="1.0" encoding="UTF-8"?>')
        return pretty
    except Exception:
        return '<?xml version="1.0" encoding="UTF-8"?>\n' + raw


# Backwards-friendly alias matching the endpoint the user sketched.
def export_fdx(checklist, fdx_content: str | None = None) -> str:
    if fdx_content:
        return inject_matrix_notes_to_fdx(fdx_content, checklist)
    return generate_standalone_fdx_notes_summary(checklist)

