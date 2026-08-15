"""CSV mapper and processor-warning tests."""

import pytest
from fastapi import FastAPI
from sqlalchemy.orm import sessionmaker
from starlette.testclient import TestClient

import integrations.finance.database as finance_db
import integrations.finance.routes as finance_routes
from integrations.finance.models import FinanceBase
from integrations.finance.routes import setup_finance_routes
from integrations.finance.services.parsers import parse_generic_csv, parse_upload
from tests.conftest import make_finance_test_engine
from tests.fixtures.finance.synthetic_samples import NAVY_FEDERAL_SAMPLE, WELLS_FARGO_SAMPLE


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
    monkeypatch.setattr(finance_routes, "require_user", lambda request: "testuser")
    app = FastAPI()
    app.include_router(setup_finance_routes())
    with TestClient(app) as client:
        yield client
    finance_db.reset_engine_cache()


@pytest.mark.area_routes
def test_generic_debit_credit_and_parentheses_negative():
    csv_text = """Posted,Merchant,Withdrawal,Deposit
07/03/2026,Coffee,(12.00),
07/04/2026,Payroll,,1200.00
"""
    result = parse_generic_csv(
        csv_text,
        mapping={"date": "Posted", "payee": "Merchant", "debit": "Withdrawal", "credit": "Deposit"},
    )
    assert [tx.amount_cents for tx in result.transactions] == [-1200, 120000]
    assert result.transactions[0].fitid is None
    signed = parse_generic_csv(
        "Date,Payee,Amount\n07/03/2026,Coffee,(12.00)\n",
        mapping={"date": "Date", "payee": "Payee", "amount": "Amount"},
    )
    assert signed.transactions[0].amount_cents == -1200


@pytest.mark.area_routes
def test_needs_mapping_when_headers_unknown():
    csv_text = "ColA,ColB,ColC\n07/03/2026,Coffee,-12.00\n"
    fmt, rows, errors, extra = parse_upload("odd.csv", csv_text.encode("utf-8"))
    assert fmt == "csv_generic"
    assert extra["needs_mapping"] is True
    assert rows == []
    assert "ColA" in extra["columns"]


@pytest.mark.area_routes
def test_mapping_does_not_invent_fitid():
    csv_text = "Date,Payee,Amount\n07/03/2026,Coffee,-12.00\n"
    result = parse_generic_csv(csv_text, mapping={"date": "Date", "payee": "Payee", "amount": "Amount"})
    assert result.transactions[0].fitid is None


@pytest.mark.area_routes
def test_wells_and_nfcu_regression_stay_detected():
    fmt, rows, _errors, extra = parse_upload("wells.csv", WELLS_FARGO_SAMPLE.encode("utf-8"))
    assert fmt == "csv_wells_fargo"
    assert extra["needs_mapping"] is False
    assert len(rows) == 2
    fmt, rows, _errors, extra = parse_upload("nfcu.csv", NAVY_FEDERAL_SAMPLE.encode("utf-8"))
    assert fmt == "csv_navy_federal"
    assert extra["needs_mapping"] is False


@pytest.mark.area_routes
def test_saved_mapping_reused_by_fingerprint(finance_client):
    csv_text = "Posted,Merchant,Amt\n07/03/2026,Coffee,-12.00\n"
    acct = finance_client.post("/api/finance/accounts", json={"name": "PayPal", "purpose": "processor", "rail": "paypal"}).json()
    first = finance_client.post(
        "/api/finance/import/preview",
        data={"account_id": acct["id"]},
        files={"file": ("paypal.csv", csv_text.encode("utf-8"), "text/csv")},
    )
    assert first.status_code == 200
    body = first.json()
    assert body["needs_mapping"] is True
    saved = finance_client.post("/api/finance/import/mappings", json={
        "name": "PayPal export",
        "fingerprint": body["fingerprint"],
        "mapping": {"date": "Posted", "payee": "Merchant", "amount": "Amt"},
    })
    assert saved.status_code == 200
    second = finance_client.post(
        "/api/finance/import/preview",
        data={"account_id": acct["id"]},
        files={"file": ("paypal.csv", csv_text.encode("utf-8"), "text/csv")},
    )
    assert second.status_code == 200
    reused = second.json()
    assert reused["needs_mapping"] is False
    assert reused["new_count"] == 1
    assert reused["warning"]
    commit = finance_client.post("/api/finance/import/commit", json={"preview_id": reused["preview_id"]})
    assert commit.status_code == 200
    assert commit.json()["imported_count"] == 1
    assert commit.json()["warning"]


@pytest.mark.area_routes
def test_same_nfcu_file_into_two_accounts_does_not_mix(finance_client):
    business = finance_client.post("/api/finance/accounts", json={"name": "NFCU business", "purpose": "operating"}).json()
    trip = finance_client.post("/api/finance/accounts", json={"name": "NFCU trip", "purpose": "trip"}).json()
    for acct in (business, trip):
        preview = finance_client.post(
            "/api/finance/import/preview",
            data={"account_id": acct["id"]},
            files={"file": ("nfcu.csv", NAVY_FEDERAL_SAMPLE.encode("utf-8"), "text/csv")},
        )
        assert preview.status_code == 200
        commit = finance_client.post("/api/finance/import/commit", json={"preview_id": preview.json()["preview_id"]})
        assert commit.status_code == 200
        assert commit.json()["imported_count"] == 2
    txs_b = finance_client.get("/api/finance/transactions", params={"account_id": business["id"]}).json()
    txs_t = finance_client.get("/api/finance/transactions", params={"account_id": trip["id"]}).json()
    assert txs_b["total"] == 2
    assert txs_t["total"] == 2
