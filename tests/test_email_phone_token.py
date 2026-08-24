"""Bearer ody_ tokens can use /api/email/* as the token owner.

Cookie sessions still go through email_helpers.require_user. Tokens need
email:read for GET / mark-read, email:draft for drafts, email:send to SMTP-send.
Owner is request.state.api_token_owner so PhoneApp sees the same IMAP accounts
as the web UI.
"""

from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from routes.api_token_routes import ALLOWED_SCOPES
from routes.email_mobile_routes import require_owner, require_user
from routes.email_routes import require_owner as routes_require_owner
from routes.email_routes import require_user as routes_require_user


def _req(*, method="GET", path="/api/email/list", api_token=True, scopes=None, owner="alice", current_user=None):
    if current_user is None:
        current_user = "api" if api_token else owner
    return SimpleNamespace(
        method=method,
        url=SimpleNamespace(path=path),
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


def test_email_scopes_are_allowed_on_api_tokens():
    assert "email:read" in ALLOWED_SCOPES
    assert "email:draft" in ALLOWED_SCOPES
    assert "email:send" in ALLOWED_SCOPES


def test_email_routes_use_mobile_require_user():
    assert routes_require_user is require_user
    assert routes_require_owner is require_owner


def test_get_accepts_read_scoped_token_as_owner():
    req = _req(method="GET", path="/api/email/list", scopes=["email:read"])
    assert require_user(req) == "alice"


def test_get_accepts_send_scoped_token_as_owner():
    req = _req(method="GET", path="/api/email/list", scopes=["email:send"])
    assert require_user(req) == "alice"


def test_get_rejects_finance_only_token():
    req = _req(method="GET", path="/api/email/list", scopes=["finance:read", "finance:write"])
    with pytest.raises(HTTPException) as exc:
        require_user(req)
    assert exc.value.status_code == 403
    assert "email:read" in str(exc.value.detail)


def test_send_requires_email_send_scope():
    req = _req(method="POST", path="/api/email/send", scopes=["email:read"])
    with pytest.raises(HTTPException) as exc:
        require_user(req)
    assert exc.value.status_code == 403
    assert "email:send" in str(exc.value.detail)


def test_send_accepts_send_scoped_token_as_owner():
    req = _req(method="POST", path="/api/email/send", scopes=["email:send"])
    assert require_user(req) == "alice"


def test_draft_requires_draft_or_send():
    req = _req(method="POST", path="/api/email/draft", scopes=["email:read"])
    with pytest.raises(HTTPException) as exc:
        require_user(req)
    assert exc.value.status_code == 403


def test_draft_accepts_draft_scope():
    req = _req(method="POST", path="/api/email/draft", scopes=["email:draft"])
    assert require_user(req) == "alice"


def test_mark_read_accepts_read_scope():
    req = _req(method="POST", path="/api/email/mark-read/12", scopes=["email:read"])
    assert require_user(req) == "alice"


def test_token_without_owner_is_401():
    req = _req(method="GET", scopes=["email:read"], owner=None)
    with pytest.raises(HTTPException) as exc:
        require_user(req)
    assert exc.value.status_code in (401, 403)


def test_cookie_session_still_uses_session_helper(monkeypatch):
    called = {}

    def _session_user(request):
        called["ok"] = True
        return "bob"

    monkeypatch.setattr("routes.email_mobile_routes._session_require_user", _session_user)
    req = _req(method="GET", api_token=False, owner="bob", current_user="bob")
    assert require_user(req) == "bob"
    assert called["ok"] is True
