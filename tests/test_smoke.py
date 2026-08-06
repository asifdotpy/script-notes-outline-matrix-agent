"""Smoke test: schema + persistence + analytics on embedded chDB (free, no cloud).

Verifies the ClickHouse-active-runtime path works end to end without any cloud
account, and that flipping to Cloud requires only env vars (handled in client.py).
"""
import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# Force embedded chDB so the test needs no ClickHouse Cloud account/credits.
# CLICKHOUSE_ENABLED=false makes mcp-clickhouse register the chDB tools
# (run_chdb_select_query) instead of the real-client run_query. CHDB_DATA_PATH must be a
# file path (not ':memory:') so DDL persists across calls.
os.environ.setdefault("CHDB_ENABLED", "true")
os.environ.setdefault("CLICKHOUSE_ENABLED", "false")
os.environ.setdefault("CHDB_DATA_PATH", "/tmp/agentic_cinema_chdb_test")
os.environ["CLICKHOUSE_ALLOW_WRITE_ACCESS"] = "true"


def test_schema_and_analytics():
    from src.clickhouse import client as ch

    ch.init_schema()

    sid = ch.insert_script("The Tunnel — Draft 1", "mixed_feedback")
    n1 = ch.insert_note(sid, "Cut two pages from the intro", "pacing", "", "1", "high")
    n2 = ch.insert_note(sid, "Expand the dinner scene", "character", "Maya/Daniel", "5", "high")
    n3 = ch.insert_note(sid, "Fix missing scene numbers", "format", "", "", "low")
    ch.insert_conflict(sid, n1, n2, "Conflicting guidance on scene length/pace.")
    # Map a note to its scene (the agent's write_clickhouse step populates note_scene_map).
    ch.run_query(
        f"INSERT INTO note_scene_map (id, note_id, script_id, scene_id, scene_heading) "
        f"VALUES ('{ch.new_id()}', '{n2}', '{sid}', '5', 'INT. DINING ROOM - NIGHT')"
    )

    analytics = ch.analytics_for(sid)
    assert analytics["conflict_count"] >= 1
    assert analytics["scene_count"] >= 1
    types = {row["note_type"] for row in analytics["by_type"]}
    assert "pacing" in types and "format" in types


def test_parse_email():
    from src.ingestion.pdf_parser import parse_email

    lines = parse_email(ROOT / "tests" / "sample_feedback.eml")
    assert any("dinner scene" in ln.lower() for ln in lines)
    assert len(lines) > 3
