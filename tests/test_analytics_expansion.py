#!/usr/bin/env python3
"""Test the new ClickHouse analytics queries (items 1-12) against chDB with planted data.

Each test:
1. Seeds a named test project with notes + conflicts in chDB.
2. Calls the analytics query function.
3. Asserts the result has the expected shape.

IMPORTANT: env vars MUST be set before importing src.clickhouse.client or
src.analytics.queries, because mcp-clickhouse's _query_tool_name() reads env
at call time and CHDB_ENABLED=false/CLICKHOUSE_ENABLED=true with empty host
breaks the port parser. We follow suite E's pattern: CHDB_ENABLED=true and
CLICKHOUSE_ENABLED=false, with a file-backed CHDB_DATA_PATH.

Run with:  python tests/test_analytics_expansion.py
Or via pytest:  pytest tests/test_analytics_expansion.py -v
"""

import os
import shutil
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Env setup — MUST happen before ANY src.* import
# ---------------------------------------------------------------------------
ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

CHDB_PATH = "/tmp/agentic_cinema_chdb_test_analytics"
os.environ["CHDB_ENABLED"] = "true"
os.environ["CLICKHOUSE_ENABLED"] = "false"
os.environ["CHDB_DATA_PATH"] = CHDB_PATH
os.environ["CLICKHOUSE_ALLOW_WRITE_ACCESS"] = "true"
os.environ["CLICKHOUSE_MCP_AUTH_DISABLED"] = "true"
# Ensure no residual Cloud config leaks in
os.environ.pop("CLICKHOUSE_HOST", None)
os.environ.pop("CLICKHOUSE_PORT", None)
os.environ.pop("CLICKHOUSE_USER", None)
os.environ.pop("CLICKHOUSE_PASSWORD", None)
os.environ.pop("CLICKHOUSE_SECURE", None)

from src.analytics import queries as q
from src.clickhouse import client as ch  # noqa: E402


_PROJECT_A = "test-forecast-horizon"
_PROJECT_B = "test-stakeholder-friction"


def _setup_chdb() -> None:
    """One-time chDB init: wipe old data dir, init schema.

    IMPORTANT: re-set CHDB_DATA_PATH here (not just at module level) so this test
    owns its own chDB instance regardless of module-load ordering. Other test modules
    (e.g. suite E) also set CHDB_DATA_PATH at module level and may overwrite ours
    before our module-level _setup_chdb() call runs.
    """
    os.environ["CHDB_DATA_PATH"] = CHDB_PATH
    shutil.rmtree(CHDB_PATH, ignore_errors=True)
    ch.init_schema()


def _safe_cleanup(project_id: str) -> None:
    """Delete a project's rows, tolerating missing tables/database."""
    # Pin our own chDB path — another test module may have overwritten
    # CHDB_DATA_PATH at module level (e.g. suite E).
    os.environ["CHDB_DATA_PATH"] = CHDB_PATH
    pid = project_id.replace("'", "''")
    try:
        ch.run_query(f"ALTER TABLE script_notes_matrix.notes_raw DELETE WHERE project_id = '{pid}'")
    except Exception:
        pass
    try:
        ch.run_query(f"ALTER TABLE script_notes_matrix.notes_conflicts DELETE WHERE project_id = '{pid}'")
    except Exception:
        pass


# Initialize chDB once when the test module loads
_setup_chdb()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def _seed_project(project_id: str, notes: list[dict], conflicts: list[dict] | None = None) -> None:
    """Insert notes + optional conflicts into chDB for a test project."""
    # Pin our own CHDB_DATA_PATH so module-level imports from other test files
    # (e.g. suite E) can't clobber it before we run. init_schema() is idempotent
    # (CREATE TABLE IF NOT EXISTS), so re-calling it here is a no-op when the
    # tables already exist in our instance.
    os.environ["CHDB_DATA_PATH"] = CHDB_PATH
    ch.init_schema()
    pid = project_id.replace("'", "''")
    for note in notes:
        ch.run_query(f"""
            INSERT INTO script_notes_matrix.notes_raw
                (note_id, project_id, draft_version, source_type, source_author,
                 scene_number, scene_heading, category, severity, raw_note_text)
            VALUES
                (generateUUIDv4(), '{pid}', 1,
                 '{note.get('source_type', 'producer_email')}',
                 '{note.get('source_author', 'Test Author')}',
                 {int(note.get('scene_number', 0))},
                 '{note.get('scene_heading', '')}',
                 '{note.get('category', 'Other')}',
                 '{note.get('severity', 'Minor')}',
                 '{note.get('raw_note_text', '').replace(chr(39), chr(39)+chr(39))}')
        """)
    if conflicts:
        for c in conflicts:
            ch.run_query(f"""
                INSERT INTO script_notes_matrix.notes_conflicts
                    (conflict_id, project_id, draft_version, scene_number,
                     stakeholder_a, note_a, stakeholder_b, note_b,
                     conflict_type, resolution_status)
                VALUES
                    (generateUUIDv4(), '{pid}', 1, {int(c.get('scene_number', 0))},
                     '{c.get('stakeholder_a', 'Author A')}',
                     '{c.get('note_a', '').replace(chr(39), chr(39)+chr(39))}',
                     '{c.get('stakeholder_b', 'Author B')}',
                     '{c.get('note_b', '').replace(chr(39), chr(39)+chr(39))}',
                     '{c.get('conflict_type', 'Unspecified')}',
                     '{c.get('resolution_status', 'Unresolved')}')
            """)


def _safe_cleanup(project_id: str) -> None:
    """Delete a project's rows, tolerating missing tables/database."""
    # Pin our own chDB path — another test module may have overwritten
    # CHDB_DATA_PATH at module level (e.g. suite E).
    os.environ["CHDB_DATA_PATH"] = CHDB_PATH
    pid = project_id.replace("'", "''")
    try:
        ch.run_query(f"ALTER TABLE script_notes_matrix.notes_raw DELETE WHERE project_id = '{pid}'")
    except Exception:
        pass
    try:
        ch.run_query(f"ALTER TABLE script_notes_matrix.notes_conflicts DELETE WHERE project_id = '{pid}'")
    except Exception:
        pass


# Initialize chDB once when the test module loads
_setup_chdb()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_severity_heatmap_shape() -> None:
    """Item 1: severity_heatmap returns (scene_number, severity, note_count) rows."""
    _safe_cleanup(_PROJECT_A)
    _seed_project(_PROJECT_A, [
        {"scene_number": 1, "category": "Pacing", "severity": "Critical", "raw_note_text": "Drags"},
        {"scene_number": 1, "category": "Pacing", "severity": "Major", "raw_note_text": "Slow"},
        {"scene_number": 2, "category": "Character", "severity": "Critical", "raw_note_text": "Unclear mot"},
        {"scene_number": 2, "category": "Character", "severity": "Minor", "raw_note_text": "Likable"},
        {"scene_number": 3, "category": "Dialogue", "severity": "Minor", "raw_note_text": "Too on nose"},
    ])
    try:
        rows = q.severity_heatmap(_PROJECT_A, 1)
        assert isinstance(rows, list), f"expected list, got {type(rows)}"
        assert len(rows) >= 1, "expected at least 1 heatmap row"
        for r in rows:
            assert "scene_number" in r, "missing scene_number"
            assert "severity" in r, "missing severity"
            assert "note_count" in r, "missing note_count"
            assert int(r["note_count"]) >= 1, "note_count should be >= 1"
        # Scene 1 should have 2 rows (Critical + Major)
        scene1_rows = [r for r in rows if int(r["scene_number"]) == 1]
        assert len(scene1_rows) >= 2, f"scene 1 should have >=2 severity rows, got {len(scene1_rows)}"
    finally:
        _safe_cleanup(_PROJECT_A)


def test_category_severity_matrix_shape() -> None:
    """Item 2: category_severity_matrix returns (category, severity, note_count) rows."""
    _safe_cleanup(_PROJECT_A)
    _seed_project(_PROJECT_A, [
        {"scene_number": 1, "category": "Pacing", "severity": "Critical", "raw_note_text": "Drags"},
        {"scene_number": 1, "category": "Pacing", "severity": "Minor", "raw_note_text": "Edgy"},
        {"scene_number": 2, "category": "Logic", "severity": "Critical", "raw_note_text": "Plot hole"},
        {"scene_number": 2, "category": "Logic", "severity": "Major", "raw_note_text": "Wound tight"},
    ])
    try:
        rows = q.category_severity_matrix(_PROJECT_A, 1)
        assert isinstance(rows, list)
        assert len(rows) >= 2
        for r in rows:
            assert "category" in r
            assert "severity" in r
            assert "note_count" in r
        cats = {r["category"] for r in rows}
        assert "Pacing" in cats
        assert "Logic" in cats
    finally:
        _safe_cleanup(_PROJECT_A)


def test_stakeholder_influence_shape() -> None:
    """Item 3: stakeholder_influence returns per-author total_notes + critical_notes."""
    _safe_cleanup(_PROJECT_A)
    _seed_project(_PROJECT_A, [
        {"source_author": "Producer Jane", "scene_number": 1, "category": "Pacing", "severity": "Critical", "raw_note_text": "Cut intro"},
        {"source_author": "Producer Jane", "scene_number": 2, "category": "Character", "severity": "Major", "raw_note_text": "Arc unclear"},
        {"source_author": "Director Sam", "scene_number": 1, "category": "Pacing", "severity": "Minor", "raw_note_text": "Loved the slow build"},
        {"source_author": "Director Sam", "scene_number": 3, "category": "Dialogue", "severity": "Critical", "raw_note_text": "On the nose"},
        {"source_author": "Consultant Lee", "scene_number": 2, "category": "Logic", "severity": "Major", "raw_note_text": "Plot hole"},
    ])
    try:
        rows = q.stakeholder_influence(_PROJECT_A, 1)
        assert isinstance(rows, list)
        assert len(rows) >= 2
        for r in rows:
            assert "source_author" in r
            assert "total_notes" in r
            assert "critical_notes" in r
            assert "critical_ratio" in r
        # Producer Jane has 2 notes, 1 critical
        jane = [r for r in rows if r["source_author"] == "Producer Jane"]
        assert len(jane) == 1, f"expected 1 row for Producer Jane, got {len(jane)}"
        assert int(jane[0]["total_notes"]) == 2
        assert int(jane[0]["critical_notes"]) == 1
        assert 0 < float(jane[0]["critical_ratio"]) <= 1.0
    finally:
        _safe_cleanup(_PROJECT_A)


def test_conflict_type_breakdown_shape() -> None:
    """Item 4: conflict_type_breakdown returns per-type total + unresolved counts."""
    _safe_cleanup(_PROJECT_A)
    _seed_project(_PROJECT_A, [
        {"scene_number": 1, "source_author": "A", "category": "Pacing", "severity": "Critical", "raw_note_text": "Cut"},
        {"scene_number": 1, "source_author": "B", "category": "Pacing", "severity": "Major", "raw_note_text": "Expand"},
    ], conflicts=[
        {"scene_number": 1, "stakeholder_a": "Producer", "note_a": "Cut intro",
         "stakeholder_b": "Director", "note_b": "Let it breathe",
         "conflict_type": "Structural", "resolution_status": "Unresolved"},
        {"scene_number": 1, "stakeholder_a": "Producer", "note_a": "Cut intro",
         "stakeholder_b": "Consultant", "note_b": "Cut more",
         "conflict_type": "Structural", "resolution_status": "Unresolved"},
        {"scene_number": 2, "stakeholder_a": "Director", "note_a": "More tension",
         "stakeholder_b": "Consultant", "note_b": "Less is more",
         "conflict_type": "Tone", "resolution_status": "Resolved"},
    ])
    try:
        rows = q.conflict_type_breakdown(_PROJECT_A, 1)
        assert isinstance(rows, list)
        assert len(rows) >= 2  # Structural + Tone
        for r in rows:
            assert "conflict_type" in r
            assert "total_conflicts" in r
            assert "unresolved_count" in r
            assert "unresolved_ratio" in r
        structural = [r for r in rows if r["conflict_type"] == "Structural"]
        assert len(structural) == 1
        assert int(structural[0]["total_conflicts"]) == 2
        assert int(structural[0]["unresolved_count"]) == 2
    finally:
        _safe_cleanup(_PROJECT_A)


def test_conflict_aging_shape() -> None:
    """Item 5: conflict_aging returns buckets + summary with unresolved_count."""
    _safe_cleanup(_PROJECT_A)
    _seed_project(_PROJECT_A, [
        {"scene_number": 1, "source_author": "A", "category": "Pacing", "severity": "Critical", "raw_note_text": "Cut"},
        {"scene_number": 1, "source_author": "B", "category": "Pacing", "severity": "Major", "raw_note_text": "Expand"},
    ], conflicts=[
        {"scene_number": 1, "stakeholder_a": "Producer", "note_a": "Cut",
         "stakeholder_b": "Director", "note_b": "Breathe",
         "conflict_type": "Structural", "resolution_status": "Unresolved"},
    ])
    try:
        result = q.conflict_aging(_PROJECT_A, 1)
        assert isinstance(result, dict), f"expected dict, got {type(result)}"
        assert "buckets" in result
        assert "summary" in result
        buckets = result["buckets"]
        assert isinstance(buckets, list)
        summary = result["summary"]
        assert isinstance(summary, dict)
        assert "unresolved_count" in summary
        assert "avg_hours_open" in summary
        assert "max_hours_open" in summary
        assert "median_hours_open" in summary
        assert int(summary["unresolved_count"]) >= 1
        # Buckets should have the 6 time-range keys
        for r in buckets:
            for key in ["h_0_6", "h_6_24", "d_1_3", "d_3_7", "d_7_14", "d_14_plus", "total_in_bucket"]:
                assert key in r, f"missing bucket key {key}"
    finally:
        _safe_cleanup(_PROJECT_A)


def test_draft_progression_shape() -> None:
    """Item 6: draft_progression returns notes + conflicts series per draft."""
    _safe_cleanup(_PROJECT_A)
    _seed_project(_PROJECT_A, [
        {"scene_number": 1, "category": "Pacing", "severity": "Critical", "raw_note_text": "Draft 1 note"},
        {"scene_number": 2, "category": "Character", "severity": "Major", "raw_note_text": "Draft 1 note 2"},
        {"scene_number": 1, "category": "Pacing", "severity": "Minor", "raw_note_text": "Draft 2 note"},
        {"scene_number": 2, "category": "Character", "severity": "Critical", "raw_note_text": "Draft 2 note 2"},
    ], conflicts=[
        {"scene_number": 1, "stakeholder_a": "A", "note_a": "Cut",
         "stakeholder_b": "B", "note_b": "Breathe",
         "conflict_type": "Structural", "resolution_status": "Unresolved"},
    ])
    try:
        result = q.draft_progression(_PROJECT_A)
        assert isinstance(result, dict)
        assert "notes" in result
        assert "conflicts" in result
        notes = result["notes"]
        conflicts = result["conflicts"]
        assert isinstance(notes, list)
        assert isinstance(conflicts, list)
        # All notes are draft 1 (we only inserted draft_version=1)
        notes_drafts = {int(r["draft_version"]) for r in notes}
        assert notes_drafts == {1}, f"expected only draft 1, got {notes_drafts}"
        for r in notes:
            assert "draft_version" in r
            assert "total_notes" in r
        for r in conflicts:
            assert "draft_version" in r
            assert "total_conflicts" in r
            assert "unresolved_conflicts" in r
    finally:
        _safe_cleanup(_PROJECT_A)


def test_expected_scenes_to_revise() -> None:
    """Item 8: expected_scenes_to_revise counts scenes with notes / conflicts / both."""
    _safe_cleanup(_PROJECT_A)
    _seed_project(_PROJECT_A, [
        {"scene_number": 1, "category": "Pacing", "severity": "Critical", "raw_note_text": "Scene 1 note"},
        {"scene_number": 2, "category": "Character", "severity": "Major", "raw_note_text": "Scene 2 note"},
        {"scene_number": 3, "category": "Dialogue", "severity": "Minor", "raw_note_text": "Scene 3 note"},
    ], conflicts=[
        {"scene_number": 1, "stakeholder_a": "A", "note_a": "Cut",
         "stakeholder_b": "B", "note_b": "Breathe",
         "conflict_type": "Structural", "resolution_status": "Unresolved"},
    ])
    try:
        result = q.expected_scenes_to_revise(_PROJECT_A, 1)
        assert isinstance(result, dict)
        assert "scenes_with_notes" in result
        assert "scenes_with_conflicts" in result
        assert "scenes_with_both" in result
        assert "all_scenes_with_activity" in result
        assert int(result["scenes_with_notes"]) == 3  # scenes 1,2,3
        assert int(result["scenes_with_conflicts"]) == 1  # scene 1
        assert int(result["scenes_with_both"]) == 1  # scene 1
        assert int(result["all_scenes_with_activity"]) == 3
    finally:
        _safe_cleanup(_PROJECT_A)


def test_stakeholder_alignment() -> None:
    """Item 9: stakeholder_alignment returns conflict_rate + alignment_ratio."""
    _safe_cleanup(_PROJECT_A)
    _seed_project(_PROJECT_A, [
        {"scene_number": 1, "category": "Pacing", "severity": "Critical", "raw_note_text": "S1"},
        {"scene_number": 2, "category": "Character", "severity": "Major", "raw_note_text": "S2"},
        {"scene_number": 3, "category": "Dialogue", "severity": "Minor", "raw_note_text": "S3"},
    ], conflicts=[
        {"scene_number": 1, "stakeholder_a": "A", "note_a": "Cut",
         "stakeholder_b": "B", "note_b": "Breathe",
         "conflict_type": "Structural", "resolution_status": "Unresolved"},
    ])
    try:
        result = q.stakeholder_alignment(_PROJECT_A, 1)
        assert isinstance(result, dict)
        assert "scenes_with_notes" in result
        assert "scenes_with_conflicts" in result
        assert "conflict_rate" in result
        assert "alignment_ratio" in result
        assert int(result["scenes_with_notes"]) == 3
        # Scene 1 has the conflict. The query counts distinct scene_numbers > 0
        # in notes_conflicts for this project/draft. Only scene 1 has a conflict.
        assert int(result["scenes_with_conflicts"]) == 1
        assert 0.0 <= float(result["conflict_rate"]) <= 1.0
        assert 0.0 <= float(result["alignment_ratio"]) <= 1.0
        assert abs(float(result["alignment_ratio"]) - (1.0 - float(result["conflict_rate"]))) < 0.001
    finally:
        _safe_cleanup(_PROJECT_A)


def test_revision_risk_score_shape_and_bounds() -> None:
    """Item 7: revision_risk_score returns 0-100 score + components + level."""
    _safe_cleanup(_PROJECT_A)
    _seed_project(_PROJECT_A, [
        {"scene_number": 1, "category": "Pacing", "severity": "Critical", "raw_note_text": "S1 critical"},
        {"scene_number": 1, "category": "Pacing", "severity": "Critical", "raw_note_text": "S1 critical 2"},
        {"scene_number": 1, "category": "Pacing", "severity": "Major", "raw_note_text": "S1 major"},
        {"scene_number": 2, "category": "Character", "severity": "Major", "raw_note_text": "S2 major"},
        {"scene_number": 3, "category": "Dialogue", "severity": "Minor", "raw_note_text": "S3 minor"},
    ], conflicts=[
        {"scene_number": 1, "stakeholder_a": "Producer", "note_a": "Cut",
         "stakeholder_b": "Director", "note_b": "Breathe",
         "conflict_type": "Structural", "resolution_status": "Unresolved"},
    ])
    try:
        result = q.revision_risk_score(_PROJECT_A, 1)
        assert isinstance(result, dict)
        assert "risk_score" in result
        assert "risk_level" in result
        assert "components" in result
        assert 0.0 <= float(result["risk_score"]) <= 100.0
        assert result["risk_level"] in ("green", "amber", "red")
        for key in ("critical_ratio", "conflict_rate", "notes_density_score", "stakeholder_fragility_score"):
            assert key in result["components"], f"missing component {key}"
            assert 0.0 <= float(result["components"][key]) <= 1.0
        # Sanity: with 2 criticals out of 5 notes + 1 conflict scene / 3 note scenes,
        # the score should be > 0 (not a totally clean project).
        # critical_ratio = 2/5 = 0.4 -> 40*0.4 = 16
        # conflict_rate = 1/3 = 0.333 -> 30*0.333 = 10
        # notes_density = 5/3 = 1.67 -> capped 10 -> 20*0.167 = 3.3
        # stakeholder_fragility = 1/10 = 0.1 -> 10*0.1 = 1
        # Total ~30.3 — well above 0.
        assert float(result["risk_score"]) > 0, f"expected non-zero risk, got {result['risk_score']} (components: {result['components']})"
    finally:
        _safe_cleanup(_PROJECT_A)


def test_cross_project_benchmarks_shape() -> None:
    """Items 10-12: global_benchmarks returns headline + leaderboard + dists."""
    # Seed two projects so there IS cross-project data
    _safe_cleanup(_PROJECT_A)
    _safe_cleanup(_PROJECT_B)
    _seed_project(_PROJECT_A, [
        {"scene_number": 1, "category": "Pacing", "severity": "Critical", "raw_note_text": "PA note"},
        {"scene_number": 2, "category": "Character", "severity": "Major", "raw_note_text": "PA note 2"},
    ], conflicts=[
        {"scene_number": 1, "stakeholder_a": "A", "note_a": "Cut",
         "stakeholder_b": "B", "note_b": "Breathe",
         "conflict_type": "Structural", "resolution_status": "Unresolved"},
    ])
    _seed_project(_PROJECT_B, [
        {"scene_number": 1, "category": "Structure", "severity": "Critical", "raw_note_text": "PB note"},
        {"scene_number": 2, "category": "Dialogue", "severity": "Minor", "raw_note_text": "PB note 2"},
        {"scene_number": 3, "category": "Logic", "severity": "Major", "raw_note_text": "PB note 3"},
    ], conflicts=[
        {"scene_number": 1, "stakeholder_a": "C", "note_a": "Restructure",
         "stakeholder_b": "D", "note_b": "Keep structure",
         "conflict_type": "Tone", "resolution_status": "Resolved"},
    ])
    try:
        result = q.global_benchmarks()
        assert isinstance(result, dict)
        assert "headline" in result
        assert "risk_leaderboard" in result
        assert "global_category_dist" in result
        assert "global_conflict_type_dist" in result
        h = result["headline"]
        for key in ("total_projects", "total_notes", "total_scenes_with_notes",
                     "total_conflicts", "global_critical_ratio"):
            assert key in h, f"missing headline key {key}"
        assert int(h["total_projects"]) >= 2, f"expected >=2 projects, got {h['total_projects']}"
        assert int(h["total_notes"]) >= 5, f"expected >=5 notes, got {h['total_notes']}"
        assert int(h["total_conflicts"]) >= 2, f"expected >=2 conflicts, got {h['total_conflicts']}"
        # Leaderboard should list both projects
        lb = result["risk_leaderboard"]
        assert isinstance(lb, list)
        assert len(lb) >= 1
        for r in lb:
            assert "project_id" in r
            assert "risk_score" in r
            assert 0.0 <= float(r["risk_score"]) <= 100.0
        # Category dist should include categories from both projects
        cd = result["global_category_dist"]
        assert isinstance(cd, list)
        cats = {r["category"] for r in cd}
        assert "Pacing" in cats
        assert "Character" in cats
        assert "Structure" in cats
    finally:
        _safe_cleanup(_PROJECT_A)
        _safe_cleanup(_PROJECT_B)


def test_project_analytics_bundle_includes_new_queries() -> None:
    """Bundled project_analytics() includes all new keys."""
    _safe_cleanup(_PROJECT_A)
    _seed_project(_PROJECT_A, [
        {"scene_number": 1, "category": "Pacing", "severity": "Critical", "raw_note_text": "Bundle test"},
    ])
    try:
        bundle = q.project_analytics(_PROJECT_A, 1)
        assert isinstance(bundle, dict)
        for key in ("scene_density", "stakeholder_disagreement", "draft_progress",
                     "severity_heatmap", "category_severity_matrix", "stakeholder_influence",
                     "conflict_type_breakdown", "conflict_aging", "draft_progression",
                     "expected_scenes_to_revise", "stakeholder_alignment", "revision_risk_score"):
            assert key in bundle, f"bundle missing {key}"
    finally:
        _safe_cleanup(_PROJECT_A)


if __name__ == "__main__":
    tests = sorted(
        (name, obj) for name, obj in sorted(globals().items())
        if name.startswith("test_") and callable(obj)
    )
    passed = failed = 0
    for name, fn in tests:
        try:
            fn()
            print(f"PASS: {name}")
            passed += 1
        except Exception as exc:
            print(f"FAIL: {name} — {exc}")
            failed += 1
    print(f"\n{passed} passed, {failed} failed, {passed + failed} total")
    sys.exit(0 if failed == 0 else 1)
