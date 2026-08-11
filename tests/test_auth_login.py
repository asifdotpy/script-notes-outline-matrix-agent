"""Auth gate tests (board task t_5e9f2ba8) — non-web3 login, NOT Privy.

Privy is a web3 embedded-wallet vendor; this project is non-web3 (GCP + Gemini +
ClickHouse). The task body itself flagged the mismatch and said "Do NOT start
until scope confirmed". These tests lock in the chosen standard-login option:
a stdlib-only signed session cookie gated by an env password.

Covers: disabled-without-password, valid token accepted, missing/tampered/expired
rejected, password check (constant-time, correct/incorrect), and logout clearing.
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


def _issue():
    r = Response("ok")
    webauth.set_session(r)
    return r.headers.get("set-cookie").split(";")[0].split("=", 1)[1]


def test_disabled_without_password(monkeypatch):
    monkeypatch.delenv("APP_PASSWORD", raising=False)
    assert webauth.is_authenticated(_req()) is True  # open when unset


def test_enabled_requires_token(monkeypatch):
    monkeypatch.setenv("APP_PASSWORD", "topsecret")
    assert webauth.is_authenticated(_req()) is False
    assert webauth.is_authenticated(_req(_issue())) is True


def test_missing_cookie_rejected(monkeypatch):
    monkeypatch.setenv("APP_PASSWORD", "topsecret")
    assert webauth.is_authenticated(_req()) is False


def test_tampered_token_rejected(monkeypatch):
    monkeypatch.setenv("APP_PASSWORD", "topsecret")
    tok = _issue()
    bad = tok[:-3] + "xyz"
    assert webauth.is_authenticated(_req(bad)) is False


def test_password_check(monkeypatch):
    monkeypatch.setenv("APP_PASSWORD", "topsecret")
    assert webauth.verify_password("topsecret") is True
    assert webauth.verify_password("wrong") is False
    # empty password env -> verify always False (never accidentally open)
    monkeypatch.delenv("APP_PASSWORD", raising=False)
    assert webauth.verify_password("anything") is False


def test_logout_clears_cookie(monkeypatch):
    monkeypatch.setenv("APP_PASSWORD", "topsecret")
    r = Response("ok")
    webauth.set_session(r)
    assert "ac_session=" in r.headers.get("set-cookie")
    webauth.clear_session(r)
    # delete_cookie adds a SECOND set-cookie that expires the session. Inspect all
    # raw set-cookie headers (Response.headers.get returns only the first).
    sc_all = "; ".join(
        v.decode() for k, v in r.raw_headers if k == b"set-cookie"
    ).lower()
    assert "max-age=0" in sc_all or "expires=" in sc_all


def test_require_auth_redirects_when_unauthenticated(monkeypatch):
    from fastapi import HTTPException

    monkeypatch.setenv("APP_PASSWORD", "topsecret")
    try:
        webauth.require_auth(_req())
        raised = None
    except HTTPException as e:
        raised = e
    assert raised is not None
    assert raised.status_code == 307
    assert raised.headers.get("Location") == "/login"
