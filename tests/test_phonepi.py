"""PhonePi optional builtin: connect hint, enable flag, WS proxy, Messages QR files."""

from pathlib import Path
from urllib.parse import parse_qs, urlparse

import pytest

from src.gmessages_proxy import rewrite_gmessages_html, rewrite_location
from src.phonepi import (
    gmessages_browser_url,
    phoneapp_public_url,
    phoneapp_setup_deeplink,
    phonepi_connect_hint,
    phonepi_enabled,
    phonepi_setup_deeplink,
    phonepi_ws_secret,
    verify_phonepi_ws_token,
)

_EXAMPLE_HOST = "example-host.tail123456.ts.net"
_EXAMPLE_ORIGIN = f"https://{_EXAMPLE_HOST}"


def test_phonepi_disabled_by_default(monkeypatch):
    monkeypatch.delenv("PHONEPI_ENABLED", raising=False)
    assert phonepi_enabled() is False


def test_phonepi_enabled_flag(monkeypatch):
    monkeypatch.setenv("PHONEPI_ENABLED", "true")
    assert phonepi_enabled() is True


def test_connect_hint_uses_tailscale_serve_origin(monkeypatch):
    monkeypatch.setenv("ALLOWED_ORIGINS", f"http://localhost,{_EXAMPLE_ORIGIN}")
    hint = phonepi_connect_hint()
    assert hint["host"] == _EXAMPLE_HOST
    assert hint["port"] == 443
    assert "token=" in hint["ws_url"]


def test_connect_hint_explicit_origin():
    hint = phonepi_connect_hint(_EXAMPLE_ORIGIN)
    assert hint["host"] == _EXAMPLE_HOST
    assert hint["port"] == 443
    assert hint["url"].endswith("/phonepi")


def test_phonepi_setup_deeplink_includes_ws_token(monkeypatch, tmp_path):
    monkeypatch.setenv("ODYSSEUS_DATA_DIR", str(tmp_path))
    monkeypatch.delenv("PHONEPI_WS_SECRET", raising=False)
    link = phonepi_setup_deeplink(phonepi_connect_hint(_EXAMPLE_ORIGIN))
    qs = parse_qs(urlparse(link).query)
    assert qs["token"] == [phonepi_ws_secret()]


def test_phoneapp_setup_deeplink_prefers_setup_code():
    link = phoneapp_setup_deeplink(url=_EXAMPLE_ORIGIN, setup_code="setup_abc", user="alice")
    qs = parse_qs(urlparse(link).query)
    assert qs["code"] == ["setup_abc"]
    assert "token" not in qs


def test_phonepi_setup_deeplink_uses_custom_scheme():
    hint = phonepi_connect_hint(_EXAMPLE_ORIGIN)
    link = phonepi_setup_deeplink(hint)
    parsed = urlparse(link)
    assert parsed.scheme == "phonepi"
    assert parsed.netloc == "setup"
    qs = parse_qs(parsed.query)
    assert qs["host"] == [_EXAMPLE_HOST]
    assert qs["port"] == ["443"]
    assert not link.startswith("wss://")


def test_phoneapp_setup_deeplink_carries_url_token_user():
    link = phoneapp_setup_deeplink(
        url=_EXAMPLE_ORIGIN,
        token="ody_test",
        user="belhun",
    )
    parsed = urlparse(link)
    assert parsed.scheme == "odyphone"
    assert parsed.netloc == "setup"
    qs = parse_qs(parsed.query)
    assert qs["url"] == [_EXAMPLE_ORIGIN]
    assert qs["token"] == ["ody_test"]
    assert qs["user"] == ["belhun"]


def test_phoneapp_public_url_strips_https_443():
    hint = phonepi_connect_hint(_EXAMPLE_ORIGIN)
    assert phoneapp_public_url(hint) == _EXAMPLE_ORIGIN


def test_verify_phonepi_ws_token(monkeypatch, tmp_path):
    monkeypatch.setenv("ODYSSEUS_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("PHONEPI_WS_SECRET", "secret123")
    assert verify_phonepi_ws_token("secret123") is True
    assert verify_phonepi_ws_token("wrong") is False


def test_phone_settings_markup_has_both_setup_qrs():
    html = Path("static/index.html").read_text(encoding="utf-8")
    assert 'id="phonepi-connect-qr"' in html
    assert 'id="gmessages-open-link"' in html
    js = Path("static/js/phonepiSettings.js").read_text(encoding="utf-8")
    assert "/phoneapp-setup" in js
    assert "messages_ui_url" in js


def test_gmessages_browser_url_uses_public_origin(monkeypatch):
    monkeypatch.setenv("ALLOWED_ORIGINS", f"http://localhost,https://{_EXAMPLE_HOST}")
    assert gmessages_browser_url() == f"https://{_EXAMPLE_HOST}/gmessages/"


def test_rewrite_gmessages_html_prefixes_api_paths():
    html = b"const API = ''; fetchJSON(`/api/conversations`); href=\"/favicon.svg\""
    out = rewrite_gmessages_html(html).decode()
    assert "`/gmessages/api/conversations`" in out
    assert 'href="/gmessages/favicon.svg"' in out
    assert "API + '/gmessages/api/mark-read'" not in out


def test_rewrite_location_adds_prefix():
    assert rewrite_location("/api/status") == "/gmessages/api/status"
    assert rewrite_location("/gmessages/") == "/gmessages/"


def test_gmessages_proxy_requires_admin(monkeypatch, tmp_path):
    monkeypatch.setenv("PHONEPI_ENABLED", "true")
    monkeypatch.setenv("AUTH_ENABLED", "false")
    monkeypatch.setenv("ODYSSEUS_DATA_DIR", str(tmp_path))
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from routes.phonepi_routes import setup_phonepi_routes

    app = FastAPI()
    app.include_router(setup_phonepi_routes())
    client = TestClient(app)
    res = client.get("/gmessages/", headers={"Accept": "text/html"})
    assert res.status_code == 503
    assert "Google Messages" in res.text


def test_gmessages_proxy_serves_html(monkeypatch, tmp_path):
    monkeypatch.setenv("PHONEPI_ENABLED", "true")
    monkeypatch.setenv("AUTH_ENABLED", "false")
    monkeypatch.setenv("ODYSSEUS_DATA_DIR", str(tmp_path))

    import httpx

    class FakeResponse:
        status_code = 200
        content = b"<html><script>fetch(`/api/status`)</script></html>"
        headers = {"content-type": "text/html; charset=utf-8"}

    class FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        async def request(self, *args, **kwargs):
            return FakeResponse()

    monkeypatch.setattr("src.gmessages_proxy._ensure_bridge_running", lambda: True)
    monkeypatch.setattr("src.gmessages_proxy.httpx.AsyncClient", lambda **kwargs: FakeClient())

    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from routes.phonepi_routes import setup_phonepi_routes

    app = FastAPI()
    app.include_router(setup_phonepi_routes())
    client = TestClient(app)
    res = client.get("/gmessages/", headers={"Accept": "text/html"})
    assert res.status_code == 200
    assert "/gmessages/api/status" in res.text


def test_phonepi_proxy_rejects_missing_token(monkeypatch, tmp_path):
    monkeypatch.setenv("PHONEPI_ENABLED", "true")
    monkeypatch.setenv("AUTH_ENABLED", "false")
    monkeypatch.setenv("ODYSSEUS_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("PHONEPI_WS_SECRET", "ws-secret")
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from routes.phonepi_routes import setup_phonepi_routes

    app = FastAPI()
    app.include_router(setup_phonepi_routes())
    client = TestClient(app)
    with pytest.raises(Exception):
        with client.websocket_connect("/phonepi"):
            pass
