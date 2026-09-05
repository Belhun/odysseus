"""Invoice viewer return-context, history trim, save-as-new stack, price-compare."""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest
from fastapi import FastAPI
from starlette.testclient import TestClient

from integrations.sysforge.install import run_install
from integrations.sysforge.routes import setup_sysforge_routes

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


def _install_active(monkeypatch, tmp_path):
    plugins_root = tmp_path / "plugins"
    monkeypatch.setattr("src.plugins.registry.PLUGINS_DATA_ROOT", plugins_root)
    monkeypatch.setattr(
        "src.plugins.registry.plugin_data_dir", lambda pid: plugins_root / pid
    )
    monkeypatch.setattr("src.settings.FEATURES_FILE", str(tmp_path / "features.json"))
    result = run_install()
    assert result["ok"] is True
    monkeypatch.setattr("integrations.sysforge.routes.is_plugin_active", lambda _pid: True)
    return plugins_root


def _app_client(monkeypatch, tmp_path):
    _install_active(monkeypatch, tmp_path)
    app = FastAPI()
    app.include_router(setup_sysforge_routes())
    return TestClient(app)


@pytest.mark.skipif(not _HAS_NODE, reason="node binary not on PATH")
def test_capture_gate_viewer_edit_preserves_origin():
    js = f"""
    import {{
      captureIfStartingInvoiceFlow,
      peek,
      consume,
      _resetForTests,
    }} from '{_file_url(_JS / "invoice-return-context.js")}';

    _resetForTests();
    const fromClassic = captureIfStartingInvoiceFlow('client-dashboard', {{ clientId: 7 }});
    const afterClassic = peek();
    const fromViewer = captureIfStartingInvoiceFlow('invoice-view', {{ clientId: 99 }});
    const afterViewer = peek();
    const fromCalc = captureIfStartingInvoiceFlow('invoice-calculator', {{ clientId: 99 }});
    const afterCalc = peek();
    const taken = consume();
    const afterConsume = peek();

    console.log(JSON.stringify({{
      fromClassic,
      afterClassic,
      fromViewer,
      afterViewer,
      fromCalc,
      afterCalc,
      taken,
      afterConsume,
    }}));
    """
    data = _run_node(js)
    assert data["fromClassic"] is True
    assert data["afterClassic"]["originRoute"] == "client-dashboard"
    assert data["afterClassic"]["clientId"] == "7"
    assert data["fromViewer"] is False
    assert data["afterViewer"]["clientId"] == "7"
    assert data["fromCalc"] is False
    assert data["afterCalc"]["clientId"] == "7"
    assert data["taken"]["clientId"] == "7"
    assert data["afterConsume"] is None


@pytest.mark.skipif(not _HAS_NODE, reason="node binary not on PATH")
def test_trim_invoice_flow_from_history():
    js = f"""
    import * as router from '{_file_url(_JS / "router.js")}';

    router._resetForTests();
    const host = {{
      children: [],
      appendChild(el) {{ this.children.push(el); return el; }},
    }};
    router.mount(host, {{ syncHash: false }});
    for (const key of ['client-dashboard', 'invoice-calculator', 'invoice-view', 'dashboard']) {{
      router.register(key, {{
        title: key,
        mount: () => {{}},
        activate: () => {{}},
      }});
    }}

    router.navigate('client-dashboard', {{ params: {{ clientId: '7' }} }});
    router.navigate('invoice-calculator', {{ params: {{ invoiceId: '1' }} }});
    const mid = router.trimInvoiceFlowFromHistory();
    const afterCalcTrim = router._getHistoryForTests();

    router.navigate('invoice-calculator', {{ params: {{ invoiceId: '1' }} }});
    router.navigate('invoice-view', {{ params: {{ id: '2' }} }});
    const trimmed = router.trimInvoiceFlowFromHistory();
    const afterBoth = router._getHistoryForTests();

    console.log(JSON.stringify({{
      mid,
      afterCalcTrim,
      trimmed,
      afterBoth,
    }}));
    """
    data = _run_node(js)
    assert [h["routeKey"] for h in data["afterCalcTrim"]] == ["client-dashboard"]
    assert [h["routeKey"] for h in data["afterBoth"]] == ["client-dashboard"]
    assert data["afterBoth"][0]["params"].get("clientId") == "7"


@pytest.mark.skipif(not _HAS_NODE, reason="node binary not on PATH")
def test_save_as_new_nav_stack_leaves_classic_under_viewer():
    js = f"""
    import * as router from '{_file_url(_JS / "router.js")}';
    import {{ peek, _resetForTests as resetCtx }} from '{_file_url(_JS / "invoice-return-context.js")}';

    router._resetForTests();
    resetCtx();
    const host = {{
      children: [],
      appendChild(el) {{
        el._sysforgeClassic = {{ selectedClient: {{ id: 7, display_name: 'Ada' }} }};
        this.children.push(el);
        return el;
      }},
    }};
    router.mount(host, {{ syncHash: false }});
    for (const key of ['client-dashboard', 'invoice-calculator', 'invoice-view']) {{
      router.register(key, {{
        title: key,
        mount: () => {{}},
        activate: () => {{}},
      }});
    }}

    router.navigate('client-dashboard');
    router.navigateToInvoiceCalculatorEdit(42);
    const ctxAfterEdit = peek();
    router.navigateToViewerAfterSaveAsNew(99, 7);
    const state = router.getState();
    const history = router._getHistoryForTests();

    console.log(JSON.stringify({{
      ctxAfterEdit,
      routeKey: state.routeKey,
      params: state.params,
      history: history.map((h) => h.routeKey),
      underViewer: history.length >= 2 ? history[history.length - 2].routeKey : null,
    }}));
    """
    data = _run_node(js)
    assert data["ctxAfterEdit"]["originRoute"] == "client-dashboard"
    assert data["ctxAfterEdit"]["clientId"] == "7"
    assert data["routeKey"] == "invoice-view"
    assert data["params"]["id"] == "99"
    assert data["history"][-1] == "invoice-view"
    assert "invoice-calculator" not in data["history"]
    assert data["underViewer"] == "client-dashboard"


@pytest.mark.skipif(not _HAS_NODE, reason="node binary not on PATH")
def test_after_save_return_classic_and_fallback():
    js = f"""
    import * as router from '{_file_url(_JS / "router.js")}';
    import {{
      captureIfStartingInvoiceFlow,
      _resetForTests as resetCtx,
    }} from '{_file_url(_JS / "invoice-return-context.js")}';

    function setup() {{
      router._resetForTests();
      resetCtx();
      const host = {{
        children: [],
        appendChild(el) {{ this.children.push(el); return el; }},
      }};
      router.mount(host, {{ syncHash: false }});
      for (const key of ['client-dashboard', 'invoice-calculator', 'dashboard']) {{
        router.register(key, {{
          title: key,
          mount: () => {{}},
          activate: () => {{}},
        }});
      }}
    }}

    setup();
    router.navigate('client-dashboard', {{ params: {{ clientId: '3' }} }});
    captureIfStartingInvoiceFlow('client-dashboard', {{ clientId: 3 }});
    router.navigate('invoice-calculator', {{ params: {{ invoiceId: '10' }} }});
    router.navigateAfterInvoiceSave(3);
    const withCtx = {{
      routeKey: router.getState().routeKey,
      params: router.getState().params,
      history: router._getHistoryForTests().map((h) => h.routeKey),
    }};

    setup();
    router.navigate('invoice-calculator', {{ params: {{ invoiceId: '10' }} }});
    router.navigateAfterInvoiceSave(55);
    const fallback = {{
      routeKey: router.getState().routeKey,
      params: router.getState().params,
    }};

    console.log(JSON.stringify({{ withCtx, fallback }}));
    """
    data = _run_node(js)
    assert data["withCtx"]["routeKey"] == "client-dashboard"
    assert data["withCtx"]["params"]["clientId"] == "3"
    assert "invoice-calculator" not in data["withCtx"]["history"]
    assert data["fallback"]["routeKey"] == "client-dashboard"
    assert data["fallback"]["params"]["clientId"] == "55"


@pytest.mark.skipif(not _HAS_NODE, reason="node binary not on PATH")
def test_viewer_edit_route_emits_calculator_invoice_id():
    js = f"""
    import {{ buildInvoiceEditRoute, isForbiddenClientDashboardEditRoute }} from '{_file_url(_JS / "routes-contract.js")}';
    import * as router from '{_file_url(_JS / "router.js")}';
    import {{ peek, _resetForTests as resetCtx }} from '{_file_url(_JS / "invoice-return-context.js")}';

    router._resetForTests();
    resetCtx();
    const host = {{
      children: [],
      appendChild(el) {{
        el._sysforgeClassic = {{ selectedClient: {{ id: 7 }} }};
        this.children.push(el);
        return el;
      }},
    }};
    router.mount(host, {{ syncHash: false }});
    for (const key of ['client-dashboard', 'invoice-view', 'invoice-calculator']) {{
      router.register(key, {{ title: key, mount: () => {{}}, activate: () => {{}} }});
    }}

    router.navigate('client-dashboard');
    router.navigateToInvoiceViewer(12);
    const ctxBeforeEdit = peek();
    router.navigateToInvoiceCalculatorEdit(12);
    const ctxAfterEdit = peek();
    const edit = buildInvoiceEditRoute(12);
    const state = router.getState();

    console.log(JSON.stringify({{
      edit,
      forbidden: isForbiddenClientDashboardEditRoute(edit.routeKey),
      ctxBeforeEdit,
      ctxAfterEdit,
      routeKey: state.routeKey,
      params: state.params,
    }}));
    """
    data = _run_node(js)
    assert data["edit"]["routeKey"] == "invoice-calculator"
    assert data["edit"]["params"]["invoiceId"] == "12"
    assert data["forbidden"] is False
    assert data["ctxBeforeEdit"]["clientId"] == "7"
    assert data["ctxAfterEdit"]["clientId"] == "7"
    assert data["routeKey"] == "invoice-calculator"
    assert data["params"]["invoiceId"] == "12"


@pytest.mark.skipif(not _HAS_NODE, reason="node binary not on PATH")
def test_price_compare_pure_fn():
    js = f"""
    import {{
      compareLineToCatalog,
      flagPriceMismatches,
    }} from '{_file_url(_JS / "invoice-price-compare.js")}';

    const same = compareLineToCatalog(1500, 1500);
    const diff = compareLineToCatalog(1500, 1800);
    const flagged = flagPriceMismatches(
      [
        {{ id: 1, part_id: 10, unit_price_cents: 1000 }},
        {{ id: 2, part_id: 11, unit_price_cents: 2000 }},
        {{ id: 3, part_id: null, unit_price_cents: 500 }},
      ],
      new Map([[10, 1000], [11, 2500]])
    );

    console.log(JSON.stringify({{ same, diff, flagged }}));
    """
    data = _run_node(js)
    assert data["same"]["has_mismatch"] is False
    assert data["diff"]["has_mismatch"] is True
    assert data["flagged"][0]["has_price_mismatch"] is False
    assert data["flagged"][1]["has_price_mismatch"] is True
    assert data["flagged"][1]["catalog_price_cents"] == 2500
    assert data["flagged"][2]["has_price_mismatch"] is False


@pytest.mark.area_routes
def test_price_compare_endpoint_finalized_only(monkeypatch, tmp_path):
    with _app_client(monkeypatch, tmp_path) as client:
        part = client.post(
            "/api/sysforge/parts",
            json={
                "name": "Screen",
                "base_price_cents": 8900,
            },
        )
        assert part.status_code in (200, 201), part.text
        part_id = part.json()["id"]

        created_client = client.post(
            "/api/sysforge/clients",
            json={"first_name": "Sam", "last_name": "Lee"},
        )
        assert created_client.status_code == 201
        cid = created_client.json()["id"]

        inv = client.post(
            "/api/sysforge/invoices",
            json={
                "client_id": cid,
                "name": "Quote",
                "items": [
                    {
                        "part_id": part_id,
                        "part_name": "Screen",
                        "quantity_milliunits": 1000,
                        "unit_price_cents": 8900,
                        "item_type": "Part",
                        "is_taxable": True,
                    }
                ],
            },
        )
        assert inv.status_code == 201, inv.text
        iid = inv.json()["id"]

        estimate_cmp = client.get(f"/api/sysforge/invoices/{iid}/price-compare")
        assert estimate_cmp.status_code == 200
        assert estimate_cmp.json()["items"] == []

        # Drift catalog price, then finalize invoice.
        client.put(
            f"/api/sysforge/parts/{part_id}",
            json={
                "name": "Screen",
                "base_price_cents": 9900,
                "is_placeholder": False,
            },
        )
        finalized = client.put(
            f"/api/sysforge/invoices/{iid}",
            json={
                "client_id": cid,
                "name": "Quote",
                "is_finalized": True,
                "status": "Invoiced",
                "items": [
                    {
                        "part_id": part_id,
                        "part_name": "Screen",
                        "quantity_milliunits": 1000,
                        "unit_price_cents": 8900,
                        "item_type": "Part",
                        "is_taxable": True,
                    }
                ],
            },
        )
        assert finalized.status_code == 200, finalized.text
        assert finalized.json()["is_finalized"] is True

        cmp = client.get(f"/api/sysforge/invoices/{iid}/price-compare")
        assert cmp.status_code == 200
        rows = cmp.json()["items"]
        assert len(rows) == 1
        assert rows[0]["has_mismatch"] is True
        assert rows[0]["unit_price_cents"] == 8900
        assert rows[0]["catalog_price_cents"] == 9900
        assert rows[0]["part_id"] == part_id


def test_return_context_modules_exist():
    assert (_JS / "invoice-return-context.js").is_file()
    assert (_JS / "invoice-price-compare.js").is_file()
    router = (_JS / "router.js").read_text(encoding="utf-8")
    assert "navigateToViewerAfterSaveAsNew" in router
    assert "navigateAfterInvoiceSave" in router
    assert "trimInvoiceFlowFromHistory" in router
    calc = (_JS / "views" / "calculator.js").read_text(encoding="utf-8")
    assert "navigateToViewerAfterSaveAsNew" in calc
    assert "navigateAfterInvoiceSave" in calc
    viewer = (_JS / "views" / "invoice-viewer.js").read_text(encoding="utf-8")
    assert "Read-only view" in viewer
    assert "price-compare" in viewer
