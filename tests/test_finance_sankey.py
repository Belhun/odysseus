"""Sankey / cashflow map — true spend, leftover, unclassified annotation."""

import uuid
from datetime import date

import pytest
from fastapi import APIRouter, FastAPI
from fastapi.testclient import TestClient

import integrations.finance.database as finance_db
from integrations.finance.install import run_install
from integrations.finance.models import FinanceAccount, FinanceCategory, FinanceTransaction
from integrations.finance.routes_sankey import mount_sankey
from integrations.finance.services.categories import ensure_default_categories
from integrations.finance.services.sankey import month_sankey
from integrations.finance.uninstall import run_uninstall


@pytest.fixture()
def finance_db_env(monkeypatch, tmp_path):
    plugins_root = tmp_path / "plugins"
    monkeypatch.setattr("src.plugins.registry.PLUGINS_DATA_ROOT", plugins_root)
    monkeypatch.setattr("src.plugins.registry.plugin_data_dir", lambda pid: plugins_root / pid)
    monkeypatch.setattr(
        "integrations.finance.database.finance_db_path",
        lambda: plugins_root / "finance" / "finance.db",
    )
    monkeypatch.setattr(
        "integrations.finance.database.finance_config_path",
        lambda: plugins_root / "finance" / "config.json",
    )
    monkeypatch.setattr("src.settings.FEATURES_FILE", str(tmp_path / "features.json"))
    finance_db.reset_engine_cache()
    run_install()
    yield {"owner": "alice", "session_factory": finance_db.get_session_factory()}
    run_uninstall(remove_data=True)
    finance_db.reset_engine_cache()


def _acct(db, owner, name, purpose="operating", rail=None):
    acct = FinanceAccount(
        id=str(uuid.uuid4()),
        owner=owner,
        name=name,
        account_type="checking",
        purpose=purpose,
        rail=rail,
    )
    db.add(acct)
    db.commit()
    return acct


def _cat(db, owner, name):
    ensure_default_categories(db, owner)
    return (
        db.query(FinanceCategory)
        .filter(FinanceCategory.owner == owner, FinanceCategory.name == name)
        .first()
    )


def _tx(db, owner, account_id, amount, payee, cls=None, category_id=None, status="cleared", day=15):
    tx = FinanceTransaction(
        id=str(uuid.uuid4()),
        owner=owner,
        account_id=account_id,
        date=date(2026, 6, day),
        amount_cents=amount,
        payee=payee,
        dedup_hash=str(uuid.uuid4()),
        status=status,
        source="import",
        movement_class=cls,
        category_id=category_id,
    )
    db.add(tx)
    db.commit()
    return tx


def _by_id(payload):
    return {n["id"]: n for n in payload["nodes"]}


@pytest.mark.area_routes
def test_income_grocery_leftover(finance_db_env):
    owner = finance_db_env["owner"]
    db = finance_db_env["session_factory"]()
    try:
        wells = _acct(db, owner, "Wells")
        groceries = _cat(db, owner, "Groceries")
        _tx(db, owner, wells.id, 100000, "PAYROLL", cls="income")
        _tx(db, owner, wells.id, -4000, "MARKET", cls="spend", category_id=groceries.id)
        payload = month_sankey(db, owner, "2026-06")
        assert payload["income_cents"] == 100000
        assert payload["incomplete"] is False
        nodes = _by_id(payload)
        assert nodes["income"]["cents"] == 100000
        groc = next(n for n in payload["nodes"] if n.get("category_id") == groceries.id)
        assert groc["cents"] == 4000
        assert groc["kind"] == "category"
        assert nodes["leftover"]["cents"] == 96000
        assert {"source": "income", "target": groc["id"], "cents": 4000} in payload["links"]
        assert {"source": "income", "target": "leftover", "cents": 96000} in payload["links"]
        assert sum(l["cents"] for l in payload["links"] if l["source"] == "income") == 100000
    finally:
        db.close()


@pytest.mark.area_routes
def test_transfer_is_not_a_category_link(finance_db_env):
    owner = finance_db_env["owner"]
    db = finance_db_env["session_factory"]()
    try:
        wells = _acct(db, owner, "Wells")
        groceries = _cat(db, owner, "Groceries")
        _tx(db, owner, wells.id, 100000, "PAYROLL", cls="income")
        _tx(db, owner, wells.id, -20000, "TO TRIP", cls="transfer")
        _tx(db, owner, wells.id, -4000, "MARKET", cls="spend", category_id=groceries.id)
        payload = month_sankey(db, owner, "2026-06")
        labels = [n["label"] for n in payload["nodes"]]
        assert "Groceries" in labels
        assert payload["unclassified_count"] == 0
        leftover = next(n for n in payload["nodes"] if n["kind"] == "leftover")
        assert leftover["cents"] == 96000
        assert all("trip" not in (n["label"] or "").lower() for n in payload["nodes"])
        assert sum(l["cents"] for l in payload["links"] if l["source"] == "income") == 100000
    finally:
        db.close()


@pytest.mark.area_routes
def test_unclassified_is_annotation_not_second_link(finance_db_env):
    owner = finance_db_env["owner"]
    db = finance_db_env["session_factory"]()
    try:
        wells = _acct(db, owner, "Wells")
        groceries = _cat(db, owner, "Groceries")
        _tx(db, owner, wells.id, 100000, "PAYROLL", cls="income")
        _tx(db, owner, wells.id, -4000, "MARKET", category_id=groceries.id)
        payload = month_sankey(db, owner, "2026-06")
        assert payload["incomplete"] is True
        assert payload["unclassified_count"] == 1
        assert payload["unclassified_outflow_cents"] == 4000
        nodes = _by_id(payload)
        assert nodes["unclassified"]["kind"] == "unclassified"
        assert nodes["unclassified"]["cents"] == 4000
        groc = next(n for n in payload["nodes"] if n.get("category_id") == groceries.id)
        assert groc["cents"] == 4000
        unclassified_links = [l for l in payload["links"] if l["target"] == "unclassified"]
        assert unclassified_links == []
        assert sum(l["cents"] for l in payload["links"] if l["source"] == "income") == 100000
    finally:
        db.close()


@pytest.mark.area_routes
def test_void_spend_omitted(finance_db_env):
    owner = finance_db_env["owner"]
    db = finance_db_env["session_factory"]()
    try:
        wells = _acct(db, owner, "Wells")
        groceries = _cat(db, owner, "Groceries")
        _tx(db, owner, wells.id, 50000, "PAYROLL", cls="income")
        _tx(db, owner, wells.id, -4000, "VOID MARKET", cls="spend", category_id=groceries.id, status="void")
        payload = month_sankey(db, owner, "2026-06")
        assert not any(n.get("category_id") == groceries.id for n in payload["nodes"])
        leftover = next(n for n in payload["nodes"] if n["kind"] == "leftover")
        assert leftover["cents"] == 50000
    finally:
        db.close()


@pytest.mark.area_routes
def test_reimbursement_in_is_not_income(finance_db_env):
    owner = finance_db_env["owner"]
    db = finance_db_env["session_factory"]()
    try:
        wells = _acct(db, owner, "Wells")
        groceries = _cat(db, owner, "Groceries")
        _tx(db, owner, wells.id, 80000, "PAYROLL", cls="income")
        _tx(db, owner, wells.id, -8000, "MARKET", cls="spend", category_id=groceries.id)
        _tx(db, owner, wells.id, 3000, "VENMO MOM", cls="reimbursement", category_id=groceries.id)
        payload = month_sankey(db, owner, "2026-06")
        assert payload["income_cents"] == 80000
        groc = next(n for n in payload["nodes"] if n.get("category_id") == groceries.id)
        assert groc["cents"] == 5000
        leftover = next(n for n in payload["nodes"] if n["kind"] == "leftover")
        assert leftover["cents"] == 75000
    finally:
        db.close()


@pytest.mark.area_routes
def test_invalid_month_raises(finance_db_env):
    owner = finance_db_env["owner"]
    db = finance_db_env["session_factory"]()
    try:
        with pytest.raises(ValueError):
            month_sankey(db, owner, "nope")
    finally:
        db.close()


@pytest.mark.area_routes
def test_empty_month(finance_db_env):
    owner = finance_db_env["owner"]
    db = finance_db_env["session_factory"]()
    try:
        payload = month_sankey(db, owner, "2026-06")
        assert payload["income_cents"] == 0
        assert payload["links"] == []
        assert payload["incomplete"] is False
        assert payload["nodes"][0]["id"] == "income"
    finally:
        db.close()


@pytest.mark.area_routes
def test_mount_sankey_http_400(finance_db_env, monkeypatch):
    monkeypatch.setattr(
        "integrations.finance.routes.require_finance_user",
        lambda request: finance_db_env["owner"],
    )
    monkeypatch.setattr(
        "integrations.finance.routes_sankey.get_session_factory",
        lambda: finance_db_env["session_factory"],
    )
    app = FastAPI()
    router = APIRouter()
    mount_sankey(router)
    app.include_router(router, prefix="/api/finance")
    client = TestClient(app)
    res = client.get("/api/finance/reports/sankey?month=nope")
    assert res.status_code == 400
