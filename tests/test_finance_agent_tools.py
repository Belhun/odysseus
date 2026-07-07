"""Finance agent tool tests."""

import json
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import NullPool

import integrations.finance.database as finance_db
from integrations.finance.confirmation_gate import register_finance_confirmation_gate
from integrations.finance.install import run_install
from integrations.finance.models import FinanceAccount, FinanceBase, FinanceCategory, FinanceTransaction
from integrations.finance.uninstall import run_uninstall
from src.confirmation_gates import approve_pending_choice, mint_confirmation
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
    monkeypatch.setattr(
        "src.confirmation_gates.store.CONFIRMATION_PENDING_FILE",
        str(tmp_path / "confirmation_pending.json"),
    )
    from src.confirmation_gates.store import reset_store_for_tests

    reset_store_for_tests()
    register_finance_confirmation_gate()
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
async def test_manage_finance_categorize_by_prefix_and_name(finance_tool_env):
    owner = finance_tool_env["owner"]
    db = finance_tool_env["session_factory"]()
    try:
        acct = FinanceAccount(
            id="dd8bb9fa-1234-5678-9abc-def012345678",
            owner=owner,
            name="Wells Fargo",
            account_type="checking",
        )
        cat = FinanceCategory(
            id="5b3cda32-abcd-ef01-2345-6789abcdef01",
            owner=owner,
            name="Dining",
            is_income=False,
        )
        tx = FinanceTransaction(
            id="6d7d3c81-aaaa-bbbb-cccc-ddddeeeeffff",
            owner=owner,
            account_id=acct.id,
            date=__import__("datetime").date(2026, 6, 30),
            amount_cents=-1630,
            payee="BEST PIZZA",
            dedup_hash="pizza1",
        )
        db.add_all([acct, cat, tx])
        db.commit()
    finally:
        db.close()

    by_prefix = await do_manage_finance(
        json.dumps({
            "action": "categorize_transaction",
            "transaction_id": "6d7d3c81",
            "category_id": "5b3cda32",
        }),
        owner=owner,
    )
    assert by_prefix.get("exit_code") == 0
    assert "Dining" in (by_prefix.get("response") or "")

    by_name = await do_manage_finance(
        json.dumps({
            "action": "categorize_transaction",
            "transaction_id": "6d7d3c81",
            "category_id": "Dining",
        }),
        owner=owner,
    )
    assert by_name.get("exit_code") == 0

    filtered = await do_manage_finance(
        json.dumps({
            "action": "list_transactions",
            "account_id": "dd8bb9fa",
            "limit": 5,
        }),
        owner=owner,
    )
    assert filtered.get("exit_code") == 0
    assert "BEST PIZZA" in (filtered.get("response") or "")
    assert "No matching transactions" not in (filtered.get("response") or "")


@pytest.mark.asyncio
@pytest.mark.area_routes
async def test_manage_finance_create_category_requires_confirmation(finance_tool_env):
    owner = finance_tool_env["owner"]

    blocked = await do_manage_finance(
        json.dumps({"action": "create_category", "name": "Pet Supplies"}),
        owner=owner,
        session_id="sess-finance",
    )
    assert blocked.get("exit_code") == 1
    assert "confirmation" in (blocked.get("error") or "").lower()

    token, _ = mint_confirmation(
        session_id="sess-finance",
        owner=owner,
        domain="finance",
        tool_name="manage_finance",
        action="create_category",
        payload={"name": "Pet Supplies"},
    )
    approve_pending_choice(
        token=token,
        session_id="sess-finance",
        owner=owner,
        choice="Yes, create it",
    )

    created = await do_manage_finance(
        json.dumps({
            "action": "create_category",
            "name": "Pet Supplies",
            "confirmation_token": token,
        }),
        owner=owner,
        session_id="sess-finance",
    )
    assert created.get("exit_code") == 0
    assert "Pet Supplies" in (created.get("response") or "")

    dup = await do_manage_finance(
        json.dumps({
            "action": "create_category",
            "name": "Pet Supplies",
            "confirmation_token": token,
        }),
        owner=owner,
        session_id="sess-finance",
    )
    assert dup.get("exit_code") == 1


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
async def test_app_api_blocks_finance_paths():
    from src.tools.system import do_app_api

    result = await do_app_api(
        json.dumps({"action": "call", "method": "GET", "path": "/api/finance/accounts"}),
        owner="alice",
    )
    assert result.get("exit_code") == 1
    assert "manage_finance" in (result.get("error") or "")
