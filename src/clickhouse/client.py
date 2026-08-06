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

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

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


def _server_params() -> StdioServerParameters:
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
        args=["run", "--with", "mcp-clickhouse", "--python", "3.10", "mcp-clickhouse"],
        env=env,
    )


def _query_tool_name() -> str:
    """Which MCP tool to call, given the active mode."""
    cloud = bool(os.environ.get("CLICKHOUSE_HOST"))
    ch_enabled = os.environ.get("CLICKHOUSE_ENABLED", "true").lower() != "false"
    return "run_query" if (cloud or ch_enabled) else "run_chdb_select_query"


async def _run_query(sql: str) -> list[dict]:
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


def insert_script(title: str, source_type: str) -> str:
    sid = new_id()
    run_query(
        "INSERT INTO scripts (id, title, source_type) VALUES "
        f"('{sid}', '{title.replace(chr(39), chr(39) * 2)}', '{source_type}')"
    )
    return sid


def insert_note(
    script_id: str, raw_text: str, note_type: str,
    character: str = "", scene_ref: str = "", severity: str = "medium",
) -> str:
    nid = new_id()
    esc = lambda s: s.replace(chr(39), chr(39) * 2)
    run_query(
        "INSERT INTO notes (id, script_id, raw_text, note_type, character, scene_ref, severity) "
        f"VALUES ('{nid}', '{script_id}', '{esc(raw_text)}', '{note_type}', "
        f"'{esc(character)}', '{esc(scene_ref)}', '{severity}')"
    )
    return nid


def insert_conflict(script_id: str, note_a_id: str, note_b_id: str, description: str) -> str:
    cid = new_id()
    esc = lambda s: s.replace(chr(39), chr(39) * 2)
    run_query(
        "INSERT INTO conflicts (id, script_id, note_a_id, note_b_id, description) "
        f"VALUES ('{cid}', '{script_id}', '{note_a_id}', '{note_b_id}', '{esc(description)}')"
    )
    return cid


def analytics_for(script_id: str) -> dict:
    """Live analytics over persisted data — the load-bearing ClickHouse story."""
    by_type = run_query(
        f"SELECT note_type, count() AS n FROM notes WHERE script_id='{script_id}' "
        "GROUP BY note_type ORDER BY n DESC"
    )
    conflict_count = run_query(
        f"SELECT count() AS n FROM conflicts WHERE script_id='{script_id}'"
    )
    scene_count = run_query(
        f"SELECT countDistinct(scene_id) AS n FROM note_scene_map WHERE script_id='{script_id}'"
    )
    return {
        "by_type": by_type,
        "conflict_count": conflict_count[0]["n"] if conflict_count else 0,
        "scene_count": scene_count[0]["n"] if scene_count else 0,
    }


if __name__ == "__main__":
    init_schema()
    print("schema initialized OK")
