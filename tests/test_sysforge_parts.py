"""Parts CRUD, search, SKU conflict — SysForge PartService parity."""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from starlette.testclient import TestClient

from integrations.sysforge.db import connection as db_connection
from integrations.sysforge.db.migration_runner import ensure_schema
from integrations.sysforge.install import run_install
from integrations.sysforge.routes import setup_sysforge_routes
from integrations.sysforge.services import parts as parts_service
from integrations.sysforge.services.sku import SkuConflictError, normalize_sku


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


def test_normalize_sku():
    assert normalize_sku(None) is None
    assert normalize_sku("") is None
    assert normalize_sku("  ") is None
    assert normalize_sku("  ABC  ") == "ABC"


@pytest.mark.area_routes
def test_add_part_persists_cents(monkeypatch, tmp_path):
    _install_active(monkeypatch, tmp_path)
    part_id = parts_service.add_part(
        {"name": "OLED Panel", "sku": "OLED-100", "base_price_cents": 12000}
    )
    part = parts_service.get_part(part_id)
    assert part is not None
    assert part["name"] == "OLED Panel"
    assert part["sku"] == "OLED-100"
    assert part["base_price_cents"] == 12000
    assert part["is_placeholder"] is False


@pytest.mark.area_routes
def test_update_part_name_price(monkeypatch, tmp_path):
    _install_active(monkeypatch, tmp_path)
    part_id = parts_service.add_part(
        {"name": "Screen", "base_price_cents": 1000}
    )
    parts_service.update_part(
        part_id,
        {"name": "Screen Pro", "base_price_cents": 2500},
    )
    part = parts_service.get_part(part_id)
    assert part["name"] == "Screen Pro"
    assert part["base_price_cents"] == 2500


@pytest.mark.area_routes
def test_delete_unused_removes_row(monkeypatch, tmp_path):
    _install_active(monkeypatch, tmp_path)
    part_id = parts_service.add_part({"name": "Temp", "base_price_cents": 100})
    assert parts_service.delete_part(part_id) is True
    assert parts_service.get_part(part_id) is None


@pytest.mark.area_routes
def test_delete_referenced_nulls_line_part_id(monkeypatch, tmp_path):
    _install_active(monkeypatch, tmp_path)
    part_id = parts_service.add_part({"name": "Linked", "base_price_cents": 500})
    conn = db_connection.connect()
    try:
        cur = conn.execute(
            """
            INSERT INTO Invoices (Status, PartsSubtotalCents, LaborCostCents,
              ShippingCostCents, TaxAmountCents, FinalTotalCents)
            VALUES ('Estimate', 0, 0, 0, 0, 0)
            """
        )
        invoice_id = cur.lastrowid
        conn.execute(
            """
            INSERT INTO InvoiceItems (
              InvoiceId, PartId, PartName, QuantityMilliunits,
              UnitPriceCents, LineTotalCents, ItemType
            ) VALUES (?, ?, 'Linked', 1000, 500, 500, 'Part')
            """,
            (invoice_id, part_id),
        )
        conn.commit()
    finally:
        conn.close()

    assert parts_service.get_part_usage_count(part_id) == 1
    assert parts_service.delete_part(part_id) is True
    assert parts_service.get_part(part_id) is None

    conn = db_connection.connect()
    try:
        row = conn.execute(
            "SELECT PartId FROM InvoiceItems WHERE InvoiceId = ?",
            (invoice_id,),
        ).fetchone()
        assert row["PartId"] is None
    finally:
        conn.close()


@pytest.mark.area_routes
def test_get_placeholder_parts_only(monkeypatch, tmp_path):
    _install_active(monkeypatch, tmp_path)
    parts_service.add_part({"name": "Real", "base_price_cents": 100})
    parts_service.add_part(
        {"name": "Fake", "base_price_cents": 100, "is_placeholder": True}
    )
    placeholders = parts_service.get_placeholder_parts()
    assert len(placeholders) == 1
    assert placeholders[0]["name"] == "Fake"
    assert placeholders[0]["is_placeholder"] is True


@pytest.mark.area_routes
def test_sku_conflict_on_create(monkeypatch, tmp_path):
    client = _client(monkeypatch, tmp_path)
    assert client.post(
        "/api/sysforge/parts",
        json={"name": "A", "sku": "DUP-1", "base_price_cents": 100},
    ).status_code == 200
    res = client.post(
        "/api/sysforge/parts",
        json={"name": "B", "sku": "DUP-1", "base_price_cents": 200},
    )
    assert res.status_code == 409
    body = res.json()
    assert body["code"] == "sku_conflict"
    assert body["sku"] == "DUP-1"
    assert body["conflicting_part"]["name"] == "A"


@pytest.mark.area_routes
def test_search_prefers_real_over_placeholder(monkeypatch, tmp_path):
    _install_active(monkeypatch, tmp_path)
    parts_service.add_part({"name": "Digitizer Pro", "base_price_cents": 100})
    parts_service.add_part(
        {
            "name": "Digitizer",
            "base_price_cents": 50,
            "is_placeholder": True,
        }
    )
    hits = parts_service.search_parts("Digitizer", include_placeholders=True)
    assert len(hits) == 1
    assert hits[0]["is_placeholder"] is False
    assert hits[0]["name"] == "Digitizer Pro"


@pytest.mark.area_routes
def test_search_falls_back_to_placeholders(monkeypatch, tmp_path):
    _install_active(monkeypatch, tmp_path)
    parts_service.add_part(
        {"name": "Only Placeholder", "base_price_cents": 50, "is_placeholder": True}
    )
    hits = parts_service.search_parts("Only", include_placeholders=True)
    assert len(hits) == 1
    assert hits[0]["is_placeholder"] is True
    assert parts_service.search_parts("Only", include_placeholders=False) == []


@pytest.mark.area_routes
def test_search_blank_returns_empty(monkeypatch, tmp_path):
    _install_active(monkeypatch, tmp_path)
    parts_service.add_part({"name": "X", "base_price_cents": 1})
    assert parts_service.search_parts("") == []
    assert parts_service.search_parts("   ") == []


@pytest.mark.area_routes
def test_parts_api_list_get_convert(monkeypatch, tmp_path):
    client = _client(monkeypatch, tmp_path)
    created = client.post(
        "/api/sysforge/parts",
        json={
            "name": "Glass",
            "sku": "GL-1",
            "base_price_cents": 800,
            "is_placeholder": True,
        },
    )
    assert created.status_code == 200
    part_id = created.json()["id"]

    listed = client.get("/api/sysforge/parts?placeholders=1")
    assert listed.status_code == 200
    assert any(p["id"] == part_id for p in listed.json()["items"])

    got = client.get(f"/api/sysforge/parts/{part_id}")
    assert got.status_code == 200
    assert got.json()["is_placeholder"] is True

    conv = client.post(
        f"/api/sysforge/parts/{part_id}/convert",
        json={"name": "Glass", "sku": "GL-1", "base_price_cents": 900},
    )
    assert conv.status_code == 204
    assert client.get(f"/api/sysforge/parts/{part_id}").json()["is_placeholder"] is False


@pytest.mark.area_routes
@pytest.mark.area_security
def test_parts_routes_inactive_404(monkeypatch):
    monkeypatch.setattr("integrations.sysforge.routes.is_plugin_active", lambda _pid: False)
    app = FastAPI()
    app.include_router(setup_sysforge_routes())
    with TestClient(app) as client:
        assert client.get("/api/sysforge/parts").status_code == 404
        assert client.get("/api/sysforge/parts/search?q=x").status_code == 404


@pytest.mark.area_routes
def test_service_sku_conflict_raises(monkeypatch, tmp_path):
    _install_active(monkeypatch, tmp_path)
    parts_service.add_part({"name": "A", "sku": "S1", "base_price_cents": 1})
    with pytest.raises(SkuConflictError) as exc:
        parts_service.add_part({"name": "B", "sku": "S1", "base_price_cents": 2})
    assert exc.value.sku == "S1"
