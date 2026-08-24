"""Finance routes accept scoped ody_ tokens as the token owner.

Browser sessions still go through cookie require_user. Bearer tokens with only
chat (or no finance scope) stay rejected. GET needs finance:read; mutating
methods need finance:write. The owner is request.state.api_token_owner so the
phone client reads the same ledger as the web UI.
"""

from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from integrations.finance import routes as finance_routes
from routes.api_token_routes import ALLOWED_SCOPES, TOKEN_PROFILES, _normalize_scopes


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


def test_finance_scopes_are_allowed_on_api_tokens():
    assert "finance:read" in ALLOWED_SCOPES
    assert "finance:write" in ALLOWED_SCOPES
    assert _normalize_scopes(["finance:write"]) == ["finance:read", "finance:write"]
    assert TOKEN_PROFILES["phone_finance"] == ["finance:read", "finance:write"]


def test_finance_get_accepts_read_scoped_token_as_owner():
    req = _req(method="GET", scopes=["finance:read"])
    assert finance_routes.require_user(req) == "alice"


def test_finance_get_accepts_write_scoped_token_as_owner():
    req = _req(method="GET", scopes=["finance:read", "finance:write"])
    assert finance_routes.require_user(req) == "alice"


def test_finance_post_requires_write_scope():
    req = _req(method="POST", scopes=["finance:read"])
    with pytest.raises(HTTPException) as exc:
        finance_routes.require_user(req)
    assert exc.value.status_code == 403
    assert "finance:write" in str(exc.value.detail)


def test_finance_post_accepts_write_scoped_token_as_owner():
    req = _req(method="POST", scopes=["finance:write"])
    assert finance_routes.require_user(req) == "alice"


def test_finance_rejects_chat_only_token():
    req = _req(method="GET", scopes=["chat"])
    with pytest.raises(HTTPException) as exc:
        finance_routes.require_user(req)
    assert exc.value.status_code == 403


def test_finance_rejects_token_without_owner():
    req = _req(method="GET", scopes=["finance:read"], owner=None)
    with pytest.raises(HTTPException) as exc:
        finance_routes.require_user(req)
    assert exc.value.status_code in (401, 403)


def test_finance_cookie_session_still_uses_current_user(monkeypatch):
    monkeypatch.setenv("AUTH_ENABLED", "true")
    req = _req(method="GET", api_token=False, owner="bob", current_user="bob")
    assert finance_routes.require_user(req) == "bob"
