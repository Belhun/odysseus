"""Finance agent tool tests."""

import json
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import NullPool

import integrations.finance.database as finance_db
from integrations.finance.models import FinanceAccount, FinanceBase, FinanceCategory, FinanceTransaction
from integrations.finance.install import run_install
from integrations.finance.uninstall import run_uninstall
from src.tools.finance import do_manage_finance
from tests.fixtures.finance.synthetic_samples import WELLS_FARGO_SAMPLE


@pytest.fixture()
def finance_tool_env(monkeypatch, tmp_path):
    plugins_root = tmp_path / "plugins"
    monkeypatch.setattr("src.plugins.registry.PLUGINS_DATA_ROOT", plugins_root)
    monkeypatch.setattr("src.plugins.registry.plugin_data_dir", lambda pid: plugins_root / pid)
    monkeypatch.setattr(
        "integrations.finance.database.finance_db_path",
        lambda: plugins_root / "finance" / "finance.db",
    )
    monkeypatch.setattr("src.settings.FEATURES_FILE", str(tmp_path / "features.json"))
    finance_db.reset_engine_cache()
    run_install()

    db_path = plugins_root / "finance" / "finance.db"
    engine = create_engine(
        f"sqlite:///{db_path}",
        connect_args={"check_same_thread": False},
        poolclass=NullPool,
    )
    session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    monkeypatch.setattr("integrations.finance.database.get_session_factory", lambda: session_factory)

    yield {"owner": "alice", "session_factory": session_factory}

    run_uninstall(remove_data=True)
    finance_db.reset_engine_cache()


@pytest.mark.asyncio
@pytest.mark.area_routes
@pytest.mark.area_security
async def test_manage_finance_blocked_when_plugin_inactive(monkeypatch):
    monkeypatch.setattr("src.plugins.registry.is_plugin_active", lambda _pid: False)
    result = await do_manage_finance(json.dumps({"action": "list_accounts"}), owner="alice")
    assert result.get("exit_code") == 1
    assert "not installed" in (result.get("error") or "").lower()


@pytest.mark.asyncio
@pytest.mark.area_routes
async def test_manage_finance_list_accounts_and_spending(finance_tool_env):
    owner = finance_tool_env["owner"]
    db = finance_tool_env["session_factory"]()
    try:
        acct = FinanceAccount(
            id="acct-1",
            owner=owner,
            name="Checking",
            account_type="checking",
            opening_balance_cents=0,
        )
        cat = FinanceCategory(
            id="cat-grocery",
            owner=owner,
            name="Groceries",
            is_income=False,
        )
        db.add_all([acct, cat])
        db.add(FinanceTransaction(
            id="tx-1",
            owner=owner,
            account_id=acct.id,
            date=__import__("datetime").date(2026, 6, 1),
            amount_cents=-2500,
            payee="WHOLE FOODS",
            dedup_hash="abc",
            category_id=cat.id,
        ))
        db.commit()
    finally:
        db.close()

    accounts = await do_manage_finance(json.dumps({"action": "list_accounts"}), owner=owner)
    assert accounts.get("exit_code") == 0
    assert "Checking" in accounts.get("response", "")

    spending = await do_manage_finance(
        json.dumps({"action": "spending_report", "month": "2026-06"}),
        owner=owner,
    )
    assert spending.get("exit_code") == 0
    assert "Groceries" in spending.get("response", "")

    txs = await do_manage_finance(
        json.dumps({"action": "list_transactions", "search": "WHOLE"}),
        owner=owner,
    )
    assert txs.get("exit_code") == 0
    assert "WHOLE FOODS" in txs.get("response", "")


@pytest.mark.asyncio
@pytest.mark.area_routes
async def test_manage_finance_owner_scoped(finance_tool_env):
    owner = finance_tool_env["owner"]
    db = finance_tool_env["session_factory"]()
    try:
        db.add(FinanceAccount(
            id="acct-bob",
            owner="bob",
            name="Secret",
            account_type="checking",
        ))
        db.commit()
    finally:
        db.close()

    result = await do_manage_finance(json.dumps({"action": "list_accounts"}), owner=owner)
    assert "Secret" not in (result.get("response") or "")


@pytest.mark.asyncio
@pytest.mark.area_routes
async def test_categorize_transaction_with_prefix_ids(finance_tool_env):
    owner = finance_tool_env["owner"]
    db = finance_tool_env["session_factory"]()
    try:
        acct = FinanceAccount(
            id="dd8bb9fa-1111-2222-3333-444455556666",
            owner=owner,
            name="Wells",
            account_type="checking",
        )
        income = FinanceCategory(
            id="f3d20a4e-aaaa-bbbb-cccc-ddddeeeeffff",
            owner=owner,
            name="Income",
            is_income=True,
        )
        db.add_all([acct, income])
        db.add(FinanceTransaction(
            id="c522e957-bbbb-cccc-dddd-eeeeffff0000",
            owner=owner,
            account_id=acct.id,
            date=__import__("datetime").date(2026, 6, 26),
            amount_cents=6000,
            payee="ATM CASH DEPOSIT ON 06/26",
            dedup_hash="dep1",
        ))
        db.commit()
    finally:
        db.close()

    result = await do_manage_finance(json.dumps({
        "action": "categorize_transaction",
        "transaction_id": "c522e957",
        "category_name": "Income",
    }), owner=owner)
    assert result.get("exit_code") == 0, result
    assert "Income" in result.get("response", "")

    db = finance_tool_env["session_factory"]()
    try:
        tx = db.query(FinanceTransaction).filter(FinanceTransaction.id.startswith("c522e957")).one()
        assert tx.category_id == "f3d20a4e-aaaa-bbbb-cccc-ddddeeeeffff"
    finally:
        db.close()


@pytest.mark.asyncio
@pytest.mark.area_routes
async def test_create_rule_applies_to_existing_transactions(finance_tool_env):
    owner = finance_tool_env["owner"]
    db = finance_tool_env["session_factory"]()
    try:
        acct = FinanceAccount(id="acct-1", owner=owner, name="Checking", account_type="checking")
        income = FinanceCategory(id="inc-1", owner=owner, name="Income", is_income=True)
        db.add_all([acct, income])
        db.add(FinanceTransaction(
            id="tx-atm",
            owner=owner,
            account_id=acct.id,
            date=__import__("datetime").date(2026, 6, 26),
            amount_cents=6000,
            payee="ATM CASH DEPOSIT",
            dedup_hash="atm1",
        ))
        db.commit()
    finally:
        db.close()

    result = await do_manage_finance(json.dumps({
        "action": "create_rule",
        "pattern": "ATM CASH DEPOSIT",
        "category_name": "Income",
    }), owner=owner)
    assert result.get("exit_code") == 0
    assert "Categorized 1" in result.get("response", "")

    db = finance_tool_env["session_factory"]()
    try:
        tx = db.query(FinanceTransaction).filter(FinanceTransaction.id == "tx-atm").one()
        assert tx.category_id == "inc-1"
    finally:
        db.close()


@pytest.mark.asyncio
@pytest.mark.area_routes
async def test_app_api_blocks_finance_paths():
    from src.tools.system import do_app_api

    result = await do_app_api(
        json.dumps({"action": "call", "method": "GET", "path": "/api/finance/accounts"}),
        owner="alice",
    )
    assert result.get("exit_code") == 1
    assert "manage_finance" in (result.get("error") or "")
