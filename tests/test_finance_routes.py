"""Finance plugin API and install tests."""

import json
from pathlib import Path

import pytest
from fastapi import FastAPI
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import NullPool
from starlette.testclient import TestClient

import integrations.finance.database as finance_db
import integrations.finance.routes as finance_routes
from integrations.finance.models import FinanceAccount, FinanceBase
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

    engine = create_engine(
        f"sqlite:///{db_path}",
        connect_args={"check_same_thread": False},
        poolclass=NullPool,
    )
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
