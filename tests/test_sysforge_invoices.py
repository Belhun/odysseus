"""Invoice create/edit/save-as-new + orphan-order contracts."""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from starlette.testclient import TestClient

from integrations.sysforge.db import connection as db_connection
from integrations.sysforge.db.migration_runner import ensure_schema
from integrations.sysforge.install import run_install
from integrations.sysforge.routes import setup_sysforge_routes
from integrations.sysforge.services import invoices as invoice_service
from integrations.sysforge.services import parts as parts_service
from integrations.sysforge.services.invoice_validation import InvoiceValidationError


def _install_active(monkeypatch, tmp_path):
    plugins_root = tmp_path / "plugins"
    monkeypatch.setattr("src.plugins.registry.PLUGINS_DATA_ROOT", plugins_root)
    monkeypatch.setattr(
        "src.plugins.registry.plugin_data_dir", lambda pid: plugins_root / pid
    )
    monkeypatch.setattr("src.settings.FEATURES_FILE", str(tmp_path / "features.json"))
    result = run_install()
    assert result["ok"] is True
    monkeypatch.setattr(
        "integrations.sysforge.routes.is_plugin_active", lambda _pid: True
    )
    ensure_schema()
    return plugins_root


def _client(monkeypatch, tmp_path):
    _install_active(monkeypatch, tmp_path)
    app = FastAPI()
    app.include_router(setup_sysforge_routes())
    return TestClient(app)


def _item(
    *,
    part_name="Screen",
    unit_price_cents=5000,
    quantity_milliunits=1000,
    item_type="Part",
    part_id=None,
    is_taxable=True,
):
    return {
        "part_id": part_id,
        "part_name": part_name,
        "sku": None,
        "quantity_milliunits": quantity_milliunits,
        "unit_price_cents": unit_price_cents,
        "discount_type": "None",
        "discount_value": 0,
        "is_taxable": is_taxable,
        "sort_order": 0,
        "item_type": item_type,
        "supplier_id": None,
    }


@pytest.mark.area_routes
def test_create_persists_header_and_items(monkeypatch, tmp_path):
    client = _client(monkeypatch, tmp_path)
    res = client.post(
        "/api/sysforge/invoices",
        json={
            "name": "Alex - 07/17/2026",
            "client_info": "Alex Rivera",
            "tax_rate_bps": 725,
            "include_tax": True,
            "items": [_item()],
        },
    )
    assert res.status_code == 201, res.text
    body = res.json()
    assert body["id"] >= 1
    assert body["name"] == "Alex - 07/17/2026"
    assert body["status"] == "Estimate"
    assert body["is_finalized"] is False
    assert body["sent_at"] is None
    assert len(body["items"]) == 1
    assert body["parts_subtotal_cents"] == 5000
    assert body["tax_amount_cents"] == 363  # 5000 * 7.25%
    assert body["final_total_cents"] == 5363


@pytest.mark.area_routes
def test_create_empty_items_400(monkeypatch, tmp_path):
    client = _client(monkeypatch, tmp_path)
    res = client.post(
        "/api/sysforge/invoices",
        json={"name": "Empty", "items": []},
    )
    assert res.status_code == 400
    assert "line item" in res.json()["detail"].lower()


@pytest.mark.area_routes
def test_update_same_id_does_not_create_second(monkeypatch, tmp_path):
    _install_active(monkeypatch, tmp_path)
    created = invoice_service.create_invoice(
        {"name": "Orig", "tax_rate_bps": 0, "include_tax": False},
        [_item(part_name="A", unit_price_cents=1000)],
    )
    iid = created["id"]
    updated = invoice_service.update_invoice(
        iid,
        {"name": "Orig", "tax_rate_bps": 0, "include_tax": False},
        [_item(part_name="B", unit_price_cents=2000)],
    )
    assert updated["id"] == iid
    assert updated["items"][0]["part_name"] == "B"
    assert updated["parts_subtotal_cents"] == 2000

    conn = db_connection.connect()
    try:
        count = conn.execute("SELECT COUNT(*) AS c FROM Invoices").fetchone()["c"]
        assert count == 1
    finally:
        conn.close()


@pytest.mark.area_routes
def test_update_replaces_items(monkeypatch, tmp_path):
    client = _client(monkeypatch, tmp_path)
    created = client.post(
        "/api/sysforge/invoices",
        json={
            "name": "Multi",
            "include_tax": False,
            "tax_rate_bps": 0,
            "items": [
                _item(part_name="One"),
                _item(part_name="Two", unit_price_cents=1000),
            ],
        },
    ).json()
    iid = created["id"]
    res = client.put(
        f"/api/sysforge/invoices/{iid}",
        json={
            "include_tax": False,
            "tax_rate_bps": 0,
            "items": [_item(part_name="Only", unit_price_cents=3000)],
        },
    )
    assert res.status_code == 200
    body = res.json()
    assert len(body["items"]) == 1
    assert body["items"][0]["part_name"] == "Only"


@pytest.mark.area_routes
def test_update_empty_items_allowed(monkeypatch, tmp_path):
    client = _client(monkeypatch, tmp_path)
    created = client.post(
        "/api/sysforge/invoices",
        json={
            "name": "Wipe",
            "include_tax": False,
            "tax_rate_bps": 0,
            "items": [_item()],
        },
    ).json()
    iid = created["id"]
    res = client.put(
        f"/api/sysforge/invoices/{iid}",
        json={"items": []},
    )
    assert res.status_code == 200
    body = res.json()
    assert body["id"] == iid
    assert body["name"] == "Wipe"
    assert body["items"] == []
    assert body["final_total_cents"] == 0


@pytest.mark.area_routes
def test_update_preserves_status_finalized_sent(monkeypatch, tmp_path):
    _install_active(monkeypatch, tmp_path)
    created = invoice_service.create_invoice(
        {"name": "Paid one", "include_tax": False, "tax_rate_bps": 0},
        [_item()],
    )
    iid = created["id"]
    invoice_service.update_invoice(
        iid,
        {
            "status": "Paid",
            "is_finalized": True,
            "sent_at": "2026-07-01T12:00:00Z",
            "include_tax": False,
            "tax_rate_bps": 0,
        },
        [_item()],
        status_fields_set={"status", "is_finalized", "sent_at"},
    )
    # Calculator-style update omits status fields
    updated = invoice_service.update_invoice(
        iid,
        {"include_tax": False, "tax_rate_bps": 0},
        [_item(unit_price_cents=6000)],
        status_fields_set=set(),
    )
    assert updated["status"] == "Paid"
    assert updated["is_finalized"] is True
    assert updated["sent_at"] is not None
    assert updated["parts_subtotal_cents"] == 6000


@pytest.mark.area_routes
def test_save_as_new_returns_new_id(monkeypatch, tmp_path):
    client = _client(monkeypatch, tmp_path)
    created = client.post(
        "/api/sysforge/invoices",
        json={
            "name": "Original",
            "include_tax": False,
            "tax_rate_bps": 0,
            "items": [_item(part_name="Keep")],
        },
    ).json()
    orig_id = created["id"]
    res = client.post(
        f"/api/sysforge/invoices/{orig_id}/save-as-new",
        json={
            "name": "Clone",
            "include_tax": False,
            "tax_rate_bps": 0,
            "items": [_item(part_name="Keep", unit_price_cents=5000)],
        },
    )
    assert res.status_code == 201
    clone = res.json()
    assert clone["id"] != orig_id
    assert clone["name"] == "Clone"
    assert clone["status"] == "Estimate"
    assert clone["is_finalized"] is False
    orig = client.get(f"/api/sysforge/invoices/{orig_id}").json()
    assert orig["name"] == "Original"
    assert len(orig["items"]) == 1


@pytest.mark.area_routes
def test_status_stored_as_text(monkeypatch, tmp_path):
    _install_active(monkeypatch, tmp_path)
    created = invoice_service.create_invoice(
        {"name": "S", "include_tax": False, "tax_rate_bps": 0},
        [_item()],
    )
    conn = db_connection.connect()
    try:
        row = conn.execute(
            "SELECT typeof(Status) AS t, Status FROM Invoices WHERE Id = ?",
            (created["id"],),
        ).fetchone()
        assert row["Status"] == "Estimate"
        assert row["t"] == "text"
    finally:
        conn.close()


@pytest.mark.area_routes
def test_orphan_order_keeps_placeholders_on_update(monkeypatch, tmp_path):
    """BUG-006: cleanup after re-insert must not delete still-referenced placeholders."""
    _install_active(monkeypatch, tmp_path)
    created = invoice_service.create_invoice(
        {"name": "PH", "include_tax": False, "tax_rate_bps": 0},
        [_item(part_name="Mystery Panel", part_id=None)],
    )
    iid = created["id"]
    part_id = created["items"][0]["part_id"]
    assert part_id is not None
    part = parts_service.get_part(part_id)
    assert part is not None
    assert part["is_placeholder"] is True

    # Update keeping same placeholder line (same part_id)
    updated = invoice_service.update_invoice(
        iid,
        {"include_tax": False, "tax_rate_bps": 0, "name": "PH"},
        [
            _item(
                part_name="Mystery Panel",
                part_id=part_id,
                unit_price_cents=5500,
            )
        ],
    )
    assert updated["items"][0]["part_id"] == part_id
    assert parts_service.get_part(part_id) is not None


@pytest.mark.area_routes
def test_orphan_cleanup_removes_unused_after_update(monkeypatch, tmp_path):
    _install_active(monkeypatch, tmp_path)
    created = invoice_service.create_invoice(
        {"name": "PH2", "include_tax": False, "tax_rate_bps": 0},
        [_item(part_name="Temp Placeholder", part_id=None)],
    )
    part_id = created["items"][0]["part_id"]
    assert parts_service.get_part(part_id) is not None

    invoice_service.update_invoice(
        created["id"],
        {"include_tax": False, "tax_rate_bps": 0, "name": "PH2"},
        [_item(part_name="Catalog Part", part_id=None)],  # new placeholder name
    )
    # Old placeholder should be gone; new one exists
    assert parts_service.get_part(part_id) is None
    new_items = invoice_service.get_invoice(created["id"])["items"]
    assert new_items[0]["part_id"] != part_id
    assert parts_service.get_part(new_items[0]["part_id"]) is not None


@pytest.mark.area_routes
def test_plugin_inactive_invoice_routes_404(monkeypatch, tmp_path):
    _install_active(monkeypatch, tmp_path)
    monkeypatch.setattr(
        "integrations.sysforge.routes.is_plugin_active", lambda _pid: False
    )
    app = FastAPI()
    app.include_router(setup_sysforge_routes())
    client = TestClient(app)
    assert client.get("/api/sysforge/invoices/1").status_code == 404
    assert (
        client.post(
            "/api/sysforge/invoices",
            json={"name": "X", "items": [_item()]},
        ).status_code
        == 404
    )


@pytest.mark.area_routes
def test_fk_missing_part_maps_to_409(monkeypatch, tmp_path):
    client = _client(monkeypatch, tmp_path)
    res = client.post(
        "/api/sysforge/invoices",
        json={
            "name": "FK",
            "include_tax": False,
            "tax_rate_bps": 0,
            "items": [_item(part_name="Linked", part_id=999999)],
        },
    )
    assert res.status_code == 409, res.text
    detail = res.json()["detail"]
    assert detail["code"] == "foreign_key"
    assert "part" in detail["message"].lower() or "supplier" in detail["message"].lower()


@pytest.mark.area_routes
def test_get_and_list_by_client(monkeypatch, tmp_path):
    client = _client(monkeypatch, tmp_path)
    c = client.post(
        "/api/sysforge/clients",
        json={"first_name": "Sam", "last_name": "Lee"},
    ).json()
    inv = client.post(
        "/api/sysforge/invoices",
        json={
            "name": "Sam job",
            "client_id": c["id"],
            "client_info": c["display_name"],
            "include_tax": False,
            "tax_rate_bps": 0,
            "items": [_item()],
        },
    ).json()
    got = client.get(f"/api/sysforge/invoices/{inv['id']}")
    assert got.status_code == 200
    assert got.json()["client"]["id"] == c["id"]

    listed = client.get(f"/api/sysforge/invoices?client_id={c['id']}")
    assert listed.status_code == 200
    assert any(i["id"] == inv["id"] for i in listed.json()["invoices"])

    listed2 = client.get(f"/api/sysforge/clients/{c['id']}/invoices")
    assert listed2.status_code == 200
    assert any(i["id"] == inv["id"] for i in listed2.json()["invoices"])


@pytest.mark.area_routes
def test_validation_rejects_bad_tax(monkeypatch, tmp_path):
    _install_active(monkeypatch, tmp_path)
    with pytest.raises(InvoiceValidationError):
        invoice_service.create_invoice(
            {"name": "Bad", "tax_rate_bps": 20000, "include_tax": True},
            [_item()],
        )


def test_calculate_totals_misc_and_shipping(monkeypatch, tmp_path):
    _install_active(monkeypatch, tmp_path)
    inv = {
        "include_tax": True,
        "include_shipping": True,
        "tax_rate_bps": 1000,  # 10%
        "shipping_rate_cents": 500,
    }
    items = [
        _item(part_name="P", unit_price_cents=1000, item_type="Part"),
        _item(part_name="L", unit_price_cents=2000, item_type="Labor", is_taxable=False),
        _item(part_name="M", unit_price_cents=300, item_type="Misc", is_taxable=False),
    ]
    invoice_service.calculate_invoice_totals(inv, items)
    assert inv["parts_subtotal_cents"] == 1000
    assert inv["labor_cost_cents"] == 2000
    # Taxable = Part lines (or is_taxable): 1000 → 100 tax
    assert inv["tax_amount_cents"] == 100
    assert inv["shipping_cost_cents"] == 500
    assert inv["final_total_cents"] == 1000 + 2000 + 300 + 100 + 500
