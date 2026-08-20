"""Finance agent tool tests."""

import json
from pathlib import Path

import pytest
from sqlalchemy.orm import sessionmaker

import integrations.finance.database as finance_db
from tests.conftest import make_finance_test_engine
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
    engine = make_finance_test_engine(db_path)
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

    blocked = await do_manage_finance(
        json.dumps({
            "action": "categorize_transaction",
            "transaction_id": "6d7d3c81",
            "category_id": "5b3cda32",
        }),
        owner=owner,
        session_id="sess-cat",
    )
    assert blocked.get("exit_code") == 1

    token, _ = mint_confirmation(
        session_id="sess-cat",
        owner=owner,
        domain="finance",
        tool_name="manage_finance",
        action="categorize_transaction",
        payload={
            "transaction_id": "6d7d3c81-aaaa-bbbb-cccc-ddddeeeeffff",
            "category_id": "5b3cda32-abcd-ef01-2345-6789abcdef01",
        },
    )
    approve_pending_choice(
        token=token,
        session_id="sess-cat",
        owner=owner,
        choice="Yes",
    )

    by_prefix = await do_manage_finance(
        json.dumps({
            "action": "categorize_transaction",
            "transaction_id": "6d7d3c81",
            "category_id": "5b3cda32",
            "confirmation_token": token,
        }),
        owner=owner,
        session_id="sess-cat",
    )
    assert by_prefix.get("exit_code") == 0
    assert "Dining" in (by_prefix.get("response") or "")

    token2, _ = mint_confirmation(
        session_id="sess-cat2",
        owner=owner,
        domain="finance",
        tool_name="manage_finance",
        action="categorize_transaction",
        payload={
            "transaction_id": "6d7d3c81-aaaa-bbbb-cccc-ddddeeeeffff",
            "category_id": "5b3cda32-abcd-ef01-2345-6789abcdef01",
        },
    )
    approve_pending_choice(token=token2, session_id="sess-cat2", owner=owner, choice="Yes")

    by_name = await do_manage_finance(
        json.dumps({
            "action": "categorize_transaction",
            "transaction_id": "6d7d3c81",
            "category_id": "Dining",
            "confirmation_token": token2,
        }),
        owner=owner,
        session_id="sess-cat2",
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
async def test_manage_finance_batch_create_categories_with_one_token(finance_tool_env):
    owner = finance_tool_env["owner"]
    items = [
        {"name": "Family Transfers"},
        {"name": "Investigate"},
    ]

    token, _ = mint_confirmation(
        session_id="sess-batch",
        owner=owner,
        domain="finance",
        tool_name="manage_finance",
        action="create_category",
        payload={"items": items},
    )
    approve_pending_choice(
        token=token,
        session_id="sess-batch",
        owner=owner,
        choice="Yes, create them all!",
    )

    first = await do_manage_finance(
        json.dumps({
            "action": "create_category",
            "name": "Family Transfers",
            "confirmation_token": token,
        }),
        owner=owner,
        session_id="sess-batch",
    )
    assert first.get("exit_code") == 0

    second = await do_manage_finance(
        json.dumps({
            "action": "create_category",
            "name": "Investigate",
            "confirmation_token": token,
        }),
        owner=owner,
        session_id="sess-batch",
    )
    assert second.get("exit_code") == 0

    blocked = await do_manage_finance(
        json.dumps({
            "action": "create_category",
            "name": "Investigate",
            "confirmation_token": token,
        }),
        owner=owner,
        session_id="sess-batch",
    )
    assert blocked.get("exit_code") == 1


@pytest.mark.asyncio
@pytest.mark.area_routes
async def test_manage_finance_create_categories_batch_action(finance_tool_env):
    owner = finance_tool_env["owner"]
    categories = [
        {"name": "Business Income"},
        {"name": "Personal Income"},
    ]

    token, _ = mint_confirmation(
        session_id="sess-batch2",
        owner=owner,
        domain="finance",
        tool_name="manage_finance",
        action="create_category",
        payload={"items": categories},
    )
    approve_pending_choice(
        token=token,
        session_id="sess-batch2",
        owner=owner,
        choice="Yes",
    )

    created = await do_manage_finance(
        json.dumps({
            "action": "create_categories",
            "categories": categories,
            "confirmation_token": token,
        }),
        owner=owner,
        session_id="sess-batch2",
    )
    assert created.get("exit_code") == 0
    assert "Business Income" in (created.get("response") or "")
    assert "Personal Income" in (created.get("response") or "")


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


@pytest.mark.asyncio
@pytest.mark.area_routes
async def test_manage_finance_list_rules(finance_tool_env):
    owner = finance_tool_env["owner"]
    db = finance_tool_env["session_factory"]()
    try:
        cat = FinanceCategory(id="cat-1", owner=owner, name="Dining", is_income=False)
        db.add(cat)
        db.commit()
        from integrations.finance.models import FinanceCategorizationRule
        db.add(FinanceCategorizationRule(
            id="rule-1", owner=owner, pattern="PIZZA", category_id=cat.id, priority=10
        ))
        db.commit()
    finally:
        db.close()

    result = await do_manage_finance(json.dumps({"action": "list_rules"}), owner=owner)
    assert result.get("exit_code") == 0
    assert "PIZZA" in (result.get("response") or "")


@pytest.mark.asyncio
@pytest.mark.area_routes
async def test_manage_finance_net_worth(finance_tool_env):
    owner = finance_tool_env["owner"]
    db = finance_tool_env["session_factory"]()
    try:
        db.add(FinanceAccount(
            id="acct-check", owner=owner, name="Checking", account_type="checking",
            opening_balance_cents=50000,
        ))
        db.commit()
    finally:
        db.close()

    result = await do_manage_finance(json.dumps({"action": "net_worth"}), owner=owner)
    assert result.get("exit_code") == 0
    assert "Net worth" in (result.get("response") or "")


@pytest.mark.asyncio
@pytest.mark.area_routes
async def test_manage_finance_set_budget_requires_confirmation(finance_tool_env):
    owner = finance_tool_env["owner"]
    db = finance_tool_env["session_factory"]()
    try:
        cat = FinanceCategory(id="cat-bud", owner=owner, name="Groceries", is_income=False)
        db.add(cat)
        db.commit()
    finally:
        db.close()

    blocked = await do_manage_finance(
        json.dumps({"action": "set_budget", "category_id": "cat-bud", "limit_cents": 50000}),
        owner=owner,
        session_id="sess-bud",
    )
    assert blocked.get("exit_code") == 1

    token, _ = mint_confirmation(
        session_id="sess-bud",
        owner=owner,
        domain="finance",
        tool_name="manage_finance",
        action="set_budget",
        payload={"category_id": "cat-bud", "month": __import__("datetime").date.today().strftime("%Y-%m"), "limit_cents": 50000},
    )
    approve_pending_choice(token=token, session_id="sess-bud", owner=owner, choice="Yes")

    ok = await do_manage_finance(
        json.dumps({
            "action": "set_budget",
            "category_id": "cat-bud",
            "limit_cents": 50000,
            "confirmation_token": token,
        }),
        owner=owner,
        session_id="sess-bud",
    )
    assert ok.get("exit_code") == 0


@pytest.mark.asyncio
@pytest.mark.area_routes
@pytest.mark.area_security
async def test_manage_finance_auto_approve_skips_confirmation(finance_tool_env, monkeypatch):
    owner = finance_tool_env["owner"]
    db = finance_tool_env["session_factory"]()
    try:
        acct = FinanceAccount(
            id="acct-auto",
            owner=owner,
            name="Checking",
            account_type="checking",
        )
        cat = FinanceCategory(
            id="cat-auto-1111-2222-3333-444455556666",
            owner=owner,
            name="Food",
            is_income=False,
        )
        tx = FinanceTransaction(
            id="tx-auto-aaaa-bbbb-cccc-ddddeeeeffff",
            owner=owner,
            account_id=acct.id,
            date=__import__("datetime").date(2026, 6, 30),
            amount_cents=-900,
            payee="COFFEE SHOP",
            dedup_hash="coffee-auto",
        )
        db.add_all([acct, cat, tx])
        db.commit()
    finally:
        db.close()

    monkeypatch.setattr(
        "src.confirmation_gates.core.auto_approve_finance_enabled",
        lambda user: user == owner,
    )

    result = await do_manage_finance(
        json.dumps({
            "action": "categorize_transaction",
            "transaction_id": "tx-auto",
            "category_id": "cat-auto",
        }),
        owner=owner,
        session_id="sess-auto",
    )
    assert result.get("exit_code") == 0
    assert "Food" in (result.get("response") or "")


@pytest.mark.asyncio
@pytest.mark.area_routes
async def test_manage_finance_invalid_limit_returns_structured_error(finance_tool_env):
    owner = finance_tool_env["owner"]
    result = await do_manage_finance(
        json.dumps({"action": "list_transactions", "limit": "not-a-number"}),
        owner=owner,
    )
    assert result.get("exit_code") == 1
    assert "invalid argument value" in (result.get("error") or "").lower()


@pytest.mark.asyncio
@pytest.mark.area_routes
async def test_manage_finance_suggest_categories(finance_tool_env):
    owner = finance_tool_env["owner"]
    db = finance_tool_env["session_factory"]()
    try:
        acct = FinanceAccount(id="acct-s", owner=owner, name="Checking", account_type="checking")
        db.add(acct)
        for i in range(3):
            db.add(FinanceTransaction(
                id=f"tx-s-{i}",
                owner=owner,
                account_id=acct.id,
                date=__import__("datetime").date(2026, 5, i + 1),
                amount_cents=-1500,
                payee="NETFLIX.COM",
                dedup_hash=f"nf-{i}",
                bank_category="Entertainment",
            ))
        db.commit()
    finally:
        db.close()

    result = await do_manage_finance(json.dumps({"action": "suggest_categories"}), owner=owner)
    assert result.get("exit_code") == 0
    assert "NETFLIX" in (result.get("response") or "")
    assert "create_rule" in (result.get("response") or "")


@pytest.mark.asyncio
@pytest.mark.area_routes
async def test_manage_finance_create_rule_auto_applies_existing(finance_tool_env):
    owner = finance_tool_env["owner"]
    db = finance_tool_env["session_factory"]()
    try:
        acct = FinanceAccount(id="acct-rule", owner=owner, name="Checking", account_type="checking")
        cat = FinanceCategory(id="cat-rule", owner=owner, name="Streaming", is_income=False)
        tx = FinanceTransaction(
            id="tx-rule-1",
            owner=owner,
            account_id=acct.id,
            date=__import__("datetime").date(2026, 6, 1),
            amount_cents=-1599,
            payee="NETFLIX.COM",
            dedup_hash="nf-rule-1",
        )
        db.add_all([acct, cat, tx])
        db.commit()
    finally:
        db.close()

    token, _ = mint_confirmation(
        session_id="sess-rule",
        owner=owner,
        domain="finance",
        tool_name="manage_finance",
        action="create_rule",
        payload={"pattern": "NETFLIX", "category_id": "cat-rule", "priority": 100},
    )
    approve_pending_choice(token=token, session_id="sess-rule", owner=owner, choice="Yes")

    result = await do_manage_finance(
        json.dumps({
            "action": "create_rule",
            "pattern": "NETFLIX",
            "category_id": "cat-rule",
            "priority": 100,
            "confirmation_token": token,
        }),
        owner=owner,
        session_id="sess-rule",
    )
    assert result.get("exit_code") == 0
    assert "changed=1" in (result.get("response") or "")

    db = finance_tool_env["session_factory"]()
    try:
        refreshed = db.query(FinanceTransaction).filter_by(id="tx-rule-1").one()
        assert refreshed.category_id == "cat-rule"
    finally:
        db.close()


def _seed_tx(db, owner, *, acct_id, tx_id, payee, amount_cents=-1000, category_id=None, movement_class=None):
    db.add(FinanceTransaction(
        id=tx_id,
        owner=owner,
        account_id=acct_id,
        date=__import__("datetime").date(2026, 6, 1),
        amount_cents=amount_cents,
        payee=payee,
        dedup_hash=tx_id,
        category_id=category_id,
        movement_class=movement_class,
    ))


@pytest.mark.asyncio
@pytest.mark.area_routes
async def test_manage_finance_batch_classify_transaction_ids(finance_tool_env, monkeypatch):
    owner = finance_tool_env["owner"]
    db = finance_tool_env["session_factory"]()
    try:
        db.add(FinanceAccount(id="acct-bulk", owner=owner, name="Checking", account_type="checking"))
        for i in range(4):
            _seed_tx(db, owner, acct_id="acct-bulk", tx_id=f"tx-pass-{i:04d}-aaaa-bbbb-cccc-ddddeeeeffff", payee=f"VENMO {i}")
        _seed_tx(db, owner, acct_id="acct-bulk", tx_id="tx-keep-0001-aaaa-bbbb-cccc-ddddeeeeffff", payee="COSTCO")
        db.commit()
    finally:
        db.close()

    monkeypatch.setattr(
        "src.confirmation_gates.core.auto_approve_finance_enabled",
        lambda user: user == owner,
    )
    ids = [f"tx-pass-{i:04d}" for i in range(4)]
    result = await do_manage_finance(
        json.dumps({
            "action": "classify_transaction",
            "transaction_ids": ids,
            "movement_class": "pass_through",
        }),
        owner=owner,
        session_id="sess-bulk-class",
    )
    assert result.get("exit_code") == 0, result
    assert "4" in (result.get("response") or "")
    assert "pass_through" in (result.get("response") or "")

    db = finance_tool_env["session_factory"]()
    try:
        rows = db.query(FinanceTransaction).filter(FinanceTransaction.owner == owner).all()
        by_id = {tx.id: tx for tx in rows}
        for i in range(4):
            assert by_id[f"tx-pass-{i:04d}-aaaa-bbbb-cccc-ddddeeeeffff"].movement_class == "pass_through"
        assert by_id["tx-keep-0001-aaaa-bbbb-cccc-ddddeeeeffff"].movement_class is None
    finally:
        db.close()


@pytest.mark.asyncio
@pytest.mark.area_routes
async def test_manage_finance_batch_categorize_transaction_ids(finance_tool_env, monkeypatch):
    owner = finance_tool_env["owner"]
    db = finance_tool_env["session_factory"]()
    try:
        db.add(FinanceAccount(id="acct-cat", owner=owner, name="Checking", account_type="checking"))
        db.add(FinanceCategory(id="cat-groc-1111-2222-3333-444455556666", owner=owner, name="Groceries", is_income=False))
        for i in range(3):
            _seed_tx(db, owner, acct_id="acct-cat", tx_id=f"tx-groc-{i:04d}-aaaa-bbbb-cccc-ddddeeeeffff", payee=f"SAFEWAY {i}")
        db.commit()
    finally:
        db.close()

    monkeypatch.setattr(
        "src.confirmation_gates.core.auto_approve_finance_enabled",
        lambda user: user == owner,
    )
    result = await do_manage_finance(
        json.dumps({
            "action": "categorize_transaction",
            "transaction_ids": ["tx-groc-0000", "tx-groc-0001", "tx-groc-0002"],
            "category_id": "Groceries",
        }),
        owner=owner,
        session_id="sess-bulk-cat",
    )
    assert result.get("exit_code") == 0, result
    assert "Groceries" in (result.get("response") or "")

    db = finance_tool_env["session_factory"]()
    try:
        rows = db.query(FinanceTransaction).filter(FinanceTransaction.owner == owner).all()
        assert {tx.category_id for tx in rows} == {"cat-groc-1111-2222-3333-444455556666"}
    finally:
        db.close()


@pytest.mark.asyncio
@pytest.mark.area_routes
async def test_manage_finance_mixed_bulk_updates(finance_tool_env, monkeypatch):
    owner = finance_tool_env["owner"]
    db = finance_tool_env["session_factory"]()
    try:
        db.add(FinanceAccount(id="acct-mix", owner=owner, name="Checking", account_type="checking"))
        db.add(FinanceCategory(id="cat-dine-1111-2222-3333-444455556666", owner=owner, name="Dining", is_income=False))
        _seed_tx(db, owner, acct_id="acct-mix", tx_id="tx-mix-pass-aaaa-bbbb-cccc-ddddeeeeffff", payee="PAYPAL INST XFER")
        _seed_tx(db, owner, acct_id="acct-mix", tx_id="tx-mix-inc-aaaa-bbbb-cccc-ddddeeeeffff", payee="PAYROLL", amount_cents=50000)
        _seed_tx(db, owner, acct_id="acct-mix", tx_id="tx-mix-dine-aaaa-bbbb-cccc-ddddeeeeffff", payee="PIZZA")
        db.commit()
    finally:
        db.close()

    monkeypatch.setattr(
        "src.confirmation_gates.core.auto_approve_finance_enabled",
        lambda user: user == owner,
    )
    result = await do_manage_finance(
        json.dumps({
            "action": "bulk_update_transactions",
            "updates": [
                {"transaction_ids": ["tx-mix-pass"], "movement_class": "pass_through"},
                {"transaction_ids": ["tx-mix-inc"], "movement_class": "income"},
                {"transaction_ids": ["tx-mix-dine"], "category_id": "Dining", "movement_class": "spend"},
            ],
        }),
        owner=owner,
        session_id="sess-bulk-mix",
    )
    assert result.get("exit_code") == 0, result
    assert "pass_through" in (result.get("response") or "")
    assert "income" in (result.get("response") or "")
    assert "Dining" in (result.get("response") or "")

    db = finance_tool_env["session_factory"]()
    try:
        rows = {tx.id: tx for tx in db.query(FinanceTransaction).filter_by(owner=owner).all()}
        assert rows["tx-mix-pass-aaaa-bbbb-cccc-ddddeeeeffff"].movement_class == "pass_through"
        assert rows["tx-mix-inc-aaaa-bbbb-cccc-ddddeeeeffff"].movement_class == "income"
        dine = rows["tx-mix-dine-aaaa-bbbb-cccc-ddddeeeeffff"]
        assert dine.movement_class == "spend"
        assert dine.category_id == "cat-dine-1111-2222-3333-444455556666"
    finally:
        db.close()


@pytest.mark.asyncio
@pytest.mark.area_routes
async def test_manage_finance_classify_apply_to_payee(finance_tool_env, monkeypatch):
    owner = finance_tool_env["owner"]
    db = finance_tool_env["session_factory"]()
    try:
        db.add(FinanceAccount(id="acct-payee", owner=owner, name="Checking", account_type="checking"))
        _seed_tx(db, owner, acct_id="acct-payee", tx_id="tx-sbx-1-aaaa-bbbb-cccc-ddddeeeeffff", payee="STARBUCKS")
        _seed_tx(db, owner, acct_id="acct-payee", tx_id="tx-sbx-2-aaaa-bbbb-cccc-ddddeeeeffff", payee="STARBUCKS")
        _seed_tx(db, owner, acct_id="acct-payee", tx_id="tx-other-aaaa-bbbb-cccc-ddddeeeeffff", payee="COSTCO")
        db.commit()
    finally:
        db.close()

    monkeypatch.setattr(
        "src.confirmation_gates.core.auto_approve_finance_enabled",
        lambda user: user == owner,
    )
    result = await do_manage_finance(
        json.dumps({
            "action": "classify_transaction",
            "transaction_ids": ["tx-sbx-1"],
            "movement_class": "spend",
            "apply_to_payee": True,
        }),
        owner=owner,
        session_id="sess-payee",
    )
    assert result.get("exit_code") == 0, result
    db = finance_tool_env["session_factory"]()
    try:
        rows = {tx.id: tx for tx in db.query(FinanceTransaction).filter_by(owner=owner).all()}
        assert rows["tx-sbx-1-aaaa-bbbb-cccc-ddddeeeeffff"].movement_class == "spend"
        assert rows["tx-sbx-2-aaaa-bbbb-cccc-ddddeeeeffff"].movement_class == "spend"
        assert rows["tx-other-aaaa-bbbb-cccc-ddddeeeeffff"].movement_class is None
    finally:
        db.close()


@pytest.mark.asyncio
@pytest.mark.area_routes
async def test_manage_finance_bulk_classify_requires_confirmation(finance_tool_env):
    owner = finance_tool_env["owner"]
    db = finance_tool_env["session_factory"]()
    try:
        db.add(FinanceAccount(id="acct-gate", owner=owner, name="Checking", account_type="checking"))
        _seed_tx(db, owner, acct_id="acct-gate", tx_id="tx-gate-aaaa-bbbb-cccc-ddddeeeeffff", payee="VENMO")
        db.commit()
    finally:
        db.close()

    blocked = await do_manage_finance(
        json.dumps({
            "action": "classify_transaction",
            "transaction_ids": ["tx-gate"],
            "movement_class": "transfer",
        }),
        owner=owner,
        session_id="sess-gate",
    )
    assert blocked.get("exit_code") == 1
    assert "confirmation" in (blocked.get("error") or "").lower()


@pytest.mark.asyncio
@pytest.mark.area_routes
async def test_manage_finance_bulk_rejects_over_limit(finance_tool_env, monkeypatch):
    owner = finance_tool_env["owner"]
    monkeypatch.setattr(
        "src.confirmation_gates.core.auto_approve_finance_enabled",
        lambda user: user == owner,
    )
    result = await do_manage_finance(
        json.dumps({
            "action": "classify_transaction",
            "transaction_ids": [f"tx-{i:04d}" for i in range(501)],
            "movement_class": "spend",
        }),
        owner=owner,
        session_id="sess-limit",
    )
    assert result.get("exit_code") == 1
    assert "500" in (result.get("error") or "")


@pytest.mark.asyncio
@pytest.mark.area_routes
async def test_manage_finance_list_shows_class_and_unclassified_filter(finance_tool_env):
    owner = finance_tool_env["owner"]
    db = finance_tool_env["session_factory"]()
    try:
        db.add(FinanceAccount(id="acct-list", owner=owner, name="Checking", account_type="checking"))
        _seed_tx(
            db, owner, acct_id="acct-list", tx_id="tx-listed-aaaa-bbbb-cccc-ddddeeeeffff",
            payee="WHOLE FOODS", movement_class="spend",
        )
        _seed_tx(
            db, owner, acct_id="acct-list", tx_id="tx-nullcl-aaaa-bbbb-cccc-ddddeeeeffff",
            payee="MYSTERY",
        )
        db.commit()
    finally:
        db.close()

    listed = await do_manage_finance(
        json.dumps({"action": "list_transactions", "limit": 10}),
        owner=owner,
    )
    assert listed.get("exit_code") == 0
    assert "spend" in (listed.get("response") or "")
    assert "unclassified" in (listed.get("response") or "")

    only_null = await do_manage_finance(
        json.dumps({"action": "list_transactions", "unclassified": True, "limit": 10}),
        owner=owner,
    )
    assert only_null.get("exit_code") == 0
    assert "MYSTERY" in (only_null.get("response") or "")
    assert "WHOLE FOODS" not in (only_null.get("response") or "")


@pytest.mark.asyncio
@pytest.mark.area_routes
async def test_agent_search_matches_payee_or_memo_tokens(finance_tool_env):
    owner = finance_tool_env["owner"]
    db = finance_tool_env["session_factory"]()
    try:
        db.add(FinanceAccount(
            id="acct-search", owner=owner, name="Checking", account_type="checking",
        ))
        tx = FinanceTransaction(
            id="tx-voice-aaaa-bbbb-cccc-ddddeeeeffff",
            owner=owner,
            account_id="acct-search",
            date=__import__("datetime").date(2026, 6, 1),
            amount_cents=-1200,
            payee="GOOGLE SERVICES",
            memo="GOOGLE *VOICE one-time",
            dedup_hash="voice-memo",
        )
        db.add(tx)
        db.commit()
    finally:
        db.close()

    result = await do_manage_finance(
        json.dumps({
            "action": "list_transactions",
            "search": "GOOGLE VOICE",
        }),
        owner=owner,
    )
    assert result.get("exit_code") == 0
    assert "GOOGLE SERVICES" in (result.get("response") or "")


@pytest.mark.asyncio
@pytest.mark.area_routes
async def test_agent_listing_bounds_negative_limit_and_final_page(finance_tool_env):
    owner = finance_tool_env["owner"]
    db = finance_tool_env["session_factory"]()
    try:
        db.add(FinanceAccount(
            id="acct-page", owner=owner, name="Checking", account_type="checking",
        ))
        for i in range(30):
            _seed_tx(
                db,
                owner,
                acct_id="acct-page",
                tx_id=f"tx-page-{i:04d}-aaaa-bbbb-cccc-ddddeeeeffff",
                payee=f"MERCHANT {i}",
            )
        db.commit()
    finally:
        db.close()

    bounded = await do_manage_finance(
        json.dumps({"action": "list_transactions", "limit": -1}),
        owner=owner,
    )
    assert "showing 1 of 30" in (bounded.get("response") or "")

    final_page = await do_manage_finance(
        json.dumps({"action": "list_transactions", "limit": 25, "offset": 25}),
        owner=owner,
    )
    assert "showing 5 of 30" in (final_page.get("response") or "")
    assert "next page" not in (final_page.get("response") or "").lower()


@pytest.mark.asyncio
@pytest.mark.area_routes
async def test_apply_to_payee_never_exceeds_500_rows(finance_tool_env, monkeypatch):
    owner = finance_tool_env["owner"]
    db = finance_tool_env["session_factory"]()
    try:
        db.add(FinanceAccount(
            id="acct-cap", owner=owner, name="Checking", account_type="checking",
        ))
        for i in range(600):
            _seed_tx(
                db,
                owner,
                acct_id="acct-cap",
                tx_id=f"tx-cap-{i:04d}-aaaa-bbbb-cccc-ddddeeeeffff",
                payee="DICE & DRIP",
            )
        db.commit()
    finally:
        db.close()
    monkeypatch.setattr(
        "src.confirmation_gates.core.auto_approve_finance_enabled",
        lambda user: user == owner,
    )

    first = await do_manage_finance(
        json.dumps({
            "action": "classify_transaction",
            "transaction_ids": ["tx-cap-0000"],
            "movement_class": "spend",
            "apply_to_payee": True,
        }),
        owner=owner,
        session_id="sess-cap",
    )
    assert first.get("exit_code") == 0
    assert "updated=500" in (first.get("response") or "")
    assert "remaining=100" in (first.get("response") or "")

    db = finance_tool_env["session_factory"]()
    try:
        assert db.query(FinanceTransaction).filter_by(
            owner=owner, movement_class="spend"
        ).count() == 500
    finally:
        db.close()


@pytest.mark.asyncio
@pytest.mark.area_routes
async def test_classify_by_category_skips_p2p_sign_and_transfers(finance_tool_env, monkeypatch):
    owner = finance_tool_env["owner"]
    db = finance_tool_env["session_factory"]()
    try:
        db.add(FinanceAccount(
            id="acct-safe", owner=owner, name="Checking", account_type="checking",
        ))
        db.add_all([
            FinanceCategory(
                id="cat-subs", owner=owner, name="Subscriptions", is_income=False,
            ),
            FinanceCategory(
                id="cat-transfer", owner=owner, name="Transfers (label only)", is_income=False,
            ),
        ])
        _seed_tx(
            db, owner, acct_id="acct-safe", tx_id="tx-zelle-in",
            payee="ZELLE FROM MOM", amount_cents=2500, category_id="cat-subs",
        )
        _seed_tx(
            db, owner, acct_id="acct-safe", tx_id="tx-zelle-out",
            payee="ZELLE TO MOM", amount_cents=-2500, category_id="cat-subs",
        )
        _seed_tx(
            db, owner, acct_id="acct-safe", tx_id="tx-netflix",
            payee="NETFLIX", amount_cents=-1599, category_id="cat-subs",
        )
        _seed_tx(
            db, owner, acct_id="acct-safe", tx_id="tx-transfer-label",
            payee="BANK TRANSFER", amount_cents=-5000, category_id="cat-transfer",
        )
        db.commit()
    finally:
        db.close()
    monkeypatch.setattr(
        "src.confirmation_gates.core.auto_approve_finance_enabled",
        lambda user: user == owner,
    )

    result = await do_manage_finance(
        json.dumps({
            "action": "classify_by_category",
            "category_id": "cat-subs",
            "movement_class": "spend",
        }),
        owner=owner,
        session_id="sess-safe",
    )
    assert result.get("exit_code") == 0, result
    assert "updated=1" in (result.get("response") or "")

    transfers = await do_manage_finance(
        json.dumps({
            "action": "classify_by_category",
            "category_id": "cat-transfer",
        }),
        owner=owner,
        session_id="sess-safe",
    )
    assert transfers.get("exit_code") == 0
    assert "updated=0" in (transfers.get("response") or "")

    db = finance_tool_env["session_factory"]()
    try:
        rows = {
            tx.id: tx for tx in db.query(FinanceTransaction).filter_by(owner=owner).all()
        }
        assert rows["tx-netflix"].movement_class == "spend"
        assert rows["tx-zelle-in"].movement_class is None
        assert rows["tx-zelle-out"].movement_class is None
        assert rows["tx-transfer-label"].movement_class is None
    finally:
        db.close()


@pytest.mark.asyncio
@pytest.mark.area_routes
async def test_one_confirmation_reused_for_category_continuation(finance_tool_env):
    owner = finance_tool_env["owner"]
    db = finance_tool_env["session_factory"]()
    try:
        db.add(FinanceAccount(
            id="acct-loop", owner=owner, name="Checking", account_type="checking",
        ))
        db.add(FinanceCategory(
            id="cat-loop", owner=owner, name="Dining", is_income=False,
        ))
        for i in range(501):
            _seed_tx(
                db,
                owner,
                acct_id="acct-loop",
                tx_id=f"tx-loop-{i:04d}-aaaa-bbbb-cccc-ddddeeeeffff",
                payee=f"COFFEE {i % 3}",
                category_id="cat-loop",
            )
        db.commit()
    finally:
        db.close()

    token, error = mint_confirmation(
        session_id="sess-loop",
        owner=owner,
        domain="finance",
        tool_name="manage_finance",
        action="classify_by_category",
        payload={
            "category_id": "cat-loop",
            "movement_class": "spend",
            "overwrite": False,
            "max_updates": 500,
            "max_uses": 2,
        },
    )
    assert error is None
    approve_pending_choice(
        token=token,
        session_id="sess-loop",
        owner=owner,
        choice="Yes",
    )
    call = {
        "action": "classify_by_category",
        "category_id": "cat-loop",
        "confirmation_token": token,
    }
    first = await do_manage_finance(
        json.dumps(call), owner=owner, session_id="sess-loop",
    )
    second = await do_manage_finance(
        json.dumps(call), owner=owner, session_id="sess-loop",
    )
    assert "updated=500" in (first.get("response") or "")
    assert "remaining=1" in (first.get("response") or "")
    assert "updated=1" in (second.get("response") or "")
    assert "remaining=0" in (second.get("response") or "")


@pytest.mark.asyncio
@pytest.mark.area_routes
async def test_rule_apply_existing_is_fill_only_unless_overwrite(finance_tool_env):
    owner = finance_tool_env["owner"]
    db = finance_tool_env["session_factory"]()
    try:
        db.add(FinanceAccount(
            id="acct-rule-overwrite", owner=owner, name="Checking", account_type="checking",
        ))
        db.add_all([
            FinanceCategory(id="cat-old", owner=owner, name="Utilities", is_income=False),
            FinanceCategory(id="cat-new", owner=owner, name="Phone", is_income=False),
        ])
        _seed_tx(
            db,
            owner,
            acct_id="acct-rule-overwrite",
            tx_id="tx-rule-overwrite",
            payee="GOOGLE *VOICE",
            category_id="cat-old",
        )
        db.commit()
    finally:
        db.close()

    async def create(overwrite, session_id):
        payload = {
            "pattern": r"^GOOGLE \*VOICE$",
            "category_id": "cat-new",
            "priority": 10,
            "apply_existing": True,
            "overwrite": overwrite,
            "max_updates": 500,
        }
        token, _ = mint_confirmation(
            session_id=session_id,
            owner=owner,
            domain="finance",
            tool_name="manage_finance",
            action="create_rule",
            payload=payload,
        )
        approve_pending_choice(
            token=token, session_id=session_id, owner=owner, choice="Yes",
        )
        return await do_manage_finance(
            json.dumps({
                "action": "create_rule",
                **payload,
                "confirmation_token": token,
            }),
            owner=owner,
            session_id=session_id,
        )

    fill_only = await create(False, "sess-rule-fill")
    assert "changed=0" in (fill_only.get("response") or "")
    overwritten = await create(True, "sess-rule-overwrite")
    assert "changed=1" in (overwritten.get("response") or "")

    db = finance_tool_env["session_factory"]()
    try:
        tx = db.query(FinanceTransaction).filter_by(id="tx-rule-overwrite").one()
        assert tx.category_id == "cat-new"
    finally:
        db.close()


@pytest.mark.asyncio
@pytest.mark.area_routes
async def test_classification_status_reports_remaining_without_rows(finance_tool_env):
    owner = finance_tool_env["owner"]
    db = finance_tool_env["session_factory"]()
    try:
        db.add(FinanceAccount(
            id="acct-status", owner=owner, name="Checking", account_type="checking",
        ))
        _seed_tx(
            db, owner, acct_id="acct-status", tx_id="tx-status-null",
            payee="MYSTERY", amount_cents=-500,
        )
        _seed_tx(
            db, owner, acct_id="acct-status", tx_id="tx-status-spend",
            payee="DINER", amount_cents=-800, movement_class="spend",
        )
        db.commit()
    finally:
        db.close()

    result = await do_manage_finance(
        json.dumps({"action": "classification_status"}),
        owner=owner,
    )
    response = result.get("response") or ""
    assert "total=2" in response
    assert "'unclassified': 1" in response
    assert "tx-status" not in response


FINANCE_READ_ACTIONS = {
    "list_accounts",
    "list_transactions",
    "spending_report",
    "budget_status",
    "trends",
    "net_worth",
    "list_categories",
    "list_rules",
    "suggest_categories",
    "list_recurring",
    "list_import_batches",
    "list_planned",
    "job_scenario",
    "test_rule",
    "classification_status",
}

FINANCE_PAPER_WRITES = {
    "create_planned",
    "delete_planned",
    "set_job_take_home",
}


def _manage_finance_enum():
    """Read the live schema enum without importing tool_schemas (circular with agent_tools)."""
    import re

    text = (Path(__file__).resolve().parents[1] / "src" / "tool_schemas.py").read_text(encoding="utf-8")
    block = re.search(
        r'"name": "manage_finance".*?"enum": \[(.*?)\]',
        text,
        flags=re.S,
    )
    if not block:
        raise AssertionError("manage_finance schema not found")
    return set(re.findall(r'"([a-z_]+)"', block.group(1)))


@pytest.mark.area_security
def test_every_manage_finance_write_action_is_gated():
    from integrations.finance.confirmation_gate import register_finance_confirmation_gate
    from src.confirmation_gates import get_tool_gate

    register_finance_confirmation_gate()
    gate = get_tool_gate("finance", "manage_finance")
    assert gate is not None
    writes = _manage_finance_enum() - FINANCE_READ_ACTIONS - FINANCE_PAPER_WRITES
    missing = sorted(writes - set(gate.actions))
    assert missing == []


@pytest.mark.asyncio
@pytest.mark.area_security
async def test_auto_approve_does_not_bypass_hard_gated_delete(finance_tool_env, monkeypatch):
    owner = finance_tool_env["owner"]
    monkeypatch.setattr(
        "src.confirmation_gates.core.auto_approve_finance_enabled",
        lambda user: user == owner,
    )
    result = await do_manage_finance(
        json.dumps({"action": "delete_transaction", "transaction_id": "tx-missing"}),
        owner=owner,
        session_id="sess-hard",
    )
    assert result.get("exit_code") == 1
    assert "confirmation" in (result.get("error") or "").lower()


@pytest.mark.area_security
def test_update_transaction_confirmation_requires_amount_and_date():
    from integrations.finance.confirmation_gate import _validate_update_transaction

    err = _validate_update_transaction({"transaction_id": "tx-1"}, {"transaction_id": "tx-1"})
    assert err
    assert "amount_cents" in err or "date" in err
