"""Calendar routes accept scoped ody_ tokens as the token owner.

Cookie sessions still go through require_user. Bearer tokens without
calendar:read / calendar:write stay 403. GET needs calendar:read (write also
counts); mutating methods need calendar:write. Owner is effective_user so
PhoneApp reads the same CalendarEvent rows as the web UI.
"""
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from routes.api_token_routes import ALLOWED_SCOPES, TOKEN_PROFILES, _normalize_scopes
from routes.calendar_routes import _require_user


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


def test_calendar_scopes_are_allowed_on_api_tokens():
    assert "calendar:read" in ALLOWED_SCOPES
    assert "calendar:write" in ALLOWED_SCOPES
    assert _normalize_scopes(["calendar:write"]) == ["calendar:read", "calendar:write"]
    assert TOKEN_PROFILES["phone_calendar"] == ["calendar:read", "calendar:write"]


def test_calendar_get_accepts_read_scoped_token_as_owner():
    req = _req(method="GET", scopes=["calendar:read"])
    assert _require_user(req) == "alice"


def test_calendar_get_accepts_write_scoped_token_as_owner():
    req = _req(method="GET", scopes=["calendar:read", "calendar:write"])
    assert _require_user(req) == "alice"


def test_calendar_post_requires_write_scope():
    req = _req(method="POST", scopes=["calendar:read"])
    with pytest.raises(HTTPException) as exc:
        _require_user(req)
    assert exc.value.status_code == 403
    assert "calendar:write" in str(exc.value.detail)


def test_calendar_post_accepts_write_scoped_token_as_owner():
    req = _req(method="POST", scopes=["calendar:write"])
    assert _require_user(req) == "alice"


def test_calendar_rejects_chat_only_token():
    req = _req(method="GET", scopes=["chat"])
    with pytest.raises(HTTPException) as exc:
        _require_user(req)
    assert exc.value.status_code == 403
    assert "calendar:read" in str(exc.value.detail)


def test_calendar_rejects_finance_only_token():
    req = _req(method="GET", scopes=["finance:read", "finance:write"])
    with pytest.raises(HTTPException) as exc:
        _require_user(req)
    assert exc.value.status_code == 403
    assert "calendar:read" in str(exc.value.detail)


def test_calendar_rejects_token_without_owner():
    req = _req(method="GET", scopes=["calendar:read"], owner=None)
    with pytest.raises(HTTPException) as exc:
        _require_user(req)
    assert exc.value.status_code in (401, 403)


def test_calendar_cookie_session_still_uses_require_user():
    req = _req(method="GET", api_token=False, owner="bob", current_user="bob")
    assert _require_user(req) == "bob"
