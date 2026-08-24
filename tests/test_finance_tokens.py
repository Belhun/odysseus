"""Finance ody_ token scopes stay additive on /api/finance routes."""

from types import SimpleNamespace

import pytest
from fastapi import FastAPI, HTTPException
from sqlalchemy.orm import sessionmaker
from starlette.testclient import TestClient
from tests.conftest import make_finance_test_engine

import integrations.finance.database as finance_db
import integrations.finance.routes as finance_routes
from integrations.finance.models import FinanceBase
from integrations.finance.routes import require_finance_user, setup_finance_routes
from routes.api_token_routes import ALLOWED_SCOPES, _normalize_scopes


def _token_request(*, scopes, method="GET", owner="alice"):
    return SimpleNamespace(
        state=SimpleNamespace(
            current_user="api",
            api_token=True,
            api_token_owner=owner,
            api_token_scopes=list(scopes),
        ),
        method=method,
        app=SimpleNamespace(state=SimpleNamespace()),
        client=SimpleNamespace(host="203.0.113.10"),
    )


def test_finance_write_scope_implies_read():
    assert "finance:read" in ALLOWED_SCOPES
    assert "finance:write" in ALLOWED_SCOPES
    assert _normalize_scopes("finance:write") == ["finance:read", "finance:write"]


def test_phone_finance_profile_is_read_and_write():
    from routes.api_token_routes import TOKEN_PROFILES

    assert TOKEN_PROFILES["phone_finance"] == ["finance:read", "finance:write"]
    assert _normalize_scopes(None, "phone_finance") == ["finance:read", "finance:write"]
    assert "chat" not in _normalize_scopes(None, "phone_finance")


def test_chat_token_cannot_use_finance_routes():
    req = _token_request(scopes=["chat"], method="GET")
    with pytest.raises(HTTPException) as exc:
        require_finance_user(req)
    assert exc.value.status_code == 403
    assert "finance:read" in str(exc.value.detail)


def test_finance_read_allows_get_and_blocks_write():
    assert require_finance_user(_token_request(scopes=["finance:read"], method="GET")) == "alice"
    with pytest.raises(HTTPException) as exc:
        require_finance_user(_token_request(scopes=["finance:read"], method="POST"))
    assert exc.value.status_code == 403
    assert "finance:write" in str(exc.value.detail)


def test_finance_write_allows_post():
    assert require_finance_user(_token_request(scopes=["finance:write"], method="POST")) == "alice"
    assert require_finance_user(_token_request(scopes=["finance:write"], method="GET")) == "alice"


def test_cookie_session_still_uses_require_user(monkeypatch):
    monkeypatch.setattr(finance_routes, "require_user", lambda request: "cookie-user")
    req = SimpleNamespace(
        state=SimpleNamespace(api_token=False, current_user="cookie-user"),
        method="GET",
        app=SimpleNamespace(state=SimpleNamespace()),
        client=SimpleNamespace(host="127.0.0.1"),
    )
    assert require_finance_user(req) == "cookie-user"


@pytest.fixture()
def token_finance_client(monkeypatch, tmp_path):
    finance_db.reset_engine_cache()
    db_path = tmp_path / "finance.db"
    monkeypatch.setattr(finance_db, "finance_db_path", lambda: db_path)
    monkeypatch.setattr("integrations.finance.routes.is_plugin_active", lambda _pid: True)

    engine = make_finance_test_engine(db_path)
    FinanceBase.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    monkeypatch.setattr(finance_routes, "get_session_factory", lambda: session_factory)

    app = FastAPI()

    @app.middleware("http")
    async def stamp_token(request, call_next):
        request.state.api_token = True
        request.state.api_token_owner = "testuser"
        request.state.api_token_scopes = [
            s for s in request.headers.get("x-scopes", "").split(",") if s
        ]
        return await call_next(request)

    app.include_router(setup_finance_routes())
    with TestClient(app) as client:
        yield client
    finance_db.reset_engine_cache()


@pytest.mark.area_routes
def test_finance_read_token_lists_accounts(token_finance_client):
    res = token_finance_client.get("/api/finance/accounts", headers={"x-scopes": "finance:read"})
    assert res.status_code == 200
    assert "accounts" in res.json()


@pytest.mark.area_routes
def test_finance_read_token_cannot_create_account(token_finance_client):
    res = token_finance_client.post(
        "/api/finance/accounts",
        headers={"x-scopes": "finance:read"},
        json={"name": "Checking"},
    )
    assert res.status_code == 403


@pytest.mark.area_routes
def test_finance_write_token_can_create_account(token_finance_client):
    res = token_finance_client.post(
        "/api/finance/accounts",
        headers={"x-scopes": "finance:write"},
        json={"name": "Checking", "account_type": "checking"},
    )
    assert res.status_code == 200, res.text
    assert res.json()["name"] == "Checking"


@pytest.mark.area_routes
def test_chat_token_is_forbidden_on_finance_http(token_finance_client):
    res = token_finance_client.get("/api/finance/accounts", headers={"x-scopes": "chat"})
    assert res.status_code == 403
