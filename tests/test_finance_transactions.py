"""Ledger CRUD, pins, and posted-balance route tests."""

import pytest
from fastapi import FastAPI
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import NullPool
from starlette.testclient import TestClient

import integrations.finance.database as finance_db
import integrations.finance.routes as finance_routes
from integrations.finance.models import FinanceBase, FinanceMutationLog
from integrations.finance.routes import setup_finance_routes
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
def test_account_purpose_and_pins_round_trip(finance_client):
    res = finance_client.post("/api/finance/accounts", json={
        "name": "Trip checking",
        "account_type": "checking",
        "purpose": "trip",
        "opening_balance_cents": 50000,
        "posted_pin_cents": 48000,
        "posted_pin_as_of": "2026-08-01",
        "available_cents": 47000,
        "available_as_of": "2026-08-01",
    })
    assert res.status_code == 200
    body = res.json()
    assert body["purpose"] == "trip"
    assert body["posted_cents"] == 50000
    assert body["balance_cents"] == 50000
    assert body["posted_pin_cents"] == 48000
    assert body["available_cents"] == 47000

    bad = finance_client.post("/api/finance/accounts", json={
        "name": "Nope",
        "purpose": "household",
    })
    assert bad.status_code == 400

    processor = finance_client.post("/api/finance/accounts", json={
        "name": "PayPal",
        "purpose": "processor",
        "rail": "paypal",
    })
    assert processor.status_code == 200
    assert processor.json()["rail"] == "paypal"


@pytest.mark.area_routes
def test_pins_endpoint_does_not_change_posted(finance_client):
    acct = finance_client.post("/api/finance/accounts", json={
        "name": "WF",
        "opening_balance_cents": 10000,
    }).json()
    pinned = finance_client.post(
        f"/api/finance/accounts/{acct['id']}/pins",
        json={"posted_pin_cents": 999, "available_cents": 111},
    )
    assert pinned.status_code == 200
    assert pinned.json()["posted_pin_cents"] == 999
    assert pinned.json()["available_cents"] == 111
    assert pinned.json()["posted_cents"] == 10000


@pytest.mark.area_routes
def test_import_and_batch_delete_never_touch_pins(finance_client):
    acct = finance_client.post("/api/finance/accounts", json={
        "name": "WF",
        "opening_balance_cents": 0,
        "posted_pin_cents": 77777,
        "available_cents": 88888,
    }).json()
    preview = finance_client.post(
        "/api/finance/import/preview",
        data={"account_id": acct["id"]},
        files={"file": ("wells.csv", WELLS_FARGO_SAMPLE.encode("utf-8"), "text/csv")},
    ).json()
    commit = finance_client.post("/api/finance/import/commit", json={"preview_id": preview["preview_id"]})
    assert commit.status_code == 200
    after_import = finance_client.get("/api/finance/accounts").json()["accounts"][0]
    assert after_import["posted_pin_cents"] == 77777
    assert after_import["available_cents"] == 88888
    assert after_import["posted_cents"] != 77777

    batches = finance_client.get("/api/finance/import/batches").json()["batches"]
    finance_client.delete(f"/api/finance/import/batches/{batches[0]['id']}")
    after_delete = finance_client.get("/api/finance/accounts").json()["accounts"][0]
    assert after_delete["posted_pin_cents"] == 77777
    assert after_delete["available_cents"] == 88888
    assert after_delete["posted_cents"] == 0


@pytest.mark.area_routes
def test_manual_create_void_delete_and_imported_409(finance_client):
    acct = finance_client.post("/api/finance/accounts", json={
        "name": "Cash",
        "opening_balance_cents": 10000,
        "posted_pin_cents": 10000,
    }).json()
    created = finance_client.post("/api/finance/transactions", json={
        "account_id": acct["id"],
        "date": "2026-08-02",
        "amount_cents": -1500,
        "payee": "Parking",
        "status": "cleared",
    })
    assert created.status_code == 200
    tx = created.json()
    assert tx["source"] == "manual"
    assert tx["is_manual"] is True

    listed = finance_client.get("/api/finance/accounts").json()["accounts"][0]
    assert listed["posted_cents"] == 8500
    assert listed["posted_pin_cents"] == 10000

    voided = finance_client.post(f"/api/finance/transactions/{tx['id']}/void")
    assert voided.status_code == 200
    assert voided.json()["status"] == "void"
    after_void = finance_client.get("/api/finance/accounts").json()["accounts"][0]
    assert after_void["posted_cents"] == 10000
    assert after_void["posted_pin_cents"] == 10000

    hidden = finance_client.get("/api/finance/transactions", params={"account_id": acct["id"]})
    assert hidden.json()["total"] == 0
    shown = finance_client.get(
        "/api/finance/transactions",
        params={"account_id": acct["id"], "include_void": True},
    )
    assert shown.json()["total"] == 1

    finance_client.post(f"/api/finance/transactions/{tx['id']}/unvoid")
    deleted = finance_client.delete(f"/api/finance/transactions/{tx['id']}")
    assert deleted.status_code == 200

    preview = finance_client.post(
        "/api/finance/import/preview",
        data={"account_id": acct["id"]},
        files={"file": ("wells.csv", WELLS_FARGO_SAMPLE.encode("utf-8"), "text/csv")},
    ).json()
    finance_client.post("/api/finance/import/commit", json={"preview_id": preview["preview_id"]})
    imported = finance_client.get("/api/finance/transactions", params={"account_id": acct["id"]}).json()
    imported_id = imported["transactions"][0]["id"]
    blocked = finance_client.delete(f"/api/finance/transactions/{imported_id}")
    assert blocked.status_code == 409


@pytest.mark.area_routes
def test_patch_manual_amount_and_mutation_log(finance_client):
    acct = finance_client.post("/api/finance/accounts", json={
        "name": "Cash",
        "opening_balance_cents": 0,
    }).json()
    tx = finance_client.post("/api/finance/transactions", json={
        "account_id": acct["id"],
        "date": "2026-08-02",
        "amount_cents": -400,
        "payee": "Coffee",
    }).json()
    patched = finance_client.patch(
        f"/api/finance/transactions/{tx['id']}",
        json={"amount_cents": -500, "date": "2026-08-03"},
    )
    assert patched.status_code == 200
    assert patched.json()["amount_cents"] == -500
    assert patched.json()["date"] == "2026-08-03"
    assert finance_client.get("/api/finance/accounts").json()["accounts"][0]["posted_cents"] == -500

    from integrations.finance.routes import get_session_factory

    db = get_session_factory()()
    try:
        logs = db.query(FinanceMutationLog).filter(FinanceMutationLog.owner == "testuser").all()
        actions = {row.action for row in logs}
        assert "create" in actions
        assert "patch" in actions
    finally:
        db.close()
