"""Chat-scope gate for PhoneApp mobile chat routes.

Cookie sessions use ``require_user``. Bearer ``ody_`` tokens must include
``chat`` and resolve to the token owner via ``effective_user`` so the phone
sees the same sessions as the web UI. Finance scopes are not accepted here.
"""

from fastapi import HTTPException, Request

from src.auth_helpers import effective_user, require_user


def _token_scopes(request: Request) -> set[str]:
    scopes = getattr(request.state, "api_token_scopes", None) or []
    if isinstance(scopes, str):
        scopes = [part.strip() for part in scopes.split(",")]
    return {str(s).strip() for s in scopes if str(s).strip()}


def require_chat_user(request: Request) -> str:
    """Return the chat owner for this request.

    Tokens without ``chat`` get 403. Tokens without an owner get 401.
    Cookie callers follow ``require_user``, then ``effective_user``.
    """
    if getattr(request.state, "api_token", False):
        if "chat" not in _token_scopes(request):
            raise HTTPException(403, "API token requires chat scope")
        owner = getattr(request.state, "api_token_owner", None)
        if not owner:
            raise HTTPException(401, "Not authenticated")
        return owner
    require_user(request)
    return effective_user(request) or ""
