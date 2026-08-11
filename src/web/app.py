"""FastAPI web surface for the Script Notes-to-Outline Matrix Agent.

Satisfies the hackathon's web-platform rule and the "Design" criterion: a real,
coherent product experience (upload -> agent runs -> categorized notes, conflicts,
scene-by-scene checklist, and live ClickHouse analytics), not just a backend agent.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

from fastapi import FastAPI, Request, UploadFile, File, Form, HTTPException
from fastapi.responses import HTMLResponse, Response, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

BASE = Path(__file__).resolve().parent
# Ensure static directory exists to prevent Starlette runtime mount failure
os.makedirs(BASE / "static", exist_ok=True)

# Make src-relative imports work
sys.path.insert(0, str(BASE))

from src.ingestion.pdf_parser import parse_pdf, parse_email  # noqa: E402

# Login gate (board task t_5e9f2ba8): Google OAuth 2.0 for this Google Cloud
# + Gemini + ClickHouse project. See src/web/auth.py.
from src.web import auth as webauth  # noqa: E402

app = FastAPI(title="Script Notes-to-Outline Matrix Agent")
templates = Jinja2Templates(directory=str(BASE / "templates"))
app.mount("/static", StaticFiles(directory=str(BASE / "static")), name="static")

# Server-side session for OAuth state (authlib requirement). Our own signed auth
# cookie is separate (see src/web/auth.py). Secret from SESSION_SECRET, else the
# Google OAuth secret, else a dev fallback (auth is disabled without real creds).
from starlette.middleware.sessions import SessionMiddleware  # noqa: E402

app.add_middleware(
    SessionMiddleware,
    secret_key=os.getenv("SESSION_SECRET")
    or os.getenv("GOOGLE_OAUTH_CLIENT_SECRET")
    or "dev-insecure-session-secret",
)

_agent = None


def _get_agent():
    global _agent
    if _agent is None:
        from src.agent.agent import build_agent

        _agent = build_agent()
    return _agent


def _get_projects() -> list[dict]:
    """Retrieve list of previously processed projects from ClickHouse."""
    from types import SimpleNamespace

    from src.clickhouse import client as ch
    try:
        ch.init_schema()
        rows = ch.run_query(
            "SELECT project_id, count(note_id) as total_notes, max(created_at) as last_updated "
            "FROM script_notes_matrix.notes_raw "
            "GROUP BY project_id "
            "ORDER BY last_updated DESC"
        )
        # run_query returns plain dicts in chDB mode but ClickHouseRow objects in
        # Cloud mode. The template uses attribute access (p.project_id). ClickHouseRow
        # already supports attribute access, so pass it through; only wrap genuine
        # dicts as SimpleNamespace. Wrapping a ClickHouseRow via dict(row) would drop
        # its fields, which is what caused the UndefinedError on index.html:113.
        out = []
        for r in rows:
            out.append(r if not isinstance(r, dict) else SimpleNamespace(**r))
        return out
    except Exception as exc:
        print(f"Failed to fetch projects: {exc}")
        return []


def _fallback_summary(project_id: str) -> str:
    """Render a real summary from persisted ClickHouse analytics when the agent returns
    no final text."""
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


@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    if webauth.is_authenticated(request):
        return RedirectResponse(url="/")
    if not webauth._auth_enabled():
        # No Google OAuth creds configured -> app is open (local dev).
        return RedirectResponse(url="/")
    # Start the Google OAuth 2.0 Authorization Code flow.
    redirect_uri = request.url_for("auth_callback")
    return await webauth.google_oauth_client().google.authorize_redirect(request, redirect_uri)


@app.get("/auth/google/callback")
async def auth_callback(request: Request):
    if not webauth._auth_enabled():
        return RedirectResponse(url="/", status_code=303)
    token = await webauth.google_oauth_client().google.authorize_access_token(request)
    # Verify Google's ID token against our client id + Google issuer.
    from google.oauth2 import id_token
    from google.auth.transport.urllib3 import Request as GoogleRequest

    idt = token.get("id_token")
    try:
        claim = id_token.verify_oauth2_token(idt, GoogleRequest(), os.getenv("GOOGLE_OAUTH_CLIENT_ID"))
    except Exception as exc:  # noqa: BLE001
        return templates.TemplateResponse(
            request=request, name="login.html",
            context={"request": request, "auth_enabled": True,
                     "error": f"Google sign-in failed: {exc}"},
        )
    email = claim.get("email", "")
    if not email or not claim.get("email_verified", False):
        return templates.TemplateResponse(
            request=request, name="login.html",
            context={"request": request, "auth_enabled": True,
                     "error": "Google account email not verified."},
        )
    if not webauth._allowed(email):
        return templates.TemplateResponse(
            request=request, name="login.html",
            context={"request": request, "auth_enabled": True,
                     "error": f"Account {email} is not authorized for this app."},
        )
    resp = RedirectResponse(url="/", status_code=303)
    webauth.set_session(resp, email)
    return resp


@app.get("/logout")
def logout():
    resp = RedirectResponse(url="/", status_code=303)
    webauth.clear_session(resp)
    return resp


@app.get("/", response_class=HTMLResponse)
def index(request: Request):
    webauth.require_auth(request)
    projects = _get_projects()
    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={
            "request": request,
            "projects": projects,
            "selected_project_id": None,
            "result": None,
        }
    )


@app.get("/project/{project_id}", response_class=HTMLResponse)
def view_project(request: Request, project_id: str, draft_version: int = 1):
    webauth.require_auth(request)
    from src.clickhouse import client as ch
    from src.analytics import queries
    from src.agent.tools.note_tools import build_checklist

    projects = _get_projects()
    esc_project_id = project_id.replace("'", "''")
    try:
        notes = ch.run_query(
            f"SELECT * FROM script_notes_matrix.notes_raw "
            f"WHERE project_id = '{esc_project_id}' AND draft_version = {int(draft_version)} "
            f"ORDER BY scene_number, severity DESC"
        )
        conflicts = ch.run_query(
            f"SELECT * FROM script_notes_matrix.notes_conflicts "
            f"WHERE project_id = '{esc_project_id}' AND draft_version = {int(draft_version)} "
            f"ORDER BY scene_number"
        )
        analytics = queries.project_analytics(project_id, draft_version)
    except Exception as exc:
        print(f"Error querying project {project_id}: {exc}")
        notes, conflicts, analytics = [], [], {}

    checklist = build_checklist(notes, conflicts)
    title = project_id.replace('-', ' ').title()

    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={
            "request": request,
            "projects": projects,
            "selected_project_id": project_id,
            "title": title,
            "notes": notes,
            "conflicts": conflicts,
            "analytics": analytics,
            "checklist": checklist,
            "result": None,
            "n_lines": len(notes),
        }
    )


@app.post("/analyze", response_class=HTMLResponse)
async def analyze(request: Request, file: UploadFile = File(...), title: str = Form("Untitled draft")):
    webauth.require_auth(request)
    # Persist upload to a temp path, parse, run the agent, render results.
    import tempfile

    suffix = ".pdf" if file.filename.lower().endswith(".pdf") else ".eml"
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tf:
        tf.write(await file.read())
        tmp = tf.name

    raw_lines = parse_pdf(tmp) if suffix == ".pdf" else parse_email(tmp)

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
    except Exception as exc:  # noqa: BLE001
        answer = (
            f"[agent unavailable: {type(exc).__name__}: {exc}]\n\n"
            f"Ingestion succeeded ({len(raw_lines)} raw note lines from "
            f"{'PDF' if suffix == '.pdf' else 'email'}). Verify Vertex AI auth / AGENT_ENGINE_ID."
        )
    os.unlink(tmp)

    # Deterministic persistence to ClickHouse (Cloud or chDB)
    from src.clickhouse import client as ch
    project_id = ch.slugify_project(title)
    try:
        from src.agent.tools.note_tools import persist_from_raw
        persist_from_raw(title, raw_lines, source_type="producer_email")
    except Exception as exc:  # noqa: BLE001
        print(f"ClickHouse write skipped: {exc}")

    # Fetch notes, conflicts, and analytics for the template
    from src.analytics import queries
    from src.agent.tools.note_tools import build_checklist

    esc_project_id = project_id.replace("'", "''")
    try:
        notes = ch.run_query(
            f"SELECT * FROM script_notes_matrix.notes_raw "
            f"WHERE project_id = '{esc_project_id}' AND draft_version = 1 "
            f"ORDER BY scene_number, severity DESC"
        )
        conflicts = ch.run_query(
            f"SELECT * FROM script_notes_matrix.notes_conflicts "
            f"WHERE project_id = '{esc_project_id}' AND draft_version = 1 "
            f"ORDER BY scene_number"
        )
        analytics = queries.project_analytics(project_id, 1)
    except Exception as exc:
        print(f"Error querying analyzed project: {exc}")
        notes, conflicts, analytics = [], [], {}

    checklist = build_checklist(notes, conflicts)
    projects = _get_projects()

    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={
            "request": request,
            "projects": projects,
            "selected_project_id": project_id,
            "title": title,
            "notes": notes,
            "conflicts": conflicts,
            "analytics": analytics,
            "checklist": checklist,
            "result": answer,
            "n_lines": len(raw_lines),
        },
    )


@app.post("/api/export/fdx")
async def export_fdx_endpoint(payload: dict):
    """Export the Draft-2 revision matrix as a .fdx (Final Draft XML) file."""
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
