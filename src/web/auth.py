"""Google OAuth 2.0 login gate + JWT token layer for the Agentic Cinema web app (board task t_5e9f2ba8).

Supports TWO auth modes depending on deployment:

  SAME-ORIGIN (Cloud Run alone, pre-split):
    The existing signed http-only session cookie (_COOKIE_NAME) is set on the
    Cloud Run domain and FastAPI's SessionMiddleware carries the OAuth state.
    require_auth() redirects to /login when the cookie is absent/invalid.

  CROSS-ORIGIN (Vercel frontend + Cloud Run backend, post-split):
    Google OAuth still starts and finishes on the Cloud Run backend, but after
    the callback verifies the ID token we additionally emit a short-lived JWT
    (HS256, 1h) and redirect the browser to the Vercel frontend's callback page
    with ?token=<jwt> in the URL. The frontend stores the JWT and sends it as
    Authorization: Bearer on every API call. Protected endpoints use
    require_jwt() (a FastAPI dependency) instead of require_auth() — they return
    401 JSON, not a 307 redirect.

Both modes can coexist: same-origin callers still get the cookie; cross-origin
callers use the JWT. require_auth() is for the HTML-era routes (kept for any
in-place Cloud Run use); require_jwt() is for the new /api/* JSON routes.
"""
from __future__ import annotations

import hashlib
import hmac
import os
import secrets
import time
from functools import wraps
from typing import Callable

import jwt as pyjwt
from fastapi import Request, HTTPException, status
from starlette.responses import Response  # noqa: F401 (re-exported for app.py)

from authlib.integrations.starlette_client import OAuth  # OAuth client

_COOKIE_NAME = "ac_session"
_MAX_AGE = 60 * 60 * 12  # 12h session cookie
_CLOCK_SKEW = 60

# --- JWT constants (cross-origin auth for Vercel frontend) ---
JWT_ISSUER = "agentic-cinema"
JWT_AUDIENCE = "agentic-cinema-frontend"
JWT_LIFETIME_SEC = 60 * 60  # 1 hour

# Google OAuth 2.0 identity provider.
_oauth = OAuth()
_oauth.register(
    name="google",
    server_metadata_url="https://accounts.google.com/.well-known/openid-configuration",
    client_id=os.getenv("GOOGLE_OAUTH_CLIENT_ID", ""),
    client_secret=os.getenv("GOOGLE_OAUTH_CLIENT_SECRET", ""),
    client_kwargs={"scope": "openid email profile"},
    redirect_uri=os.getenv("OAUTH_REDIRECT_URI", ""),
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
        samesite="none",
        secure=True,
        path="/",
    )


def clear_session(response: Response) -> None:
    response.delete_cookie(_COOKIE_NAME, path="/")


def get_user(request: Request) -> str | None:
    """Return the signed-in user's email from the session cookie, or None."""
    if not _auth_enabled():
        return "local-dev"  # auth disabled -> treated as a benign pseudo-user
    return _verify_token(request.cookies.get(_COOKIE_NAME))


def is_authenticated(request: Request) -> bool:
    return get_user(request) is not None


def require_auth(request: Request) -> None:
    """FastAPI dependency: redirect to /login when not authenticated (same-origin)."""
    if not is_authenticated(request):
        raise HTTPException(
            status_code=307,
            detail="Not authenticated",
            headers={"Location": "/login"},
        )


# --- JWT helpers (cross-origin auth for Vercel frontend) ---

def _jwt_secret() -> str:
    """JWT signing secret. Must be a non-empty string at runtime when auth is enabled."""
    return os.getenv("JWT_SECRET", "") or os.getenv("GOOGLE_OAUTH_CLIENT_SECRET", "")


def make_jwt_token(email: str, extra_claims: dict | None = None) -> str:
    """Issue a short-lived HS256 JWT for the given email.

    The token is meant to be sent to the Vercel frontend (via ?token= in a redirect
    URL) and then used as Authorization: Bearer on API calls. 1-hour lifetime.
    """
    now = int(time.time())
    payload = {
        "iss": JWT_ISSUER,
        "aud": JWT_AUDIENCE,
        "sub": email,
        "email": email,
        "iat": now,
        "exp": now + JWT_LIFETIME_SEC,
        "jti": secrets.token_hex(8),
    }
    if extra_claims:
        payload.update(extra_claims)
    secret = _jwt_secret()
    if not secret:
        raise RuntimeError(
            "JWT_SECRET (or GOOGLE_OAUTH_CLIENT_SECRET) not configured — cannot sign JWT"
        )
    return pyjwt.encode(payload, secret, algorithm="HS256")


def verify_jwt_token(token: str) -> dict | None:
    """Validate a JWT and return its payload, or None if invalid/expired."""
    secret = _jwt_secret()
    if not secret or not token:
        return None
    try:
        payload = pyjwt.decode(
            token,
            secret,
            algorithms=["HS256"],
            issuer=JWT_ISSUER,
            audience=JWT_AUDIENCE,
            options={"require": ["iss", "aud", "sub", "exp", "iat"]},
        )
    except pyjwt.PyJWTError:
        return None
    return payload


def get_jwt_email(request: Request) -> str | None:
    """Extract and verify the JWT from the Authorization: Bearer header."""
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        return None
    token = auth_header[7:]
    payload = verify_jwt_token(token)
    if payload is None:
        return None
    return payload.get("email") or payload.get("sub")


def require_jwt(request: Request) -> None:
    """FastAPI dependency for JSON API routes: return 401 if no valid JWT."""
    if get_jwt_email(request) is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated. Sign in with Google first.",
        )


def jwt_protected(func: Callable) -> Callable:
    """Wrap a path-operation function so it requires a valid JWT (401 on failure)."""
    @wraps(func)
    async def wrapper(request: Request, *args, **kwargs):
        require_jwt(request)
        return await func(request, *args, **kwargs)

    return wrapper


def google_oauth_client():
    """Expose the configured authlib OAuth client (for app.py route handlers)."""
    return _oauth
