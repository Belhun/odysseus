"""Posted vs available balance tests."""

from datetime import date

import pytest
import integrations.finance.database as finance_db
from integrations.finance.install import run_install
from integrations.finance.models import FinanceAccount, FinanceTransaction
from integrations.finance.services.balances import (
    account_balance_snapshot,
    is_posted_row,
    posted_cents,
)
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
    monkeypatch.setattr("src.settings.FEATURES_FILE", str(tmp_path / "features.json"))
    finance_db.reset_engine_cache()
    run_install()
    yield {"owner": "alice", "session_factory": finance_db.get_session_factory()}
    run_uninstall(remove_data=True)
    finance_db.reset_engine_cache()


def _acct(db, owner, **kwargs):
    acct = FinanceAccount(
        id=kwargs.get("id", "acct-1"),
        owner=owner,
        name=kwargs.get("name", "Checking"),
        account_type="checking",
        opening_balance_cents=kwargs.get("opening_balance_cents", 10000),
        opening_balance_date=kwargs.get("opening_balance_date"),
        posted_pin_cents=kwargs.get("posted_pin_cents"),
        available_cents=kwargs.get("available_cents"),
    )
    db.add(acct)
    db.commit()
    return acct


def _tx(db, owner, acct_id, tx_id, amount, status="cleared", day=1, month=7):
    db.add(
        FinanceTransaction(
            id=tx_id,
            owner=owner,
            account_id=acct_id,
            date=date(2026, month, day),
            amount_cents=amount,
            payee=tx_id,
            dedup_hash=tx_id,
            status=status,
            source="manual",
        )
    )
    db.commit()


@pytest.mark.area_routes
def test_is_posted_row_unknown_status_counts():
    tx = FinanceTransaction(status="mystery")
    assert is_posted_row(tx) is True
    tx.status = None
    assert is_posted_row(tx) is True
    tx.status = "void"
    assert is_posted_row(tx) is False
    tx.status = "pending"
    assert is_posted_row(tx) is False
    tx.status = "cleared"
    assert is_posted_row(tx) is True
    tx.status = "reconciled"
    assert is_posted_row(tx) is True


@pytest.mark.area_routes
def test_posted_excludes_void_and_pending(finance_db_env):
    owner = finance_db_env["owner"]
    db = finance_db_env["session_factory"]()
    try:
        acct = _acct(db, owner, opening_balance_cents=10000)
        _tx(db, owner, acct.id, "tx-cleared", -4000, "cleared")
        _tx(db, owner, acct.id, "tx-void", -1000, "void")
        _tx(db, owner, acct.id, "tx-pending", -500, "pending")
        _tx(db, owner, acct.id, "tx-weird", -200, "banana")
        assert posted_cents(db, acct) == 5800
        snap = account_balance_snapshot(db, acct)
        assert snap["posted_cents"] == 5800
        assert snap["balance_cents"] == 5800
        assert snap["opening_balance_cents"] == 10000
    finally:
        db.close()


@pytest.mark.area_routes
def test_pins_are_snapshots_not_derived(finance_db_env):
    owner = finance_db_env["owner"]
    db = finance_db_env["session_factory"]()
    try:
        acct = _acct(
            db,
            owner,
            opening_balance_cents=0,
            posted_pin_cents=99999,
            available_cents=1234,
        )
        _tx(db, owner, acct.id, "tx-1", -4000, "cleared")
        snap = account_balance_snapshot(db, acct)
        assert snap["posted_cents"] == -4000
        assert snap["posted_pin_cents"] == 99999
        assert snap["available_cents"] == 1234
    finally:
        db.close()


@pytest.mark.area_routes
def test_posted_ignores_rows_before_opening_balance_date(finance_db_env):
    owner = finance_db_env["owner"]
    db = finance_db_env["session_factory"]()
    try:
        acct = _acct(
            db,
            owner,
            opening_balance_cents=100000,
            opening_balance_date=date(2026, 7, 1),
        )
        _tx(db, owner, acct.id, "tx-before", -4000, day=15, month=6)
        _tx(db, owner, acct.id, "tx-after", -2000, day=2, month=7)
        assert posted_cents(db, acct) == 98000
    finally:
        db.close()


@pytest.mark.area_routes
def test_mixed_case_void_is_unposted(finance_db_env):
    owner = finance_db_env["owner"]
    db = finance_db_env["session_factory"]()
    try:
        acct = _acct(db, owner, opening_balance_cents=10000)
        _tx(db, owner, acct.id, "tx-void-case", -4000, "Void")
        _tx(db, owner, acct.id, "tx-void-pad", -1000, " void ")
        assert posted_cents(db, acct) == 10000
        from integrations.finance.services.balances import is_posted_row

        row = db.query(FinanceTransaction).filter(FinanceTransaction.id == "tx-void-case").one()
        assert is_posted_row(row) is False
    finally:
        db.close()
