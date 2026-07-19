"""SysForge Business backup / restore / JSON import + BUG-018 reindex."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi import FastAPI
from starlette.testclient import TestClient

from integrations.sysforge import backup_service
from integrations.sysforge.backup_models import ImportOptions, SQL_IMPORT_REJECT_MESSAGE
from integrations.sysforge.backup_service import UnsupportedExportVersion
from integrations.sysforge.db import connection as db_connection
from integrations.sysforge.install import run_install
from integrations.sysforge.routes import setup_sysforge_routes
from integrations.sysforge.services.clients import rebuild_clients_fts, search_clients

FIXTURE = (
    Path(__file__).resolve().parent / "fixtures" / "sysforge" / "sample-export.json"
)


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
    return plugins_root


def _client(monkeypatch, tmp_path):
    _install_active(monkeypatch, tmp_path)
    app = FastAPI()
    app.include_router(setup_sysforge_routes())
    return TestClient(app)


def _load_fixture() -> dict:
    assert FIXTURE.is_file(), f"missing fixture {FIXTURE}"
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


@pytest.mark.area_routes
def test_create_backup_writes_zip(monkeypatch, tmp_path):
    plugins_root = _install_active(monkeypatch, tmp_path)
    result = backup_service.create_backup(include_drafts=False)
    assert result.success is True
    assert result.backup is not None
    zip_path = plugins_root / "sysforge" / "backups" / result.backup.filename
    assert zip_path.is_file()
    assert zip_path.suffix == ".zip"
    # Extract and integrity-check inner db
    import zipfile
    import tempfile

    with tempfile.TemporaryDirectory() as td:
        with zipfile.ZipFile(zip_path) as zf:
            zf.extractall(td)
        db = Path(td) / "sysforge.db"
        assert db.is_file()
        assert backup_service.validate_database_file(db) is True
        assert (Path(td) / "manifest.json").is_file()
        assert (Path(td) / "config.json").is_file()


@pytest.mark.area_routes
def test_restore_rejects_invalid_db(monkeypatch, tmp_path):
    plugins_root = _install_active(monkeypatch, tmp_path)
    live = db_connection.db_path()
    before = live.read_bytes()
    bad = plugins_root / "sysforge" / "backups" / "sysforge-backup-2099-01-01-000000.db"
    bad.parent.mkdir(parents=True, exist_ok=True)
    bad.write_bytes(b"not a sqlite database")
    result = backup_service.restore_backup(bad)
    assert result.success is False
    assert "integrity" in result.message.lower()
    assert live.read_bytes() == before


@pytest.mark.area_routes
def test_restore_round_trip(monkeypatch, tmp_path):
    _install_active(monkeypatch, tmp_path)
    # Seed a client
    conn = db_connection.connect()
    try:
        conn.execute(
            """
            INSERT INTO Clients (Id, FirstName, LastName, PhoneNorm, IsDeleted)
            VALUES (42, 'Ada', 'Lovelace', '5550001111', 0)
            """
        )
        conn.commit()
    finally:
        conn.close()
    rebuild_clients_fts()

    created = backup_service.create_backup()
    assert created.success and created.backup

    # Wipe client
    conn = db_connection.connect()
    try:
        conn.execute("DELETE FROM Clients WHERE Id = 42")
        conn.commit()
    finally:
        conn.close()
    rebuild_clients_fts()
    assert search_clients("Ada") == []

    path = backup_service.find_backup_file(created.backup.id)
    assert path is not None
    restored = backup_service.restore_backup(path)
    assert restored.success is True
    assert restored.search_rebuilt is True
    assert restored.safety_backup_id
    hits = search_clients("Ada")
    assert any(int(h["id"]) == 42 for h in hits)


@pytest.mark.area_routes
def test_import_json_sample_export(monkeypatch, tmp_path):
    _install_active(monkeypatch, tmp_path)
    data = _load_fixture()
    result = backup_service.import_from_json(data, ImportOptions())
    assert result.success is True
    assert result.clients_imported == 12
    assert result.parts_imported == 10
    assert result.invoices_imported == 10
    assert result.invoice_items_imported == 19
    assert result.search_rebuilt is True


@pytest.mark.area_routes
def test_import_json_invalid_version(monkeypatch, tmp_path):
    _install_active(monkeypatch, tmp_path)
    with pytest.raises(UnsupportedExportVersion):
        backup_service.import_from_json(
            {"exportVersion": "9.9", "clients": []}, ImportOptions()
        )


@pytest.mark.area_routes
def test_import_conflict_skip_no_overwrite(monkeypatch, tmp_path):
    _install_active(monkeypatch, tmp_path)
    data = _load_fixture()
    backup_service.import_from_json(data, ImportOptions())
    # Change Maria's name
    conn = db_connection.connect()
    try:
        conn.execute(
            "UPDATE Clients SET FirstName = 'Changed' WHERE Id = 90001"
        )
        conn.commit()
    finally:
        conn.close()
    again = backup_service.import_from_json(
        data, ImportOptions(conflict="skip", import_parts=False, import_invoices=False, import_invoice_items=False, import_settings=False)
    )
    assert again.clients_imported == 0
    assert again.clients_skipped == 12
    conn = db_connection.connect()
    try:
        row = conn.execute(
            "SELECT FirstName FROM Clients WHERE Id = 90001"
        ).fetchone()
        assert row[0] == "Changed"
    finally:
        conn.close()


@pytest.mark.area_routes
def test_import_conflict_overwrite_updates(monkeypatch, tmp_path):
    _install_active(monkeypatch, tmp_path)
    data = _load_fixture()
    backup_service.import_from_json(data, ImportOptions())
    conn = db_connection.connect()
    try:
        conn.execute(
            "UPDATE Clients SET FirstName = 'Changed' WHERE Id = 90001"
        )
        conn.commit()
    finally:
        conn.close()
    again = backup_service.import_from_json(
        data,
        ImportOptions(
            conflict="overwrite",
            import_parts=False,
            import_invoices=False,
            import_invoice_items=False,
            import_settings=False,
        ),
    )
    assert again.clients_imported == 12
    conn = db_connection.connect()
    try:
        row = conn.execute(
            "SELECT FirstName FROM Clients WHERE Id = 90001"
        ).fetchone()
        assert row[0] == "Maria"
    finally:
        conn.close()


@pytest.mark.area_routes
def test_import_fk_violation_rolls_back(monkeypatch, tmp_path):
    _install_active(monkeypatch, tmp_path)
    payload = {
        "exportVersion": "1.0",
        "clients": [],
        "parts": [],
        "invoices": [
            {
                "id": 1,
                "clientId": 99999,
                "name": "orphan",
                "status": "Estimate",
                "partsSubtotalCents": 0,
                "laborCostCents": 0,
                "shippingCostCents": 0,
                "taxAmountCents": 0,
                "finalTotalCents": 0,
            }
        ],
        "invoiceItems": [],
    }
    with pytest.raises(Exception):
        backup_service.import_from_json(
            payload,
            ImportOptions(
                import_clients=False,
                import_parts=False,
                import_settings=False,
                import_invoice_items=False,
            ),
        )
    conn = db_connection.connect()
    try:
        count = conn.execute("SELECT COUNT(*) FROM Invoices").fetchone()[0]
        assert count == 0
    finally:
        conn.close()


@pytest.mark.area_routes
def test_import_then_search_finds_maria(monkeypatch, tmp_path):
    client = _client(monkeypatch, tmp_path)
    data = _load_fixture()
    result = backup_service.import_from_json(data, ImportOptions())
    assert result.success is True
    hits = search_clients("Maria")
    assert any(int(h["id"]) == 90001 for h in hits)
    chen = search_clients("Chen")
    assert any(int(h["id"]) == 90001 for h in chen)
    res = client.get("/api/sysforge/clients/search", params={"q": "Maria"})
    assert res.status_code == 200
    rows = res.json().get("results") or []
    assert any(int(r["id"]) == 90001 for r in rows)


@pytest.mark.area_routes
def test_import_skip_rebuilds_stale_index(monkeypatch, tmp_path):
    """BUG-018: Skip re-import with 0 imported still rebuilds FTS."""
    _install_active(monkeypatch, tmp_path)
    data = _load_fixture()
    first = backup_service.import_from_json(data, ImportOptions())
    assert first.clients_imported == 12
    assert any(int(h["id"]) == 90001 for h in search_clients("Maria"))

    # Corrupt FTS so name search fails while rows still exist in Clients.
    conn = db_connection.connect()
    try:
        conn.execute("DELETE FROM clients_fts")
        conn.commit()
        listed = conn.execute(
            "SELECT COUNT(*) FROM Clients WHERE IsDeleted = 0"
        ).fetchone()[0]
        assert listed >= 12
    finally:
        conn.close()
    assert search_clients("Maria") == []

    again = backup_service.import_from_json(
        data,
        ImportOptions(
            conflict="skip",
            import_parts=False,
            import_invoices=False,
            import_invoice_items=False,
            import_settings=False,
        ),
    )
    assert again.clients_imported == 0
    assert again.clients_skipped == 12
    assert again.search_rebuilt is True
    assert again.success is True
    hits = search_clients("Maria")
    assert any(int(h["id"]) == 90001 for h in hits)


@pytest.mark.area_routes
def test_export_import_payments_and_merge_column(monkeypatch, tmp_path):
    """JSON export includes payments + MergedIntoClientId; import restores them."""
    _install_active(monkeypatch, tmp_path)
    from integrations.sysforge.services import invoices as invoice_service
    from integrations.sysforge.services import payments as payments_service
    from integrations.sysforge.services import clients as clients_service

    client_a = clients_service.add_client(
        {"first_name": "Sam", "last_name": "Survivor", "phone_number": "5551001"}
    )
    client_b = clients_service.add_client(
        {"first_name": "Lee", "last_name": "Loser", "phone_number": "5551002"}
    )
    inv = invoice_service.create_invoice(
        {
            "name": "Pay me",
            "client_id": client_a["id"],
            "client_info": "Sam Survivor",
            "include_tax": False,
            "tax_rate_bps": 0,
        },
        [
            {
                "part_id": None,
                "part_name": "Board",
                "sku": None,
                "quantity_milliunits": 1000,
                "unit_price_cents": 4000,
                "discount_type": "None",
                "discount_value": 0,
                "is_taxable": True,
                "sort_order": 0,
                "item_type": "Part",
                "supplier_id": None,
            }
        ],
    )
    payments_service.add_payment(inv["id"], amount_cents=1500, method="Card")

    # Soft-merge marker on loser (minimal column check; full merge tool tested elsewhere).
    conn = db_connection.connect()
    try:
        conn.execute(
            """
            UPDATE Clients
            SET IsDeleted = 1, MergedIntoClientId = ?
            WHERE Id = ?
            """,
            (client_a["id"], client_b["id"]),
        )
        conn.commit()
    finally:
        conn.close()

    payload = backup_service.export_to_json()
    assert "payments" in payload
    assert len(payload["payments"]) == 1
    assert payload["payments"][0]["amountCents"] == 1500
    assert "invoiceDocuments" in payload
    loser_row = next(c for c in payload["clients"] if c["id"] == client_b["id"])
    assert loser_row["isDeleted"] is True
    assert loser_row["mergedIntoClientId"] == client_a["id"]

    # Wipe and re-import
    conn = db_connection.connect()
    try:
        conn.execute("DELETE FROM Payments")
        conn.execute("DELETE FROM InvoiceItems")
        conn.execute("DELETE FROM Invoices")
        conn.execute("DELETE FROM Clients")
        conn.commit()
    finally:
        conn.close()

    result = backup_service.import_from_json(payload, ImportOptions())
    assert result.success is True
    assert result.payments_imported == 1

    conn = db_connection.connect()
    try:
        pay = conn.execute("SELECT AmountCents, Method FROM Payments").fetchone()
        assert pay is not None
        assert int(pay[0]) == 1500
        merged = conn.execute(
            "SELECT MergedIntoClientId, IsDeleted FROM Clients WHERE Id = ?",
            (client_b["id"],),
        ).fetchone()
        assert merged is not None
        assert int(merged[0]) == client_a["id"]
        assert int(merged[1]) == 1
    finally:
        conn.close()


@pytest.mark.area_routes
def test_sql_upload_rejected(monkeypatch, tmp_path):
    client = _client(monkeypatch, tmp_path)
    res = client.post(
        "/api/sysforge/backup/import.json",
        files={"file": ("dump.sql", b"BEGIN; SELECT 1;", "application/sql")},
    )
    assert res.status_code == 400
    assert "SQL" in res.json()["detail"] or "SQL" in str(res.json())

    res2 = client.post(
        "/api/sysforge/backup/restore",
        files={"file": ("dump.sql", b"BEGIN; SELECT 1;", "application/sql")},
    )
    assert res2.status_code == 400
    detail = res2.json().get("detail") or ""
    assert "SQL" in detail or SQL_IMPORT_REJECT_MESSAGE[:20] in detail


@pytest.mark.area_routes
def test_backup_routes_404_when_plugin_inactive(monkeypatch):
    monkeypatch.setattr(
        "integrations.sysforge.routes.is_plugin_active", lambda _pid: False
    )
    app = FastAPI()
    app.include_router(setup_sysforge_routes())
    with TestClient(app) as client:
        assert client.get("/api/sysforge/backup/list").status_code == 404
        assert client.post("/api/sysforge/backup/create", json={}).status_code == 404


@pytest.mark.area_routes
def test_global_export_unchanged_by_plugin_backup(monkeypatch, tmp_path):
    """Plugin backup must not be required for Odysseus /api/export shape."""
    _install_active(monkeypatch, tmp_path)
    backup_service.create_backup()
    # Host export route expects managers; assert contract keys only via source module.
    from routes import backup_routes

    src = Path(backup_routes.__file__).read_text(encoding="utf-8")
    assert "/api/export" in src
    assert "memories" in src
    assert "Clients" not in src
    assert "sysforge.db" not in src


@pytest.mark.area_routes
def test_backup_api_create_list_import(monkeypatch, tmp_path):
    client = _client(monkeypatch, tmp_path)
    created = client.post("/api/sysforge/backup/create", json={"include_drafts": False})
    assert created.status_code == 200
    assert created.json()["ok"] is True
    listed = client.get("/api/sysforge/backup/list")
    assert listed.status_code == 200
    assert len(listed.json()["backups"]) >= 1

    with FIXTURE.open("rb") as fh:
        res = client.post(
            "/api/sysforge/backup/import.json",
            files={"file": ("sample-export.json", fh, "application/json")},
            data={
                "import_clients": "true",
                "conflict": "skip",
            },
        )
    assert res.status_code == 200
    body = res.json()
    assert body["ok"] is True
    assert body["search_rebuilt"] is True
    assert body["clients_imported"] == 12


@pytest.mark.area_routes
def test_schedule_get_put(monkeypatch, tmp_path):
    client = _client(monkeypatch, tmp_path)
    got = client.get("/api/sysforge/backup/schedule")
    assert got.status_code == 200
    assert got.json()["schedule_enabled"] is False
    put = client.put(
        "/api/sysforge/backup/schedule",
        json={
            "schedule_enabled": True,
            "schedule_interval_days": 3,
            "retention_days": 14,
            "include_drafts": True,
        },
    )
    assert put.status_code == 200
    assert put.json()["schedule_enabled"] is True
    assert put.json()["schedule_interval_days"] == 3
