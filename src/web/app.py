"""FastAPI JSON API surface for the Script Notes-to-Outline Matrix Agent.

This is the BACKEND half of the Vercel-frontend / GCP-backend split.  All
server-rendered HTML routes from the original monolith have been removed;
what remains is a pure JSON REST API consumed by the Next.js frontend on
Vercel.  The agent, ClickHouse persistence, and Google OAuth gate are
unchanged — only the response shape changed from Jinja2 templates to JSON.

Backwards-compatibility note
----------------------------
The original HTML routes (/ , /project/{id} , /login , /auth/google/callback ,
/logout) are GONE in this file.  If you still need the in-place Cloud Run HTML
app (e.g. for a quick demo without the frontend), deploy the pre-split
app.py from git history instead.

CORS
----
The frontend on *.vercel.app and the backend on *.run.app are different
origins.  CORS middleware is configured to allow the frontend origin (from
FRONTEND_URL env var) and to expose the Authorization header so the JWT can
be sent as a Bearer token.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Request, UploadFile, File, Form, HTTPException, Depends
from fastapi.responses import JSONResponse, Response, RedirectResponse
from fastapi.middleware.cors import CORSMiddleware

# ---------------------------------------------------------------------------
# Ensure src-relative imports work (same trick as the original app.py)
# ---------------------------------------------------------------------------
BASE = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE))

from src.ingestion.pdf_parser import parse_pdf, parse_email  # noqa: E402

# Login gate helpers — Google OAuth client + JWT layer.
from src.web import auth as webauth  # noqa: E402

app = FastAPI(title="Script Notes-to-Outline Matrix Agent API")


@app.middleware("http")
async def https_scheme(request: Request, call_next):
    """Force https scheme for OAuth — Cloud Run terminates TLS and forwards as http."""
    if request.headers.get("x-forwarded-proto") == "https":
        request.scope["scheme"] = "https"
    response = await call_next(request)
    return response

# ---------------------------------------------------------------------------
# CORS — frontend on Vercel (*.vercel.app), backend on Cloud Run (*.run.app)
# ---------------------------------------------------------------------------
_FRONTEND_URL = os.getenv("FRONTEND_URL", "").rstrip("/")
if _FRONTEND_URL:
    _ALLOWED_ORIGINS = [_FRONTEND_URL]
else:
    _ALLOWED_ORIGINS = ["*"]  # fallback for local dev without FRONTEND_URL set

app.add_middleware(
    CORSMiddleware,
    allow_origins=_ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
    expose_headers=["Set-Cookie"],
)


# ---------------------------------------------------------------------------
# Authlib SessionMiddleware — required for the OAuth state machine.
# Same as the original app.py; the secret comes from SESSION_SECRET or the
# Google OAuth client secret, with a dev fallback when neither is set.
# ---------------------------------------------------------------------------
from starlette.middleware.sessions import SessionMiddleware  # noqa: E402

app.add_middleware(
    SessionMiddleware,
    secret_key=(
        os.getenv("SESSION_SECRET")
        or os.getenv("GOOGLE_OAUTH_CLIENT_SECRET")
        or "dev-insecure-session-secret"
    ),
)


# ---------------------------------------------------------------------------
# Lazy agent — same as the original app.py
# ---------------------------------------------------------------------------
_agent = None


def _get_agent():
    global _agent
    if _agent is None:
        from src.agent.agent import build_agent

        _agent = build_agent()
    return _agent


# ---------------------------------------------------------------------------
# Helpers — shared with the original app.py, unchanged
# ---------------------------------------------------------------------------

def _get_projects() -> list[dict]:
    """Retrieve list of previously processed projects from ClickHouse."""
    from src.clickhouse import client as ch

    try:
        ch.init_schema()
        rows = ch.run_query(
            "SELECT project_id, count(note_id) as total_notes, max(created_at) as last_updated "
            "FROM script_notes_matrix.notes_raw "
            "GROUP BY project_id "
            "ORDER BY last_updated DESC"
        )
        out = []
        for r in rows:
            if isinstance(r, dict):
                out.append({k: str(v) if isinstance(v, str) else v for k, v in r.items()})
            else:
                d = dict(r)
                out.append({k: str(v) if isinstance(v, str) else v for k, v in d.items()})
        return out
    except Exception as exc:
        print(f"Failed to fetch projects: {exc}")
        return []


def _fallback_summary(project_id: str) -> str:
    """Render a real summary from persisted ClickHouse analytics when the agent returns no final text."""
    from src.clickhouse import client as ch

    try:
        a = ch.analytics_for(project_id)
    except Exception:
        return (
            f"[agent persisted {project_id} to ClickHouse but analytics unavailable. "
            f"See the live ClickHouse panel.]"
        )
    lines = [
        f"# scenes with notes: {len(a.get('scene_density', []))}",
        f"# stakeholder disagreement rows: {len(a.get('stakeholder_disagreement', []))}",
        f"# draft progress rows: {len(a.get('draft_progress', []))}",
        "",
        "Draft-2 revision plan (persisted in ClickHouse via mcp-clickhouse):",
        "See the live analytics panel / notes_matrix view for the full matrix.",
    ]
    return "\n".join(lines)


def _slugify_project(title: str) -> str:
    from src.clickhouse import client as ch

    return ch.slugify_project(title)


def _query_project(project_id: str, draft_version: int = 1) -> dict:
    """Fetch notes, conflicts, analytics, and checklist for one project."""
    from src.clickhouse import client as ch
    from src.analytics import queries
    from src.agent.tools.note_tools import build_checklist

    esc = project_id.replace("'", "''")
    try:
        notes = ch.run_query(
            f"SELECT * FROM script_notes_matrix.notes_raw "
            f"WHERE project_id = '{esc}' AND draft_version = {int(draft_version)} "
            f"ORDER BY scene_number, severity DESC"
        )
        conflicts = ch.run_query(
            f"SELECT * FROM script_notes_matrix.notes_conflicts "
            f"WHERE project_id = '{esc}' AND draft_version = {int(draft_version)} "
            f"ORDER BY scene_number"
        )
        analytics = queries.project_analytics(project_id, draft_version)
    except Exception as exc:
        print(f"Error querying project {project_id}: {exc}")
        notes, conflicts, analytics = [], [], {}

    checklist = build_checklist(notes, conflicts)
    return {
        "notes": notes,
        "conflicts": conflicts,
        "analytics": analytics,
        "checklist": checklist,
    }


# ---------------------------------------------------------------------------
# Health (public — no auth)
# ---------------------------------------------------------------------------

@app.get("/api/health")
async def health() -> dict:
    """Return service health: ClickHouse + Agent Engine connectivity."""
    clickhouse_status = "unknown"
    agent_status = "unknown"
    try:
        from src.clickhouse import client as ch

        ch.init_schema()
        clickhouse_status = "connected"
    except Exception as exc:
        clickhouse_status = f"error: {exc}"

    try:
        _get_agent()
        agent_status = "connected"
    except Exception as exc:
        agent_status = f"error: {exc}"

    return {
        "status": "ok" if clickhouse_status == "connected" and agent_status == "connected" else "degraded",
        "clickhouse": clickhouse_status,
        "agent_engine": agent_status,
    }


# ---------------------------------------------------------------------------
# Auth endpoints
# ---------------------------------------------------------------------------

@app.get("/api/auth/google/login")
async def auth_google_login(request: Request):
    """Start the Google OAuth 2.0 Authorization Code flow."""
    if not webauth._auth_enabled():
        return JSONResponse(
            status_code=403,
            content={"detail": "Google OAuth is not configured (missing client ID/secret)."},
        )
    # Use explicit redirect URI from env, or construct from host header
    explicit_redirect = os.getenv("OAUTH_REDIRECT_URI")
    if explicit_redirect:
        redirect_uri_full = explicit_redirect
    else:
        host = request.headers.get("host", "").split(":")[0]
        # Force https — Cloud Run terminates TLS and forwards as http internally
        redirect_uri_full = f"https://{host}/api/auth/google/callback"
    return await webauth.google_oauth_client().google.authorize_redirect(request, redirect_uri_full)


@app.get("/api/auth/google/callback")
async def auth_google_callback(request: Request):
    """OAuth callback: verify Google ID token, check whitelist, issue JWT.

    On success: issue a JWT and redirect to the frontend callback page with
    ?token=<jwt> in the URL so the frontend can capture it.

    On failure: redirect to the frontend login page with an error message.
    """
    import logging
    logger = logging.getLogger(__name__)
    logger.info(f"OAuth callback called. Query params: {dict(request.query_params)}")
    logger.info(f"Session cookie present: {'session' in request.cookies}")
    logger.info(f"Headers: {dict(request.headers)}")

    if not webauth._auth_enabled():
        return RedirectResponse(
            url=f"{os.getenv('FRONTEND_URL', '/dummy').rstrip('/')}/login?error=oauth_disabled",
            status_code=303,
        )

    token = await webauth.google_oauth_client().google.authorize_access_token(request)
    idt = token.get("id_token")
    if not idt:
        err = "No ID token returned from Google."
        logger.error(f"OAuth callback error: {err}")
        return RedirectResponse(
            url=f"{os.getenv('FRONTEND_URL', '/dummy').rstrip('/')}/login?error={err}",
            status_code=303,
        )

    from google.oauth2 import id_token
    from google.auth.transport.requests import Request as GoogleRequest

    try:
        claim = id_token.verify_oauth2_token(
            idt, GoogleRequest(), os.getenv("GOOGLE_OAUTH_CLIENT_ID")
        )
    except Exception as exc:
        return RedirectResponse(
            url=f"{os.getenv('FRONTEND_URL', '/dummy').rstrip('/')}/login?error=google_signin_failed:{exc}",
            status_code=303,
        )

    email = claim.get("email", "")
    if not email or not claim.get("email_verified", False):
        return RedirectResponse(
            url=f"{os.getenv('FRONTEND_URL', '/dummy').rstrip('/')}/login?error=email_not_verified",
            status_code=303,
        )
    if not webauth._allowed(email):
        return RedirectResponse(
            url=f"{os.getenv('FRONTEND_URL', '/dummy').rstrip('/')}/login?error=not_authorized",
            status_code=303,
        )

    # Issue JWT and redirect to frontend callback.
    try:
        jwt_token = webauth.make_jwt_token(email)
    except RuntimeError as exc:
        return RedirectResponse(
            url=f"{os.getenv('FRONTEND_URL', '/dummy').rstrip('/')}/login?error=jwt_issue_failed:{exc}",
            status_code=303,
        )

    frontend_url = os.getenv("FRONTEND_URL", "").rstrip("/")
    if not frontend_url:
        # No FRONTEND_URL set — can't redirect. Return the token as JSON for local dev.
        return JSONResponse({"token": jwt_token, "email": email})

    callback_path = "/callback"
    full_callback = f"{frontend_url}{callback_path}?token={jwt_token}"
    return RedirectResponse(url=full_callback, status_code=303)


@app.get("/api/auth/logout")
async def auth_logout():
    """Clear the session cookie on the backend (same-origin only).

    For cross-origin logout, the frontend should clear its stored JWT and
    redirect the user to /login.
    """
    resp = RedirectResponse(url="/", status_code=303)
    webauth.clear_session(resp)
    return resp


# ---------------------------------------------------------------------------
# Protected API endpoints (require JWT)
# ---------------------------------------------------------------------------

def _require_auth(request: Request) -> None:
    """FastAPI dependency-like check: 401 if no valid JWT."""
    webauth.require_jwt(request)


@app.post("/api/analyze")
async def analyze(
    request: Request,
    file: UploadFile = File(...),
    title: str = Form("Untitled draft"),
):
    """Upload a PDF/email, run the agent, persist to ClickHouse, return results.

    Auth: JWT required (Bearer token in Authorization header).
    Content-Type: multipart/form-data.
    """
    webauth.require_jwt(request)

    import asyncio
    import tempfile

    suffix = ".pdf" if file.filename.lower().endswith(".pdf") else ".eml"
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tf:
        tf.write(await file.read())
        tmp = tf.name

    raw_lines = parse_pdf(tmp) if suffix == ".pdf" else parse_email(tmp)

    try:
        engine_id = os.getenv("AGENT_ENGINE_ID")

        async def _go() -> str:
            if engine_id:
                from vertexai import agent_engines

                remote = agent_engines.get(engine_id)
                message = f"Title: {title}\nFeedback file lines:\n" + "\n".join(raw_lines)
                out = ""
                for event in remote.stream_query(message=message, user_id="web"):
                    if isinstance(event, dict) and event.get("content"):
                        for p in event["content"].get("parts", []) or []:
                            if p.get("text"):
                                out += p["text"]
                    elif hasattr(event, "text") and event.text:
                        out += event.text
                if not out.strip():
                    from src.clickhouse import client as ch

                    out = _fallback_summary(ch.slugify_project(title))
                return out

            from google.adk.runners import InMemoryRunner
            from google.genai import types

            content = types.Content(
                role="user",
                parts=[
                    types.Part(
                        text=f"Title: {title}\nFeedback file lines:\n" + "\n".join(raw_lines)
                    )
                ],
            )
            agent = _get_agent()
            runner = InMemoryRunner(agent=agent, app_name="script_matrix")
            session = await runner.session_service.create_session(
                app_name="script_matrix", user_id="web"
            )
            out = ""
            async for event in runner.run(
                session_id=session.id, user_id="web", new_message=content
            ):
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

    # Persist to ClickHouse
    project_id = _slugify_project(title)
    try:
        from src.agent.tools.note_tools import persist_from_raw

        persist_from_raw(title, raw_lines, source_type="producer_email")
    except Exception as exc:  # noqa: BLE001
        print(f"ClickHouse write skipped: {exc}")

    # Fetch notes, conflicts, analytics, benchmarks, checklist
    try:
        from src.analytics import queries
        from src.agent.tools.note_tools import build_checklist
        from src.clickhouse import client as ch

        esc = project_id.replace("'", "''")
        notes = ch.run_query(
            f"SELECT * FROM script_notes_matrix.notes_raw "
            f"WHERE project_id = '{esc}' AND draft_version = 1 "
            f"ORDER BY scene_number, severity DESC"
        )
        conflicts = ch.run_query(
            f"SELECT * FROM script_notes_matrix.notes_conflicts "
            f"WHERE project_id = '{esc}' AND draft_version = 1 "
            f"ORDER BY scene_number"
        )
        analytics = queries.project_analytics(project_id, 1)
        benchmarks = queries.cross_project_benchmarks()
        checklist = build_checklist(notes, conflicts)
    except Exception as exc:  # noqa: BLE001
        print(f"Error querying analyzed project: {exc}")
        notes, conflicts, analytics, benchmarks, checklist = [], [], {}, {}, []

    return JSONResponse(
        content={
            "project_id": project_id,
            "title": title,
            "result": answer,
            "notes": notes,
            "conflicts": conflicts,
            "analytics": analytics,
            "benchmarks": benchmarks,
            "checklist": checklist,
            "n_lines": len(raw_lines),
            "projects": _get_projects(),
        }
    )


@app.get("/api/projects")
async def list_projects(request: Request):
    """List all previously processed projects from ClickHouse.

    Auth: JWT required.
    """
    webauth.require_jwt(request)
    return JSONResponse(content=_get_projects())


@app.get("/api/project/{project_id}")
async def view_project(
    request: Request,
    project_id: str,
    draft_version: int = 1,
):
    """Get full project detail: notes, conflicts, analytics, checklist.

    Auth: JWT required.
    Query: ?draft_version=N (default 1).
    """
    webauth.require_jwt(request)
    data = _query_project(project_id, draft_version)
    data["title"] = project_id.replace("-", " ").title()
    data["project_id"] = project_id
    data["draft_version"] = draft_version
    return JSONResponse(content=data)


@app.post("/api/export/fdx")
async def export_fdx_endpoint(request: Request, payload: dict):
    """Export the Draft-2 revision matrix as a .fdx (Final Draft XML) file.

    Auth: JWT required.
    Body: { revision_checklist, agent_text?, fdx_content? }
    Returns: binary XML with Content-Disposition: attachment.
    """
    webauth.require_jwt(request)

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
        headers={
            "Content-Disposition": "attachment; filename=Draft2_Revision_Matrix.fdx"
        },
    )


# ---------------------------------------------------------------------------
# Dev entry point (same as original)
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        app,
        host=os.getenv("WEB_HOST", "0.0.0.0"),
        port=int(os.getenv("WEB_PORT", "8080")),
    )
