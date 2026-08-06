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

from ingestion.pdf_parser import parse_pdf, parse_email
from clickhouse import client as ch


def parse_notes(file_path: str) -> list[str]:
    """Parse an external feedback file (PDF coverage or .eml/.txt producer/agent email)
    into a list of raw note lines. Returns the raw lines for the agent to categorize."""
    p = str(file_path)
    if p.lower().endswith(".pdf"):
        return parse_pdf(p)
    return parse_email(p)


def write_clickhouse(script_title: str, notes: list[dict]) -> dict:
    """Persist a script's categorized notes into ClickHouse via mcp-clickhouse and
    return live analytics. notes: list of {raw_text, note_type, character, scene_ref,
    severity, scene_id?, scene_heading?}. This is the ACTIVE runtime ClickHouse step."""
    ch.init_schema()
    sid = ch.insert_script(script_title, "mixed_feedback")
    for n in notes:
        nid = ch.insert_note(
            sid, n.get("raw_text", ""), n.get("note_type", "other"),
            n.get("character", ""), n.get("scene_ref", ""), n.get("severity", "medium"),
        )
        if n.get("scene_id"):
            ch.run_query(
                "INSERT INTO note_scene_map (id, note_id, script_id, scene_id, scene_heading) "
                f"VALUES ('{ch.new_id()}', '{nid}', '{sid}', "
                f"'{str(n['scene_id']).replace(chr(39), chr(39)*2)}', "
                f"'{str(n.get('scene_heading','')).replace(chr(39), chr(39)*2)}')"
            )
    return {"script_id": sid, "analytics": ch.analytics_for(sid)}


def query_analytics(script_id: str) -> dict:
    """Return live ClickHouse analytics for a script: note-category frequencies,
    conflict count, scene coverage. Demonstrates ClickHouse as an analytical engine."""
    return ch.analytics_for(script_id)


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
