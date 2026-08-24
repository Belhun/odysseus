"""Goals CRUD and computed progress from posted books."""

from datetime import date

import pytest
from fastapi import FastAPI
from sqlalchemy.orm import sessionmaker
from starlette.testclient import TestClient
from tests.conftest import make_finance_test_engine

import integrations.finance.database as finance_db
import integrations.finance.models_goals  # noqa: F401
import integrations.finance.routes as finance_routes
from integrations.finance.models import FinanceBase
from integrations.finance.routes import setup_finance_routes
from integrations.finance.services.goals import ensure_goals_schema


@pytest.fixture()
def finance_client(monkeypatch, tmp_path):
    finance_db.reset_engine_cache()
    db_path = tmp_path / "finance.db"
    monkeypatch.setattr(finance_db, "finance_db_path", lambda: db_path)
    monkeypatch.setattr("integrations.finance.routes.is_plugin_active", lambda _pid: True)
    monkeypatch.setattr("integrations.finance.routes.is_plugin_installed", lambda _pid: False)

    engine = make_finance_test_engine(db_path)
    FinanceBase.metadata.create_all(engine)
    ensure_goals_schema(engine)
    session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    monkeypatch.setattr(finance_routes, "get_session_factory", lambda: session_factory)
    monkeypatch.setattr(finance_routes, "require_user", lambda request: "testuser")

    app = FastAPI()
    app.include_router(setup_finance_routes())
    with TestClient(app) as client:
        yield client
    finance_db.reset_engine_cache()


def _account(client, **kwargs):
    body = {"name": "Savings", "account_type": "savings", **kwargs}
    res = client.post("/api/finance/accounts", json=body)
    assert res.status_code == 200, res.text
    return res.json()


@pytest.mark.area_routes
def test_goals_crud_and_empty_list(finance_client):
    empty = finance_client.get("/api/finance/goals")
    assert empty.status_code == 200
    assert empty.json()["goals"] == []

    acct = _account(finance_client, opening_balance_cents=250000)
    created = finance_client.post(
        "/api/finance/goals",
        json={
            "name": "Emergency fund",
            "kind": "account",
            "target_cents": 1000000,
            "target_date": "2027-08-23",
            "account_id": acct["id"],
        },
    )
    assert created.status_code == 200, created.text
    body = created.json()
    assert body["name"] == "Emergency fund"
    assert body["current_cents"] == 250000
    assert body["remaining_cents"] == 750000
    assert body["percent"] == 25
    assert body["suggested_monthly_cents"] is not None

    listed = finance_client.get("/api/finance/goals").json()["goals"]
    assert len(listed) == 1
    one = finance_client.get(f"/api/finance/goals/{body['id']}")
    assert one.status_code == 200
    patched = finance_client.patch(
        f"/api/finance/goals/{body['id']}",
        json={"name": "Safety fund", "archived": True},
    )
    assert patched.status_code == 200
    assert patched.json()["name"] == "Safety fund"
    hidden = finance_client.get("/api/finance/goals").json()["goals"]
    assert hidden == []
    shown = finance_client.get("/api/finance/goals?include_archived=true").json()["goals"]
    assert len(shown) == 1
    deleted = finance_client.delete(f"/api/finance/goals/{body['id']}")
    assert deleted.status_code == 200
    assert finance_client.get(f"/api/finance/goals/{body['id']}").status_code == 404


@pytest.mark.area_routes
def test_goals_reject_bad_kind_and_empty_name(finance_client):
    bad = finance_client.post("/api/finance/goals", json={"name": "X", "kind": "envelope", "target_cents": 1})
    assert bad.status_code == 400
    empty = finance_client.post("/api/finance/goals", json={"name": "  ", "kind": "account", "target_cents": 1})
    assert empty.status_code == 400


@pytest.mark.area_routes
def test_account_goal_progress_minus_baseline(finance_client):
    acct = _account(finance_client, opening_balance_cents=40000)
    res = finance_client.post(
        "/api/finance/goals",
        json={
            "name": "Trip",
            "kind": "account",
            "target_cents": 100000,
            "account_id": acct["id"],
            "baseline_cents": 10000,
        },
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["current_cents"] == 30000
    assert body["remaining_cents"] == 70000
    assert body["percent"] == 30


@pytest.mark.area_routes
def test_loan_goal_uses_remaining_principal(finance_client):
    acct = _account(
        finance_client,
        name="Car loan",
        account_type="loan",
        opening_balance_cents=-800000,
    )
    res = finance_client.post(
        "/api/finance/goals",
        json={
            "name": "Pay the car",
            "kind": "loan",
            "target_cents": 1000000,
            "account_id": acct["id"],
        },
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["current_cents"] == 200000
    assert body["remaining_cents"] == 800000
    assert body["percent"] == 20


@pytest.mark.area_routes
def test_category_goal_true_spend_all_time(finance_client):
    acct = _account(finance_client, name="Checking", account_type="checking")
    cat = finance_client.post(
        "/api/finance/categories",
        json={"name": "GoalDining", "is_income": False},
    )
    assert cat.status_code == 200, cat.text
    cat_id = cat.json()["id"]
    tx = finance_client.post(
        "/api/finance/transactions",
        json={
            "account_id": acct["id"],
            "date": "2025-01-15",
            "amount_cents": -4000,
            "payee": "Cafe",
            "category_id": cat_id,
            "status": "cleared",
            "movement_class": "spend",
        },
    )
    assert tx.status_code == 200, tx.text
    pending = finance_client.post(
        "/api/finance/transactions",
        json={
            "account_id": acct["id"],
            "date": "2025-02-01",
            "amount_cents": -9000,
            "payee": "Pending cafe",
            "category_id": cat_id,
            "status": "pending",
            "movement_class": "spend",
        },
    )
    assert pending.status_code == 200, pending.text
    res = finance_client.post(
        "/api/finance/goals",
        json={
            "name": "Dining cap",
            "kind": "category",
            "target_cents": 10000,
            "category_id": cat_id,
        },
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["current_cents"] == 4000
    assert body["remaining_cents"] == 6000
    assert body["percent"] == 40


@pytest.mark.area_routes
def test_goals_owner_isolation(finance_client, monkeypatch):
    acct = _account(finance_client, opening_balance_cents=1000)
    created = finance_client.post(
        "/api/finance/goals",
        json={"name": "Mine", "kind": "account", "target_cents": 5000, "account_id": acct["id"]},
    )
    assert created.status_code == 200
    goal_id = created.json()["id"]
    monkeypatch.setattr(finance_routes, "require_user", lambda request: "other-user")
    listed = finance_client.get("/api/finance/goals")
    assert listed.status_code == 200
    assert listed.json()["goals"] == []
    missing = finance_client.get(f"/api/finance/goals/{goal_id}")
    assert missing.status_code == 404


@pytest.mark.area_routes
def test_suggested_monthly_divides_remaining(finance_client):
    acct = _account(finance_client, opening_balance_cents=0)
    today = date.today()
    target = date(today.year + 1, today.month, today.day) if today.day <= 28 else date(today.year + 1, today.month, 28)
    res = finance_client.post(
        "/api/finance/goals",
        json={
            "name": "Pace",
            "kind": "account",
            "target_cents": 120000,
            "target_date": target.isoformat(),
            "account_id": acct["id"],
        },
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["remaining_cents"] == 120000
    assert body["months_remaining"] == 12
    assert body["suggested_monthly_cents"] == 10000
