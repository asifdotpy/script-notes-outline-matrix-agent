"""Relational analytics queries over the notes matrix (ClickHouse partner track).

These queries are the load-bearing ClickHouse story: scene revision density + conflict
rate, stakeholder disagreement breakdown, and draft-to-draft progress. They run against
both ClickHouse Cloud and embedded chDB via src.clickhouse.client.run_query.

mcp-clickhouse's run_query does not pass ClickHouse native {param:Type} bindings through
our wrapper, so parameters are interpolated with explicit escaping (string/int only —
never raw user SQL). This is safe for the trusted, agent-generated inputs we pass.

Expansion (2026-08-12): per-project analytics (items 1-9) and cross-project benchmarks
(items 10-12) from FEATURE_REQUEST.md / IDEAS/CLICKHOUSE_ANALYTICS_EXPANSION.md.
"""

from __future__ import annotations

from src.clickhouse import client as ch


def _q(s: str) -> str:
    """Escape a single-quoted SQL string literal."""
    return s.replace("'", "''")


# ---------------------------------------------------------------------------
# EXISTING QUERIES (preserved as-is)
# ---------------------------------------------------------------------------

def scene_density_and_conflicts(project_id: str, draft_version: int = 1) -> list[dict]:
    """Query 1 (original): which scenes carry the most notes and unresolved conflicts."""
    pid = _q(project_id)
    sql = f"""
        SELECT
            n.scene_number                                  AS scene_number,
            count(n.note_id)                                AS total_notes,
            countIf(n.severity = 'Critical')                AS critical_notes,
            count(DISTINCT c.conflict_id)                  AS conflict_count
        FROM script_notes_matrix.notes_raw AS n
        LEFT JOIN script_notes_matrix.notes_conflicts AS c
            ON n.project_id = c.project_id
           AND n.draft_version = c.draft_version
           AND n.scene_number = c.scene_number
        WHERE n.project_id = '{pid}' AND n.draft_version = {int(draft_version)}
        GROUP BY n.scene_number
        ORDER BY conflict_count DESC, total_notes DESC
    """
    return ch.run_query(sql)


def stakeholder_disagreement(project_id: str, draft_version: int = 1) -> list[dict]:
    """Query 2 (original): feedback volume + critical ratio by source type and category."""
    pid = _q(project_id)
    sql = f"""
        SELECT
            source_type,
            category,
            count(*)                              AS note_count,
            round(avg(severity = 'Critical'), 2) AS critical_ratio
        FROM script_notes_matrix.notes_raw
        WHERE project_id = '{pid}' AND draft_version = {int(draft_version)}
        GROUP BY source_type, category
        ORDER BY note_count DESC
    """
    return ch.run_query(sql)


def draft_progress(project_id: str) -> list[dict]:
    """Query 3 (original): per-draft rollup — affected scenes, total notes, distinct reviewers."""
    pid = _q(project_id)
    sql = f"""
        SELECT
            project_id,
            draft_version,
            count(DISTINCT scene_number) AS affected_scenes,
            count(note_id)                AS total_notes,
            uniqExact(source_author)      AS total_reviewers
        FROM script_notes_matrix.notes_raw
        WHERE project_id = '{pid}'
        GROUP BY project_id, draft_version
        ORDER BY draft_version ASC
    """
    return ch.run_query(sql)


# ---------------------------------------------------------------------------
# NEW — PER-PROJECT ANALYTICS (items 1-9)
# ---------------------------------------------------------------------------

def severity_heatmap(project_id: str, draft_version: int = 1) -> list[dict]:
    """Item 1: note count per (scene_number, severity) for a heatmap matrix.

    Each row = one cell of the heatmap: scene_number, severity, count.
    Render as a 2D grid (scenes x severity levels) colored by count.
    """
    pid = _q(project_id)
    sql = f"""
        SELECT
            n.scene_number          AS scene_number,
            n.severity              AS severity,
            count(n.note_id)        AS note_count
        FROM script_notes_matrix.notes_raw AS n
        WHERE n.project_id = '{pid}' AND n.draft_version = {int(draft_version)}
        GROUP BY n.scene_number, n.severity
        ORDER BY n.scene_number ASC, n.severity ASC
    """
    return ch.run_query(sql)


def category_severity_matrix(project_id: str, draft_version: int = 1) -> list[dict]:
    """Item 2: note count per (category, severity) for a stacked bar / matrix.

    Each row = one cell: category, severity, count.
    """
    pid = _q(project_id)
    sql = f"""
        SELECT
            n.category              AS category,
            n.severity              AS severity,
            count(n.note_id)        AS note_count
        FROM script_notes_matrix.notes_raw AS n
        WHERE n.project_id = '{pid}' AND n.draft_version = {int(draft_version)}
        GROUP BY n.category, n.severity
        ORDER BY n.category ASC, n.severity ASC
    """
    return ch.run_query(sql)


def stakeholder_influence(project_id: str, draft_version: int = 1) -> list[dict]:
    """Item 3: per-source-author feedback volume AND critical-volume.

    Two series per author: total notes + critical notes. Shows who is driving
    feedback and who is flagging the most severe issues.
    """
    pid = _q(project_id)
    sql = f"""
        SELECT
            source_author,
            count(*)                              AS total_notes,
            countIf(severity = 'Critical')        AS critical_notes,
            countIf(severity = 'Major')           AS major_notes,
            round(avg(severity = 'Critical'), 3)  AS critical_ratio
        FROM script_notes_matrix.notes_raw
        WHERE project_id = '{pid}' AND draft_version = {int(draft_version)}
        GROUP BY source_author
        ORDER BY total_notes DESC
    """
    return ch.run_query(sql)


def conflict_type_breakdown(project_id: str, draft_version: int = 1) -> list[dict]:
    """Item 4: per conflict_type count + unresolved count.

    Shows what KIND of disagreements are brewing and how many are still open.
    """
    pid = _q(project_id)
    sql = f"""
        SELECT
            conflict_type,
            count(*)                              AS total_conflicts,
            countIf(resolution_status = 'Unresolved') AS unresolved_count,
            round(avg(resolution_status = 'Unresolved'), 2) AS unresolved_ratio
        FROM script_notes_matrix.notes_conflicts
        WHERE project_id = '{pid}' AND draft_version = {int(draft_version)}
        GROUP BY conflict_type
        ORDER BY total_conflicts DESC
    """
    return ch.run_query(sql)


def conflict_aging(project_id: str, draft_version: int = 1) -> list[dict]:
    """Item 5: aging histogram of unresolved conflicts.

    Returns bucketed counts of how long unresolved conflicts have been open,
    in hours. Buckets: 0-6h, 6-24h, 1-3d, 3-7d, 7-14d, 14+d.

    Also returns summary stats: avg_hours_open, max_hours_open, unresolved_count.
    """
    pid = _q(project_id)
    # Bucketed histogram
    sql_buckets = f"""
        SELECT
            conflict_type,
            countIf(toInt32(hours_open) < 6)                                                    AS h_0_6,
            countIf(toInt32(hours_open) >= 6 AND toInt32(hours_open) < 24)                     AS h_6_24,
            countIf(toInt32(hours_open) >= 24 AND toInt32(hours_open) < 72)                    AS d_1_3,
            countIf(toInt32(hours_open) >= 72 AND toInt32(hours_open) < 168)                   AS d_3_7,
            countIf(toInt32(hours_open) >= 168 AND toInt32(hours_open) < 336)                  AS d_7_14,
            countIf(toInt32(hours_open) >= 336)                                                 AS d_14_plus,
            count(*)                                                                             AS total_in_bucket
        FROM (
            SELECT
                conflict_type,
                toInt32((now() - created_at) / 3600) AS hours_open
            FROM script_notes_matrix.notes_conflicts
            WHERE project_id = '{pid}'
              AND draft_version = {int(draft_version)}
              AND resolution_status = 'Unresolved'
        )
        GROUP BY conflict_type
        ORDER BY total_in_bucket DESC
    """
    # Summary stats (total unresolved, avg + max hours open)
    sql_summary = f"""
        SELECT
            count(*)                                                                        AS unresolved_count,
            round(avg(toInt32((now() - created_at) / 3600)), 1)                            AS avg_hours_open,
            round(max(toInt32((now() - created_at) / 3600)), 1)                            AS max_hours_open,
            round(quantile(0.5)(toInt32((now() - created_at) / 3600)), 1)                  AS median_hours_open
        FROM script_notes_matrix.notes_conflicts
        WHERE project_id = '{pid}'
          AND draft_version = {int(draft_version)}
          AND resolution_status = 'Unresolved'
    """
    buckets = ch.run_query(sql_buckets)
    summary = ch.run_query(sql_summary)
    return {
        "buckets": buckets,
        "summary": summary[0] if summary else {
            "unresolved_count": 0, "avg_hours_open": 0,
            "max_hours_open": 0, "median_hours_open": 0,
        },
    }


def draft_progression(project_id: str) -> list[dict]:
    """Item 6: per-draft progression — notes, conflicts, criticals across drafts.

    Reuses draft_progress for the notes side and adds a conflicts-per-draft query.
    Combine client-side or here. We return both series separately for clarity.
    """
    pid = _q(project_id)
    # Notes per draft (reuses draft_progress shape but we call it)
    notes_per_draft = draft_progress(project_id)
    # Conflicts + criticals per draft
    sql_conflicts = f"""
        SELECT
            draft_version,
            count(DISTINCT scene_number)                 AS conflict_scenes,
            count(conflict_id)                           AS total_conflicts,
            countIf(resolution_status = 'Unresolved')    AS unresolved_conflicts,
            uniqExact(conflict_type)                     AS distinct_conflict_types
        FROM script_notes_matrix.notes_conflicts
        WHERE project_id = '{pid}'
        GROUP BY draft_version
        ORDER BY draft_version ASC
    """
    conflicts_per_draft = ch.run_query(sql_conflicts)
    return {
        "notes": notes_per_draft,
        "conflicts": conflicts_per_draft,
    }


def expected_scenes_to_revise(project_id: str, draft_version: int = 1) -> dict:
    """Item 8: count of scenes that have >= 1 note OR >= 1 conflict.

    This is the "how many scenes will the writer actually touch?" estimate.
    Returns both the count and the breakdown (notes-only, conflicts-only, both).
    """
    pid = _q(project_id)
    sql = f"""
        SELECT
            count(DISTINCT case when n.note_count > 0 THEN n.scene_number END) AS scenes_with_notes,
            count(DISTINCT case when c.conflict_count > 0 THEN n.scene_number END) AS scenes_with_conflicts,
            count(DISTINCT case when n.note_count > 0 AND c.conflict_count > 0 THEN n.scene_number END) AS scenes_with_both,
            count(DISTINCT n.scene_number) AS all_scenes_with_activity
        FROM (
            SELECT scene_number, count(*) AS note_count
            FROM script_notes_matrix.notes_raw
            WHERE project_id = '{pid}' AND draft_version = {int(draft_version)}
            GROUP BY scene_number
        ) n
        LEFT JOIN (
            SELECT scene_number, count(*) AS conflict_count
            FROM script_notes_matrix.notes_conflicts
            WHERE project_id = '{pid}' AND draft_version = {int(draft_version)}
            GROUP BY scene_number
        ) c ON n.scene_number = c.scene_number
    """
    rows = ch.run_query(sql)
    if not rows:
        return {
            "scenes_with_notes": 0, "scenes_with_conflicts": 0,
            "scenes_with_both": 0, "all_scenes_with_activity": 0,
        }
    r = rows[0]
    return {
        "scenes_with_notes": int(r.get("scenes_with_notes", 0) or 0),
        "scenes_with_conflicts": int(r.get("scenes_with_conflicts", 0) or 0),
        "scenes_with_both": int(r.get("scenes_with_both", 0) or 0),
        "all_scenes_with_activity": int(r.get("all_scenes_with_activity", 0) or 0),
    }


def stakeholder_alignment(project_id: str, draft_version: int = 1) -> dict:
    """Item 9: alignment score = scenes with notes that have NO conflict / total note scenes.

    Returns conflict_rate (scenes with conflicts / scenes with notes) and the inverse
    alignment_ratio. Also returns the raw scene counts.
    """
    pid = _q(project_id)
    sql = f"""
        SELECT
            (SELECT count(DISTINCT scene_number)
             FROM script_notes_matrix.notes_raw
             WHERE project_id = '{pid}' AND draft_version = {int(draft_version)}
               AND scene_number > 0) AS scenes_with_notes,
            (SELECT count(DISTINCT scene_number)
             FROM script_notes_matrix.notes_conflicts
             WHERE project_id = '{pid}' AND draft_version = {int(draft_version)}
               AND scene_number > 0) AS scenes_with_conflicts
    """
    rows = ch.run_query(sql)
    if not rows:
        return {
            "scenes_with_notes": 0, "scenes_with_conflicts": 0,
            "conflict_rate": 0.0, "alignment_ratio": 1.0,
        }
    r = rows[0]
    scenes_notes = int(r.get("scenes_with_notes", 0) or 0)
    scenes_conflicts = int(r.get("scenes_with_conflicts", 0) or 0)
    conflict_rate = round(scenes_conflicts / scenes_notes, 3) if scenes_notes else 0.0
    return {
        "scenes_with_notes": scenes_notes,
        "scenes_with_conflicts": scenes_conflicts,
        "conflict_rate": conflict_rate,
        "alignment_ratio": round(1.0 - conflict_rate, 3),
    }


# ---------------------------------------------------------------------------
# NEW — COMPOSITE METRICS (items 7, 9)
# ---------------------------------------------------------------------------

def revision_risk_score(project_id: str, draft_version: int = 1) -> dict:
    """Item 7: Revision Risk Score (0-100), computed ENTIRELY in ClickHouse SQL.

    Formula (documented for auditability — this is a transparent proxy, not a black box):

        risk = clamp(
            40 * critical_ratio                          -- 40 pts max: how many notes are Critical?
            + 30 * conflict_rate                         -- 30 pts max: what fraction of scenes have conflicts?
            + 20 * notes_density_score                  -- 20 pts max: how crowded is the feedback per scene?
            + 10 * stakeholder_fragility_score           -- 10 pts max: how fragmented is the reviewer set?
        )

    Where:
        critical_ratio       = critical_notes / total_notes                     (0..1)
        conflict_rate        = scenes_with_conflicts / scenes_with_notes       (0..1)
        notes_density_score  = min(total_notes / max(1, scenes_with_notes) / 10, 1)  (0..1, cap 10 notes/scene)
        stakeholder_fragility = min(total_reviewers / 10, 1)                   (0..1, cap 10 reviewers)

    Each component is capped at 1 so the max score is 100.
    Interpretation:
        < 35  green  — revision likely straightforward
        35-65 amber  — revision has real rough spots; plan carefully
        > 65  red    — high probability the revision will stall or require major rework

    NOTE: This is a revision-management heuristic, NOT a predictive ML model. It flags
    scripts that are likely to need more work based on observable feedback patterns.
    """
    pid = _q(project_id)
    sql = f"""
        SELECT
            (SELECT count(DISTINCT scene_number)
             FROM script_notes_matrix.notes_raw
             WHERE project_id = '{pid}' AND draft_version = {int(draft_version)}
               AND scene_number > 0) AS scenes_with_notes,
            (SELECT count(DISTINCT scene_number)
             FROM script_notes_matrix.notes_conflicts
             WHERE project_id = '{pid}' AND draft_version = {int(draft_version)}
               AND scene_number > 0) AS scenes_with_conflicts,
            countIf(severity = 'Critical') AS critical_notes,
            count(*)                        AS total_notes,
            uniqExact(source_author)        AS total_reviewers
        FROM script_notes_matrix.notes_raw
        WHERE project_id = '{pid}' AND draft_version = {int(draft_version)}
    """
    rows = ch.run_query(sql)
    if not rows:
        return {
            "risk_score": 0, "risk_level": "green",
            "critical_ratio": 0.0, "conflict_rate": 0.0,
            "notes_density_score": 0.0, "stakeholder_fragility_score": 0.0,
            "components": {},
        }
    r = rows[0]

    total_notes = int(r.get("total_notes", 0) or 0)
    critical_notes = int(r.get("critical_notes", 0) or 0)
    scenes_notes = int(r.get("scenes_with_notes", 0) or 0)
    scenes_conflicts = int(r.get("scenes_with_conflicts", 0) or 0)
    total_reviewers = int(r.get("total_reviewers", 0) or 0)

    # Component 1: critical ratio (0..1)
    critical_ratio = round(critical_notes / total_notes, 3) if total_notes else 0.0

    # Component 2: conflict rate (0..1)
    conflict_rate = round(scenes_conflicts / scenes_notes, 3) if scenes_notes else 0.0

    # Component 3: notes density (notes per scene, capped at 10 -> 0..1)
    density_raw = round(total_notes / max(1, scenes_notes), 2) if scenes_notes else 0.0
    notes_density_score = round(min(density_raw / 10.0, 1.0), 3)

    # Component 4: stakeholder fragility (reviewers, capped at 10 -> 0..1)
    stakeholder_fragility_score = round(min(total_reviewers / 10.0, 1.0), 3)

    # Composite
    raw_score = (
        40 * critical_ratio
        + 30 * conflict_rate
        + 20 * notes_density_score
        + 10 * stakeholder_fragility_score
    )
    risk_score = round(min(max(raw_score, 0), 100), 1)

    if risk_score < 35:
        risk_level = "green"
    elif risk_score <= 65:
        risk_level = "amber"
    else:
        risk_level = "red"

    return {
        "risk_score": risk_score,
        "risk_level": risk_level,
        "critical_ratio": critical_ratio,
        "conflict_rate": conflict_rate,
        "notes_density_score": notes_density_score,
        "stakeholder_fragility_score": stakeholder_fragility_score,
        "scenes_with_notes": scenes_notes,
        "scenes_with_conflicts": scenes_conflicts,
        "total_notes": total_notes,
        "critical_notes": critical_notes,
        "total_reviewers": total_reviewers,
        "components": {
            "critical_ratio": critical_ratio,
            "conflict_rate": conflict_rate,
            "notes_density_score": notes_density_score,
            "stakeholder_fragility_score": stakeholder_fragility_score,
        },
    }


# ---------------------------------------------------------------------------
# NEW — CROSS-PROJECT BENCHMARKS (items 10-12)
# ---------------------------------------------------------------------------

def global_benchmarks() -> dict:
    """Item 10: aggregate analytics ACROSS ALL projects in ClickHouse.

    Returns headline stats + a "highest risk projects" leaderboard (top 10 by risk score).
    All values are aggregates only — no raw note text crosses the project boundary.
    """
    # Headline numbers — separate queries to avoid JOIN null-default issues in chDB
    notes_sql = """
        SELECT
            count(DISTINCT project_id)                          AS total_projects,
            count(*)                                             AS total_notes,
            count(DISTINCT scene_number)                         AS total_scenes_with_notes,
            count(DISTINCT source_author)                        AS total_reviewers_seen,
            round(avg(severity = 'Critical'), 3)                AS global_critical_ratio,
            round(avg(source_type = 'pdf_coverage'), 3)         AS pct_pdf_coverage
        FROM script_notes_matrix.notes_raw
    """
    conflict_sql = """
        SELECT
            count(DISTINCT conflict_id)                         AS total_conflicts,
            count(DISTINCT scene_number)                         AS conflict_scenes
        FROM script_notes_matrix.notes_conflicts
    """
    notes_rows = ch.run_query(notes_sql)
    conflict_rows = ch.run_query(conflict_sql)
    if not notes_rows:
        return {"headline": {}, "risk_leaderboard": [], "global_category_dist": [], "global_conflict_type_dist": []}
    h = notes_rows[0]
    c = conflict_rows[0] if conflict_rows else {"total_conflicts": 0, "conflict_scenes": 0}

    total_notes = int(h.get("total_notes", 0) or 0)
    total_scenes_notes = int(h.get("total_scenes_with_notes", 0) or 0)
    total_conflict_scenes = int(c.get("conflict_scenes", 0) or 0)
    global_conflict_rate = round(total_conflict_scenes / max(1, total_scenes_notes), 3) if total_scenes_notes else 0.0

    # Risk leaderboard — top 10 projects by risk score (reuse the risk formula per project)
    # We compute risk per project for all projects. To avoid correlated-subquery
    # overhead in chDB (which crashes the stdio subprocess with many projects), we
    # pre-aggregate the conflicts table into a small CTE and join it once.
    sql_leaderboard = """
        WITH project_agg AS (
            SELECT
                project_id,
                count(*)                                         AS total_notes,
                countIf(severity = 'Critical')                   AS critical_notes,
                count(DISTINCT scene_number)                     AS scenes_with_notes,
                uniqExact(source_author)                         AS total_reviewers
            FROM script_notes_matrix.notes_raw
            GROUP BY project_id
            HAVING total_notes > 0
            ORDER BY total_notes DESC
        ),
        conflict_agg AS (
            SELECT
                project_id,
                count(DISTINCT scene_number) AS scenes_with_conflicts
            FROM script_notes_matrix.notes_conflicts
            WHERE scene_number > 0
            GROUP BY project_id
        )
        SELECT
            p.project_id,
            p.total_notes,
            p.critical_notes,
            p.scenes_with_notes,
            coalesce(c.scenes_with_conflicts, 0)              AS scenes_with_conflicts,
            p.total_reviewers,
            round(p.critical_notes / if(p.total_notes > 1, p.total_notes, 1), 3)                                          AS critical_ratio,
            round(coalesce(c.scenes_with_conflicts, 0) / if(p.scenes_with_notes > 1, p.scenes_with_notes, 1), 3)                 AS conflict_rate,
            round(if(p.total_notes > 10 * if(p.scenes_with_notes > 1, p.scenes_with_notes, 1), 1.0, p.total_notes / if(p.scenes_with_notes > 1, p.scenes_with_notes, 1) / 10), 3) AS notes_density_score,
            round(if(p.total_reviewers > 10.0, 1.0, p.total_reviewers / 10.0), 3)                                 AS stakeholder_fragility_score,
            round(
                40 * (p.critical_notes / if(p.total_notes > 1, p.total_notes, 1))
                + 30 * (coalesce(c.scenes_with_conflicts, 0) / if(p.scenes_with_notes > 1, p.scenes_with_notes, 1))
                + 20 * if(p.total_notes > 10 * if(p.scenes_with_notes > 1, p.scenes_with_notes, 1), 1.0, p.total_notes / if(p.scenes_with_notes > 1, p.scenes_with_notes, 1) / 10)
                + 10 * if(p.total_reviewers > 10.0, 1.0, p.total_reviewers / 10.0)
            , 1)                                                                                       AS risk_score
        FROM project_agg p
        LEFT JOIN conflict_agg c ON p.project_id = c.project_id
        ORDER BY risk_score DESC
        LIMIT 10
    """
    leaderboard = ch.run_query(sql_leaderboard)

    # Global category distribution (item 11)
    sql_cat = """
        SELECT category, count(*) AS note_count
        FROM script_notes_matrix.notes_raw
        GROUP BY category
        ORDER BY note_count DESC
    """
    global_category_dist = ch.run_query(sql_cat)

    # Global conflict type distribution (item 12)
    sql_ct = """
        SELECT conflict_type, count(*) AS conflict_count
        FROM script_notes_matrix.notes_conflicts
        GROUP BY conflict_type
        ORDER BY conflict_count DESC
    """
    global_conflict_type_dist = ch.run_query(sql_ct)

    # Also: conflict rate across ALL projects (aggregate) — separate queries
    notes_rows2 = ch.run_query("""
        SELECT count(DISTINCT scene_number) AS total_scenes_with_notes
        FROM script_notes_matrix.notes_raw
        WHERE scene_number > 0
    """)
    conflict_scenes_rows = ch.run_query("""
        SELECT count(DISTINCT scene_number) AS scenes_with_conflicts_anywhere
        FROM script_notes_matrix.notes_conflicts
        WHERE scene_number > 0
    """)
    total_scenes_notes_global = int((notes_rows2[0].get("total_scenes_with_notes") or 0) if notes_rows2 else 0)
    scenes_conflicts_global = int((conflict_scenes_rows[0].get("scenes_with_conflicts_anywhere") or 0) if conflict_scenes_rows else 0)
    global_conflict_rate = round(scenes_conflicts_global / max(1, total_scenes_notes_global), 3)

    return {
        "headline": {
            "total_projects": int(h.get("total_projects", 0) or 0),
            "total_notes": total_notes,
            "total_scenes_with_notes": total_scenes_notes,
            "total_conflicts": int(c.get("total_conflicts", 0) or 0),
            "total_reviewers_seen": int(h.get("total_reviewers_seen", 0) or 0),
            "global_critical_ratio": float(h.get("global_critical_ratio", 0) or 0),
            "pct_pdf_coverage": float(h.get("pct_pdf_coverage", 0) or 0),
            "global_conflict_rate": global_conflict_rate,
        },
        "risk_leaderboard": leaderboard,
        "global_category_dist": global_category_dist,
        "global_conflict_type_dist": global_conflict_type_dist,
    }


# ---------------------------------------------------------------------------
# BUNDLE — existing + new per-project analytics
# ---------------------------------------------------------------------------

def project_analytics(project_id: str, draft_version: int = 1) -> dict:
    """Run all per-project analytical queries and bundle them for the agent/web response.

    Includes: original 3 queries + new items 1-9.
    """
    return {
        "project_id": project_id,
        "draft_version": int(draft_version),
        # Original queries
        "scene_density": scene_density_and_conflicts(project_id, draft_version),
        "stakeholder_disagreement": stakeholder_disagreement(project_id, draft_version),
        "draft_progress": draft_progress(project_id),
        # New per-project (items 1-9)
        "severity_heatmap": severity_heatmap(project_id, draft_version),
        "category_severity_matrix": category_severity_matrix(project_id, draft_version),
        "stakeholder_influence": stakeholder_influence(project_id, draft_version),
        "conflict_type_breakdown": conflict_type_breakdown(project_id, draft_version),
        "conflict_aging": conflict_aging(project_id, draft_version),
        "draft_progression": draft_progression(project_id),
        "expected_scenes_to_revise": expected_scenes_to_revise(project_id, draft_version),
        "stakeholder_alignment": stakeholder_alignment(project_id, draft_version),
        "revision_risk_score": revision_risk_score(project_id, draft_version),
    }


def cross_project_benchmarks() -> dict:
    """Item 10-12: aggregate analytics across all projects.

    For the new "Cross-Project Benchmarks" tab.
    """
    return global_benchmarks()
