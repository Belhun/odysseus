"""PartPriceHistory append + Update Prices preview/apply."""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from starlette.testclient import TestClient

from integrations.sysforge.db.migration_runner import ensure_schema
from integrations.sysforge.install import run_install
from integrations.sysforge.routes import setup_sysforge_routes
from integrations.sysforge.services import invoices as invoice_service
from integrations.sysforge.services import parts as parts_service
from integrations.sysforge.services import price_history as history_service
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
    monkeypatch.setattr("integrations.sysforge.routes.is_plugin_active", lambda _pid: True)
    ensure_schema()
    return plugins_root


def _client(monkeypatch, tmp_path):
    _install_active(monkeypatch, tmp_path)
    app = FastAPI()
    app.include_router(setup_sysforge_routes())
    return TestClient(app)


def _seed_estimate_with_part(base_cents: int = 1000, unit_cents: int = 800):
    part_id = parts_service.add_part(
        {"name": "Screen Glass", "sku": "SG-1", "base_price_cents": base_cents}
    )
    inv = invoice_service.create_invoice(
        {"client_info": "Pat Price", "include_tax": False, "tax_rate_bps": 0},
        [
            {
                "part_id": part_id,
                "part_name": "Screen Glass",
                "sku": "SG-1",
                "quantity_milliunits": 1000,
                "unit_price_cents": unit_cents,
                "item_type": "Part",
            }
        ],
    )
    return inv, part_id


@pytest.mark.area_routes
def test_patch_base_price_appends_catalog_edit_history(monkeypatch, tmp_path):
    _install_active(monkeypatch, tmp_path)
    part_id = parts_service.add_part(
        {"name": "Battery", "sku": "BAT-1", "base_price_cents": 500}
    )
    parts_service.update_part(
        part_id,
        {"name": "Battery", "sku": "BAT-1", "base_price_cents": 750},
    )
    hist = history_service.get_part_price_history(part_id)
    assert len(hist) == 1
    assert hist[0]["price_cents"] == 750
    assert hist[0]["source"] == "catalog_edit"
    assert hist[0]["effective_at"]
    assert isinstance(hist[0]["price_cents"], int)


@pytest.mark.area_routes
def test_explicit_price_history_post(monkeypatch, tmp_path):
    client = _client(monkeypatch, tmp_path)
    part_id = parts_service.add_part(
        {"name": "Flex", "sku": "FX-1", "base_price_cents": 200}
    )
    res = client.post(
        f"/api/sysforge/parts/{part_id}/price-history",
        json={"price_cents": 225, "source": "manual", "note": "shelf check"},
    )
    assert res.status_code == 200
    assert isinstance(res.json()["id"], int)
    listed = client.get(f"/api/sysforge/parts/{part_id}/price-history")
    assert listed.status_code == 200
    items = listed.json()["items"]
    assert len(items) == 1
    assert items[0]["price_cents"] == 225
    assert items[0]["source"] == "manual"
    assert items[0]["note"] == "shelf check"


@pytest.mark.area_routes
def test_update_prices_preview_and_apply(monkeypatch, tmp_path):
    _install_active(monkeypatch, tmp_path)
    inv, part_id = _seed_estimate_with_part(base_cents=1200, unit_cents=800)
    invoice_id = inv["id"]
    item_id = inv["items"][0]["id"]

    preview = invoice_service.preview_update_prices(invoice_id)
    assert len(preview) == 1
    assert preview[0]["item_id"] == item_id
    assert preview[0]["part_id"] == part_id
    assert preview[0]["current_unit_cents"] == 800
    assert preview[0]["proposed_cents"] == 1200
    assert preview[0]["delta_cents"] == 400
    assert preview[0]["source"] == "base"

    updated = invoice_service.apply_update_prices(
        invoice_id,
        [{"item_id": item_id, "proposed_cents": 1200}],
    )
    assert updated["items"][0]["unit_price_cents"] == 1200
    assert updated["final_total_cents"] >= 1200


@pytest.mark.area_routes
def test_update_prices_history_choice(monkeypatch, tmp_path):
    _install_active(monkeypatch, tmp_path)
    inv, part_id = _seed_estimate_with_part(base_cents=1000, unit_cents=900)
    hid = history_service.add_part_price_history(
        part_id, 1100, source="manual", note="promo"
    )
    item_id = inv["items"][0]["id"]
    preview = invoice_service.preview_update_prices(
        inv["id"],
        choices=[{"item_id": item_id, "source": "history", "history_id": hid}],
    )
    assert preview[0]["proposed_cents"] == 1100
    assert preview[0]["source"] == "history"
    assert preview[0]["history_id"] == hid
    part = parts_service.get_part(part_id)
    assert part["base_price_cents"] == 1000


@pytest.mark.area_routes
def test_update_prices_blocked_when_finalized(monkeypatch, tmp_path):
    _install_active(monkeypatch, tmp_path)
    inv, _part_id = _seed_estimate_with_part()
    item = inv["items"][0]
    invoice_service.update_invoice(
        inv["id"],
        {
            "client_info": inv.get("client_info") or "Pat Price",
            "is_finalized": True,
            "status": "Estimate",
            "include_tax": False,
            "tax_rate_bps": 0,
        },
        [
            {
                "part_id": item["part_id"],
                "part_name": item["part_name"],
                "unit_price_cents": item["unit_price_cents"],
                "quantity_milliunits": 1000,
                "item_type": "Part",
            }
        ],
        status_fields_set={"is_finalized", "status"},
    )
    with pytest.raises(InvoiceValidationError, match="finalized"):
        invoice_service.preview_update_prices(inv["id"])


@pytest.mark.area_routes
def test_update_prices_blocked_when_invoiced(monkeypatch, tmp_path):
    client = _client(monkeypatch, tmp_path)
    inv, _part_id = _seed_estimate_with_part()
    item = inv["items"][0]
    invoice_service.update_invoice(
        inv["id"],
        {
            "client_info": inv.get("client_info") or "Pat Price",
            "status": "Invoiced",
            "include_tax": False,
            "tax_rate_bps": 0,
        },
        [
            {
                "part_id": item["part_id"],
                "part_name": item["part_name"],
                "unit_price_cents": item["unit_price_cents"],
                "quantity_milliunits": 1000,
                "item_type": "Part",
            }
        ],
        status_fields_set={"status"},
    )
    res = client.post(
        f"/api/sysforge/invoices/{inv['id']}/update-prices/preview",
        json={"choices": []},
    )
    assert res.status_code == 400
    assert "invoiced" in res.json()["detail"].lower()


@pytest.mark.area_routes
def test_update_prices_api_apply(monkeypatch, tmp_path):
    client = _client(monkeypatch, tmp_path)
    inv, _part_id = _seed_estimate_with_part(base_cents=1500, unit_cents=1000)
    item_id = inv["items"][0]["id"]
    preview = client.post(
        f"/api/sysforge/invoices/{inv['id']}/update-prices/preview",
        json={"choices": []},
    )
    assert preview.status_code == 200
    assert preview.json()["items"][0]["proposed_cents"] == 1500

    applied = client.post(
        f"/api/sysforge/invoices/{inv['id']}/update-prices/apply",
        json={"items": [{"item_id": item_id, "proposed_cents": 1500}]},
    )
    assert applied.status_code == 200
    body = applied.json()
    assert body["items"][0]["unit_price_cents"] == 1500
    assert isinstance(body["items"][0]["unit_price_cents"], int)
