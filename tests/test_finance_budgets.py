"""Budget copy and income-target tests."""

import pytest
import integrations.finance.database as finance_db
from integrations.finance.install import run_install
from integrations.finance.models import FinanceCategory, FinanceMonthSettings
from integrations.finance.services.budgets import copy_budgets_for_owner, get_income_target, set_income_target, upsert_budget_for_owner
from integrations.finance.services.categories import ensure_default_categories
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


@pytest.mark.area_routes
def test_copy_june_to_july_copies_limits_and_income_target(finance_db_env):
    owner = finance_db_env["owner"]
    db = finance_db_env["session_factory"]()
    try:
        ensure_default_categories(db, owner)
        groceries = db.query(FinanceCategory).filter(
            FinanceCategory.owner == owner, FinanceCategory.name == "Groceries"
        ).one()
        upsert_budget_for_owner(db, owner, category_id=groceries.id, month="2026-06", limit_cents=40000)
        set_income_target(db, owner, "2026-06", 250000)
        copy_budgets_for_owner(db, owner, "2026-06", "2026-07")
        assert get_income_target(db, owner, "2026-07") == 250000
        from integrations.finance.services.reports import spending_by_category
        rows = spending_by_category(db, owner, "2026-07")
        grocery = next(r for r in rows if r["category_name"] == "Groceries")
        assert grocery["limit_cents"] == 40000
        assert grocery["spent_cents"] == 0
    finally:
        db.close()


@pytest.mark.area_routes
def test_month_settings_owner_isolation(finance_db_env):
    owner = finance_db_env["owner"]
    db = finance_db_env["session_factory"]()
    try:
        set_income_target(db, owner, "2026-07", 10000)
        other = db.query(FinanceMonthSettings).filter(FinanceMonthSettings.owner == "bob").count()
        assert other == 0
        assert get_income_target(db, "bob", "2026-07") == 0
    finally:
        db.close()
