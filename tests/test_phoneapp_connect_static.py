"""PhoneApp Connect contract: login path, empty token, MagicDNS map."""

from pathlib import Path

_REPO = Path(__file__).resolve().parent.parent
_APP = _REPO / "PhoneApp"


def _read(rel: str) -> str:
    return (_APP / rel).read_text(encoding="utf-8")


def test_phoneapp_posts_auth_login_not_api_login():
    source = _read("lib/ody_client.dart") + _read("lib/connect_screen.dart")
    assert "/api/auth/login" in source
    assert '"/api/login"' not in source
    assert "'/api/login'" not in source


def test_empty_token_does_not_password_login():
    connect = _read("lib/connect_logic.dart") + _read("lib/ody_client.dart")
    assert "validateToken" in connect
    assert "Paste an ody_ API token" in connect
    assert "connectWithToken" in connect
    assert "loginWithPassword" in connect
    token_fn = connect.split("Future<FinanceConnectResult> connectWithToken", 1)[1]
    token_fn = token_fn.split("Future<FinanceConnectResult> loginWithPassword", 1)[0]
    assert "loginPath" not in token_fn
    assert "validateToken" in token_fn


def test_io_factory_uses_deploy_config_not_hardcoded_hosts():
    io = (
        _read("lib/ody_http_factory_io.dart")
        + _read("lib/deploy_config.dart")
        + _read("lib/connect_logic.dart")
    )
    assert "DeployConfig" in io
    assert "dell-mini-pc" not in io
    assert "tailcbcc46" not in io
    assert "100.79.4.36" not in io
