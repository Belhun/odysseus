"""Admin settings validation for email local sync pacing/budget keys."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from src.settings import DEFAULT_SETTINGS


@pytest.fixture
def settings_route(tmp_path, monkeypatch):
    fastapi = pytest.importorskip("fastapi")
    from routes import auth_routes

    monkeypatch.setattr(auth_routes, "migrate_from_settings", lambda: None)

    stored = dict(DEFAULT_SETTINGS)

    monkeypatch.setattr(auth_routes, "_load_settings", lambda: dict(stored))

    def _save_settings(data):
        stored.clear()
        stored.update(data)
        return stored

    monkeypatch.setattr(auth_routes, "_save_settings", _save_settings)

    class _AuthManager:
        def get_username_for_token(self, token):
            return "admin" if token == "session-token" else None

        def is_admin(self, user):
            return user == "admin"

    router = auth_routes.setup_auth_routes(_AuthManager())

    def endpoint(path, method):
        for route in router.routes:
            if getattr(route, "path", "") == path and method in getattr(route, "methods", set()):
                return route.endpoint
        raise AssertionError(f"{method} {path} route not registered")

    class _JsonRequest(SimpleNamespace):
        def __init__(self, body):
            super().__init__(
                cookies={auth_routes.SESSION_COOKIE: "session-token"},
                client=SimpleNamespace(host="127.0.0.1"),
                _body=body,
            )

        async def json(self):
            return self._body

    return endpoint("/api/auth/settings", "POST"), _JsonRequest, fastapi.HTTPException, stored


@pytest.mark.parametrize(
    ("key", "sent", "expected"),
    [
        ("email_local_sync_max_sync_seconds", 9999, 3600),
        ("email_local_sync_max_sync_seconds", -5, 0),
        ("email_local_sync_account_delay_ms", 120_000, 60_000),
        ("email_local_sync_chunk_delay_ms", 9000, 5000),
        ("email_local_sync_backfill_batch", 0, 1),
        ("email_local_sync_backfill_batch", 900, 500),
    ],
)
def test_email_local_sync_int_ranges_clamp(settings_route, key, sent, expected):
    set_settings, request_cls, http_exception, stored = settings_route

    result = asyncio.run(set_settings(request_cls({key: sent})))

    assert result[key] == expected
    assert stored[key] == expected


def test_email_local_sync_max_sync_seconds_rejects_non_integer(settings_route):
    set_settings, request_cls, http_exception, _stored = settings_route

    with pytest.raises(http_exception) as exc:
        asyncio.run(set_settings(request_cls({"email_local_sync_max_sync_seconds": "fast"})))

    assert exc.value.status_code == 400
    assert "email_local_sync_max_sync_seconds must be an integer" in exc.value.detail
