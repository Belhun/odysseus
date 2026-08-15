"""Finance plugin API and install tests."""

import json
from pathlib import Path

import pytest
from fastapi import FastAPI
from sqlalchemy.orm import sessionmaker
from starlette.testclient import TestClient
from tests.conftest import make_finance_test_engine

import integrations.finance.database as finance_db
import integrations.finance.routes as finance_routes
from integrations.finance.database import init_finance_db
from integrations.finance.models import FinanceAccount, FinanceBase, FinanceTransaction
from integrations.finance.routes import setup_finance_routes
from integrations.finance.install import run_install
from integrations.finance.uninstall import run_uninstall
from routes.plugin_routes import setup_plugin_routes
from tests.fixtures.finance.synthetic_samples import WELLS_FARGO_SAMPLE


@pytest.fixture()
def finance_client(monkeypatch, tmp_path):
    finance_db.reset_engine_cache()
    db_path = tmp_path / "finance.db"
    monkeypatch.setattr(finance_db, "finance_db_path", lambda: db_path)
    monkeypatch.setattr("integrations.finance.routes.is_plugin_active", lambda _pid: True)

    engine = make_finance_test_engine(db_path)
    FinanceBase.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    monkeypatch.setattr(finance_routes, "get_session_factory", lambda: session_factory)

    def _fake_require_user(request):
        return "testuser"

    monkeypatch.setattr(finance_routes, "require_user", _fake_require_user)

    app = FastAPI()
    app.include_router(setup_finance_routes())
    with TestClient(app) as client:
        yield client
    finance_db.reset_engine_cache()


@pytest.mark.area_routes
@pytest.mark.area_security
def test_finance_accounts_owner_scoped(finance_client):
    res = finance_client.post("/api/finance/accounts", json={
        "name": "Checking",
        "institution": "Test Bank",
        "account_type": "checking",
    })
    assert res.status_code == 200
    account_id = res.json()["id"]

    db = finance_routes.get_session_factory()()
    try:
        row = db.query(FinanceAccount).filter(FinanceAccount.id == account_id).one()
        assert row.owner == "testuser"
    finally:
        db.close()


@pytest.mark.area_routes
def test_finance_import_preview_and_commit(finance_client):
    acct = finance_client.post("/api/finance/accounts", json={"name": "WF", "account_type": "checking"}).json()
    account_id = acct["id"]

    preview = finance_client.post(
        "/api/finance/import/preview",
        data={"account_id": account_id},
        files={"file": ("wells.csv", WELLS_FARGO_SAMPLE.encode("utf-8"), "text/csv")},
    )
    assert preview.status_code == 200
    body = preview.json()
    assert body["new_count"] == 2

    commit = finance_client.post("/api/finance/import/commit", json={"preview_id": body["preview_id"]})
    assert commit.status_code == 200
    assert commit.json()["imported_count"] == 2


@pytest.mark.area_routes
def test_finance_transactions_pagination(finance_client):
    acct = finance_client.post("/api/finance/accounts", json={"name": "WF", "account_type": "checking"}).json()
    account_id = acct["id"]

    preview = finance_client.post(
        "/api/finance/import/preview",
        data={"account_id": account_id},
        files={"file": ("wells.csv", WELLS_FARGO_SAMPLE.encode("utf-8"), "text/csv")},
    ).json()
    finance_client.post("/api/finance/import/commit", json={"preview_id": preview["preview_id"]})

    page1 = finance_client.get(f"/api/finance/transactions?account_id={account_id}&limit=1&offset=0")
    assert page1.status_code == 200
    body1 = page1.json()
    assert body1["total"] == 2
    assert len(body1["transactions"]) == 1

    page2 = finance_client.get(f"/api/finance/transactions?account_id={account_id}&limit=1&offset=1")
    assert page2.status_code == 200
    body2 = page2.json()
    assert body2["total"] == 2
    assert len(body2["transactions"]) == 1
    assert body1["transactions"][0]["id"] != body2["transactions"][0]["id"]


@pytest.mark.area_routes
def test_plugin_install_writes_marker_and_feature(monkeypatch, tmp_path):
    plugins_root = tmp_path / "plugins"
    monkeypatch.setattr("src.plugins.registry.PLUGINS_DATA_ROOT", plugins_root)
    monkeypatch.setattr("src.plugins.registry.plugin_data_dir", lambda pid: plugins_root / pid)
    monkeypatch.setattr(
        "integrations.finance.database.finance_db_path",
        lambda: plugins_root / "finance" / "finance.db",
    )
    monkeypatch.setattr("src.settings.FEATURES_FILE", str(tmp_path / "features.json"))
    finance_db.reset_engine_cache()

    result = run_install()
    assert result["ok"] is True
    marker = plugins_root / "finance" / "installed.json"
    assert marker.is_file()
    features = json.loads((tmp_path / "features.json").read_text())
    assert features.get("finance") is True

    uninstall = run_uninstall(remove_data=False)
    assert uninstall["ok"] is True
    assert not marker.is_file()


@pytest.mark.area_routes
def test_plugin_catalog_lists_finance(monkeypatch):
    app = FastAPI()
    app.include_router(setup_plugin_routes())
    with TestClient(app) as client:
        res = client.get("/api/plugins/catalog")
        assert res.status_code == 200
        ids = [p["id"] for p in res.json().get("plugins", [])]
        assert "finance" in ids
        assert "sysforge" in ids


@pytest.mark.area_routes
@pytest.mark.area_security
def test_plugin_install_and_uninstall_require_admin(monkeypatch):
    app = FastAPI()
    app.include_router(setup_plugin_routes())

    def deny(_request):
        from fastapi import HTTPException
        raise HTTPException(403, "Admin only")

    monkeypatch.setattr("routes.plugin_routes.require_admin", deny)
    with TestClient(app) as client:
        assert client.post("/api/plugins/finance/install").status_code == 403
        assert client.post("/api/plugins/finance/uninstall", json={}).status_code == 403


@pytest.mark.area_routes
def test_plugin_install_idempotent(monkeypatch, tmp_path):
    plugins_root = tmp_path / "plugins"
    monkeypatch.setattr("src.plugins.registry.PLUGINS_DATA_ROOT", plugins_root)
    monkeypatch.setattr("src.plugins.registry.plugin_data_dir", lambda pid: plugins_root / pid)
    monkeypatch.setattr(
        "integrations.finance.database.finance_db_path",
        lambda: plugins_root / "finance" / "finance.db",
    )
    monkeypatch.setattr("src.settings.FEATURES_FILE", str(tmp_path / "features.json"))
    finance_db.reset_engine_cache()

    first = run_install()
    assert first["ok"] is True
    assert first.get("already_installed") is not True

    second = run_install()
    assert second["ok"] is True
    assert second.get("already_installed") is True
    assert second.get("reload_required") is False


@pytest.mark.area_routes
def test_finance_garbage_ofx_returns_400(finance_client):
    acct = finance_client.post("/api/finance/accounts", json={"name": "WF", "account_type": "checking"}).json()
    res = finance_client.post(
        "/api/finance/import/preview",
        data={"account_id": acct["id"]},
        files={"file": ("bad.ofx", b"not valid ofx content", "application/octet-stream")},
    )
    assert res.status_code == 400
    assert res.status_code != 500


@pytest.mark.area_routes
def test_finance_empty_upload_returns_400(finance_client):
    acct = finance_client.post("/api/finance/accounts", json={"name": "WF", "account_type": "checking"}).json()
    res = finance_client.post(
        "/api/finance/import/preview",
        data={"account_id": acct["id"]},
        files={"file": ("empty.csv", b"", "text/csv")},
    )
    assert res.status_code == 400


@pytest.mark.area_routes
def test_finance_net_worth_route(finance_client):
    finance_client.post("/api/finance/accounts", json={
        "name": "Checking",
        "account_type": "checking",
        "opening_balance_cents": 100000,
    })
    finance_client.post("/api/finance/accounts", json={
        "name": "Visa",
        "account_type": "credit_card",
        "opening_balance_cents": -50000,
    })
    res = finance_client.get("/api/finance/reports/net-worth")
    assert res.status_code == 200
    body = res.json()
    assert body["assets_cents"] == 100000
    assert body["liabilities_cents"] == 50000
    assert body["net_worth_cents"] == 50000


@pytest.mark.area_routes
def test_finance_transaction_filters_and_csv_export(finance_client):
    acct = finance_client.post("/api/finance/accounts", json={"name": "WF", "account_type": "checking"}).json()
    preview = finance_client.post(
        "/api/finance/import/preview",
        data={"account_id": acct["id"]},
        files={"file": ("wells.csv", WELLS_FARGO_SAMPLE.encode("utf-8"), "text/csv")},
    ).json()
    finance_client.post("/api/finance/import/commit", json={"preview_id": preview["preview_id"]})

    filtered = finance_client.get(
        "/api/finance/transactions",
        params={"search": "MERCHANT", "max_amount_cents": 0},
    )
    assert filtered.status_code == 200
    assert filtered.json()["total"] >= 1

    csv_res = finance_client.get("/api/finance/transactions/export.csv", params={"search": "MERCHANT"})
    assert csv_res.status_code == 200
    assert "text/csv" in csv_res.headers.get("content-type", "")
    assert "payee" in csv_res.text.splitlines()[0].lower()


@pytest.mark.area_routes
def test_finance_wal_pragmas_on_connect(monkeypatch, tmp_path):
    finance_db.reset_engine_cache()
    db_path = tmp_path / "pragma.db"
    monkeypatch.setattr(finance_db, "finance_db_path", lambda: db_path)
    engine = finance_db.get_engine()
    with engine.connect() as conn:
        journal = conn.exec_driver_sql("PRAGMA journal_mode").scalar()
        busy = conn.exec_driver_sql("PRAGMA busy_timeout").scalar()
        sync = conn.exec_driver_sql("PRAGMA synchronous").scalar()
    assert str(journal).lower() == "wal"
    assert int(busy) == 5000
    assert int(sync) == 1  # NORMAL
    finance_db.reset_engine_cache()


@pytest.mark.area_routes
def test_finance_dedup_unique_index_migration(monkeypatch, tmp_path):
    finance_db.reset_engine_cache()
    db_path = tmp_path / "dedup.db"
    monkeypatch.setattr(finance_db, "finance_db_path", lambda: db_path)

    engine = make_finance_test_engine(db_path)
    FinanceBase.metadata.create_all(engine)
    from sqlalchemy import text
    with engine.connect() as conn:
        conn.execute(text("DROP INDEX IF EXISTS ix_finance_tx_account_dedup"))
        conn.execute(text(
            "CREATE INDEX ix_finance_tx_account_dedup "
            "ON finance_transactions (account_id, dedup_hash)"
        ))
        conn.commit()
    session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    db = session_factory()
    try:
        acct = FinanceAccount(id="acct-dedup", owner="u1", name="Test", account_type="checking")
        db.add(acct)
        for i in range(2):
            db.add(FinanceTransaction(
                id=f"tx-dup-{i}",
                owner="u1",
                account_id=acct.id,
                date=__import__("datetime").date(2026, 1, i + 1),
                amount_cents=-100,
                payee="DUP",
                dedup_hash="same-hash",
            ))
        db.commit()
    finally:
        db.close()
    engine.dispose()

    finance_db.reset_engine_cache()
    init_finance_db()

    db2 = finance_db.get_session_factory()()
    try:
        count = db2.query(FinanceTransaction).filter(
            FinanceTransaction.dedup_hash == "same-hash"
        ).count()
        assert count == 1
    finally:
        db2.close()
    finance_db.reset_engine_cache()
