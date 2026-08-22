"""Web-steal v1 APIs: paste import, splits GET/DELETE, operators, payees, averages."""

from datetime import date

import pytest
from fastapi import FastAPI
from sqlalchemy.orm import sessionmaker
from starlette.testclient import TestClient
from tests.conftest import make_finance_test_engine
from tests.fixtures.finance.synthetic_samples import WELLS_FARGO_SAMPLE

import integrations.finance.database as finance_db
import integrations.finance.routes as finance_routes
from integrations.finance.models import (
    FinanceBase,
    FinanceCategorizationRule,
    FinanceTransaction,
)
from integrations.finance.routes import setup_finance_routes
from integrations.finance.services.categories import (
    apply_rules_to_transactions,
    create_rule_for_owner,
    rule_matches_payee,
    rule_matches_transaction,
)
from integrations.finance.services.reports import previous_months


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


def _account(client):
    return client.post("/api/finance/accounts", json={"name": "Checking", "account_type": "checking"}).json()


def _cat(client, name="Groceries"):
    cats = client.get("/api/finance/categories").json()["categories"]
    return next(c for c in cats if c["name"] == name)


@pytest.mark.area_routes
def test_preview_text_matches_multipart_file_preview(finance_client):
    acct = _account(finance_client)
    file_preview = finance_client.post(
        "/api/finance/import/preview",
        data={"account_id": acct["id"]},
        files={"file": ("wells.csv", WELLS_FARGO_SAMPLE.encode("utf-8"), "text/csv")},
    )
    assert file_preview.status_code == 200, file_preview.text
    text_preview = finance_client.post(
        "/api/finance/import/preview-text",
        json={
            "account_id": acct["id"],
            "text": WELLS_FARGO_SAMPLE,
            "filename": "clipboard.csv",
        },
    )
    assert text_preview.status_code == 200, text_preview.text
    file_body = file_preview.json()
    text_body = text_preview.json()
    assert text_body["new_count"] == file_body["new_count"] == 2
    assert text_body["format"] == file_body["format"]
    assert len(text_body["rows"]) == len(file_body["rows"])


@pytest.mark.area_routes
def test_preview_text_rejects_oversized_payload(finance_client, monkeypatch):
    acct = _account(finance_client)
    monkeypatch.setattr(finance_routes, "FINANCE_IMPORT_MAX_BYTES", 16)
    res = finance_client.post(
        "/api/finance/import/preview-text",
        json={"account_id": acct["id"], "text": "x" * 40},
    )
    assert res.status_code == 413


@pytest.mark.area_routes
def test_split_get_delete_and_list_flags(finance_client):
    acct = _account(finance_client)
    groc = _cat(finance_client, "Groceries")
    gas = _cat(finance_client, "Gas & Fuel")
    parent = finance_client.post("/api/finance/transactions", json={
        "account_id": acct["id"],
        "date": "2026-07-10",
        "amount_cents": -8000,
        "payee": "TARGET",
        "movement_class": "spend",
    }).json()
    put = finance_client.put(
        f"/api/finance/transactions/{parent['id']}/splits",
        json={
            "splits": [
                {"category_id": groc["id"], "amount_cents": -5000, "memo": "food"},
                {"category_id": gas["id"], "amount_cents": -3000, "memo": "fuel"},
            ]
        },
    )
    assert put.status_code == 200, put.text
    listed = finance_client.get("/api/finance/transactions", params={"account_id": acct["id"]}).json()
    row = next(tx for tx in listed["transactions"] if tx["id"] == parent["id"])
    assert row["is_split"] is True
    assert row["split_count"] == 2
    assert row["amount_cents"] == -8000

    got = finance_client.get(f"/api/finance/transactions/{parent['id']}/splits")
    assert got.status_code == 200
    assert len(got.json()["splits"]) == 2

    blocked = finance_client.patch(
        f"/api/finance/transactions/{parent['id']}",
        json={"category_id": groc["id"]},
    )
    assert blocked.status_code == 400

    too_many = finance_client.put(
        f"/api/finance/transactions/{parent['id']}/splits",
        json={"splits": [{"amount_cents": -1, "memo": str(i)} for i in range(63)]},
    )
    assert too_many.status_code == 422

    cleared = finance_client.delete(f"/api/finance/transactions/{parent['id']}/splits")
    assert cleared.status_code == 200
    assert cleared.json()["deleted"] == 2
    empty = finance_client.get(f"/api/finance/transactions/{parent['id']}/splits").json()
    assert empty["splits"] == []
    listed2 = finance_client.get("/api/finance/transactions", params={"account_id": acct["id"]}).json()
    row2 = next(tx for tx in listed2["transactions"] if tx["id"] == parent["id"])
    assert row2["is_split"] is False
    assert row2["amount_cents"] == -8000


@pytest.mark.area_routes
def test_payee_autocomplete_orders_by_frequency(finance_client):
    acct = _account(finance_client)
    for i, payee in enumerate(["STARBUCKS", "STARBUCKS", "SAFEWAY", "STARBUCKS"]):
        finance_client.post("/api/finance/transactions", json={
            "account_id": acct["id"],
            "date": f"2026-07-{10 + i:02d}",
            "amount_cents": -400,
            "payee": payee,
        })
    res = finance_client.get("/api/finance/payees", params={"q": "STAR", "limit": 10})
    assert res.status_code == 200, res.text
    payees = res.json()["payees"]
    assert payees[0]["payee"] == "STARBUCKS"
    assert payees[0]["count"] == 3
    names = [p["payee"] for p in payees]
    assert "SAFEWAY" not in names


@pytest.mark.area_routes
def test_operator_rules_and_legacy_matcher(finance_client):
    acct = _account(finance_client)
    groc = _cat(finance_client, "Groceries")
    dining = _cat(finance_client, "Dining")
    finance_client.post("/api/finance/transactions", json={
        "account_id": acct["id"],
        "date": "2026-07-01",
        "amount_cents": -1200,
        "payee": "STARBUCKS #123",
        "memo": "latte",
    })
    finance_client.post("/api/finance/transactions", json={
        "account_id": acct["id"],
        "date": "2026-07-02",
        "amount_cents": -800,
        "payee": "SAFEWAY",
        "memo": "STAR market",
    })
    created = finance_client.post("/api/finance/rules", json={
        "pattern": "STARBUCKS",
        "operator": "contains",
        "match_field": "payee",
        "category_id": dining["id"],
        "priority": 10,
        "apply_existing": True,
    })
    assert created.status_code == 200, created.text
    listed = finance_client.get("/api/finance/transactions").json()["transactions"]
    by_payee = {tx["payee"]: tx for tx in listed}
    assert by_payee["STARBUCKS #123"]["category_id"] == dining["id"]
    assert by_payee["SAFEWAY"]["category_id"] is None

    memo_rule = finance_client.post("/api/finance/rules", json={
        "pattern": "STAR",
        "operator": "contains",
        "match_field": "memo",
        "category_id": groc["id"],
        "priority": 20,
        "apply_existing": True,
    })
    assert memo_rule.status_code == 200
    listed2 = finance_client.get("/api/finance/transactions").json()["transactions"]
    by_payee2 = {tx["payee"]: tx for tx in listed2}
    assert by_payee2["SAFEWAY"]["category_id"] == groc["id"]

    db = finance_routes.get_session_factory()()
    try:
        tx = FinanceTransaction(
            payee="WHOLE FOODS",
            memo="",
        )
        legacy = FinanceCategorizationRule(pattern="WHOLE", operator="", match_field="payee")
        assert rule_matches_transaction(legacy, tx)
        assert rule_matches_payee("WHOLE", "WHOLE FOODS")
        equals = FinanceCategorizationRule(pattern="WHOLE FOODS", operator="equals", match_field="payee")
        assert rule_matches_transaction(equals, tx)
        assert not rule_matches_transaction(
            FinanceCategorizationRule(pattern="WHOLE", operator="equals", match_field="payee"),
            tx,
        )
        starts = FinanceCategorizationRule(pattern="WHOLE", operator="starts_with", match_field="payee")
        assert rule_matches_transaction(starts, tx)
        ends = FinanceCategorizationRule(pattern="FOODS", operator="ends_with", match_field="payee")
        assert rule_matches_transaction(ends, tx)
        missing = FinanceCategorizationRule(pattern="COSTCO", operator="not_contains", match_field="payee")
        assert rule_matches_transaction(missing, tx)
        regex = FinanceCategorizationRule(pattern=r"WHOLE\s+FOODS", operator="regex", match_field="payee")
        assert rule_matches_transaction(regex, tx)
    finally:
        db.close()


@pytest.mark.area_routes
def test_create_rule_without_operator_stays_legacy(finance_client):
    _account(finance_client)
    dining = _cat(finance_client, "Dining")
    res = finance_client.post("/api/finance/rules", json={
        "pattern": "PIZZA",
        "category_id": dining["id"],
        "priority": 50,
    })
    assert res.status_code == 200, res.text
    rules = finance_client.get("/api/finance/rules").json()["rules"]
    assert rules[0]["operator"] == ""
    assert rules[0]["match_field"] == "payee"


@pytest.mark.area_routes
def test_budget_copy_month_averages_exclude_requested_month(finance_client):
    acct = _account(finance_client)
    groc = _cat(finance_client, "Groceries")
    amounts = {
        date(2026, 4, 10): -3000,
        date(2026, 5, 10): -6000,
        date(2026, 6, 10): -9000,
        date(2026, 7, 10): -11100,
    }
    for day, cents in amounts.items():
        finance_client.post("/api/finance/transactions", json={
            "account_id": acct["id"],
            "date": day.isoformat(),
            "amount_cents": cents,
            "payee": "SAFEWAY",
            "category_id": groc["id"],
            "movement_class": "spend",
        })
    res = finance_client.get("/api/finance/budgets", params={"month": "2026-07"})
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["average_lookback_months"] == 3
    assert body["average_source_months"] == previous_months("2026-07", 3)
    grocery = next(r for r in body["categories"] if r["category_id"] == groc["id"])
    assert grocery["spent_cents"] == 11100
    assert grocery["average_spend_cents"] == 6000
    assert grocery["suggested_limit_cents"] == 6000


@pytest.mark.area_routes
def test_previous_months_rolls_year():
    assert previous_months("2026-01", 3) == ["2025-12", "2025-11", "2025-10"]


@pytest.mark.area_routes
def test_create_rule_for_owner_accepts_operator_without_agent_change(finance_client):
    _account(finance_client)
    dining = _cat(finance_client, "Dining")
    db = finance_routes.get_session_factory()()
    try:
        rule = create_rule_for_owner(
            db,
            "testuser",
            pattern="NETFLIX",
            category_id=dining["id"],
            apply_existing=False,
        )
        assert rule.operator == ""
        assert rule.match_field == "payee"
        apply_rules_to_transactions(db, "testuser", [])
    finally:
        db.close()
