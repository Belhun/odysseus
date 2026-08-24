"""Token-aware owner for /api/email/* so PhoneApp Bearer tokens work.

Cookie sessions still use email_helpers.require_owner / require_user.
Bearer ody_ tokens need email:read (GET, mark-read/unread), email:draft
(drafts), or email:send (SMTP send) and resolve to api_token_owner so the
phone sees the same IMAP accounts as the web UI.

Imported by email_routes.setup_email_routes() in place of the session-only
helpers. IMAP handlers are unchanged.
"""

from fastapi import HTTPException, Query, Request

from routes.email_helpers import (
    _assert_owns_account,
    require_owner as _session_require_owner,
    require_user as _session_require_user,
)

_EMAIL_READ = frozenset({"email:read", "email:draft", "email:send"})
_EMAIL_DRAFT = frozenset({"email:draft", "email:send"})
_EMAIL_SEND = frozenset({"email:send"})


def _token_scopes(request: Request) -> set[str]:
    scopes = getattr(request.state, "api_token_scopes", None) or []
    if isinstance(scopes, str):
        scopes = [s.strip() for s in scopes.split(",")]
    return {str(s).strip() for s in scopes if str(s).strip()}


def _request_path(request: Request) -> str:
    url = getattr(request, "url", None)
    return str(getattr(url, "path", "") or "")


def _is_api_token(request: Request) -> bool:
    return bool(getattr(request.state, "api_token", False))


def _token_owner(request: Request, needed: frozenset[str], label: str) -> str:
    scopes = _token_scopes(request)
    if not scopes.intersection(needed):
        raise HTTPException(403, f"API token requires {label} scope")
    owner = getattr(request.state, "api_token_owner", None)
    if not owner:
        raise HTTPException(401, "Not authenticated")
    return str(owner)


def require_user(request: Request) -> str:
    """Cookie sessions: email_helpers.require_user. Tokens: email scopes + owner."""
    if not _is_api_token(request):
        return _session_require_user(request)
    path = _request_path(request).rstrip("/")
    method = (getattr(request, "method", "GET") or "GET").upper()
    if method in ("GET", "HEAD", "OPTIONS"):
        return _token_owner(request, _EMAIL_READ, "email:read")
    if path.endswith("/send"):
        return _token_owner(request, _EMAIL_SEND, "email:send")
    if path.endswith("/draft"):
        return _token_owner(request, _EMAIL_DRAFT, "email:draft")
    return _token_owner(request, _EMAIL_READ, "email:read")


def require_owner(request: Request, account_id: str | None = Query(None)) -> str:
    """Same as require_user, plus optional query account_id ownership check."""
    if not _is_api_token(request):
        return _session_require_owner(request, account_id)
    owner = require_user(request)
    if account_id:
        _assert_owns_account(account_id, owner)
    return owner
