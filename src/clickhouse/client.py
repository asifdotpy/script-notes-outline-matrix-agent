"""ClickHouse client backed by the official mcp-clickhouse MCP server.

Implements the hackathon's hard requirement: ACTIVE RUNTIME use of ClickHouse via
the official mcp-clickhouse MCP server (not a README mention). The server is
launched as a subprocess (stdio transport) and queried over MCP. This works with
both ClickHouse Cloud (set CLICKHOUSE_* env) and embedded chDB (CHDB_ENABLED=true),
so development runs free and the live submission flips to Cloud via env vars only.

Concurrency model
-----------------
The MCP stdio client is async. ADK agent tools and FastAPI handlers may call
`run_query` from *within* an already-running event loop (ADK runs async). To avoid
nested-event-loop crashes ("Event loop is closed", leaked coroutines), this module
owns ONE dedicated background event loop on a private thread for the lifetime of the
process. `run_query` submits coroutines to that loop via `run_coroutine_threadsafe`
and blocks on the returned future — safe from any caller context (sync or async).
"""
from __future__ import annotations

import asyncio
import json
import os
import threading
import uuid
from pathlib import Path

SCHEMA_PATH = Path(__file__).parent / "schema.sql"

# --- dedicated loop + lock for the MCP stdio client (process-lifetime) ---
_LOOP: asyncio.AbstractEventLoop | None = None
_LOOP_THREAD: threading.Thread | None = None
_LOOP_LOCK = threading.Lock()


def _ensure_loop() -> asyncio.AbstractEventLoop:
    """Start (once) a private event loop on a background thread."""
    global _LOOP, _LOOP_THREAD
    with _LOOP_LOCK:
        if _LOOP is not None and not _LOOP.is_closed():
            return _LOOP
        loop = asyncio.new_event_loop()

        def _run() -> None:
            asyncio.set_event_loop(loop)
            loop.run_forever()

        t = threading.Thread(target=_run, daemon=True)
        t.start()
        _LOOP = loop
        _LOOP_THREAD = t
        return loop


def _server_params() -> "StdioServerParameters":
    """Build stdio launch params for the mcp-clickhouse server from env.

    Mirrors the official config: uv run --with mcp-clickhouse mcp-clickhouse,
    with CLICKHOUSE_*/CHDB_* env forwarded (mcp-clickhouse reads them directly).

    Tool selection (per mcp_server.py registration logic):
      - Cloud mode (CLICKHOUSE_HOST set): real ClickHouse client + `run_query` tool.
        Leave CLICKHOUSE_ENABLED unset/true.
      - Local chDB mode: set CLICKHOUSE_ENABLED=false so the real-client `run_query`
        tool is NOT registered, and chDB tools (run_chdb_select_query) register instead.
        chDB runs fully in-process (free, no account/credits).
    """
    # Imported lazily so the module loads cleanly even where mcp-clickhouse/chdb are not
    # importable at startup (e.g. some hosted runtimes) — only needed when a query runs.
    from mcp import StdioServerParameters
    env = dict(os.environ)
    # Default to embedded chDB if nothing else is configured (free local dev).
    # IMPORTANT: chDB needs a *file-backed* data path for the mcp-clickhouse wrapper to
    # persist DDL across calls — ':memory:' creates an isolated session per call and tables
    # vanish. Use a temp dir (override via CHDB_DATA_PATH).
    if "CHDB_ENABLED" not in env and "CLICKHOUSE_HOST" not in env:
        env["CHDB_ENABLED"] = "true"
        env["CLICKHOUSE_ENABLED"] = "false"
    if "CHDB_DATA_PATH" not in env:
        import tempfile

        env["CHDB_DATA_PATH"] = os.path.join(tempfile.gettempdir(), "agentic_cinema_chdb")
    # Allow writes (INSERT/CREATE) but never destructive ops.
    env.setdefault("CLICKHOUSE_ALLOW_WRITE_ACCESS", "true")
    env["CLICKHOUSE_ALLOW_DROP"] = "false"
    return StdioServerParameters(
        command="uv",
        args=["run", "--with", "mcp-clickhouse[chdb]", "--python", "3.10", "mcp-clickhouse"],
        env=env,
    )


def _query_tool_name() -> str:
    """Which MCP tool to call, given the active mode."""
    env = dict(os.environ)
    if "CHDB_ENABLED" not in env and "CLICKHOUSE_HOST" not in env:
        env["CHDB_ENABLED"] = "true"
        env["CLICKHOUSE_ENABLED"] = "false"
    cloud = bool(env.get("CLICKHOUSE_HOST"))
    ch_enabled = env.get("CLICKHOUSE_ENABLED", "true").lower() != "false"
    return "run_query" if (cloud or ch_enabled) else "run_chdb_select_query"


async def _run_query(sql: str) -> list[dict]:
    from mcp import ClientSession
    from mcp.client.stdio import stdio_client
    params = _server_params()
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.call_tool(_query_tool_name(), {"query": sql})
            # mcp-clickhouse returns JSON text. run_query/run_chdb_select_query return a
            # JSON string of shape {"columns": [...], "rows": [[...], ...]} OR an error
            # dict {"status": "error", "message": "..."} OR a list. Normalize to rows.
            for item in result.content:
                if getattr(item, "type", None) == "text":
                    try:
                        data = json.loads(item.text)
                    except Exception:
                        return [{"text": item.text}]
                    if isinstance(data, dict) and data.get("status") == "error":
                        raise RuntimeError(f"ClickHouse query failed: {data.get('message')}")
                    if isinstance(data, dict) and "columns" in data and "rows" in data:
                        cols = data["columns"]
                        return [dict(zip(cols, row)) for row in data["rows"]]
                    if isinstance(data, list):
                        return data
                    return [data]
            return []


def run_query(sql: str) -> list[dict]:
    """Synchronous, caller-agnostic query runner.

    Submits the async MCP call to the private background loop and blocks on the
    future, so it is safe to call from sync functions, ADK async tools, and
    FastAPI handlers alike (no nested-loop crashes).
    """
    loop = _ensure_loop()
    future = asyncio.run_coroutine_threadsafe(_run_query(sql), loop)
    return future.result()


def init_schema() -> None:
    """Apply the idempotent DDL so the tables/views exist before first use."""
    ddl = SCHEMA_PATH.read_text()
    # Execute each statement separated by ';'. Strip '--' comment lines and skip empties
    # so chDB (which doesn't auto-strip leading comments) doesn't treat a comment as a
    # no-op statement and so the CREATE VIEW references unqualified table names.
    cleaned = "\n".join(
        ln for ln in ddl.splitlines() if not ln.strip().startswith("--")
    )
    for stmt in cleaned.split(";"):
        stmt = stmt.strip()
        if stmt:
            run_query(stmt)


def new_id() -> str:
    return str(uuid.uuid4())


def slugify_project(title: str) -> str:
    """Derive a stable project_id from a script title, e.g. 'The Matrix' -> 'the-matrix'."""
    import re
    slug = re.sub(r"[^a-z0-9]+", "-", (title or "untitled").lower()).strip("-")
    return slug or "untitled"


def insert_note(
    project_id: str, draft_version: int,
    source_type: str, source_author: str,
    scene_number: int, scene_heading: str,
    category: str, severity: str, raw_note_text: str,
) -> str:
    nid = new_id()
    esc = lambda s: s.replace(chr(39), chr(39) * 2)
    run_query(
        "INSERT INTO script_notes_matrix.notes_raw "
        "(note_id, project_id, draft_version, source_type, source_author, "
        " scene_number, scene_heading, category, severity, raw_note_text) "
        f"VALUES ('{nid}', '{esc(project_id)}', {int(draft_version)}, '{esc(source_type)}', "
        f"'{esc(source_author)}', {int(scene_number)}, '{esc(scene_heading)}', "
        f"'{esc(category)}', '{esc(severity)}', '{esc(raw_note_text)}')"
    )
    return nid


def insert_conflict(
    project_id: str, draft_version: int, scene_number: int,
    stakeholder_a: str, note_a: str,
    stakeholder_b: str, note_b: str,
    conflict_type: str = "Unspecified",
) -> str:
    cid = new_id()
    esc = lambda s: s.replace(chr(39), chr(39) * 2)
    run_query(
        "INSERT INTO script_notes_matrix.notes_conflicts "
        "(conflict_id, project_id, draft_version, scene_number, stakeholder_a, note_a, "
        " stakeholder_b, note_b, conflict_type) "
        f"VALUES ('{cid}', '{esc(project_id)}', {int(draft_version)}, {int(scene_number)}, "
        f"'{esc(stakeholder_a)}', '{esc(note_a)}', '{esc(stakeholder_b)}', '{esc(note_b)}', "
        f"'{esc(conflict_type)}')"
    )
    return cid


def analytics_for(project_id: str, draft_version: int = 1) -> dict:
    """Live relational analytics over persisted notes + conflicts — the ClickHouse story."""
    from src.analytics.queries import project_analytics
    return project_analytics(project_id, draft_version)


if __name__ == "__main__":
    init_schema()
    print("schema initialized OK")
