"""Placeholder triage queue — list + convert + SKU conflict + hash route."""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest
from fastapi import FastAPI
from starlette.testclient import TestClient

from integrations.sysforge.db import connection as db_connection
from integrations.sysforge.db.migration_runner import ensure_schema
from integrations.sysforge.install import run_install
from integrations.sysforge.routes import setup_sysforge_routes
from integrations.sysforge.services import parts as parts_service

_REPO = Path(__file__).resolve().parent.parent
_JS = _REPO / "integrations" / "sysforge" / "static" / "js"
_HAS_NODE = shutil.which("node") is not None


def _file_url(path: Path) -> str:
    return path.resolve().as_uri()


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
    ensure_schema()
    return plugins_root


def _client(monkeypatch, tmp_path):
    _install_active(monkeypatch, tmp_path)
    app = FastAPI()
    app.include_router(setup_sysforge_routes())
    return TestClient(app)


@pytest.mark.area_routes
def test_triage_list_includes_usage(monkeypatch, tmp_path):
    _install_active(monkeypatch, tmp_path)
    ph_id = parts_service.add_part(
        {
            "name": "Odd Digitizer",
            "base_price_cents": 400,
            "is_placeholder": True,
        }
    )
    conn = db_connection.connect()
    try:
        cur = conn.execute(
            """
            INSERT INTO Invoices (
              Status, PartsSubtotalCents, LaborCostCents,
              ShippingCostCents, TaxAmountCents, FinalTotalCents
            ) VALUES ('Estimate', 0, 0, 0, 0, 0)
            """
        )
        inv_id = int(cur.lastrowid)
        conn.execute(
            """
            INSERT INTO InvoiceItems (
              InvoiceId, PartId, PartName, QuantityMilliunits,
              UnitPriceCents, LineTotalCents, ItemType
            ) VALUES (?, ?, 'Odd Digitizer', 1000, 400, 400, 'Part')
            """,
            (inv_id, ph_id),
        )
        conn.commit()
    finally:
        conn.close()

    items = parts_service.list_placeholder_triage()
    assert len(items) == 1
    assert items[0]["id"] == ph_id
    assert items[0]["usage_count"] == 1
    assert items[0]["is_placeholder"] is True


@pytest.mark.area_routes
def test_triage_convert_clears_placeholder(monkeypatch, tmp_path):
    client = _client(monkeypatch, tmp_path)
    ph_id = parts_service.add_part(
        {
            "name": "Temp Part",
            "base_price_cents": 100,
            "is_placeholder": True,
        }
    )
    res = client.post(
        f"/api/sysforge/parts/placeholders/{ph_id}/convert",
        json={
            "name": "Catalog Part",
            "sku": "CAT-99",
            "base_price_cents": 250,
            "is_placeholder": False,
        },
    )
    assert res.status_code == 204
    part = parts_service.get_part(ph_id)
    assert part is not None
    assert part["is_placeholder"] is False
    assert part["sku"] == "CAT-99"
    assert part["base_price_cents"] == 250
    hits = parts_service.search_parts("Catalog")
    assert any(h["id"] == ph_id and h["is_placeholder"] is False for h in hits)
    leftover = client.get("/api/sysforge/parts/placeholders")
    assert leftover.status_code == 200
    assert all(i["id"] != ph_id for i in leftover.json()["items"])


@pytest.mark.area_routes
def test_triage_convert_sku_conflict_409(monkeypatch, tmp_path):
    client = _client(monkeypatch, tmp_path)
    parts_service.add_part(
        {"name": "Existing", "sku": "TAKEN-1", "base_price_cents": 50}
    )
    ph_id = parts_service.add_part(
        {
            "name": "Placeholder Clash",
            "base_price_cents": 50,
            "is_placeholder": True,
        }
    )
    res = client.post(
        f"/api/sysforge/parts/placeholders/{ph_id}/convert",
        json={
            "name": "Placeholder Clash",
            "sku": "TAKEN-1",
            "base_price_cents": 50,
            "is_placeholder": False,
        },
    )
    assert res.status_code == 409
    body = res.json()
    assert body["code"] == "sku_conflict"
    assert body["conflicting_part"]["sku"] == "TAKEN-1"
    still = parts_service.get_part(ph_id)
    assert still["is_placeholder"] is True


@pytest.mark.skipif(not _HAS_NODE, reason="node binary not on PATH")
def test_parts_triage_hash_route():
    js = f"""
    import {{ buildHash, parseHash, ROUTE }} from '{_file_url(_JS / "routes-contract.js")}';
    const hash = buildHash(ROUTE.PARTS_TRIAGE);
    const parsed = parseHash(hash);
    const fromPath = parseHash('#sysforge/parts/triage');
    console.log(JSON.stringify({{ hash, parsed, fromPath, key: ROUTE.PARTS_TRIAGE }}));
    """
    proc = subprocess.run(
        ["node", "--input-type=module"],
        input=js,
        capture_output=True,
        text=True,
        cwd=str(_REPO),
        timeout=30,
    )
    assert proc.returncode == 0, proc.stderr or proc.stdout
    data = json.loads(proc.stdout.strip().splitlines()[-1])
    assert data["hash"] == "#sysforge/parts/triage"
    assert data["parsed"]["routeKey"] == "parts-triage"
    assert data["fromPath"]["routeKey"] == "parts-triage"
    assert data["key"] == "parts-triage"
