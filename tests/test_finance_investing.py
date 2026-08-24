"""Investing holdings API: manual values, owner isolation, no ledger posts."""

from pathlib import Path

import pytest
from fastapi import APIRouter, FastAPI
from sqlalchemy.orm import sessionmaker
from starlette.testclient import TestClient

import integrations.finance.database as finance_db
import integrations.finance.routes_investing as investing_routes
from integrations.finance.models import FinanceAccount, FinanceBase, FinanceTransaction
from integrations.finance.models_investing import FinanceInvestValuation
from integrations.finance.routes_investing import mount_investing
from integrations.finance.services.accounts import ACCOUNT_TYPES, create_account_for_owner
from integrations.finance.services.investing import (
    ensure_invest_schema,
    millishares_from_input,
    shares_string,
)
from tests.conftest import make_finance_test_engine

_REPO = Path(__file__).resolve().parent.parent
_JS = _REPO / "integrations" / "finance" / "static" / "js" / "investing.js"


@pytest.fixture()
def invest_client(monkeypatch, tmp_path):
    finance_db.reset_engine_cache()
    db_path = tmp_path / "finance.db"
    monkeypatch.setattr(finance_db, "finance_db_path", lambda: db_path)

    engine = make_finance_test_engine(db_path)
    FinanceBase.metadata.create_all(engine)
    ensure_invest_schema(engine)
    session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    monkeypatch.setattr(investing_routes, "get_session_factory", lambda: session_factory)
    monkeypatch.setattr(investing_routes, "require_finance_user", lambda request: "testuser")

    app = FastAPI()
    router = APIRouter(prefix="/api/finance")
    mount_investing(router)
    app.include_router(router)
    with TestClient(app) as client:
        yield client, session_factory
    finance_db.reset_engine_cache()


@pytest.mark.area_routes
def test_investment_is_an_account_type():
    assert "investment" in ACCOUNT_TYPES


@pytest.mark.area_routes
def test_millishares_round_trip():
    assert millishares_from_input(shares="1.5") == 1500
    assert millishares_from_input(shares=1.5) == 1500
    assert millishares_from_input(shares_millishares=250) == 250
    assert shares_string(1500) == "1.5"
    assert shares_string(0) == "0"
    with pytest.raises(ValueError):
        millishares_from_input(shares="-1")


@pytest.mark.area_routes
def test_list_empty(invest_client):
    client, _ = invest_client
    res = client.get("/api/finance/invest/assets")
    assert res.status_code == 200
    assert res.json() == {"assets": []}
    summary = client.get("/api/finance/invest/summary")
    assert summary.status_code == 200
    body = summary.json()
    assert body["asset_count"] == 0
    assert body["total_current_value_cents"] == 0
    assert body["unrealized_gain_pct"] is None


@pytest.mark.area_routes
def test_create_vti_gain_and_summary(invest_client):
    client, _ = invest_client
    res = client.post(
        "/api/finance/invest/assets",
        json={
            "name": "VTI",
            "symbol": "VTI",
            "asset_kind": "etf",
            "shares": "1.5",
            "cost_basis_cents": 10000,
            "current_value_cents": 12000,
        },
    )
    assert res.status_code == 200, res.text
    asset = res.json()
    assert asset["shares_millishares"] == 1500
    assert asset["shares"] == "1.5"
    assert asset["unrealized_gain_cents"] == 2000
    assert asset["unrealized_gain_pct"] == 20.0

    listed = client.get("/api/finance/invest/assets").json()["assets"]
    assert len(listed) == 1
    summary = client.get("/api/finance/invest/summary").json()
    assert summary["total_current_value_cents"] == 12000
    assert summary["total_cost_basis_cents"] == 10000
    assert summary["unrealized_gain_cents"] == 2000
    assert summary["unrealized_gain_pct"] == 20.0
    assert summary["asset_count"] == 1
    assert summary["allocation"] == [
        {"asset_kind": "etf", "value_cents": 12000, "pct": 100.0}
    ]


@pytest.mark.area_routes
def test_value_update_appends_snapshots_same_day(invest_client):
    client, session_factory = invest_client
    created = client.post(
        "/api/finance/invest/assets",
        json={"name": "Cash", "asset_kind": "cash", "current_value_cents": 0},
    ).json()
    asset_id = created["id"]
    first = client.post(
        f"/api/finance/invest/assets/{asset_id}/value",
        json={"current_value_cents": 11000, "as_of": "2026-08-23"},
    )
    assert first.status_code == 200
    second = client.post(
        f"/api/finance/invest/assets/{asset_id}/value",
        json={"current_value_cents": 11500, "as_of": "2026-08-23"},
    )
    assert second.status_code == 200
    assert second.json()["current_value_cents"] == 11500

    hist = client.get(f"/api/finance/invest/assets/{asset_id}/valuations")
    assert hist.status_code == 200
    rows = hist.json()["valuations"]
    assert len(rows) == 2
    assert [row["value_cents"] for row in rows] == [11500, 11000]

    db = session_factory()
    try:
        assert db.query(FinanceTransaction).count() == 0
        assert db.query(FinanceInvestValuation).count() == 2
    finally:
        db.close()


@pytest.mark.area_routes
def test_owner_isolation_404(invest_client):
    client, session_factory = invest_client
    created = client.post(
        "/api/finance/invest/assets",
        json={"name": "Alice fund", "asset_kind": "fund", "current_value_cents": 1},
    ).json()
    asset_id = created["id"]

    db = session_factory()
    try:
        from integrations.finance.services.investing import create_asset_for_owner

        other = create_asset_for_owner(
            db, "bob", name="Bob stock", asset_kind="stock", current_value_cents=9
        )
        bob_id = other.id
    finally:
        db.close()

    listed = client.get("/api/finance/invest/assets").json()["assets"]
    ids = {row["id"] for row in listed}
    assert asset_id in ids
    assert bob_id not in ids
    assert client.get(f"/api/finance/invest/assets/{bob_id}").status_code == 404
    assert client.post(
        f"/api/finance/invest/assets/{bob_id}/value",
        json={"current_value_cents": 2},
    ).status_code == 404


@pytest.mark.area_routes
def test_archive_hides_from_default_list(invest_client):
    client, _ = invest_client
    created = client.post(
        "/api/finance/invest/assets",
        json={"name": "Old", "asset_kind": "other", "current_value_cents": 100},
    ).json()
    patched = client.patch(
        f"/api/finance/invest/assets/{created['id']}",
        json={"archived": True},
    )
    assert patched.status_code == 200
    assert client.get("/api/finance/invest/assets").json()["assets"] == []
    archived = client.get("/api/finance/invest/assets?include_archived=true").json()["assets"]
    assert len(archived) == 1
    assert client.get("/api/finance/invest/summary").json()["asset_count"] == 0


@pytest.mark.area_routes
def test_bad_kind_and_negative_cents(invest_client):
    client, _ = invest_client
    bad_kind = client.post(
        "/api/finance/invest/assets",
        json={"name": "X", "asset_kind": "p2p"},
    )
    assert bad_kind.status_code == 400
    negative = client.post(
        "/api/finance/invest/assets",
        json={"name": "X", "asset_kind": "stock", "cost_basis_cents": -1},
    )
    assert negative.status_code == 400


@pytest.mark.area_routes
def test_optional_account_must_be_owned(invest_client):
    client, session_factory = invest_client
    db = session_factory()
    try:
        alice_acct = create_account_for_owner(
            db, "testuser", name="Brokerage", account_type="investment"
        )
        bob_acct = create_account_for_owner(
            db, "bob", name="Bob broker", account_type="investment"
        )
        alice_id = alice_acct.id
        bob_id = bob_acct.id
    finally:
        db.close()

    ok = client.post(
        "/api/finance/invest/assets",
        json={"name": "Linked", "asset_kind": "stock", "account_id": alice_id},
    )
    assert ok.status_code == 200
    assert ok.json()["account_id"] == alice_id
    stolen = client.post(
        "/api/finance/invest/assets",
        json={"name": "Nope", "asset_kind": "stock", "account_id": bob_id},
    )
    assert stolen.status_code == 400


@pytest.mark.area_routes
def test_delete_cascades_valuations(invest_client):
    client, session_factory = invest_client
    created = client.post(
        "/api/finance/invest/assets",
        json={"name": "Temp", "current_value_cents": 50},
    ).json()
    client.post(
        f"/api/finance/invest/assets/{created['id']}/value",
        json={"current_value_cents": 60},
    )
    gone = client.delete(f"/api/finance/invest/assets/{created['id']}")
    assert gone.status_code == 200
    assert client.get(f"/api/finance/invest/assets/{created['id']}").status_code == 404
    db = session_factory()
    try:
        assert db.query(FinanceInvestValuation).count() == 0
        assert db.query(FinanceAccount).count() == 0
    finally:
        db.close()


@pytest.mark.area_routes
def test_investing_js_source_contract():
    src = _JS.read_text(encoding="utf-8")
    assert "window.renderFinanceInvesting" in src
    assert "No holdings yet. Add an asset and type its current value. Odysseus does not fetch quotes." in src
    assert "/invest/assets" in src
    assert "/invest/summary" in src
    assert "/value" in src
    assert "finance-money" in src
