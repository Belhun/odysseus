"""SysForge nav lifecycle + View/Edit route contracts (JS pure + router apply)."""

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
    """Node ESM on Windows needs file:// URLs, not bare drive paths."""
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
def test_view_edit_route_builders_never_emit_invoice_edit():
    js = f"""
    import {{
      buildInvoiceViewRoute,
      buildInvoiceEditRoute,
      buildNewInvoiceRoute,
      buildHash,
      parseHash,
      isForbiddenClientDashboardEditRoute,
      ROUTE,
    }} from '{_file_url(_JS / "routes-contract.js")}';

    const view = buildInvoiceViewRoute(42);
    const edit = buildInvoiceEditRoute(42);
    const neu = buildNewInvoiceRoute(7);
    const viewHash = buildHash(view.routeKey, view.params);
    const editHash = buildHash(edit.routeKey, edit.params);
    const parsedView = parseHash(viewHash);
    const parsedEdit = parseHash(editHash);

    console.log(JSON.stringify({{
      viewRoute: view.routeKey,
      viewParams: view.params,
      editRoute: edit.routeKey,
      editParams: edit.params,
      newRoute: neu.routeKey,
      newParams: neu.params,
      viewHash,
      editHash,
      parsedView,
      parsedEdit,
      editIsForbidden: isForbiddenClientDashboardEditRoute(edit.routeKey),
      invoiceEditForbidden: isForbiddenClientDashboardEditRoute('invoice-edit'),
      calculatorKey: ROUTE.INVOICE_CALCULATOR,
    }}));
    """
    data = _run_node(js)
    assert data["viewRoute"] == "invoice-view"
    assert data["viewParams"] == {"id": "42"}
    assert data["editRoute"] == "invoice-calculator"
    assert data["editParams"] == {"invoiceId": "42"}
    assert data["newRoute"] == "invoice-calculator"
    assert data["newParams"] == {"clientId": "7"}
    assert "invoice-edit" not in data["editHash"]
    assert data["viewHash"] == "#sysforge/invoice-view/42"
    assert "invoiceId=42" in data["editHash"]
    assert data["parsedView"]["routeKey"] == "invoice-view"
    assert data["parsedView"]["params"]["id"] == "42"
    assert data["parsedEdit"]["routeKey"] == "invoice-calculator"
    assert data["parsedEdit"]["params"]["invoiceId"] == "42"
    assert data["editIsForbidden"] is False
    assert data["invoiceEditForbidden"] is True


@pytest.mark.skipif(not _HAS_NODE, reason="node binary not on PATH")
def test_same_surface_reapply_does_not_unbind_shell_handlers():
    js = f"""
    import * as router from '{_file_url(_JS / "router.js")}';
    import {{ isSameSurface, makeSurface, shouldUnbindShellHandlers }} from '{_file_url(_JS / "panel-lifecycle.js")}';

    router._resetForTests();

    const host = {{ children: [], appendChild(el) {{ this.children.push(el); return el; }} }};
    let bindCount = 0;
    let unbindCount = 0;
    let activateCount = 0;
    let deactivateCount = 0;
    let clickCount = 0;

    router.mount(host, {{
      syncHash: false,
      onShellBind: () => {{ bindCount += 1; }},
      onShellUnbind: () => {{ unbindCount += 1; }},
    }});

    router.register('dashboard', {{
      title: 'Shop home',
      mount: (el) => {{
        el._click = () => {{ clickCount += 1; }};
      }},
      activate: () => {{ activateCount += 1; }},
      deactivate: () => {{ deactivateCount += 1; }},
    }});

    router.register('clients', {{
      title: 'Clients',
      mount: () => {{}},
      activate: () => {{}},
      deactivate: () => {{}},
    }});

    router.navigate('dashboard', {{ replace: true }});
    const first = router.getCurrent();
    const ctrl = host.children[0];

    // Double apply same controller (ViewChanged + NavigateToItemDirect mirror).
    router.applyNavigation('dashboard', {{}}, {{ replace: true }});
    router.applyNavigation('dashboard', {{}}, {{ replace: true }});

    const same = isSameSurface(
      makeSurface('dashboard', {{}}, ctrl),
      makeSurface('dashboard', {{}}, ctrl),
    );
    const shouldUnbind = shouldUnbindShellHandlers(
      makeSurface('dashboard', {{}}, ctrl),
      makeSurface('dashboard', {{}}, ctrl),
    );

    // Card click still works on cached controller.
    ctrl._click();

    // Navigate away and back — handlers re-bind; click still works.
    router.navigate('clients');
    router.navigate('dashboard');
    ctrl._click();

    const histLenBefore = router.getState().historyLength;
    router.applyNavigation('dashboard', {{}}, {{ replace: true }});
    const histLenAfter = router.getState().historyLength;

    console.log(JSON.stringify({{
      bindCount,
      unbindCount,
      activateCount,
      deactivateCount,
      clickCount,
      same,
      shouldUnbind,
      firstRoute: first.routeKey,
      histLenBefore,
      histLenAfter,
      cacheSize: router.getState().cacheSize,
    }}));
    """
    data = _run_node(js)
    assert data["same"] is True
    assert data["shouldUnbind"] is False
    # bind: dashboard enter, clients enter, dashboard re-enter (not on re-apply)
    assert data["bindCount"] == 3
    assert data["unbindCount"] == 2
    assert data["clickCount"] >= 2  # card still fires after double-apply and round-trip
    assert data["histLenBefore"] == data["histLenAfter"]
    assert data["activateCount"] >= 3  # enter + 2 reapplies + re-enter


@pytest.mark.skipif(not _HAS_NODE, reason="node binary not on PATH")
def test_param_change_invoice_view_and_hash_round_trip():
    js = f"""
    import * as router from '{_file_url(_JS / "router.js")}';
    import {{ buildHash, parseHash }} from '{_file_url(_JS / "routes-contract.js")}';

    router._resetForTests();
    const host = {{ children: [], appendChild(el) {{ this.children.push(el); return el; }} }};
    const activates = [];
    const deactivates = [];

    router.mount(host, {{ syncHash: false }});
    router.register('invoice-view', {{
      title: 'Invoice',
      mount: () => {{}},
      activate: (_el, params) => activates.push({{ ...params }}),
      deactivate: () => deactivates.push(1),
    }});

    router.navigate('invoice-view', {{ params: {{ id: '1' }} }});
    router.navigate('invoice-view', {{ params: {{ id: '2' }} }});
    const hash = buildHash('invoice-view', {{ id: '2' }});
    const parsed = parseHash(hash);
    router.applyFromHash(hash);

    console.log(JSON.stringify({{
      activates,
      deactivateCount: deactivates.length,
      current: router.getCurrent(),
      hash,
      parsed,
      cacheSize: router.getState().cacheSize,
    }}));
    """
    data = _run_node(js)
    assert data["activates"][0]["id"] == "1"
    assert data["activates"][1]["id"] == "2"
    assert data["deactivateCount"] >= 1
    assert data["current"]["routeKey"] == "invoice-view"
    assert data["current"]["params"]["id"] == "2"
    assert data["hash"] == "#sysforge/invoice-view/2"
    assert data["cacheSize"] >= 2


@pytest.mark.skipif(not _HAS_NODE, reason="node binary not on PATH")
def test_history_back_no_extra_push_on_reapply():
    js = f"""
    import * as router from '{_file_url(_JS / "router.js")}';

    router._resetForTests();
    const host = {{ children: [], appendChild(el) {{ this.children.push(el); return el; }} }};
    router.mount(host, {{ syncHash: false }});
    for (const id of ['dashboard', 'clients', 'drafts']) {{
      router.register(id, {{ title: id, mount: () => {{}}, activate: () => {{}} }});
    }}

    router.navigate('dashboard', {{ replace: true }});
    router.navigate('clients');
    router.navigate('drafts');
    const mid = router.getState().historyLength;
    router.back();
    const afterBack = router.getCurrent();
    const lenAfterBack = router.getState().historyLength;
    router.applyNavigation('clients', {{}}, {{ replace: true }});
    const lenAfterReapply = router.getState().historyLength;

    console.log(JSON.stringify({{
      mid,
      afterBack,
      lenAfterBack,
      lenAfterReapply,
    }}));
    """
    data = _run_node(js)
    assert data["mid"] == 3
    assert data["afterBack"]["routeKey"] == "clients"
    assert data["lenAfterBack"] == 2
    assert data["lenAfterReapply"] == 2


@pytest.mark.skipif(not _HAS_NODE, reason="node binary not on PATH")
def test_lru_cache_does_not_evict_fresh_panel_before_touch():
    """Regression: new panels used lastUsed=0 so _evictIfNeeded dropped them immediately."""
    js = f"""
    import * as router from '{_file_url(_JS / "router.js")}';

    router._resetForTests();
    const host = {{ children: [], appendChild(el) {{ this.children.push(el); return el; }} }};
    router.mount(host, {{ syncHash: false }});

    const ids = [
      'dashboard',
      'settings',
      'diagnostics',
      'clients',
      'client-dashboard',
      'client-merge',
      'invoices-outstanding',
    ];
    for (const id of ids) {{
      router.register(id, {{
        title: id,
        mount: (el) => {{ el.textContent = id; }},
        activate: () => {{}},
      }});
    }}

    for (const id of ids) {{
      router.navigate(id);
    }}

    const current = router.getCurrent();
    const visible = host.children.filter((el) => !el.hidden);
  const mergeEl = host.children.find((el) => el.dataset.route === 'client-merge');

    console.log(JSON.stringify({{
      currentRoute: current?.routeKey,
      visibleCount: visible.length,
      visibleRoute: visible[0]?.dataset?.route || null,
      mergeInDom: Boolean(mergeEl),
      mergeHidden: mergeEl?.hidden ?? null,
      hostChildCount: host.children.length,
      cacheSize: router.getState().cacheSize,
    }}));
    """
    data = _run_node(js)
    assert data["currentRoute"] == "invoices-outstanding"
    assert data["visibleCount"] == 1
    assert data["visibleRoute"] == "invoices-outstanding"
    assert data["mergeInDom"] is True
    assert data["mergeHidden"] is True
    assert data["cacheSize"] == 5


def test_shell_source_wires_view_edit_contracts():
    index = (_JS / "index.js").read_text(encoding="utf-8")
    viewer = (_JS / "views" / "invoice-viewer.js").read_text(encoding="utf-8")
    client_dash = (_JS / "views" / "client-dashboard.js").read_text(encoding="utf-8")
    contract = (_JS / "routes-contract.js").read_text(encoding="utf-8")

    assert "invoice-view" in index
    assert "invoice-calculator" in index
    assert "client-dashboard" in index
    assert "buildInvoiceEditRoute" in viewer
    assert "buildInvoiceViewRoute" in client_dash
    assert "buildInvoiceEditRoute" in client_dash
    assert "INVOICE_CALCULATOR" in contract
    assert "buildInvoiceEditRoute" in contract
    # Edit helper must return calculator, not a dedicated edit page.
    assert "routeKey:ROUTE.INVOICE_CALCULATOR" in contract.replace(" ", "")
    assert (_JS / "panel-lifecycle.js").is_file()
    assert (_JS / "router.js").is_file()
