"""Relational analytics queries over the notes matrix (ClickHouse partner track).

These queries are the load-bearing ClickHouse story: scene revision density + conflict
rate, stakeholder disagreement breakdown, and draft-to-draft progress. They run against
both ClickHouse Cloud and embedded chDB via src.clickhouse.client.run_query.

mcp-clickhouse's run_query does not pass ClickHouse native {param:Type} bindings through
our wrapper, so parameters are interpolated with explicit escaping (string/int only —
never raw user SQL). This is safe for the trusted, agent-generated inputs we pass.
"""
from __future__ import annotations

from src.clickhouse import client as ch


def _q(s: str) -> str:
    """Escape a single-quoted SQL string literal."""
    return s.replace("'", "''")


def scene_density_and_conflicts(project_id: str, draft_version: int = 1) -> list[dict]:
    """Query 1: which scenes carry the most notes and unresolved conflicts."""
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
    """Query 2: feedback volume + critical ratio by source type and category."""
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
    """Query 3: per-draft rollup — affected scenes, total notes, distinct reviewers."""
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


def project_analytics(project_id: str, draft_version: int = 1) -> dict:
    """Run all three analytical queries and bundle them for the agent/web response."""
    return {
        "project_id": project_id,
        "draft_version": int(draft_version),
        "scene_density": scene_density_and_conflicts(project_id, draft_version),
        "stakeholder_disagreement": stakeholder_disagreement(project_id, draft_version),
        "draft_progress": draft_progress(project_id),
    }
