"""PhoneApp auth introspection — scopes and feature flags for the current credential."""

from __future__ import annotations

from fastapi import APIRouter, Request

from companion.routes import token_owner

# PhoneApp surfaces and the read scope (or chat) that unlocks them.
_PHONE_FEATURES = (
    ("chat", "chat", "Chat"),
    ("finance", "finance:read", "Finance"),
    ("notes", "notes:read", "Notes"),
    ("calendar", "calendar:read", "Calendar"),
    ("email", "email:read", "Email"),
    ("todos", "todos:read", "Todos"),
    ("documents", "documents:read", "Documents"),
    ("memory", "memory:read", "Memory"),
    ("cookbook", "cookbook:read", "Cookbook"),
)


def _scope_set(request: Request) -> set[str]:
    raw = getattr(request.state, "api_token_scopes", None) or []
    if isinstance(raw, str):
        return {s.strip() for s in raw.split(",") if s.strip()}
    return {str(s).strip() for s in raw if str(s).strip()}


def _feature_flags(scopes: set[str], *, full_access: bool) -> dict[str, bool]:
    if full_access:
        return {key: True for key, _, _ in _PHONE_FEATURES}
    out: dict[str, bool] = {}
    for key, required, _ in _PHONE_FEATURES:
        out[key] = required in scopes
    return out


def setup_mobile_auth_routes() -> APIRouter:
    router = APIRouter(tags=["mobile_auth"])

    @router.get("/api/mobile/auth")
    def mobile_auth(request: Request):
        """Return auth mode, owner, scopes, and PhoneApp feature flags."""
        is_token = bool(getattr(request.state, "api_token", False))
        owner = token_owner(request)
        if is_token:
            scopes = sorted(_scope_set(request))
            features = _feature_flags(set(scopes), full_access=False)
            return {
                "auth": "token",
                "owner": owner,
                "scopes": scopes,
                "features": features,
            }
        return {
            "auth": "session",
            "owner": owner,
            "scopes": None,
            "features": _feature_flags(set(), full_access=True),
        }

    return router
