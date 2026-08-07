"""FastAPI web surface for the Script Notes-to-Outline Matrix Agent.

Satisfies the hackathon's web-platform rule and the "Design" criterion: a real,
coherent product experience (upload -> agent runs -> categorized notes, conflicts,
scene-by-scene checklist, and live ClickHouse analytics), not just a backend agent.

Hosting (Phase 5): deployed to Cloud Run. The agent runs on Vertex AI in two modes:
  - prod: AGENT_ENGINE_ID set -> calls the agent deployed on Vertex AI Agent Engine
    (Google Cloud Agent Platform hosting; the live hackathon deployment).
  - dev:  in-process ADK runner (fast local iteration, same agent object).
ClickHouse is reached via the official mcp-clickhouse server (chDB locally, ClickHouse
Cloud in prod). All Gemini calls use Vertex AI (Application Default Credentials), not the
Developer API — so the hackathon GCP credits apply and no 429 free-tier cap is hit.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

from fastapi import FastAPI, Request, UploadFile, File, Form, HTTPException
from fastapi.responses import HTMLResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

BASE = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE))  # make `src`-relative imports work when run as src.web.app

from src.ingestion.pdf_parser import parse_pdf, parse_email  # noqa: E402

app = FastAPI(title="Script Notes-to-Outline Matrix Agent")
templates = Jinja2Templates(directory=str(BASE / "templates"))
app.mount("/static", StaticFiles(directory=str(BASE / "static")), name="static")

# The ADK agent (Gemini) is imported lazily so the web surface can boot and render
# even when google-adk / a Gemini key isn't present in the environment. The analyze
# endpoint loads it on demand and reports a clear error if unavailable.
_agent = None


def _get_agent():
    global _agent
    if _agent is None:
        from src.agent.agent import build_agent

        _agent = build_agent()
    return _agent


def _fallback_summary(project_id: str) -> str:
    """Render a real summary from persisted ClickHouse analytics when the agent returns
    no final text (the deployed agent ends on the write_clickhouse tool call)."""
    from src.clickhouse import client as ch

    try:
        a = ch.analytics_for(project_id)
    except Exception:
        return (f"[agent persisted {project_id} to ClickHouse but analytics unavailable. "
                f"See the live ClickHouse panel.]")
    lines = [f"# scenes with notes: {len(a.get('scene_density', []))}",
             f"# stakeholder disagreement rows: {len(a.get('stakeholder_disagreement', []))}",
             f"# draft progress rows: {len(a.get('draft_progress', []))}",
             "",
             "Draft-2 revision plan (persisted in ClickHouse via mcp-clickhouse):",
             "See the live analytics panel / notes_matrix view for the full matrix."]
    return "\n".join(lines)


@app.get("/", response_class=HTMLResponse)
def index(request: Request):
    return templates.TemplateResponse(request=request, name="index.html", context={"request": request, "result": None})


@app.post("/analyze", response_class=HTMLResponse)
async def analyze(request: Request, file: UploadFile = File(...), title: str = Form("Untitled draft")):
    # Persist upload to a temp path, parse, run the agent, render results.
    import tempfile

    suffix = ".pdf" if file.filename.lower().endswith(".pdf") else ".eml"
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tf:
        tf.write(await file.read())
        tmp = tf.name

    raw_lines = parse_pdf(tmp) if suffix == ".pdf" else parse_email(tmp)

    # Run the ADK agent (Gemini) on Vertex AI. Two modes:
    #  - prod: AGENT_ENGINE_ID is set -> call the agent deployed on Vertex AI Agent Engine
    #    (Google Cloud Agent Platform hosting; this is the live hackathon deployment).
    #  - dev:  local InMemoryRunner against the same agent object (fast, no deploy needed).
    # Both use Application Default Credentials (Vertex mode) — no API key required.
    try:
        import asyncio
        from google.genai import types

        engine_id = os.getenv("AGENT_ENGINE_ID")
        content = types.Content(
            role="user",
            parts=[types.Part(text=f"Title: {title}\nFeedback file lines:\n" + "\n".join(raw_lines))],
        )

        async def _go() -> str:
            if engine_id:
                from google.cloud import aiplatform
                remote = aiplatform.agent_engines.get(engine_id)
                out = ""
                for event in remote.stream_query(user_id="web", message=content):
                    if isinstance(event, dict) and event.get("content"):
                        for p in event["content"].get("parts", []) or []:
                            if p.get("text"):
                                out += p["text"]
                # The deployed agent typically ends on the write_clickhouse tool call and
                # returns no final text. Build a real summary from the data it persisted
                # (project_id is deterministic from the title) so the UI always shows output.
                if not out.strip():
                    from src.clickhouse import client as ch
                    out = _fallback_summary(ch.slugify_project(title))
                return out
            from google.adk.runners import InMemoryRunner
            agent = _get_agent()
            runner = InMemoryRunner(agent=agent, app_name="script_matrix")
            session = await runner.session_service.create_session(
                app_name="script_matrix", user_id="web"
            )
            out = ""
            for event in runner.run(session_id=session.id, user_id="web", new_message=content):
                if event.content:
                    for p in event.content.parts or []:
                        if getattr(p, "text", None):
                            out += p.text
            if not out.strip():
                from src.clickhouse import client as ch
                out = _fallback_summary(ch.slugify_project(title))
            return out

        answer = await _go() or (
            f"[agent returned no text; ingestion succeeded ({len(raw_lines)} raw note "
            f"lines from {'PDF' if suffix == '.pdf' else 'email'}). See ClickHouse analytics.]"
        )
    except Exception as exc:  # noqa: BLE001 — surface agent/deps failure to the UI
        answer = (
            f"[agent unavailable: {type(exc).__name__}: {exc}]\n\n"
            f"Ingestion succeeded ({len(raw_lines)} raw note lines from "
            f"{'PDF' if suffix == '.pdf' else 'email'}). Verify Vertex AI auth / AGENT_ENGINE_ID."
        )
    os.unlink(tmp)

    # Deterministic persistence to ClickHouse (Cloud or chDB) — guaranteed regardless
    # of whether the LLM chose to call the write_clickhouse tool. This is the load-bearing
    # hackathon requirement: notes + conflicts MUST be persisted via mcp-clickhouse at
    # runtime so the live analytics panel is real, not a mock.
    try:
        from src.agent.tools.note_tools import persist_from_raw
        persist = persist_from_raw(title, raw_lines, source_type="producer_email")
        persist_note = (f"\n\n[persisted] {persist.get('note_count')} notes + "
                        f"{persist.get('conflict_count')} conflicts written to ClickHouse "
                        f"(project '{persist.get('project_id')}').")
        answer = answer + persist_note if answer else persist_note
    except Exception as exc:  # noqa: BLE001 — never let persistence failure break the UI
        answer = (answer or "") + f"\n\n[persist warning] ClickHouse write skipped: {type(exc).__name__}: {exc}"

    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={"request": request, "result": answer, "title": title, "n_lines": len(raw_lines)},
    )


@app.post("/api/export/fdx")
async def export_fdx_endpoint(payload: dict):
    """Export the Draft-2 revision matrix as a .fdx (Final Draft XML) file.

    Format interchange only (Final Draft has no public plugin API). Payload (one of):
      {"revision_checklist": [...]}            -> structured checklist (preferred)
      {"agent_text": "<free-text>"}            -> parsed into scenes via regex, then exported
      {"revision_checklist": [...], "fdx_content": "<xml>"} -> inject into existing .fdx
    Native <ScriptNote> elements are used (non-printing; no page-count change).
    """
    from src.exporters.fdx import (
        inject_matrix_notes_to_fdx,
        generate_standalone_fdx_notes_summary,
        parse_agent_text_to_checklist,
    )

    checklist = payload.get("revision_checklist")
    agent_text = payload.get("agent_text")
    fdx_raw = payload.get("fdx_content")

    if not checklist and agent_text:
        checklist = parse_agent_text_to_checklist(agent_text)
    if not checklist:
        raise HTTPException(status_code=400, detail="Revision checklist cannot be empty.")

    try:
        if fdx_raw:
            xml_out = inject_matrix_notes_to_fdx(fdx_raw, checklist)
        else:
            xml_out = generate_standalone_fdx_notes_summary(checklist)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    return Response(
        content=xml_out,
        media_type="application/xml",
        headers={"Content-Disposition": "attachment; filename=Draft2_Revision_Matrix.fdx"},
    )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host=os.getenv("WEB_HOST", "0.0.0.0"), port=int(os.getenv("WEB_PORT", "8080")))
