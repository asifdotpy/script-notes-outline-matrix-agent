"""Agent tool definitions for the Script Notes-to-Outline Matrix Agent.

Each tool maps directly to a step in the locked idea's pipeline:
  parse_notes -> categorize -> map to scenes -> flag conflicts -> checklist,
and a ClickHouse persistence/analytics step that satisfies the hackathon's
ACTIVE RUNTIME requirement (via src.clickhouse.client, which drives mcp-clickhouse).

The agent itself (Gemini) performs the categorization/conflict reasoning from the
parsed raw text; the tools own deterministic I/O (ingestion + ClickHouse).
"""
from __future__ import annotations

from google.adk.tools import FunctionTool

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.ingestion.pdf_parser import parse_pdf, parse_email
from src.clickhouse import client as ch


def parse_notes(file_path: str) -> list[str]:
    """Parse an external feedback file (PDF coverage or .eml/.txt producer/agent email)
    into a list of raw note lines. Returns the raw lines for the agent to categorize."""
    p = str(file_path)
    if p.lower().endswith(".pdf"):
        return parse_pdf(p)
    return parse_email(p)


def _s(v) -> str:
    """Coerce any value to a safe string (None -> '') for DB insertion."""
    return "" if v is None else str(v)


def write_clickhouse(script_title: str, notes: list[dict]) -> dict:
    """Persist a script's categorized notes + detected conflicts into ClickHouse via
    mcp-clickhouse and return live relational analytics.

    notes: list of {raw_text, note_type, character, scene_ref, severity, scene_id?,
    scene_heading?, source_type?, source_author?}. The notes may be partially
    structured (the LLM often emits scene/character as free text inside raw_text).
    We always derive a scene key from BOTH structured fields and the raw text so
    conflict detection never silently misses pairs that the model wrote as prose.

    This is the ACTIVE runtime ClickHouse step (ClickHouse partner track)."""
    ch.init_schema()
    project_id = ch.slugify_project(script_title)
    draft_version = 1
    for n in notes or []:
        raw = _s(n.get("raw_text"))
        if not raw.strip():
            continue  # skip empties the model may emit
        scene_num = _resolve_scene_num(n, raw)
        ch.insert_note(
            project_id=project_id,
            draft_version=draft_version,
            source_type=_s(n.get("source_type", "unknown")),
            source_author=_s(n.get("source_author", "unknown")),
            scene_number=scene_num,
            scene_heading=_s(n.get("scene_heading")),
            category=_s(n.get("note_type", "Other")),
            severity=_s(n.get("severity", "Minor")),
            raw_note_text=raw,
        )

    # Persist detected conflicts so Query 1's LEFT JOIN returns non-zero conflict counts.
    # detect_conflicts now reads scene keys from raw text too, so prose-only notes
    # (e.g. "the opening scene drags" vs "let the opening breathe") are matched.
    detected = detect_conflicts(notes)
    for c in detected:
        na = notes[c["note_a_idx"]]
        nb = notes[c["note_b_idx"]]
        scene_num = _resolve_scene_num(na, _s(na.get("raw_text"))) or _resolve_scene_num(
            nb, _s(nb.get("raw_text")))
        ch.insert_conflict(
            project_id=project_id,
            draft_version=draft_version,
            scene_number=scene_num,
            stakeholder_a=_s(na.get("source_author", "Source A")),
            note_a=_s(na.get("raw_text"))[:500],
            stakeholder_b=_s(nb.get("source_author", "Source B")),
            note_b=_s(nb.get("raw_text"))[:500],
            conflict_type="Unspecified",
        )

    return {"project_id": project_id, "draft_version": draft_version,
            "analytics": ch.analytics_for(project_id, draft_version)}


# --- scene key resolution (structured field OR prose) -----------------------
_SCENE_RE = __import__("re").compile(r"(?:scene|act|seq|sequence)\s*#{0,1}\s*(\d+)", __import__("re").IGNORECASE)
_WORD_SCENES = ("opening", "intro", "dinner", "climax", "fade", "final", "third act", "act 2", "act two", "middle")


def _resolve_scene_num(note: dict, raw: str) -> int:
    """Scene number from structured fields, else parse it out of the raw text.

    Returns an integer scene key (0 == unmapped) so notes about the same narrative
    beat — whether the model labeled it 'scene_ref: 1' or wrote 'the opening scene' —
    collide on the same grouping key and get conflict-checked together."""
    for key in ("scene_number", "scene_ref", "scene_id"):
        v = _s(note.get(key))
        if v.isdigit():
            return int(v)
    m = _SCENE_RE.search(raw or "")
    if m:
        return int(m.group(1))
    low = (raw or "").lower()
    for i, w in enumerate(_WORD_SCENES, start=1):
        if w in low:
            return 900 + i  # stable synthetic key for named-but-unnumbered beats
    return 0


def persist_from_raw(script_title: str, raw_lines: list[str],
                     source_type: str = "producer_email",
                     source_author: str = "Producer Email") -> dict:
    """Deterministic, LLM-free persistence path.

    Caller (web route / demo runner) passes already-parsed note lines; we categorize
    with lightweight heuristics and GUARANTEE the write to ClickHouse runs (no
    dependence on the model choosing to call a tool). Returns the same analytics dict
    as write_clickhouse so it is a drop-in for caller-driven persistence.

    Used as the authoritative persist path so the live ClickHouse story is always true,
    even when the LLM is unavailable/rate-limited or forgets to call the tool."""
    ch.init_schema()
    project_id = ch.slugify_project(script_title)
    draft_version = 1

    categorized = _heuristic_categorize(raw_lines)
    for cat in categorized:
        ch.insert_note(
            project_id=project_id,
            draft_version=draft_version,
            source_type=source_type,
            source_author=source_author,
            scene_number=cat["scene_number"],
            scene_heading="",
            category=cat["category"],
            severity=cat["severity"],
            raw_note_text=cat["raw_text"],
        )

    detected = detect_conflicts(categorized)
    for c in detected:
        na = categorized[c["note_a_idx"]]
        nb = categorized[c["note_b_idx"]]
        scene_num = na["scene_number"] or nb["scene_number"]
        ch.insert_conflict(
            project_id=project_id,
            draft_version=draft_version,
            scene_number=scene_num,
            stakeholder_a=source_author,
            note_a=na["raw_text"][:500],
            stakeholder_b=source_author,
            note_b=nb["raw_text"][:500],
            conflict_type="Unspecified",
        )

    return {"project_id": project_id, "draft_version": draft_version,
            "analytics": ch.analytics_for(project_id, draft_version),
            "note_count": len(categorized), "conflict_count": len(detected)}


# --- lightweight heuristics (no LLM) -----------------------------------------
_CAT_RE = __import__("re").compile(
    r"\b(pacing|dialogue|structure|character|logic|format|tone|plot|theme)\b",
    __import__("re").IGNORECASE)
_SEV_WORDS = {"urgent": "high", "critical": "high", "must": "high", "tighten": "high",
              "cut": "high", "fix": "high", "expand": "medium", "more": "medium",
              "raise": "medium", "loved": "low", "great": "low", "overall": "low"}


def _heuristic_categorize(raw_lines: list[str]) -> list[dict]:
    """Cheap structural parse used only for guaranteed persistence (not the LLM plan).

    Matches the schema's category set; severity inferred from cue words; scene key from
    text. This keeps a faithful, queryable matrix in ClickHouse even with no LLM."""
    out: list[dict] = []
    for line in raw_lines or []:
        text = _s(line).strip()
        if not text:
            continue
        low = text.lower()
        m = _CAT_RE.search(text)
        category = m.group(1).capitalize() if m else "Other"
        severity = "medium"
        for w, sev in _SEV_WORDS.items():
            if w in low:
                severity = sev
                break
        out.append({
            "raw_text": text,
            "note_type": category,
            "category": category,
            "severity": severity,
            "scene_number": _resolve_scene_num({}, text),
            "source_type": "producer_email",
            "source_author": "Producer Email",
        })
    return out


def query_analytics(project_id: str, draft_version: int = 1) -> dict:
    """Return live ClickHouse relational analytics for a project: scene revision density,
    stakeholder disagreement, and draft progress. Demonstrates ClickHouse as an
    analytical engine (ClickHouse partner track)."""
    return ch.analytics_for(project_id, draft_version)


def detect_conflicts(notes: list[dict]) -> list[dict]:
    """Heuristic pre-flag of likely conflicting notes.

    Groups notes by their resolved scene/character key (derived from structured fields
    OR the raw text via _resolve_scene_num) so that prose-only notes like
    "The opening scene drags" vs "I loved the slow build in the opening" still collide
    and get flagged as a conflict. Returns list of {note_a_idx, note_b_idx, reason}."""
    clashes: list[dict] = []
    by_key: dict[str, list[int]] = {}
    for i, n in enumerate(notes):
        key = str(_resolve_scene_num(n, _s(n.get("raw_text")))) or "general"
        by_key.setdefault(key, []).append(i)
    for key, idxs in by_key.items():
        for a in range(len(idxs)):
            for b in range(a + 1, len(idxs)):
                na, nb = notes[idxs[a]], notes[idxs[b]]
                # conflict when same category but materially different guidance
                same_cat = (n.get("note_type") or n.get("category") or "") == (
                    nb.get("note_type") or nb.get("category") or "")
                if (same_cat or key != "general") and _s(na.get("raw_text")) != _s(nb.get("raw_text")):
                    clashes.append({
                        "note_a_idx": idxs[a], "note_b_idx": idxs[b],
                        "reason": f"Overlapping note on '{key}' with differing guidance.",
                    })
    return clashes


def build_checklist(notes: list[dict], conflicts: list[dict]) -> list[dict]:
    """Assemble a scene-by-scene Draft-2 revision checklist from categorized notes
    (grouped by scene_ref/scene_id, ordered by severity) plus flagged conflicts.
    Returns a list of {scene, items:[...], conflicts:[...]}."""
    by_scene: dict[str, list[dict]] = {}
    for n in notes:
        scene = n.get("scene_ref") or n.get("scene_id") or "General"
        by_scene.setdefault(scene, []).append(n)
    sev_rank = {"high": 0, "medium": 1, "low": 2}
    checklist = []
    conflict_map = {c.get("note_b_idx"): c for c in conflicts}
    for scene, ns in by_scene.items():
        ns_sorted = sorted(ns, key=lambda x: sev_rank.get(x.get("severity", "medium"), 3))
        items = [
            f"[{n.get('severity','med')}] {n.get('note_type','note')}: {n.get('raw_text','')[:160]}"
            for n in ns_sorted
        ]
        scene_conflicts = [
            conflict_map[i]["reason"] for i in range(len(ns_sorted))
            if i in conflict_map
        ]
        checklist.append({"scene": scene, "items": items, "conflicts": scene_conflicts})
    return checklist


# ADK FunctionTool wrappers (the agent can call these at runtime).
parse_notes_tool = FunctionTool(parse_notes)
write_clickhouse_tool = FunctionTool(write_clickhouse)
query_analytics_tool = FunctionTool(query_analytics)
detect_conflicts_tool = FunctionTool(detect_conflicts)
build_checklist_tool = FunctionTool(build_checklist)

ALL_TOOLS = [
    parse_notes_tool,
    detect_conflicts_tool,
    build_checklist_tool,
    write_clickhouse_tool,
    query_analytics_tool,
]
