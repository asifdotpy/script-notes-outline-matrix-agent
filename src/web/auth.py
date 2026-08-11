"""Non-web3 login gate for the Agentic Cinema web app (board task t_5e9f2ba8).

WHY NOT PRIVY: The task title said "Privy", but Privy is a web3 embedded-wallet
auth vendor. This project is explicitly NON-web3 (Google Cloud + Gemini +
ClickHouse screenwriting agent). The task body itself flagged this and said
"Do NOT start until scope confirmed". We implement the standard-login option
(option B): a lightweight, dependency-free session-cookie gate using only the
Python stdlib (hmac-signed cookie). It fits the existing server-rendered Jinja /
FastAPI stack with no React, no wallet, no crypto.

Auth model (intentionally simple for a hackathon demo, not production-grade):
  - A single shared app password, read from APP_PASSWORD (env). If unset, auth is
    DISABLED (the app behaves as before) so local dev / demos without creds work.
  - On POST /login with the correct password we set a signed, http-only,
    root-path session cookie. /logout clears it.
  - require_auth() is a FastAPI dependency that 302-redirects unauthenticated
    requests to /login. It is applied to every protected route.

To upgrade to real multi-user auth later (Google OAuth, email magic links), swap
the verify_password() check for an OAuth/identity provider; the cookie mechanism
stays the same.
"""
from __future__ import annotations

import hashlib
import hmac
import os
import secrets
import time

from fastapi import Request, Form, HTTPException, Depends
from fastapi.responses import RedirectResponse

from starlette.responses import Response  # noqa: F401  (re-exported for app.py)

_COOKIE_NAME = "ac_session"
_MAX_AGE = 60 * 60 * 12  # 12h
_CLOCK_SKEW = 60


def _secret() -> bytes:
    """A stable signing secret derived from APP_SECRET or APP_PASSWORD.

    We do NOT invent a persistent secret at random (that would invalidate cookies
    every process start). Falls back to a dev-only constant if neither env var is
    set — acceptable because auth is also disabled then.
    """
    raw = os.getenv("APP_SECRET") or os.getenv("APP_PASSWORD") or "dev-insecure-secret"
    return hashlib.sha256(raw.encode()).digest()


def _auth_enabled() -> bool:
    return bool(os.getenv("APP_PASSWORD"))


def _make_token() -> str:
    """A signed, timestamped token: b64-ish payload.hmac."""
    payload = f"{int(time.time())}.{secrets.token_urlsafe(16)}"
    sig = hmac.new(_secret(), payload.encode(), hashlib.sha256).hexdigest()
    return f"{payload}.{sig}"


def _verify_token(token: str | None) -> bool:
    if not token or token.count(".") != 2:
        return False
    payload, sig = token.rsplit(".", 1)
    expected = hmac.new(_secret(), payload.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, sig):
        return False
    try:
        issued = int(payload.split(".", 1)[0])
    except ValueError:
        return False
    now = int(time.time())
    # Allow a small amount of clock skew in EITHER direction: a token issued up to
    # _CLOCK_SKEW seconds in the future (receiver clock behind) or in the past
    # within _MAX_AGE (+ skew tolerance) is valid. A freshly issued token has
    # now - issued == 0, which must pass.
    delta = now - issued
    return -_CLOCK_SKEW <= delta <= (_MAX_AGE + _CLOCK_SKEW)


def set_session(response: Response) -> None:
    response.set_cookie(
        _COOKIE_NAME,
        _make_token(),
        max_age=_MAX_AGE,
        httponly=True,
        samesite="lax",
        path="/",
    )


def clear_session(response: Response) -> None:
    response.delete_cookie(_COOKIE_NAME, path="/")


def verify_password(candidate: str) -> bool:
    expected = os.getenv("APP_PASSWORD", "")
    if not expected:
        return False
    # Constant-time compare to avoid timing oracles on the password.
    return hmac.compare_digest(expected, candidate)


def is_authenticated(request: Request) -> bool:
    if not _auth_enabled():
        return True  # auth disabled -> everyone is "authenticated"
    token = request.cookies.get(_COOKIE_NAME)
    return _verify_token(token)


def require_auth(request: Request) -> None:
    """FastAPI dependency: redirect to /login when not authenticated."""
    if not is_authenticated(request):
        raise HTTPException(
            status_code=307,
            detail="Not authenticated",
            headers={"Location": "/login"},
        )
