"""Contract tests for manage_sysforge (Phase 0)."""

import json

import pytest

from integrations.sysforge.install import run_install
from src.tools.sysforge import do_manage_sysforge, _dollars_to_cents, _fmt_cents
from src.tools.sysforge_constants import action_help_text, not_implemented_message


@pytest.fixture()
def sysforge_env(monkeypatch, tmp_path):
    plugins_root = tmp_path / "plugins"
    monkeypatch.setattr("src.plugins.registry.PLUGINS_DATA_ROOT", plugins_root)
    monkeypatch.setattr("src.plugins.registry.plugin_data_dir", lambda pid: plugins_root / pid)
    monkeypatch.setattr("src.settings.FEATURES_FILE", str(tmp_path / "features.json"))
    run_install()
    monkeypatch.setattr("integrations.sysforge.routes.is_plugin_active", lambda _pid: True)
    yield {"owner": "alice"}


@pytest.mark.asyncio
async def test_plugin_inactive():
    import src.plugins.registry as reg

    original = reg.is_plugin_active

    def _off(pid):
        return False if pid == "sysforge" else original(pid)

    reg.is_plugin_active = _off
    try:
        result = await do_manage_sysforge(json.dumps({"action": "status"}), owner="alice")
        assert result["exit_code"] == 1
        assert "not installed" in result["error"].lower()
    finally:
        reg.is_plugin_active = original


def test_dollar_to_cent_conversion():
    assert _dollars_to_cents(0.01, "x") == 1
    assert _dollars_to_cents(19.99, "x") == 1999
    assert _dollars_to_cents(-1.5, "x") == -150


def test_action_help_known():
    text = action_help_text("client_search")
    assert "client_search" in text


def test_action_help_unknown():
    text = action_help_text("not_a_real_action_xyz")
    assert "Unknown topic" in text


def test_not_implemented_message():
    msg = not_implemented_message("fake_future_action")
    assert "phase" in msg


@pytest.mark.asyncio
async def test_action_help_tool(sysforge_env):
    result = await do_manage_sysforge(
        json.dumps({"action": "action_help", "topic": "outstanding_list"}),
        owner=sysforge_env["owner"],
    )
    assert result["exit_code"] == 0
    assert "outstanding" in result["response"].lower()


@pytest.mark.asyncio
async def test_ui_control_business_panel():
    from src.ai_interaction import do_ui_control

    result = await do_ui_control("open_panel business route=invoices-outstanding id=42")
    assert result.get("ui_event") == "open_panel"
    assert result.get("panel") == "business"
    assert result.get("route") == "invoices-outstanding"
    assert result.get("entity_id") == "42"
