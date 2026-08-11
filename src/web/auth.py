"""Google OAuth 2.0 login gate for the Agentic Cinema web app (board task t_5e9f2ba8).

Standard Google Identity sign-in for this Google Cloud + Gemini + ClickHouse
screenwriting agent, built on the existing server-rendered Jinja / FastAPI stack.

Auth model:
  - Google OAuth 2.0 Authorization Code flow (server-side, no implicit/client-only).
  - On callback we verify Google's ID token with google.oauth2.id_token (against
    our GOOGLE_OAUTH_CLIENT_ID and the accounts.google.com issuer) and read the
    user's email; we set a signed, http-only session cookie. /logout clears it.
  - require_auth() is a FastAPI dependency that 302-redirects unauthenticated
    requests to /login.
  - If GOOGLE_OAUTH_CLIENT_ID / GOOGLE_OAUTH_CLIENT_SECRET are unset, auth is
    DISABLED (the app is open) so local dev / demos without credentials work.
  - Optional allow-list: if GOOGLE_ALLOWED_EMAILS is set (comma-separated), only
    those Google accounts may sign in (everyone else is rejected after OAuth).
"""
from __future__ import annotations

import hashlib
import hmac
import os
import secrets
import time

from fastapi import Request, HTTPException
from starlette.responses import Response  # noqa: F401 (re-exported for app.py)

from authlib.integrations.starlette_client import OAuth  # OAuth client

_COOKIE_NAME = "ac_session"
_MAX_AGE = 60 * 60 * 12  # 12h
_CLOCK_SKEW = 60

# Google OAuth 2.0 identity provider.
_oauth = OAuth()
_oauth.register(
    name="google",
    server_metadata_url="https://accounts.google.com/.well-known/openid-configuration",
    client_id=os.getenv("GOOGLE_OAUTH_CLIENT_ID", ""),
    client_secret=os.getenv("GOOGLE_OAUTH_CLIENT_SECRET", ""),
    client_kwargs={"scope": "openid email profile"},
)


def _secret() -> bytes:
    """Stable signing secret for the session cookie (never random-per-process)."""
    raw = os.getenv("APP_SECRET") or os.getenv("GOOGLE_OAUTH_CLIENT_SECRET") or "dev-insecure-secret"
    return hashlib.sha256(raw.encode()).digest()


def _auth_enabled() -> bool:
    return bool(os.getenv("GOOGLE_OAUTH_CLIENT_ID") and os.getenv("GOOGLE_OAUTH_CLIENT_SECRET"))


def _allowed(email: str) -> bool:
    allow = os.getenv("GOOGLE_ALLOWED_EMAILS")
    if not allow:
        return True
    return email.lower() in {e.strip().lower() for e in allow.split(",") if e.strip()}


def _make_token(email: str) -> str:
    payload = f"{int(time.time())}.{secrets.token_urlsafe(16)}"
    sig = hmac.new(_secret(), payload.encode(), hashlib.sha256).hexdigest()
    # embed email so the cookie is self-describing (not trusted for authz, only for UX).
    # Use '~' as the segment delimiter (email addresses contain '.', so '.' would
    # make the dot count variable and break parsing).
    return f"{payload}~{sig}~{email}"


def _verify_token(token: str | None) -> str | None:
    """Return the email if the token is valid, else None."""
    if not token or token.count("~") != 2:
        return None
    payload, sig, email = token.split("~")
    expected = hmac.new(_secret(), payload.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, sig):
        return None
    try:
        issued = int(payload.split(".", 1)[0])
    except ValueError:
        return None
    delta = int(time.time()) - issued
    if not (-_CLOCK_SKEW <= delta <= (_MAX_AGE + _CLOCK_SKEW)):
        return None
    return email


def set_session(response: Response, email: str) -> None:
    response.set_cookie(
        _COOKIE_NAME,
        _make_token(email),
        max_age=_MAX_AGE,
        httponly=True,
        samesite="lax",
        path="/",
    )


def clear_session(response: Response) -> None:
    response.delete_cookie(_COOKIE_NAME, path="/")


def get_user(request: Request) -> str | None:
    """Return the signed-in user's email, or None."""
    if not _auth_enabled():
        return "local-dev"  # auth disabled -> treated as a benign pseudo-user
    return _verify_token(request.cookies.get(_COOKIE_NAME))


def is_authenticated(request: Request) -> bool:
    return get_user(request) is not None


def require_auth(request: Request) -> None:
    """FastAPI dependency: redirect to /login when not authenticated."""
    if not is_authenticated(request):
        raise HTTPException(
            status_code=307,
            detail="Not authenticated",
            headers={"Location": "/login"},
        )


def google_oauth_client():
    """Expose the configured authlib OAuth client (for app.py route handlers)."""
    return _oauth
