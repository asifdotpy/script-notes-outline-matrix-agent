-- Script Notes-to-Outline Matrix Agent — ClickHouse schema
-- Applied at runtime by src/clickhouse/client.py (via the official mcp-clickhouse server).
-- Works on ClickHouse Cloud AND embedded chDB (same DDL).

CREATE TABLE IF NOT EXISTS scripts
(
    id          UUID,
    title       String,
    source_type String,            -- 'pdf_coverage' | 'email' | 'fountain' | 'fdx'
    created_at  DateTime DEFAULT now()
)
ENGINE = MergeTree
ORDER BY (created_at, id);

CREATE TABLE IF NOT EXISTS notes
(
    id          UUID,
    script_id   UUID,
    raw_text    String,            -- the original note line/paragraph
    note_type   String,            -- 'structure' | 'character' | 'dialogue' | 'pacing' | 'logic' | 'format' | 'other'
    character   String DEFAULT '', -- character the note references, if any
    scene_ref   String DEFAULT '', -- scene heading/number the note maps to, if identified
    severity    String DEFAULT 'medium', -- 'low' | 'medium' | 'high'
    created_at  DateTime DEFAULT now()
)
ENGINE = MergeTree
ORDER BY (script_id, note_type, created_at);

CREATE TABLE IF NOT EXISTS note_scene_map
(
    id            UUID,
    note_id       UUID,
    script_id     UUID,
    scene_id      String,          -- e.g. "3", "12A"
    scene_heading String,          -- e.g. "INT. COFFEE SHOP - DAY"
    created_at    DateTime DEFAULT now()
)
ENGINE = MergeTree
ORDER BY (script_id, scene_id);

CREATE TABLE IF NOT EXISTS conflicts
(
    id          UUID,
    script_id   UUID,
    note_a_id   UUID,
    note_b_id   UUID,
    description String,            -- human-readable explanation of the contradiction
    created_at  DateTime DEFAULT now()
)
ENGINE = MergeTree
ORDER BY (script_id, created_at);

-- View: the "matrix" — notes joined to the scenes they touch.
CREATE OR REPLACE VIEW notes_matrix AS
SELECT
    n.script_id,
    s.scene_id,
    s.scene_heading,
    n.id        AS note_id,
    n.raw_text,
    n.note_type,
    n.character,
    n.severity
FROM notes n
LEFT JOIN note_scene_map s ON n.id = s.note_id;
