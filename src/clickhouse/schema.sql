-- Script Notes-to-Outline Matrix Agent — ClickHouse schema (relational analytics)
-- Applied at runtime by src/clickhouse/client.py via the official mcp-clickhouse server.
-- Works on ClickHouse Cloud AND embedded chDB (same DDL).
-- NOTE: fully-qualified table names (no USE) because the chDB stdio wrapper runs each
-- query in a fresh session and does not persist a USE statement across calls.
-- Design: a granular notes fact table + a conflicts fact table, both keyed for the
-- analytical queries in src/analytics/queries.py (scene density, stakeholder disagreement,
-- draft-to-draft progress). This is relational analytics, NOT a key-value dump.

CREATE DATABASE IF NOT EXISTS script_notes_matrix;

-- 1. Raw ingested notes fact table.
-- One row per extracted note across all sources (PDF coverage, producer/agent email, etc).
CREATE TABLE IF NOT EXISTS script_notes_matrix.notes_raw
(
    note_id       UUID DEFAULT generateUUIDv4(),
    project_id    String,                       -- slug of the script title (e.g. 'the-matrix')
    draft_version UInt8 DEFAULT 1,
    source_type   LowCardinality(String),       -- 'pdf_coverage' | 'producer_email' | 'agent_email' | 'peer_review'
    source_author String,                        -- who wrote the note (exec, producer, manager...)
    scene_number  UInt16 DEFAULT 0,              -- 0 == not mapped to a numbered scene
    scene_heading String DEFAULT '',
    category      LowCardinality(String),        -- 'Pacing'|'Character'|'Dialogue'|'Structure'|'Logic'|'Other'
    severity      LowCardinality(String),        -- 'Minor'|'Major'|'Critical'
    raw_note_text String,
    created_at    DateTime DEFAULT now()
)
ENGINE = MergeTree
PRIMARY KEY (project_id, draft_version, scene_number)
ORDER BY (project_id, draft_version, scene_number, note_id);

-- 2. Flagged conflicts fact table.
-- One row per detected contradictory note pair between stakeholders for a scene.
CREATE TABLE IF NOT EXISTS script_notes_matrix.notes_conflicts
(
    conflict_id      UUID DEFAULT generateUUIDv4(),
    project_id       String,
    draft_version    UInt8 DEFAULT 1,
    scene_number     UInt16 DEFAULT 0,
    stakeholder_a    String,                     -- e.g. 'Producer Email'
    note_a           String,                      -- e.g. 'Cut Act 2 coffee shop scene'
    stakeholder_b    String,                      -- e.g. 'Manager PDF Coverage'
    note_b           String,                      -- e.g. 'Expand coffee shop dialogue'
    conflict_type    LowCardinality(String) DEFAULT 'Unspecified', -- 'Structural'|'Character Arc'|'Tone'|'Unspecified'
    resolution_status LowCardinality(String) DEFAULT 'Unresolved', -- 'Unresolved'|'Resolved'
    created_at       DateTime DEFAULT now()
)
ENGINE = MergeTree
PRIMARY KEY (project_id, draft_version, scene_number)
ORDER BY (project_id, draft_version, scene_number, conflict_id);

-- Convenience view: the "matrix" — notes joined to conflicts they triggered.
CREATE OR REPLACE VIEW script_notes_matrix.notes_matrix AS
SELECT
    n.project_id,
    n.draft_version,
    n.scene_number,
    n.source_type,
    n.category,
    n.severity,
    n.raw_note_text,
    c.conflict_id IS NOT NULL AS has_conflict
FROM script_notes_matrix.notes_raw n
LEFT JOIN script_notes_matrix.notes_conflicts c
    ON n.project_id = c.project_id
   AND n.draft_version = c.draft_version
   AND n.scene_number = c.scene_number;
