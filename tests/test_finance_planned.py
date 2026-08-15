"""Planned obligations and job overlay tests."""

import uuid
from datetime import date

import pytest
import integrations.finance.database as finance_db
from integrations.finance.install import run_install
from integrations.finance.models import FinanceAccount, FinanceCategory, FinanceJobScenario, FinanceTransaction
from integrations.finance.services.categories import ensure_default_categories
from integrations.finance.services.planned import (
    create_planned_for_owner,
    job_overlay,
    upsert_job_scenario,
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


def _acct(db, owner, name, purpose="operating"):
    acct = FinanceAccount(
        id=str(uuid.uuid4()),
        owner=owner,
        name=name,
        account_type="checking",
        purpose=purpose,
    )
    db.add(acct)
    db.commit()
    return acct


def _tx(db, owner, account_id, amount, payee, cls="spend", category_id=None, day=1, month=7):
    tx = FinanceTransaction(
        id=str(uuid.uuid4()),
        owner=owner,
        account_id=account_id,
        date=date(2026, month, day),
        amount_cents=amount,
        payee=payee,
        dedup_hash=str(uuid.uuid4()),
        status="cleared",
        source="import",
        movement_class=cls,
        category_id=category_id,
    )
    db.add(tx)
    db.commit()
    return tx


@pytest.mark.area_routes
def test_planned_rent_does_not_change_tx_count_or_trends(finance_db_env):
    owner = finance_db_env["owner"]
    db = finance_db_env["session_factory"]()
    try:
        wells = _acct(db, owner, "Wells")
        _tx(db, owner, wells.id, -80000, "GROCERY", month=7)
        from integrations.finance.services.reports import monthly_trends, net_worth

        before_trends = monthly_trends(db, owner, months=3)
        before_worth = net_worth(db, owner)
        before_count = db.query(FinanceTransaction).filter(FinanceTransaction.owner == owner).count()
        create_planned_for_owner(db, owner, name="Rent", kind="rent", amount_cents=120000)
        after_trends = monthly_trends(db, owner, months=3)
        after_worth = net_worth(db, owner)
        after_count = db.query(FinanceTransaction).filter(FinanceTransaction.owner == owner).count()
        assert after_count == before_count
        assert after_worth["net_worth_cents"] == before_worth["net_worth_cents"]
        assert [t["net_spend_cents"] for t in after_trends] == [t["net_spend_cents"] for t in before_trends]
    finally:
        db.close()


@pytest.mark.area_routes
def test_job_overlay_fixture_and_h7_null_surplus(finance_db_env):
    owner = finance_db_env["owner"]
    db = finance_db_env["session_factory"]()
    try:
        wells = _acct(db, owner, "Wells")
        ensure_default_categories(db, owner)
        support = db.query(FinanceCategory).filter(
            FinanceCategory.owner == owner, FinanceCategory.name == "Support", FinanceCategory.parent_id.is_(None)
        ).one()
        chip = db.query(FinanceCategory).filter(
            FinanceCategory.owner == owner, FinanceCategory.name == "Mom chip-in"
        ).one()
        _tx(db, owner, wells.id, -65000, "GROCERY", category_id=None, month=7)
        _tx(db, owner, wells.id, -15000, "CHIP IN", category_id=chip.id, month=7)
        create_planned_for_owner(db, owner, name="Rent", kind="rent", amount_cents=120000)
        create_planned_for_owner(db, owner, name="Utilities", kind="utilities", amount_cents=20000)
        create_planned_for_owner(db, owner, name="Savings", kind="savings_funding", amount_cents=10000, is_funding=True)
        upsert_job_scenario(db, owner, take_home_cents=300000)
        overlay = job_overlay(db, owner, month="2026-07")
        assert overlay["net_spend_cents"] == 80000
        assert overlay["chip_in_cents"] == 15000
        assert overlay["planned_need_cents"] == 140000
        assert overlay["planned_funding_cents"] == 10000
        assert overlay["survival_need_cents"] == 205000
        assert overlay["needed_cents"] == 215000
        assert overlay["surplus_cents"] == 95000
        assert overlay["surplus_with_savings_cents"] == 85000
        assert overlay["chip_in_rows"]
        _tx(db, owner, wells.id, -20000, "UNCLASSIFIED XFER", cls=None, month=7)
        overlay2 = job_overlay(db, owner, month="2026-07")
        assert overlay2["unclassified_outflow_cents"] >= 20000
        assert overlay2["surplus_cents"] is None
        _ = support
    finally:
        db.close()


@pytest.mark.area_routes
def test_job_scenario_second_put_upserts(finance_db_env):
    owner = finance_db_env["owner"]
    db = finance_db_env["session_factory"]()
    try:
        first = upsert_job_scenario(db, owner, take_home_cents=100000, label="Hypothetical job")
        second = upsert_job_scenario(db, owner, take_home_cents=300000, label="Hypothetical job v2")
        assert first.id == second.id
        assert db.query(FinanceJobScenario).filter(FinanceJobScenario.owner == owner).count() == 1
        assert second.take_home_cents == 300000
    finally:
        db.close()


@pytest.mark.area_routes
def test_house_sitting_is_income_not_overlay_pay(finance_db_env):
    owner = finance_db_env["owner"]
    db = finance_db_env["session_factory"]()
    try:
        wells = _acct(db, owner, "Wells")
        _tx(db, owner, wells.id, 20000, "HOUSE SITTING", cls="income", month=7, day=2)
        upsert_job_scenario(db, owner, take_home_cents=300000)
        overlay = job_overlay(db, owner, month="2026-07")
        assert overlay["take_home_cents"] == 300000
        from integrations.finance.services.reports import month_cashflow
        cf = month_cashflow(db, owner, "2026-07")
        assert cf["income_cents"] == 20000
    finally:
        db.close()
