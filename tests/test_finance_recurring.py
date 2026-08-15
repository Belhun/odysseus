"""Finance recurring bill detection tests."""

import uuid
from datetime import date, timedelta

import pytest
import integrations.finance.database as finance_db
from integrations.finance.install import run_install
from integrations.finance.models import FinanceAccount, FinanceCategory, FinanceRecurringSeries, FinanceTransaction
from integrations.finance.services.categories import ensure_default_categories
from integrations.finance.services.recurring import list_recurring_series, patch_recurring_series, refresh_recurring_series
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


def _add_recurring_transactions(db, owner: str, payee: str, base_date: date, amounts: list[int], interval: int):
    acct = FinanceAccount(id="acct-rec", owner=owner, name="Checking", account_type="checking")
    db.add(acct)
    for i, amount in enumerate(amounts):
        db.add(FinanceTransaction(
            id=str(uuid.uuid4()),
            owner=owner,
            account_id=acct.id,
            date=base_date + timedelta(days=i * interval),
            amount_cents=amount,
            payee=payee,
            dedup_hash=f"rec-{payee}-{i}",
        ))
    db.commit()


@pytest.mark.area_routes
def test_refresh_recurring_series_detects_monthly_bill(finance_db_env):
    owner = finance_db_env["owner"]
    db = finance_db_env["session_factory"]()
    try:
        base = date(2026, 1, 15)
        _add_recurring_transactions(db, owner, "SPOTIFY USA", base, [-999, -999, -1001], 30)

        count = refresh_recurring_series(db, owner)
        assert count >= 1

        series = db.query(FinanceRecurringSeries).filter(FinanceRecurringSeries.owner == owner).all()
        assert len(series) == 1
        assert series[0].cadence == "monthly"
        assert series[0].status == "active"
    finally:
        db.close()


@pytest.mark.area_routes
def test_dismissed_recurring_status_preserved_on_refresh(finance_db_env):
    owner = finance_db_env["owner"]
    db = finance_db_env["session_factory"]()
    try:
        base = date(2026, 1, 1)
        _add_recurring_transactions(db, owner, "GYM MEMBERSHIP", base, [-5000, -5000, -5000], 30)

        refresh_recurring_series(db, owner)
        row = db.query(FinanceRecurringSeries).filter(FinanceRecurringSeries.owner == owner).one()
        row.status = "dismissed"
        db.commit()

        refresh_recurring_series(db, owner)
        db.refresh(row)
        assert row.status == "dismissed"
    finally:
        db.close()


@pytest.mark.area_routes
def test_list_recurring_series_monthly_normalized(finance_db_env):
    owner = finance_db_env["owner"]
    db = finance_db_env["session_factory"]()
    try:
        base = date(2026, 2, 1)
        _add_recurring_transactions(db, owner, "ELECTRIC CO", base, [-12000, -11800, -12100], 30)

        rows = list_recurring_series(db, owner)
        assert len(rows) == 1
        assert rows[0]["monthly_normalized_cents"] > 0
        assert rows[0]["cadence"] == "monthly"
    finally:
        db.close()


@pytest.mark.area_routes
def test_mark_automatic_refuses_funding_tokens_allows_netflix(finance_db_env):
    owner = finance_db_env["owner"]
    db = finance_db_env["session_factory"]()
    try:
        ensure_default_categories(db, owner)
        sub = db.query(FinanceCategory).filter(
            FinanceCategory.owner == owner, FinanceCategory.name == "Subscriptions"
        ).one()
        _add_recurring_transactions(db, owner, "NETFLIX", date(2026, 2, 1), [-1600, -1600, -1600], 30)
        rows = list_recurring_series(db, owner)
        netflix = next(r for r in rows if r["display_payee"] == "NETFLIX")
        patched = patch_recurring_series(
            db, owner, netflix["id"], status="automatic", category_id=sub.id, movement_class="spend"
        )
        assert patched.status == "automatic"
        zelle = FinanceRecurringSeries(
            id=str(uuid.uuid4()),
            owner=owner,
            normalized_payee="ZELLE TO JANE",
            display_payee="ZELLE TO JANE",
            cadence="monthly",
            interval_days=30,
            median_amount_cents=-15000,
            status="active",
        )
        db.add(zelle)
        db.commit()
        with pytest.raises(ValueError, match="Funding"):
            patch_recurring_series(db, owner, zelle.id, status="automatic", category_id="x", movement_class="spend")
    finally:
        db.close()
