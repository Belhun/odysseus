"""Classic Client Dashboard selection / overlay / MRU contracts."""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parent.parent
_JS = _REPO / "integrations" / "sysforge" / "static" / "js"
_HAS_NODE = shutil.which("node") is not None


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
def test_clear_search_keeps_selected_client():
    js = f"""
    import {{
      clearSearchQuery,
      pickClientFromSearch,
    }} from '{_file_url(_JS / "classic-selection.js")}';

    const client = {{ id: 7, display_name: 'Ada Lovelace' }};
    let state = {{
      selectedClient: null,
      searchListSelection: null,
      searchQuery: '',
      overlayOpen: false,
    }};
    state = pickClientFromSearch(state, client);
    state = clearSearchQuery(state);

    console.log(JSON.stringify({{
      selectedId: state.selectedClient?.id,
      searchListSelection: state.searchListSelection,
      searchQuery: state.searchQuery,
    }}));
    """
    data = _run_node(js)
    assert data["selectedId"] == 7
    assert data["searchListSelection"] is None
    assert data["searchQuery"] == ""


@pytest.mark.skipif(not _HAS_NODE, reason="node binary not on PATH")
def test_overlay_guard_when_query_equals_display_name():
    js = f"""
    import {{ shouldOpenClassicOverlay }} from '{_file_url(_JS / "classic-selection.js")}';

    const client = {{ id: 1, display_name: 'Ada Lovelace' }};
    console.log(JSON.stringify({{
      closed: shouldOpenClassicOverlay('Ada Lovelace', client),
      closedCi: shouldOpenClassicOverlay('ada lovelace', client),
      openOnEdit: shouldOpenClassicOverlay('Ada Lovelac', client),
      openEmpty: shouldOpenClassicOverlay('', client),
      openNoClient: shouldOpenClassicOverlay('Ada', null),
    }}));
    """
    data = _run_node(js)
    assert data["closed"] is False
    assert data["closedCi"] is False
    assert data["openOnEdit"] is True
    assert data["openEmpty"] is True
    assert data["openNoClient"] is True


@pytest.mark.skipif(not _HAS_NODE, reason="node binary not on PATH")
def test_session_recent_mru_cap_six():
    js = f"""
    import {{
      trackRecentClient,
      seedRecentIfEmpty,
      MAX_RECENT_CLIENTS,
    }} from '{_file_url(_JS / "classic-selection.js")}';

    let recent = [];
    for (let i = 1; i <= 8; i++) {{
      recent = trackRecentClient(recent, {{ id: i, display_name: 'C' + i }});
    }}
    // Re-pick id 3 moves to front
    recent = trackRecentClient(recent, {{ id: 3, display_name: 'C3' }});
    const seeded = seedRecentIfEmpty([], [
      {{ id: 10 }}, {{ id: 11 }}, {{ id: 12 }}, {{ id: 13 }},
      {{ id: 14 }}, {{ id: 15 }}, {{ id: 16 }},
    ]);
    const already = seedRecentIfEmpty([{{ id: 99 }}], [{{ id: 1 }}]);

    console.log(JSON.stringify({{
      max: MAX_RECENT_CLIENTS,
      len: recent.length,
      ids: recent.map((c) => c.id),
      seededIds: seeded.map((c) => c.id),
      alreadyIds: already.map((c) => c.id),
    }}));
    """
    data = _run_node(js)
    assert data["max"] == 6
    assert data["len"] == 6
    assert data["ids"][0] == 3
    assert 1 not in data["ids"]  # oldest dropped
    assert data["seededIds"] == [10, 11, 12, 13, 14, 15]
    assert data["alreadyIds"] == [99]


@pytest.mark.skipif(not _HAS_NODE, reason="node binary not on PATH")
def test_classic_is_single_panel_surface():
    js = f"""
    import {{ panelCacheKey, ROUTE, buildClientDashboardRoute }} from '{_file_url(_JS / "routes-contract.js")}';

    const a = panelCacheKey(ROUTE.CLIENT_DASHBOARD, {{ clientId: '1' }});
    const b = panelCacheKey(ROUTE.CLIENT_DASHBOARD, {{ clientId: '2' }});
    const c = panelCacheKey(ROUTE.CLIENT_DASHBOARD, {{}});
    const route = buildClientDashboardRoute(9);

    console.log(JSON.stringify({{ a, b, c, route }}));
    """
    data = _run_node(js)
    assert data["a"] == data["b"] == data["c"] == "client-dashboard"
    assert data["route"]["routeKey"] == "client-dashboard"
    assert data["route"]["params"]["clientId"] == "9"


@pytest.mark.skipif(not _HAS_NODE, reason="node binary not on PATH")
def test_classic_activate_refreshes_without_client_id_param():
    """Back from viewer: same Classic surface; activate refreshes invoices."""
    js = f"""
    import * as router from '{_file_url(_JS / "router.js")}';

    router._resetForTests();
    const host = {{ children: [], appendChild(el) {{ this.children.push(el); return el; }} }};
    const activates = [];
    let invoiceLoads = 0;

    router.mount(host, {{ syncHash: false }});
    router.register('client-dashboard', {{
      title: 'Classic',
      mount: (el) => {{
        el._selectedClient = {{ id: 5, display_name: 'Ada' }};
        el._loadInvoices = () => {{ invoiceLoads += 1; }};
      }},
      activate: (el, params) => {{
        activates.push({{ ...params }});
        if (el._selectedClient) el._loadInvoices();
      }},
    }});
    router.register('invoice-view', {{
      title: 'View',
      mount: () => {{}},
      activate: () => {{}},
    }});

    router.navigate('client-dashboard', {{ replace: true }});
    router.navigate('invoice-view', {{ params: {{ id: '42' }} }});
    router.back();

    console.log(JSON.stringify({{
      activates,
      invoiceLoads,
      current: router.getCurrent(),
      cacheSize: router.getState().cacheSize,
    }}));
    """
    data = _run_node(js)
    assert data["current"]["routeKey"] == "client-dashboard"
    assert data["invoiceLoads"] >= 2  # enter + back
    assert data["cacheSize"] >= 1


def test_classic_shell_wires_clients_card_and_view_edit():
    index = (_JS / "index.js").read_text(encoding="utf-8")
    dash = (_JS / "views" / "dashboard.js").read_text(encoding="utf-8")
    classic = (_JS / "views" / "client-dashboard.js").read_text(encoding="utf-8")
    css = (
        _REPO / "integrations" / "sysforge" / "static" / "css" / "shell.css"
    ).read_text(encoding="utf-8")

    assert "route: 'client-dashboard'" in dash or 'route: "client-dashboard"' in dash
    assert "client-dashboard" in index
    assert "buildInvoiceViewRoute" in classic
    assert "buildInvoiceEditRoute" in classic
    assert "shouldOpenClassicOverlay" in classic or "classic-selection" in classic
    assert "sysforge-classic-grid" in css
    assert "Create project from invoice" not in classic or "disabled" in classic.lower()
    # No Add New on Classic overlay path
    assert "no Add New" in classic.lower() or "matches only" in classic.lower()
