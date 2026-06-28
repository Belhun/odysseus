"""Finance API route tests."""

import pytest
from fastapi import FastAPI
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import NullPool
from starlette.testclient import TestClient

import core.database as cdb
import routes.finance_routes as finance_routes
from core.database import FinanceAccount, SessionLocal
from routes.finance_routes import setup_finance_routes
from tests.fixtures.finance.synthetic_samples import WELLS_FARGO_SAMPLE


@pytest.fixture()
def finance_client(monkeypatch, tmp_path):
    engine = create_engine(
        f"sqlite:///{tmp_path / 'finance.db'}",
        connect_args={"check_same_thread": False},
        poolclass=NullPool,
    )
    cdb.Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    monkeypatch.setattr(finance_routes, "SessionLocal", session_factory)

    def _fake_require_user(request):
        return "testuser"

    monkeypatch.setattr(finance_routes, "require_user", _fake_require_user)

    app = FastAPI()
    app.include_router(setup_finance_routes())
    with TestClient(app) as client:
        yield client


@pytest.mark.area_routes
@pytest.mark.area_security
def test_finance_accounts_require_owner_scope(finance_client):
    res = finance_client.post("/api/finance/accounts", json={
        "name": "Checking",
        "institution": "Test Bank",
        "account_type": "checking",
    })
    assert res.status_code == 200
    account_id = res.json()["id"]

    db = finance_routes.SessionLocal()
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
    preview_id = body["preview_id"]

    commit = finance_client.post("/api/finance/import/commit", json={"preview_id": preview_id})
    assert commit.status_code == 200
    assert commit.json()["imported_count"] == 2

    txs = finance_client.get(f"/api/finance/transactions?account_id={account_id}")
    assert txs.status_code == 200
    assert txs.json()["total"] == 2

    preview2 = finance_client.post(
        "/api/finance/import/preview",
        data={"account_id": account_id},
        files={"file": ("wells.csv", WELLS_FARGO_SAMPLE.encode("utf-8"), "text/csv")},
    )
    assert preview2.json()["duplicate_count"] == 2
