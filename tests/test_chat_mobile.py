"""PhoneApp mobile chat routes: chat-scope tokens see the owner's sessions."""

from types import SimpleNamespace

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from src.chat_token_auth import require_chat_user
from routes.chat_mobile_routes import setup_chat_mobile_routes


def _req(*, method="GET", api_token=True, scopes=None, owner="alice", current_user=None):
    if current_user is None:
        current_user = "api" if api_token else owner
    return SimpleNamespace(
        method=method,
        state=SimpleNamespace(
            current_user=current_user,
            api_token=api_token,
            api_token_owner=owner if api_token else None,
            api_token_scopes=list(scopes or []),
        ),
        app=SimpleNamespace(
            state=SimpleNamespace(auth_manager=SimpleNamespace(is_configured=True)),
        ),
        client=SimpleNamespace(host="203.0.113.10"),
    )


def test_chat_scope_token_resolves_to_owner():
    assert require_chat_user(_req(scopes=["chat"])) == "alice"


def test_finance_token_cannot_use_chat_gate():
    with pytest.raises(HTTPException) as exc:
        require_chat_user(_req(scopes=["finance:read", "finance:write"]))
    assert exc.value.status_code == 403
    assert "chat" in str(exc.value.detail).lower()


def test_token_without_owner_is_401():
    with pytest.raises(HTTPException) as exc:
        require_chat_user(_req(scopes=["chat"], owner=None))
    assert exc.value.status_code == 401


def test_cookie_session_uses_current_user(monkeypatch):
    import src.chat_token_auth as auth

    monkeypatch.setattr(auth, "require_user", lambda request: "cookie-user")
    monkeypatch.setattr(auth, "effective_user", lambda request: "cookie-user")
    req = _req(api_token=False, current_user="cookie-user", owner=None)
    assert require_chat_user(req) == "cookie-user"


class _Sess:
    def __init__(self, sid, name, owner, archived=False):
        self.id = sid
        self.name = name
        self.owner = owner
        self.archived = archived
        self.model = "local-model"
        self.history = []
        self.message_count = 0
        self.headers = {}


class _Mgr:
    def __init__(self):
        self.sessions = {}

    def get_sessions_for_user(self, username=None):
        if not username:
            return dict(self.sessions)
        return {k: v for k, v in self.sessions.items() if v.owner == username}

    def create_session(self, session_id, name, endpoint_url, model, rag=False, owner=None):
        sess = _Sess(session_id, name, owner)
        sess.model = model
        self.sessions[session_id] = sess
        return sess


def _app(mgr, monkeypatch, default_llm=("http://llm/v1", "test-model", {})):
    monkeypatch.setattr(
        "routes.chat_mobile_routes.pick_default_llm",
        lambda owner: default_llm,
    )

    class _DB:
        def query(self, model):
            return self

        def filter(self, *args, **kwargs):
            return self

        def all(self):
            return []

        def first(self):
            return None

        def commit(self):
            return None

        def rollback(self):
            return None

        def close(self):
            return None

    monkeypatch.setattr("routes.chat_mobile_routes.SessionLocal", lambda: _DB())
    monkeypatch.setattr(
        "routes.chat_mobile_routes.owner_filter",
        lambda q, model, user, **kwargs: q,
    )

    app = FastAPI()

    @app.middleware("http")
    async def stamp(request, call_next):
        request.state.api_token = True
        request.state.api_token_owner = request.headers.get("x-owner", "alice")
        request.state.api_token_scopes = [
            s for s in request.headers.get("x-scopes", "chat").split(",") if s
        ]
        request.state.current_user = "api"
        return await call_next(request)

    app.include_router(setup_chat_mobile_routes(mgr))
    return app


def test_list_is_owner_scoped(monkeypatch):
    mgr = _Mgr()
    mgr.sessions["a"] = _Sess("a", "Alice chat", "alice")
    mgr.sessions["b"] = _Sess("b", "Bob chat", "bob")
    client = TestClient(_app(mgr, monkeypatch))
    res = client.get("/api/mobile/chat/sessions", headers={"x-scopes": "chat", "x-owner": "alice"})
    assert res.status_code == 200
    names = [s["name"] for s in res.json()["sessions"]]
    assert names == ["Alice chat"]


def test_list_rejects_finance_scope(monkeypatch):
    mgr = _Mgr()
    client = TestClient(_app(mgr, monkeypatch))
    res = client.get(
        "/api/mobile/chat/sessions",
        headers={"x-scopes": "finance:read", "x-owner": "alice"},
    )
    assert res.status_code == 403


def test_create_without_models_returns_400(monkeypatch):
    mgr = _Mgr()
    client = TestClient(_app(mgr, monkeypatch, default_llm=None))
    res = client.post("/api/mobile/chat/sessions", headers={"x-scopes": "chat"})
    assert res.status_code == 400
    assert "model" in res.json()["detail"].lower()


def test_create_with_mocked_llm(monkeypatch):
    mgr = _Mgr()
    client = TestClient(_app(mgr, monkeypatch))
    res = client.post(
        "/api/mobile/chat/sessions",
        headers={"x-scopes": "chat", "x-owner": "alice"},
        json={"name": "Phone"},
    )
    assert res.status_code == 200
    body = res.json()
    assert body["name"] == "Phone"
    assert body["model"] == "test-model"
    assert body["id"] in mgr.sessions
    assert mgr.sessions[body["id"]].owner == "alice"
