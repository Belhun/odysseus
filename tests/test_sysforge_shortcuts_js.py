"""Host-registered Business shortcuts (open_sysforge + in-Business actions).

Pins defaults in keyboard-shortcuts.js / Settings catalog, and the pure
action → route map in sysforge-shortcuts.js. No plugin-local keybind store.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parent.parent
_KB = _REPO / "static" / "js" / "keyboard-shortcuts.js"
_SETTINGS = _REPO / "static" / "js" / "settings.js"
_SHORTCUTS = (
    _REPO / "integrations" / "sysforge" / "static" / "js" / "sysforge-shortcuts.js"
)
_HAS_NODE = shutil.which("node") is not None

_ACTIONS = ("sysforge_home", "sysforge_clients", "sysforge_calculator")


def _file_url(path: Path) -> str:
    return path.resolve().as_uri()


def _run_node(script: str) -> dict:
    proc = subprocess.run(
        ["node", "--input-type=module"],
        input=script,
        capture_output=True,
        text=True,
        cwd=str(_REPO),
        timeout=30,
    )
    assert proc.returncode == 0, proc.stderr or proc.stdout
    line = proc.stdout.strip().splitlines()[-1]
    return json.loads(line)


@pytest.mark.skipif(not _HAS_NODE, reason="node binary not on PATH")
def test_default_keybinds_include_sysforge_actions_unbound():
    js = f"""
    import {{ _defaultKeybinds }} from '{_file_url(_KB)}';
    console.log(JSON.stringify({{
      open_sysforge: _defaultKeybinds.open_sysforge,
      sysforge_home: _defaultKeybinds.sysforge_home,
      sysforge_clients: _defaultKeybinds.sysforge_clients,
      sysforge_calculator: _defaultKeybinds.sysforge_calculator,
    }}));
    """
    data = _run_node(js)
    assert data["open_sysforge"] == ""
    for action in _ACTIONS:
        assert data[action] == "", action


@pytest.mark.skipif(not _HAS_NODE, reason="node binary not on PATH")
def test_sysforge_shortcut_targets():
    js = f"""
    import {{ sysforgeShortcutTarget, SYSFORGE_SHORTCUT_ACTIONS }} from '{_file_url(_SHORTCUTS)}';
    import {{ ROUTE }} from '{_file_url(_SHORTCUTS.parent / "routes-contract.js")}';
    console.log(JSON.stringify({{
      actions: SYSFORGE_SHORTCUT_ACTIONS,
      home: sysforgeShortcutTarget('sysforge_home'),
      clients: sysforgeShortcutTarget('sysforge_clients'),
      calc: sysforgeShortcutTarget('sysforge_calculator'),
      unknown: sysforgeShortcutTarget('nope'),
      routes: {{
        clients: ROUTE.CLIENT_DASHBOARD,
        calc: ROUTE.INVOICE_CALCULATOR,
      }},
    }}));
    """
    data = _run_node(js)
    assert list(data["actions"]) == list(_ACTIONS)
    assert data["home"] == {"kind": "home"}
    assert data["clients"] == {
        "kind": "navigate",
        "routeId": data["routes"]["clients"],
    }
    assert data["clients"]["routeId"] == "client-dashboard"
    assert data["calc"] == {
        "kind": "navigate",
        "routeId": data["routes"]["calc"],
    }
    assert data["calc"]["routeId"] == "invoice-calculator"
    assert data["unknown"] is None


def test_settings_catalog_lists_sysforge_actions():
    text = _SETTINGS.read_text(encoding="utf-8")
    for action in ("open_sysforge", *_ACTIONS):
        assert f"{action}:" in text or f"'{action}'" in text, action
        assert re.search(rf"['\"]{re.escape(action)}['\"]", text), action
    # Hidden when features.sysforge is off (same gate as open_sysforge).
    assert "action.startsWith('sysforge_')" in text
    assert "Open Business" in text
    assert "Business dashboard" in text
    assert "Business clients" in text
    assert "Business calculator" in text


def test_keyboard_handler_wires_sysforge_actions():
    text = _KB.read_text(encoding="utf-8")
    for action in _ACTIONS:
        assert f"'{action}'" in text, action
    assert "runSysforgeShortcut" in text
    assert "_pluginFeaturesOff" in text
