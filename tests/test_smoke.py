"""Smoke test: schema + persistence + relational analytics on embedded chDB (free, no cloud).

Verifies the ClickHouse-active-runtime path works end to end without any cloud account,
and that the three analytical queries (scene density, stakeholder disagreement, draft
progress) return sane rows over persisted notes + conflicts.
"""
import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# Force embedded chDB so the test needs no ClickHouse Cloud account/credits.
os.environ.setdefault("CHDB_ENABLED", "true")
os.environ.setdefault("CLICKHOUSE_ENABLED", "false")
os.environ.setdefault("CHDB_DATA_PATH", "/tmp/agentic_cinema_chdb_test")
os.environ["CLICKHOUSE_ALLOW_WRITE_ACCESS"] = "true"


def test_schema_and_relational_analytics():
    from src.clickhouse import client as ch
    from src.analytics import queries

    ch.init_schema()
    project_id = ch.slugify_project("The Tunnel — Draft 1")  # -> 'the-tunnel-draft-1'
    assert project_id == "the-tunnel-draft-1"

    # Persist notes across two sources, one with a conflict on scene 5.
    ch.insert_note(project_id, 1, "producer_email", "Producer", 5, "INT. DINING ROOM - NIGHT",
                   "Character", "Critical", "Expand the dinner scene between Maya and Daniel.")
    ch.insert_note(project_id, 1, "agent_email", "Manager", 5, "INT. DINING ROOM - NIGHT",
                   "Character", "Major", "Tighten the dinner scene dialogue.")
    ch.insert_note(project_id, 1, "pdf_coverage", "Coverage", 12, "EXT. ROOFTOP - DAY",
                   "Structure", "Minor", "The rooftop scene works well.")
    ch.insert_conflict(project_id, 1, 5, "Producer", "Expand the dinner scene",
                       "Manager", "Tighten the dinner scene dialogue", "Character Arc")

    # Query 1: scene density + conflict rate (scene 5 should show 2 notes + 1 conflict).
    density = queries.scene_density_and_conflicts(project_id, 1)
    by_scene = {r["scene_number"]: r for r in density}
    assert by_scene[5]["total_notes"] == 2
    assert by_scene[5]["conflict_count"] == 1

    # Query 2: stakeholder disagreement by source/category.
    disc = queries.stakeholder_disagreement(project_id, 1)
    assert len(disc) >= 3
    assert any(r["source_type"] == "producer_email" for r in disc)

    # Query 3: draft progress rollup.
    prog = queries.draft_progress(project_id)
    assert prog[0]["draft_version"] == 1
    assert prog[0]["affected_scenes"] == 2  # scenes 5 and 12
    assert prog[0]["total_notes"] == 3
    assert prog[0]["total_reviewers"] == 3  # Producer, Manager, Coverage

    # Bundle used by the agent/web response.
    bundled = ch.analytics_for(project_id, 1)
    assert bundled["scene_density"] and bundled["stakeholder_disagreement"] and bundled["draft_progress"]


def test_parse_email():
    from src.ingestion.pdf_parser import parse_email

    lines = parse_email(ROOT / "tests" / "sample_feedback.eml")
    assert any("dinner scene" in ln.lower() for ln in lines)
    assert len(lines) > 3
