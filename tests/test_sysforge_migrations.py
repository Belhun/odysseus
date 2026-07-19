"""Migration runner: apply, idempotent, checksum mismatch, post-0012 shapes."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from integrations.sysforge.db.connection import connect
from integrations.sysforge.db.exceptions import ChecksumMismatchError
from integrations.sysforge.db.migration_runner import (
    discover_migrations,
    run_migrations,
    schema_status,
)
from integrations.sysforge.install import run_install


REQUIRED_TABLES = (
    "Clients",
    "Invoices",
    "InvoiceItems",
    "Parts",
    "Suppliers",
    "Settings",
    "SchemaVersion",
)


def _column_type(conn, table: str, column: str) -> str | None:
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    for row in rows:
        # cid, name, type, notnull, dflt_value, pk
        if row[1] == column:
            return str(row[2]).upper()
    return None


@pytest.mark.area_routes
def test_fresh_migrate_creates_core_tables(tmp_path):
    db = tmp_path / "sysforge.db"
    report = run_migrations(db)
    assert report.applied_count == 29
    assert report.latest_id == 30
    assert report.latest_name == "0030_client_merge"
    assert len(report.applied_now) == 29

    conn = connect(db)
    try:
        names = {
            r[0]
            for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type IN ('table', 'view')"
            ).fetchall()
        }
        for table in REQUIRED_TABLES:
            assert table in names, f"missing table {table}"
        assert "parts_fts" in names
        assert "clients_fts" in names
        assert "InvoiceDocuments" in names
        assert "Payments" in names
        assert "PartPriceHistory" in names
        cols = {r[1] for r in conn.execute("PRAGMA table_info(Parts)").fetchall()}
        assert "PreferredSupplierId" in cols
        supplier_cols = {
            r[1] for r in conn.execute("PRAGMA table_info(Suppliers)").fetchall()
        }
        assert "IsPreferred" in supplier_cols
        assert "DefaultShippingRateCents" in supplier_cols
        client_cols = {
            r[1] for r in conn.execute("PRAGMA table_info(Clients)").fetchall()
        }
        assert "LastInteractedAt" in client_cols
    finally:
        conn.close()


@pytest.mark.area_routes
def test_screw_maps_tables_exist(tmp_path):
    db = tmp_path / "sysforge.db"
    run_migrations(db)
    conn = connect(db)
    try:
        names = {
            r[0]
            for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        for table in (
            "ScrewMaps",
            "ScrewMapImages",
            "ScrewData",
            "NoteMarkers",
            "ScrewMapSets",
            "ScrewMapSetTags",
        ):
            assert table in names, f"missing {table}"
        cols = {
            r[1] for r in conn.execute("PRAGMA table_info(ScrewMapImages)").fetchall()
        }
        assert "IsReusedFromLibrary" in cols
    finally:
        conn.close()


@pytest.mark.area_routes
def test_post_0012_money_columns_are_integer(tmp_path):
    db = tmp_path / "sysforge.db"
    run_migrations(db)
    conn = connect(db)
    try:
        assert _column_type(conn, "Invoices", "FinalTotalCents") == "INTEGER"
        assert _column_type(conn, "InvoiceItems", "UnitPriceCents") == "INTEGER"
        assert _column_type(conn, "Parts", "BasePriceCents") == "INTEGER"
    finally:
        conn.close()


@pytest.mark.area_routes
def test_migrate_idempotent(tmp_path):
    db = tmp_path / "sysforge.db"
    first = run_migrations(db)
    second = run_migrations(db)
    assert first.applied_count == second.applied_count == 29
    assert second.applied_now == []
    assert set(second.already_applied) == set(first.applied_now)


@pytest.mark.area_routes
def test_checksum_tamper_stored_row(tmp_path):
    db = tmp_path / "sysforge.db"
    run_migrations(db)
    conn = connect(db)
    try:
        conn.execute(
            "UPDATE SchemaVersion SET Checksum = ? WHERE Id = ?",
            ("DEADBEEF", 2),
        )
        conn.commit()
    finally:
        conn.close()

    with pytest.raises(ChecksumMismatchError) as exc_info:
        run_migrations(db)
    err = exc_info.value
    assert err.error_code == "MIGR-CHK-001"
    assert err.migration_id == 2
    assert err.applied_checksum == "DEADBEEF"


@pytest.mark.area_routes
def test_file_tamper_after_apply(tmp_path):
    db = tmp_path / "sysforge.db"
    mig_dir = tmp_path / "migrations"
    shutil.copytree(
        Path(__file__).resolve().parents[1]
        / "integrations"
        / "sysforge"
        / "migrations",
        mig_dir,
    )
    run_migrations(db, migrations_path=mig_dir)

    target = next(mig_dir.glob("0002_*.sql"))
    target.write_text(target.read_text(encoding="utf-8") + "\n-- tampered\n", encoding="utf-8")

    with pytest.raises(ChecksumMismatchError) as exc_info:
        run_migrations(db, migrations_path=mig_dir)
    assert exc_info.value.migration_id == 2
    assert exc_info.value.error_code == "MIGR-CHK-001"


@pytest.mark.area_routes
def test_discover_starts_at_0002_not_0001():
    migrations = discover_migrations()
    assert migrations[0].id == 2
    assert migrations[-1].id == 30
    assert len(migrations) == 29


@pytest.mark.area_routes
def test_schema_status_missing_db(tmp_path):
    status = schema_status(tmp_path / "missing.db")
    assert status["db_exists"] is False
    assert status["latest_id"] is None


@pytest.mark.area_routes
def test_install_populates_schema_version(monkeypatch, tmp_path):
    plugins_root = tmp_path / "plugins"
    monkeypatch.setattr("src.plugins.registry.PLUGINS_DATA_ROOT", plugins_root)
    monkeypatch.setattr(
        "src.plugins.registry.plugin_data_dir", lambda pid: plugins_root / pid
    )
    monkeypatch.setattr("src.settings.FEATURES_FILE", str(tmp_path / "features.json"))

    result = run_install()
    assert result["ok"] is True
    migrate_steps = [s for s in result["steps"] if s["step"] == "migrate"]
    assert migrate_steps and migrate_steps[0]["status"] == "ok"

    db = plugins_root / "sysforge" / "sysforge.db"
    conn = connect(db)
    try:
        count = conn.execute("SELECT COUNT(*) FROM SchemaVersion").fetchone()[0]
        assert count == 29
        names = {
            r[0]
            for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        assert "InvoiceDocuments" in names
        assert "Payments" in names
        for table in REQUIRED_TABLES:
            assert table in names
    finally:
        conn.close()

    # Second install is upgrade path — still migrates idempotently
    again = run_install()
    assert again["ok"] is True
    assert again.get("already_installed") is True
