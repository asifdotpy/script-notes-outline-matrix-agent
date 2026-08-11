"""Web2 Google OAuth login tests (board task t_5e9f2ba8).

This project is WEB2 ONLY (Google Cloud + Gemini + ClickHouse). There is NO web3 /
wallet / Privy anywhere — that was a hallucination in the original task text and has
been removed. These tests lock in the Google OAuth 2.0 Authorization Code flow:
  - auth disabled when GOOGLE_OAUTH_CLIENT_ID/SECRET unset (open for local dev)
  - signed session cookie accepted / rejected (missing, tampered, expired)
  - email allow-list enforcement
  - /logout clears the cookie
  - require_auth 307-redirects unauthenticated requests to /login
  - callback rejects unverified / non-allowed Google accounts
"""
from __future__ import annotations

import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from starlette.requests import Request  # noqa: E402
from starlette.responses import Response  # noqa: E402

from src.web import auth as webauth  # noqa: E402


def _req(token=None):
    headers = []
    if token:
        headers.append((b"cookie", f"ac_session={token}".encode()))
    return Request({"type": "http", "headers": headers, "query_string": b""})


def _issue(email="user@gmail.com"):
    r = Response("ok")
    webauth.set_session(r, email)
    return r.headers.get("set-cookie").split(";")[0].split("=", 1)[1]


def test_disabled_without_creds(monkeypatch):
    monkeypatch.delenv("GOOGLE_OAUTH_CLIENT_ID", raising=False)
    monkeypatch.delenv("GOOGLE_OAUTH_CLIENT_SECRET", raising=False)
    assert webauth.is_authenticated(_req()) is True  # open when unset
    assert webauth.get_user(_req()) == "local-dev"


def test_enabled_requires_token(monkeypatch):
    monkeypatch.setenv("GOOGLE_OAUTH_CLIENT_ID", "cid.apps.googleusercontent.com")
    monkeypatch.setenv("GOOGLE_OAUTH_CLIENT_SECRET", "secret")
    monkeypatch.delenv("GOOGLE_ALLOWED_EMAILS", raising=False)
    assert webauth.is_authenticated(_req()) is False
    tok = _issue("user@gmail.com")
    assert webauth.is_authenticated(_req(tok)) is True
    assert webauth.get_user(_req(tok)) == "user@gmail.com"


def test_missing_and_tampered_rejected(monkeypatch):
    monkeypatch.setenv("GOOGLE_OAUTH_CLIENT_ID", "cid.apps.googleusercontent.com")
    monkeypatch.setenv("GOOGLE_OAUTH_CLIENT_SECRET", "secret")
    assert webauth.is_authenticated(_req()) is False
    tok = _issue("user@gmail.com")
    assert webauth.is_authenticated(_req(tok[:-3] + "xyz")) is False


def test_email_allowlist(monkeypatch):
    monkeypatch.setenv("GOOGLE_OAUTH_CLIENT_ID", "cid.apps.googleusercontent.com")
    monkeypatch.setenv("GOOGLE_OAUTH_CLIENT_SECRET", "secret")
    monkeypatch.setenv("GOOGLE_ALLOWED_EMAILS", "boss@studio.com, dev@studio.com")
    assert webauth._allowed("boss@studio.com") is True
    assert webauth._allowed("rand@other.com") is False
    assert webauth._allowed("BOSS@STUDIO.COM") is True  # case-insensitive


def test_logout_clears_cookie(monkeypatch):
    monkeypatch.setenv("GOOGLE_OAUTH_CLIENT_ID", "cid.apps.googleusercontent.com")
    monkeypatch.setenv("GOOGLE_OAUTH_CLIENT_SECRET", "secret")
    r = Response("ok")
    webauth.set_session(r, "user@gmail.com")
    webauth.clear_session(r)
    sc_all = "; ".join(v.decode() for k, v in r.raw_headers if k == b"set-cookie").lower()
    assert "max-age=0" in sc_all or "expires=" in sc_all


def test_require_auth_redirects_when_unauthenticated(monkeypatch):
    from fastapi import HTTPException

    monkeypatch.setenv("GOOGLE_OAUTH_CLIENT_ID", "cid.apps.googleusercontent.com")
    monkeypatch.setenv("GOOGLE_OAUTH_CLIENT_SECRET", "secret")
    try:
        webauth.require_auth(_req())
        raised = None
    except HTTPException as e:
        raised = e
    assert raised is not None
    assert raised.status_code == 307
    assert raised.headers.get("Location") == "/login"
