"""PhoneApp /api/mobile/auth introspection."""

from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from routes.mobile_auth_routes import setup_mobile_auth_routes


def _client():
    app = FastAPI()

    @app.middleware("http")
    async def stamp(request, call_next):
        request.state.api_token = request.headers.get("x-api-token") == "1"
        request.state.api_token_owner = request.headers.get("x-owner") or None
        raw = request.headers.get("x-scopes", "")
        request.state.api_token_scopes = [s for s in raw.split(",") if s]
        request.state.current_user = (
            "api" if request.state.api_token else request.headers.get("x-user") or "alice"
        )
        return await call_next(request)

    app.include_router(setup_mobile_auth_routes())
    return TestClient(app)


def test_session_auth_reports_full_access():
    client = _client()
    res = client.get("/api/mobile/auth", headers={"x-user": "alice"})
    assert res.status_code == 200
    body = res.json()
    assert body["auth"] == "session"
    assert body["owner"] == "alice"
    assert body["scopes"] is None
    assert body["features"]["chat"] is True
    assert body["features"]["finance"] is True


def test_finance_token_scopes():
    client = _client()
    res = client.get(
        "/api/mobile/auth",
        headers={
            "x-api-token": "1",
            "x-owner": "belhun",
            "x-scopes": "finance:read,finance:write",
        },
    )
    assert res.status_code == 200
    body = res.json()
    assert body["auth"] == "token"
    assert body["owner"] == "belhun"
    assert "chat" not in body["scopes"]
    assert body["features"]["finance"] is True
    assert body["features"]["chat"] is False


def test_full_access_token_includes_chat():
    client = _client()
    res = client.get(
        "/api/mobile/auth",
        headers={
            "x-api-token": "1",
            "x-owner": "belhun",
            "x-scopes": "chat,finance:read,finance:write,notes:read",
        },
    )
    body = res.json()
    assert body["features"]["chat"] is True
    assert body["features"]["finance"] is True
    assert body["features"]["notes"] is True
    assert body["features"]["calendar"] is False
