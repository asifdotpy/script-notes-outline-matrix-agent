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
    scene_heading?, source_type?, source_author?}.
    This is the ACTIVE runtime ClickHouse step (ClickHouse partner track)."""
    ch.init_schema()
    project_id = ch.slugify_project(script_title)
    draft_version = 1
    for n in notes or []:
        raw = _s(n.get("raw_text"))
        if not raw.strip():
            continue  # skip empties the model may emit
        scene_num = 0
        for key in ("scene_number", "scene_ref", "scene_id"):
            v = _s(n.get(key))
            if v.isdigit():
                scene_num = int(v)
                break
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
    detected = detect_conflicts(notes)
    for c in detected:
        na = notes[c["note_a_idx"]]
        nb = notes[c["note_b_idx"]]
        # scene number from either note (prefer one that has it)
        scene_num = 0
        for v in (_s(na.get("scene_ref")), _s(na.get("scene_id")),
                  _s(nb.get("scene_ref")), _s(nb.get("scene_id"))):
            if v.isdigit():
                scene_num = int(v)
                break
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


def query_analytics(project_id: str, draft_version: int = 1) -> dict:
    """Return live ClickHouse relational analytics for a project: scene revision density,
    stakeholder disagreement, and draft progress. Demonstrates ClickHouse as an
    analytical engine (ClickHouse partner track)."""
    return ch.analytics_for(project_id, draft_version)


def detect_conflicts(notes: list[dict]) -> list[dict]:
    """Heuristic pre-flag of likely conflicting notes by character/scene. The agent
    uses this as a signal, then writes real conflicts via write_clickhouse's caller.
    Returns list of {note_a_idx, note_b_idx, reason} of candidate contradictions."""
    clashes: list[dict] = []
    # Group by (character or scene_ref) and compare severity/type opposites.
    by_key: dict[str, list[int]] = {}
    for i, n in enumerate(notes):
        key = (n.get("character") or n.get("scene_ref") or "").strip().lower()
        if key:
            by_key.setdefault(key, []).append(i)
    for key, idxs in by_key.items():
        for a in range(len(idxs)):
            for b in range(a + 1, len(idxs)):
                na, nb = notes[idxs[a]], notes[idxs[b]]
                if na.get("note_type") == nb.get("note_type") and na.get("raw_text") != nb.get("raw_text"):
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
