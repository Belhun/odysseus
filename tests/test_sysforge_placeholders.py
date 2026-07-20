"""Placeholder create, orphan order, merge — desktop PlaceholderWorkflow parity."""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from starlette.testclient import TestClient

from integrations.sysforge.db import connection as db_connection
from integrations.sysforge.db.migration_runner import ensure_schema
from integrations.sysforge.install import run_install
from integrations.sysforge.routes import setup_sysforge_routes
from integrations.sysforge.services import parts as parts_service
from integrations.sysforge.services.sku import SkuConflictError


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


def _insert_invoice(conn) -> int:
    cur = conn.execute(
        """
        INSERT INTO Invoices (
          Status, PartsSubtotalCents, LaborCostCents,
          ShippingCostCents, TaxAmountCents, FinalTotalCents
        ) VALUES ('Estimate', 0, 0, 0, 0, 0)
        """
    )
    return int(cur.lastrowid)


def _insert_item(conn, invoice_id: int, item: dict) -> int:
    cur = conn.execute(
        """
        INSERT INTO InvoiceItems (
          InvoiceId, PartId, PartName, SKU, QuantityMilliunits,
          UnitPriceCents, LineTotalCents, ItemType, SupplierId
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            invoice_id,
            item.get("part_id"),
            item["part_name"],
            item.get("sku"),
            item.get("quantity_milliunits", 1000),
            item["unit_price_cents"],
            item.get("line_total_cents", item["unit_price_cents"]),
            item.get("item_type", "Part"),
            item.get("supplier_id"),
        ),
    )
    return int(cur.lastrowid)


def _save_invoice_with_placeholder_order(conn, invoice_id: int | None, items: list[dict]):
    """Four-step invoice save contract used by calculator workstream."""
    if invoice_id is None:
        invoice_id = _insert_invoice(conn)
    else:
        conn.execute(
            "UPDATE Invoices SET Status = Status WHERE Id = ?",
            (invoice_id,),
        )
        conn.execute("DELETE FROM InvoiceItems WHERE InvoiceId = ?", (invoice_id,))

    parts_service.create_placeholders_from_items(conn, items)
    for item in items:
        _insert_item(conn, invoice_id, item)
    parts_service.delete_orphaned_placeholders(conn)
    return invoice_id


@pytest.mark.area_routes
def test_placeholder_create_links_item(monkeypatch, tmp_path):
    _install_active(monkeypatch, tmp_path)
    conn = db_connection.connect()
    try:
        conn.execute("BEGIN")
        items = [
            {
                "part_id": None,
                "part_name": "Test Part",
                "sku": "TEST-001",
                "unit_price_cents": 5000,
                "item_type": "Part",
            }
        ]
        invoice_id = _save_invoice_with_placeholder_order(conn, None, items)
        conn.commit()
    finally:
        conn.close()

    assert invoice_id > 0
    assert items[0]["part_id"] is not None
    part = parts_service.get_part(items[0]["part_id"])
    assert part is not None
    assert part["is_placeholder"] is True
    assert part["sku"] == "TEST-001"
    assert part["name"] == "Test Part"
    assert part["base_price_cents"] == 5000


@pytest.mark.area_routes
def test_edit_update_preserves_referenced_placeholders(monkeypatch, tmp_path):
    """BUG-006: orphan cleanup must run AFTER re-insert, not between delete/insert."""
    _install_active(monkeypatch, tmp_path)
    conn = db_connection.connect()
    try:
        conn.execute("BEGIN")
        items = [
            {
                "part_id": None,
                "part_name": "Widget",
                "sku": "WID-UPDATE-1",
                "unit_price_cents": 1000,
                "item_type": "Part",
            }
        ]
        invoice_id = _save_invoice_with_placeholder_order(conn, None, items)
        placeholder_id = items[0]["part_id"]
        conn.commit()
    finally:
        conn.close()

    # Reload and save again with same part_id (edit path)
    conn = db_connection.connect()
    try:
        conn.execute("BEGIN")
        reloaded = [
            {
                "part_id": placeholder_id,
                "part_name": "Widget",
                "sku": "WID-UPDATE-1",
                "unit_price_cents": 1000,
                "item_type": "Part",
            }
        ]
        _save_invoice_with_placeholder_order(conn, invoice_id, reloaded)
        conn.commit()
    finally:
        conn.close()

    assert parts_service.get_part(placeholder_id) is not None
    assert parts_service.get_part_usage_count(placeholder_id) == 1


@pytest.mark.area_routes
def test_orphan_deleted_when_item_removed(monkeypatch, tmp_path):
    _install_active(monkeypatch, tmp_path)
    conn = db_connection.connect()
    try:
        conn.execute("BEGIN")
        items = [
            {
                "part_id": None,
                "part_name": "Orphaned Part",
                "sku": "ORPHAN-002",
                "unit_price_cents": 5000,
                "item_type": "Part",
            }
        ]
        invoice_id = _save_invoice_with_placeholder_order(conn, None, items)
        placeholder_id = items[0]["part_id"]
        conn.commit()
    finally:
        conn.close()

    conn = db_connection.connect()
    try:
        conn.execute("BEGIN")
        _save_invoice_with_placeholder_order(conn, invoice_id, [])
        conn.commit()
    finally:
        conn.close()

    assert parts_service.get_part(placeholder_id) is None


@pytest.mark.area_routes
def test_sku_conflict_rolls_back_placeholder_and_invoice(monkeypatch, tmp_path):
    _install_active(monkeypatch, tmp_path)
    parts_service.add_part(
        {"name": "Existing Part", "sku": "CONFLICT-001", "base_price_cents": 1000}
    )

    conn = db_connection.connect()
    try:
        conn.execute("BEGIN")
        items = [
            {
                "part_id": None,
                "part_name": "New Part",
                "sku": "CONFLICT-001",
                "unit_price_cents": 5000,
                "item_type": "Part",
            }
        ]
        with pytest.raises(SkuConflictError):
            _save_invoice_with_placeholder_order(conn, None, items)
        conn.rollback()
    finally:
        conn.close()

    conn = db_connection.connect()
    try:
        assert conn.execute("SELECT COUNT(*) AS c FROM Invoices").fetchone()["c"] == 0
        assert conn.execute("SELECT COUNT(*) AS c FROM InvoiceItems").fetchone()["c"] == 0
        assert (
            conn.execute(
                "SELECT COUNT(*) AS c FROM Parts WHERE IsPlaceholder = 1"
            ).fetchone()["c"]
            == 0
        )
    finally:
        conn.close()


@pytest.mark.area_routes
def test_wrong_orphan_order_would_delete_still_used(monkeypatch, tmp_path):
    """Document why order matters: orphan delete BEFORE insert would wipe the placeholder."""
    _install_active(monkeypatch, tmp_path)
    conn = db_connection.connect()
    try:
        conn.execute("BEGIN")
        items = [
            {
                "part_id": None,
                "part_name": "OrderSensitive",
                "sku": "ORD-1",
                "unit_price_cents": 100,
                "item_type": "Part",
            }
        ]
        invoice_id = _save_invoice_with_placeholder_order(conn, None, items)
        placeholder_id = items[0]["part_id"]
        conn.commit()
    finally:
        conn.close()

    # Simulate bad order: delete items → create placeholders → delete orphans → insert
    conn = db_connection.connect()
    try:
        conn.execute("BEGIN")
        conn.execute("DELETE FROM InvoiceItems WHERE InvoiceId = ?", (invoice_id,))
        reloaded = [
            {
                "part_id": placeholder_id,
                "part_name": "OrderSensitive",
                "sku": "ORD-1",
                "unit_price_cents": 100,
                "item_type": "Part",
            }
        ]
        parts_service.create_placeholders_from_items(conn, reloaded)
        # Wrong: orphan cleanup while items are still deleted
        parts_service.delete_orphaned_placeholders(conn)
        gone = conn.execute(
            "SELECT Id FROM Parts WHERE Id = ?", (placeholder_id,)
        ).fetchone()
        assert gone is None
        conn.rollback()
    finally:
        conn.close()

    # Placeholder still exists after rollback of the bad path
    assert parts_service.get_part(placeholder_id) is not None


@pytest.mark.area_routes
def test_grouping_requires_two_same_name(monkeypatch, tmp_path):
    _install_active(monkeypatch, tmp_path)
    parts_service.add_part(
        {"name": "Screen", "base_price_cents": 100, "is_placeholder": True}
    )
    assert parts_service.get_placeholder_groups() == []

    parts_service.add_part(
        {"name": "Screen", "base_price_cents": 200, "is_placeholder": True}
    )
    parts_service.add_part(
        {"name": "Battery", "base_price_cents": 50, "is_placeholder": True}
    )
    groups = parts_service.get_placeholder_groups()
    assert len(groups) == 1
    assert groups[0]["suggested_name"] == "Screen"
    assert len(groups[0]["parts"]) == 2


@pytest.mark.area_routes
def test_merge_preserves_unit_price_cents(monkeypatch, tmp_path):
    _install_active(monkeypatch, tmp_path)
    a = parts_service.add_part(
        {"name": "Digitizer", "base_price_cents": 1000, "is_placeholder": True}
    )
    b = parts_service.add_part(
        {"name": "Digitizer", "base_price_cents": 2000, "is_placeholder": True}
    )

    conn = db_connection.connect()
    try:
        inv1 = _insert_invoice(conn)
        inv2 = _insert_invoice(conn)
        _insert_item(
            conn,
            inv1,
            {
                "part_id": a,
                "part_name": "Digitizer",
                "unit_price_cents": 1111,
            },
        )
        _insert_item(
            conn,
            inv2,
            {
                "part_id": b,
                "part_name": "Digitizer",
                "unit_price_cents": 2222,
            },
        )
        conn.commit()
    finally:
        conn.close()

    merged = parts_service.merge_placeholders([b], a)
    assert merged == 1
    assert parts_service.get_part(b) is None
    assert parts_service.get_part(a) is not None

    conn = db_connection.connect()
    try:
        prices = [
            int(r["UnitPriceCents"])
            for r in conn.execute(
                "SELECT UnitPriceCents FROM InvoiceItems WHERE PartId = ? ORDER BY UnitPriceCents",
                (a,),
            ).fetchall()
        ]
        assert prices == [1111, 2222]
        assert parts_service.get_part_usage_count(a) == 2
    finally:
        conn.close()


@pytest.mark.area_routes
def test_merge_api_rejects_empty_sources(monkeypatch, tmp_path):
    _install_active(monkeypatch, tmp_path)
    target = parts_service.add_part(
        {"name": "X", "base_price_cents": 1, "is_placeholder": True}
    )
    app = FastAPI()
    app.include_router(setup_sysforge_routes())
    with TestClient(app) as client:
        res = client.post(
            "/api/sysforge/placeholders/merge",
            json={"target_part_id": target, "source_part_ids": []},
        )
        assert res.status_code == 400


@pytest.mark.area_routes
def test_merge_api_round_trip(monkeypatch, tmp_path):
    _install_active(monkeypatch, tmp_path)
    a = parts_service.add_part(
        {"name": "Glass", "base_price_cents": 100, "is_placeholder": True}
    )
    b = parts_service.add_part(
        {"name": "Glass", "base_price_cents": 200, "is_placeholder": True}
    )
    app = FastAPI()
    app.include_router(setup_sysforge_routes())
    with TestClient(app) as client:
        groups = client.get("/api/sysforge/placeholders/groups")
        assert groups.status_code == 200
        assert len(groups.json()["groups"]) == 1

        res = client.post(
            "/api/sysforge/placeholders/merge",
            json={"target_part_id": a, "source_part_ids": [b]},
        )
        assert res.status_code == 200
        assert res.json()["merged"] == 1
        assert client.get("/api/sysforge/placeholders/groups").json()["groups"] == []


@pytest.mark.area_routes
def test_supplier_inherited_on_placeholder(monkeypatch, tmp_path):
    _install_active(monkeypatch, tmp_path)
    conn = db_connection.connect()
    try:
        cur = conn.execute(
            "INSERT INTO Suppliers (Name) VALUES ('Test Supplier')"
        )
        supplier_id = int(cur.lastrowid)
        conn.commit()
    finally:
        conn.close()

    conn = db_connection.connect()
    try:
        conn.execute("BEGIN")
        items = [
            {
                "part_id": None,
                "part_name": "Supplier Part",
                "sku": "SUP-1",
                "unit_price_cents": 5000,
                "supplier_id": supplier_id,
                "item_type": "Part",
            }
        ]
        _save_invoice_with_placeholder_order(conn, None, items)
        conn.commit()
        part_id = items[0]["part_id"]
    finally:
        conn.close()

    part = parts_service.get_part(part_id)
    assert part["supplier_id"] == supplier_id
