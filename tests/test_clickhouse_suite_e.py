"""Suite E — ClickHouse tests (board task t_0c841903).

Uses embedded chDB (file-backed, free) — no ClickHouse Cloud account/credits.
Asserts:
  E1. Persisted notes survive a FRESH query connection (re-query from a new
      mcp-clickhouse session returns identical rows) => true cross-session
      persistence, not an in-memory illusion.
  E2. analytics_for(project_id) aggregates (total_notes, by-category counts,
      conflict_count) equal a MANUAL count over the same golden dataset.
  E3. The notes_matrix view joins notes to conflicts correctly (flagged rows
      line up with the planted scene-5 conflict).
  E4. A separate write to a second project does NOT leak into the first
      (project isolation).

Implemented by inserting the golden dataset via the real client.insert_note /
insert_conflict and re-reading through a brand-new ch.init_schema + run_query
call (which spins up a fresh stdio MCP session), proving durability on the
file-backed chDB path.
"""
from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

CHDB_PATH = "/tmp/agentic_cinema_chdb_test_e"

os.environ.setdefault("CHDB_ENABLED", "true")
os.environ.setdefault("CLICKHOUSE_ENABLED", "false")
os.environ["CHDB_DATA_PATH"] = CHDB_PATH
os.environ["CLICKHOUSE_ALLOW_WRITE_ACCESS"] = "true"


@pytest.fixture
def golden_rows():
    from tests.fixtures.golden.golden_labels import GOLDEN_CATEGORIES, GOLDEN_CONFLICTS
    return GOLDEN_CATEGORIES, GOLDEN_CONFLICTS


@pytest.fixture(scope="session")
def populated():
    """Persist the golden dataset into chDB ONCE, then yield the project id.

    A session-scoped fixture is intentional: each chDB run_query spins up a fresh
    `uv run mcp-clickhouse` subprocess (~3s cold start), so re-inserting 24 notes
    per test would make the suite minutes long. The cross-session durability check
    (E1) is still valid because every run_query opens a NEW stdio MCP session over
    the SAME file-backed chDB path — data survives because it's persisted to disk,
    not held in the session.
    """
    from src.clickhouse import client as ch
    from tests.fixtures.golden.golden_labels import GOLDEN_CATEGORIES, GOLDEN_CONFLICTS

    shutil.rmtree(CHDB_PATH, ignore_errors=True)
    ch.init_schema()

    project_id = ch.slugify_project("The Last Lighthouse — Draft 1")
    for r in GOLDEN_CATEGORIES:
        _nid, _f, source_type, author, raw, category, severity, scene = r
        ch.insert_note(
            project_id, 1, source_type, author,
            int(scene), "", category.capitalize(), severity.capitalize(), raw,
        )
    # Planted scene-5 conflict (director cut vs everyone expand).
    ch.insert_conflict(
        project_id, 1, 5,
        "Nadia (director_email)", "Cut the dinner scene. Scene 5 stops the film dead.",
        "Margaret (producer_email)", "Expand the dinner scene. Scene 5 is the emotional core.",
        "Structural",
    )
    # A second, isolated project to prove no leakage.
    ch.insert_note("other-project", 1, "producer_email", "X", 2, "", "Other", "Low",
                   "completely unrelated note")

    yield project_id


# --- E1: persistence across a fresh session ---------------------------------
def test_e1_rows_survive_fresh_session(populated, golden_rows):
    from src.clickhouse import client as ch

    gold_cats, _ = golden_rows
    rows = ch.run_query(
        f"SELECT count(*) AS c FROM script_notes_matrix.notes_raw "
        f"WHERE project_id = '{populated}' AND draft_version = 1"
    )
    assert rows[0]["c"] == len(gold_cats), \
        f"expected {len(gold_cats)} persisted notes after a fresh session, got {rows[0]['c']}"


def test_e1_long_text_preserved(populated):
    from src.clickhouse import client as ch

    # Re-open via a NEW run_query (fresh stdio session) and confirm a verbatim note.
    rows = ch.run_query(
        f"SELECT raw_note_text FROM script_notes_matrix.notes_raw "
        f"WHERE project_id = '{populated}' AND scene_number = 5 "
        f"AND raw_note_text LIKE '%Expand the dinner scene%' LIMIT 1"
    )
    assert rows, "scene-5 'expand' note missing in fresh session"
    assert "Expand the dinner scene" in rows[0]["raw_note_text"]


# --- E2: analytics aggregate == manual count --------------------------------
def test_e2_analytics_matches_manual_count(populated, golden_rows):
    from src.analytics import queries

    gold_cats, _ = golden_rows
    # Manual counts over the golden dataset.
    manual_total = len(gold_cats)
    manual_by_cat: dict[str, int] = {}
    for r in gold_cats:
        manual_by_cat[r[5].capitalize()] = manual_by_cat.get(r[5].capitalize(), 0) + 1

    density = queries.scene_density_and_conflicts(populated, 1)
    disc = queries.stakeholder_disagreement(populated, 1)
    prog = queries.draft_progress(populated)

    db_total = prog[0]["total_notes"]
    assert db_total == manual_total, f"analytics total {db_total} != manual {manual_total}"

    # Query 2 groups by (source_type, category), so a category spans several rows.
    # Sum note_count across source_types to get the per-category total.
    db_by_cat: dict[str, int] = {}
    for r in disc:
        db_by_cat[r["category"]] = db_by_cat.get(r["category"], 0) + r["note_count"]
    for cat, n in manual_by_cat.items():
        assert db_by_cat.get(cat) == n, f"category {cat}: db {db_by_cat.get(cat)} != manual {n}"


def test_e2_scene_density_conflict_count(populated):
    from src.analytics import queries

    density = queries.scene_density_and_conflicts(populated, 1)
    by_scene = {r["scene_number"]: r for r in density}
    # Scene 5 carries the planted conflict.
    assert by_scene[5]["conflict_count"] == 1, by_scene[5]
    # Scene 5 also has 4 notes (producer, manager, coverage, director).
    assert by_scene[5]["total_notes"] == 4, by_scene[5]


# --- E3: notes_matrix view joins notes<->conflicts --------------------------
def test_e3_matrix_view_flags_conflict_rows(populated):
    from src.clickhouse import client as ch

    rows = ch.run_query(
        f"SELECT scene_number, has_conflict FROM script_notes_matrix.notes_matrix "
        f"WHERE project_id = '{populated}' AND draft_version = 1 "
        f"ORDER BY scene_number"
    )
    flagged = [r["scene_number"] for r in rows if r["has_conflict"]]
    assert 5 in flagged, f"scene 5 must be flagged in the matrix view; flagged={flagged}"
    # No other scene should be flagged (only one conflict planted).
    assert set(flagged) == {5}


# --- E4: project isolation --------------------------------------------------
def test_e4_other_project_does_not_leak(populated):
    from src.clickhouse import client as ch

    other = ch.run_query(
        "SELECT raw_note_text FROM script_notes_matrix.notes_raw "
        "WHERE project_id = 'other-project'"
    )
    assert len(other) == 1
    assert "completely unrelated note" in other[0]["raw_note_text"]

    mine = ch.run_query(
        f"SELECT count(*) AS c FROM script_notes_matrix.notes_raw "
        f"WHERE project_id = '{populated}'"
    )
    assert mine[0]["c"] == 23  # 23 golden notes, none from other-project
