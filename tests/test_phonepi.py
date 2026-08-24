"""PhonePi optional builtin: connect hint, enable flag, WS proxy, Messages QR files."""

from pathlib import Path
from urllib.parse import parse_qs, urlparse

from src.phonepi import (
    phoneapp_public_url,
    phoneapp_setup_deeplink,
    phonepi_connect_hint,
    phonepi_enabled,
    phonepi_setup_deeplink,
)


def test_phonepi_disabled_by_default(monkeypatch):
    monkeypatch.delenv("PHONEPI_ENABLED", raising=False)
    assert phonepi_enabled() is False


def test_phonepi_enabled_flag(monkeypatch):
    monkeypatch.setenv("PHONEPI_ENABLED", "true")
    assert phonepi_enabled() is True


def test_connect_hint_uses_tailscale_serve_origin(monkeypatch):
    monkeypatch.setenv(
        "ALLOWED_ORIGINS",
        "http://localhost,https://dell-mini-pc.tailcbcc46.ts.net",
    )
    hint = phonepi_connect_hint()
    assert hint["host"] == "dell-mini-pc.tailcbcc46.ts.net"
    assert hint["port"] == 443
    assert hint["path"] == "/phonepi"
    assert hint["scheme"] == "wss"
    assert hint["url"] == "wss://dell-mini-pc.tailcbcc46.ts.net:443/phonepi"


def test_connect_hint_explicit_origin():
    hint = phonepi_connect_hint("https://dell-mini-pc.tailcbcc46.ts.net")
    assert hint["host"] == "dell-mini-pc.tailcbcc46.ts.net"
    assert hint["port"] == 443
    assert hint["url"].endswith("/phonepi")


def test_connect_hint_loopback_http():
    hint = phonepi_connect_hint("http://127.0.0.1:7000")
    assert hint["host"] == "127.0.0.1"
    assert hint["port"] == 7000
    assert hint["scheme"] == "ws"
    assert hint["url"] == "ws://127.0.0.1:7000/phonepi"


def test_phonepi_setup_deeplink_uses_custom_scheme():
    hint = phonepi_connect_hint("https://dell-mini-pc.tailcbcc46.ts.net")
    link = phonepi_setup_deeplink(hint)
    parsed = urlparse(link)
    assert parsed.scheme == "phonepi"
    assert parsed.netloc == "setup"
    qs = parse_qs(parsed.query)
    assert qs["host"] == ["dell-mini-pc.tailcbcc46.ts.net"]
    assert qs["port"] == ["443"]
    assert not link.startswith("wss://")


def test_phoneapp_setup_deeplink_carries_url_token_user():
    link = phoneapp_setup_deeplink(
        url="https://dell-mini-pc.tailcbcc46.ts.net",
        token="ody_test",
        user="belhun",
    )
    parsed = urlparse(link)
    assert parsed.scheme == "odyphone"
    assert parsed.netloc == "setup"
    qs = parse_qs(parsed.query)
    assert qs["url"] == ["https://dell-mini-pc.tailcbcc46.ts.net"]
    assert qs["token"] == ["ody_test"]
    assert qs["user"] == ["belhun"]


def test_phoneapp_public_url_strips_https_443():
    hint = phonepi_connect_hint("https://dell-mini-pc.tailcbcc46.ts.net")
    assert phoneapp_public_url(hint) == "https://dell-mini-pc.tailcbcc46.ts.net"


def test_phone_settings_markup_has_both_setup_qrs():
    html = Path("static/index.html").read_text(encoding="utf-8")
    assert 'id="phonepi-connect-qr"' in html
    assert 'id="phonepi-deeplink"' in html
    assert 'id="phoneapp-setup-qr"' in html
    assert 'id="phoneapp-mint-qr-btn"' in html
    js = Path("static/js/phonepiSettings.js").read_text(encoding="utf-8")
    assert "/phoneapp-setup" in js


def test_phonepi_stdio_skipped_when_disabled(monkeypatch):
    monkeypatch.setenv("PHONEPI_ENABLED", "false")
    from src.builtin_mcp import phonepi_stdio_kwargs

    assert phonepi_stdio_kwargs("/app") is None


def test_gmessages_start_pair_without_binary(tmp_path, monkeypatch):
    monkeypatch.setenv("PHONEPI_GMESSAGES_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("PHONEPI_GMESSAGES_BIN", str(tmp_path / "missing-bin"))
    from src.gmessages_bridge import is_paired, start_pair

    assert is_paired() is False
    result = start_pair()
    assert result["ok"] is False
    assert "binary" in result["error"].lower()


def test_gmessages_read_pair_status_from_files(tmp_path, monkeypatch):
    monkeypatch.setenv("PHONEPI_GMESSAGES_DATA_DIR", str(tmp_path))
    from src.gmessages_bridge import read_pair_status

    (tmp_path / "qr-url.txt").write_text("https://support.google.com/messages/?p=web_computer\n", encoding="utf-8")
    (tmp_path / "pair-status.json").write_text(
        '{"state":"waiting","url":"https://support.google.com/messages/?p=web_computer"}',
        encoding="utf-8",
    )
    status = read_pair_status()
    assert status["state"] == "waiting"
    assert status["url"].startswith("https://")
    assert status["paired"] is False


def test_phonepi_proxy_closes_when_disabled(monkeypatch):
    monkeypatch.setenv("PHONEPI_ENABLED", "false")
    monkeypatch.setenv("AUTH_ENABLED", "false")
    from fastapi.testclient import TestClient
    from routes.phonepi_routes import setup_phonepi_routes
    from fastapi import FastAPI

    app = FastAPI()
    app.include_router(setup_phonepi_routes())
    client = TestClient(app)
    with client.websocket_connect("/phonepi") as ws:
        msg = ws.receive()
    assert msg.get("type") == "websocket.close"
    assert msg.get("code") == 1008
