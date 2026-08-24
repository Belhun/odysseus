"""Notes routes accept scoped ody_ tokens as the token owner.

Browser sessions still go through cookie require_user. Bearer tokens without
notes:read / notes:write stay 403. GET needs notes:read (write also counts);
mutating methods need notes:write. Owner is request.state.api_token_owner so
PhoneApp reads the same Note rows as the web UI.
"""
import uuid
from types import SimpleNamespace

import httpx
import pytest
from fastapi import FastAPI, HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import NullPool

import core.database as cdb
from core.database import Note
import routes.note_routes as nr
from routes.api_token_routes import ALLOWED_SCOPES, TOKEN_PROFILES, _normalize_scopes
from routes.note_routes import notes_owner

_PEER = ("203.0.113.7", 54321)


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


class _Identity:
    """Pure-ASGI shim: cookie user via x-test-user, token via x-test-api-token."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http":
            headers = dict(scope.get("headers") or [])
            state = scope.setdefault("state", {})
            user = headers.get(b"x-test-user")
            if user:
                state["current_user"] = user.decode()
            if headers.get(b"x-test-api-token"):
                state["current_user"] = "api"
                state["api_token"] = True
                owner = headers.get(b"x-test-owner")
                if owner:
                    state["api_token_owner"] = owner.decode()
                scopes = headers.get(b"x-test-scopes", b"").decode()
                state["api_token_scopes"] = [s.strip() for s in scopes.split(",") if s.strip()]
        await self.app(scope, receive, send)


def _temp_db(tmp_path):
    engine = create_engine(
        f"sqlite:///{tmp_path / 'notes.db'}",
        connect_args={"check_same_thread": False},
        poolclass=NullPool,
    )
    cdb.Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)


def _build_app(factory):
    app = FastAPI()
    app.state.auth_manager = SimpleNamespace(is_configured=True)
    app.include_router(nr.setup_note_routes())
    return _Identity(app)


def _client(app):
    transport = httpx.ASGITransport(app=app, client=_PEER)
    return httpx.AsyncClient(transport=transport, base_url="http://notes.test")


@pytest.fixture
def env(monkeypatch, tmp_path):
    factory = _temp_db(tmp_path)
    monkeypatch.setattr(nr, "SessionLocal", factory)
    monkeypatch.setenv("AUTH_ENABLED", "true")
    monkeypatch.delenv("LOCALHOST_BYPASS", raising=False)

    app = _build_app(factory)

    db = factory()
    db.add(Note(id="note-alice", owner="alice", title="a", content="x",
                items='[{"text": "t", "done": false}]'))
    db.add(Note(id="note-bob", owner="bob", title="b", content="y"))
    db.commit()
    db.close()
    return app, factory


def test_notes_scopes_are_allowed_on_api_tokens():
    assert "notes:read" in ALLOWED_SCOPES
    assert "notes:write" in ALLOWED_SCOPES
    assert _normalize_scopes(["notes:write"]) == ["notes:read", "notes:write"]
    assert TOKEN_PROFILES["phone_notes"] == ["notes:read", "notes:write"]
    assert TOKEN_PROFILES["phone_finance"] == ["finance:read", "finance:write"]


def test_notes_get_accepts_read_scoped_token_as_owner():
    req = _req(method="GET", scopes=["notes:read"])
    assert notes_owner(req) == "alice"


def test_notes_get_accepts_write_scoped_token_as_owner():
    req = _req(method="GET", scopes=["notes:read", "notes:write"])
    assert notes_owner(req) == "alice"


def test_notes_post_requires_write_scope():
    req = _req(method="POST", scopes=["notes:read"])
    with pytest.raises(HTTPException) as exc:
        notes_owner(req)
    assert exc.value.status_code == 403
    assert "notes:write" in str(exc.value.detail)


def test_notes_post_accepts_write_scoped_token_as_owner():
    req = _req(method="POST", scopes=["notes:write"])
    assert notes_owner(req) == "alice"


def test_notes_rejects_chat_only_token():
    req = _req(method="GET", scopes=["chat"])
    with pytest.raises(HTTPException) as exc:
        notes_owner(req)
    assert exc.value.status_code == 403


def test_notes_rejects_finance_only_token():
    req = _req(method="GET", scopes=["finance:read", "finance:write"])
    with pytest.raises(HTTPException) as exc:
        notes_owner(req)
    assert exc.value.status_code == 403
    assert "notes:read" in str(exc.value.detail)


def test_notes_rejects_token_without_owner():
    req = _req(method="GET", scopes=["notes:read"], owner=None)
    with pytest.raises(HTTPException) as exc:
        notes_owner(req)
    assert exc.value.status_code in (401, 403)


def test_notes_cookie_session_still_uses_current_user(monkeypatch):
    monkeypatch.setenv("AUTH_ENABLED", "true")
    req = _req(method="GET", api_token=False, owner="bob", current_user="bob")
    assert notes_owner(req) == "bob"


def test_unscoped_api_token_still_403():
    """Fail-closed contract: a bare api_token flag without notes scopes is 403."""
    req = _req(method="GET", scopes=[], owner=None)
    req.state.api_token_owner = None
    with pytest.raises(HTTPException) as exc:
        notes_owner(req)
    assert exc.value.status_code == 403


async def test_scoped_token_lists_only_owner_notes(env):
    app, _ = env
    headers = {
        "x-test-api-token": "1",
        "x-test-owner": "alice",
        "x-test-scopes": "notes:read",
    }
    async with _client(app) as c:
        listed = (await c.get("/api/notes", headers=headers)).json()["notes"]
        assert [n["id"] for n in listed] == ["note-alice"]
        assert (await c.get("/api/notes/note-alice", headers=headers)).status_code == 200
        assert (await c.get("/api/notes/note-bob", headers=headers)).status_code == 404


async def test_read_token_cannot_mutate(env):
    app, _ = env
    headers = {
        "x-test-api-token": "1",
        "x-test-owner": "alice",
        "x-test-scopes": "notes:read",
    }
    async with _client(app) as c:
        r = await c.put("/api/notes/note-alice", json={"title": "nope"}, headers=headers)
        assert r.status_code == 403
        r = await c.post("/api/notes/note-alice/pin", headers=headers)
        assert r.status_code == 403
        r = await c.post("/api/notes", json={"title": "ghost"}, headers=headers)
        assert r.status_code == 403


async def test_write_token_creates_and_toggles_as_owner(env):
    app, factory = env
    headers = {
        "x-test-api-token": "1",
        "x-test-owner": "alice",
        "x-test-scopes": "notes:read,notes:write",
    }
    async with _client(app) as c:
        created = await c.post(
            "/api/notes",
            json={"title": "phone", "content": "from Pixel"},
            headers=headers,
        )
        assert created.status_code == 200
        body = created.json()
        assert body["owner"] == "alice"
        assert body["title"] == "phone"
        note_id = body["id"]
        uuid.UUID(note_id)

        pinned = await c.post(f"/api/notes/{note_id}/pin", headers=headers)
        assert pinned.status_code == 200
        assert pinned.json()["pinned"] is True

        toggled = await c.post("/api/notes/note-alice/items/0/toggle", headers=headers)
        assert toggled.status_code == 200
        assert toggled.json()["items"][0]["done"] is True

        # Bob's row stays hidden.
        assert (await c.delete("/api/notes/note-bob", headers=headers)).status_code == 404

    db = factory()
    rows = {n.id: n for n in db.query(Note).all()}
    db.close()
    assert "note-bob" in rows
    assert rows["note-bob"].owner == "bob"


async def test_chat_token_cannot_list_notes(env):
    app, _ = env
    headers = {
        "x-test-api-token": "1",
        "x-test-owner": "alice",
        "x-test-scopes": "chat",
    }
    async with _client(app) as c:
        r = await c.get("/api/notes", headers=headers)
    assert r.status_code == 403
