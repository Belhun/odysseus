"""True-spend report tests (one cashflow helper)."""

import uuid
from datetime import date

import pytest
import integrations.finance.database as finance_db
from integrations.finance.install import run_install
from integrations.finance.models import FinanceAccount, FinanceCategory, FinanceTransaction, FinanceTransactionSplit
from integrations.finance.services.categories import ensure_default_categories
from integrations.finance.services.movements import link_movements
from integrations.finance.services.reports import (
    month_cashflow,
    monthly_trends,
    net_worth,
    spend_by_account,
    spending_by_category,
    overlay_surplus_cents,
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
    cat = (
        db.query(FinanceCategory)
        .filter(FinanceCategory.owner == owner, FinanceCategory.name == name)
        .first()
    )
    return cat


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


@pytest.mark.area_routes
def test_trip_funding_excluded_hotel_is_travel_spend(finance_db_env):
    owner = finance_db_env["owner"]
    db = finance_db_env["session_factory"]()
    try:
        wells = _acct(db, owner, "Wells")
        trip = _acct(db, owner, "Trip", purpose="trip")
        travel = _cat(db, owner, "Travel")
        out_leg = _tx(db, owner, wells.id, -50000, "NAVY FEDERAL")
        in_leg = _tx(db, owner, trip.id, 50000, "WELLS")
        link_movements(db, owner, [out_leg.id, in_leg.id])
        _tx(db, owner, trip.id, -8000, "HOTEL", cls="spend", category_id=travel.id)
        cf = month_cashflow(db, owner, "2026-06")
        assert cf["net_spend_cents"] == 8000
        assert cf["income_cents"] == 0
        cats = spending_by_category(db, owner, "2026-06")
        travel_row = next(r for r in cats if r["category_name"] == "Travel")
        assert travel_row["spent_cents"] == 8000
    finally:
        db.close()


@pytest.mark.area_routes
def test_google_bill_counts_once(finance_db_env):
    owner = finance_db_env["owner"]
    db = finance_db_env["session_factory"]()
    try:
        wells = _acct(db, owner, "Wells")
        paypal = _acct(db, owner, "PayPal", purpose="processor", rail="paypal")
        google = _acct(db, owner, "Google", purpose="processor", rail="google")
        sub = _cat(db, owner, "Subscriptions")
        spend = _tx(db, owner, google.id, -1299, "GOOGLE ONE", category_id=sub.id)
        paypal_leg = _tx(db, owner, paypal.id, 1299, "GOOGLE")
        wells_leg = _tx(db, owner, wells.id, -1299, "PAYPAL INST XFER")
        link_movements(db, owner, [spend.id, paypal_leg.id, wells_leg.id])
        cf = month_cashflow(db, owner, "2026-06")
        assert cf["net_spend_cents"] == 1299
        assert cf["income_cents"] == 0
    finally:
        db.close()


@pytest.mark.area_routes
def test_mom_reimbursement_nets_and_is_not_income(finance_db_env):
    owner = finance_db_env["owner"]
    db = finance_db_env["session_factory"]()
    try:
        wells = _acct(db, owner, "Wells")
        sub = _cat(db, owner, "Subscriptions")
        _tx(db, owner, wells.id, -8000, "T-MOBILE", cls="spend", category_id=sub.id)
        _tx(db, owner, wells.id, 4000, "ZELLE FROM MOM", cls="reimbursement")
        cf = month_cashflow(db, owner, "2026-06")
        assert cf["gross_spend_cents"] == 8000
        assert cf["reimbursement_in_cents"] == 4000
        assert cf["net_spend_cents"] == 4000
        assert cf["income_cents"] == 0
        cats = spending_by_category(db, owner, "2026-06")
        sub_row = next(r for r in cats if r["category_name"] == "Subscriptions")
        assert sub_row["spent_cents"] == 8000
    finally:
        db.close()


@pytest.mark.area_routes
def test_verizon_zelle_to_mom_is_not_spend(finance_db_env):
    owner = finance_db_env["owner"]
    db = finance_db_env["session_factory"]()
    try:
        wells = _acct(db, owner, "Wells")
        _tx(db, owner, wells.id, -5500, "ZELLE TO MOM VERIZON", cls="reimbursement")
        cf = month_cashflow(db, owner, "2026-06")
        assert cf["net_spend_cents"] == 0
        assert cf["income_cents"] == 0
        assert cf["reimbursement_out_cents"] == 5500
    finally:
        db.close()


@pytest.mark.area_routes
def test_chip_in_is_support_spend(finance_db_env):
    owner = finance_db_env["owner"]
    db = finance_db_env["session_factory"]()
    try:
        wells = _acct(db, owner, "Wells")
        support = _cat(db, owner, "Support")
        _tx(db, owner, wells.id, -15000, "ZELLE TO MOM", cls="spend", category_id=support.id)
        cf = month_cashflow(db, owner, "2026-06")
        assert cf["net_spend_cents"] == 15000
        cats = spending_by_category(db, owner, "2026-06")
        row = next(r for r in cats if r["category_name"] == "Support")
        assert row["spent_cents"] == 15000
    finally:
        db.close()


@pytest.mark.area_routes
def test_null_class_fail_open_and_include_transfers(finance_db_env):
    owner = finance_db_env["owner"]
    db = finance_db_env["session_factory"]()
    try:
        wells = _acct(db, owner, "Wells")
        _tx(db, owner, wells.id, -4000, "GROCERY")
        _tx(db, owner, wells.id, 100000, "HOUSE SITTING", cls="income")
        _tx(db, owner, wells.id, -20000, "TO TRIP", cls="transfer")
        cf = month_cashflow(db, owner, "2026-06")
        assert cf["net_spend_cents"] == 4000
        assert cf["income_cents"] == 100000
        assert cf["unclassified_count"] == 1
        assert cf["incomplete"] is True
        lie = month_cashflow(db, owner, "2026-06", include_transfers=True)
        assert lie["spending_cents"] == 24000
        assert lie["income_cents"] == 100000
    finally:
        db.close()


@pytest.mark.area_routes
def test_void_excluded_and_navy_business_included(finance_db_env):
    owner = finance_db_env["owner"]
    db = finance_db_env["session_factory"]()
    try:
        navy = _acct(db, owner, "Navy business", purpose="operating")
        _tx(db, owner, navy.id, -2500, "GROCERY", cls="spend")
        _tx(db, owner, navy.id, -9000, "VOIDED", cls="spend", status="void")
        cf = month_cashflow(db, owner, "2026-06")
        assert cf["net_spend_cents"] == 2500
    finally:
        db.close()


@pytest.mark.area_routes
def test_unlinked_transfer_amount_still_spend_until_classified(finance_db_env):
    owner = finance_db_env["owner"]
    db = finance_db_env["session_factory"]()
    try:
        wells = _acct(db, owner, "Wells")
        _tx(db, owner, wells.id, -50000, "NAVY FEDERAL")
        cf = month_cashflow(db, owner, "2026-06")
        assert cf["net_spend_cents"] == 50000
    finally:
        db.close()


@pytest.mark.area_routes
def test_over_reimbursed_category_spent_is_negative(finance_db_env):
    owner = finance_db_env["owner"]
    db = finance_db_env["session_factory"]()
    try:
        wells = _acct(db, owner, "Wells")
        sub = _cat(db, owner, "Subscriptions")
        _tx(db, owner, wells.id, -8000, "T-MOBILE", cls="spend", category_id=sub.id)
        _tx(db, owner, wells.id, 12000, "ZELLE FROM MOM", cls="reimbursement", category_id=sub.id)
        cats = spending_by_category(db, owner, "2026-06")
        row = next(r for r in cats if r["category_name"] == "Subscriptions")
        assert row["spent_cents"] == -4000
    finally:
        db.close()


@pytest.mark.area_routes
def test_voided_split_parent_excluded_from_category_totals(finance_db_env):
    owner = finance_db_env["owner"]
    db = finance_db_env["session_factory"]()
    try:
        wells = _acct(db, owner, "Wells")
        sub = _cat(db, owner, "Subscriptions")
        parent = _tx(db, owner, wells.id, -8000, "SPLIT BILL", cls="spend", status="void")
        db.add(FinanceTransactionSplit(
            id=str(uuid.uuid4()),
            owner=owner,
            transaction_id=parent.id,
            category_id=sub.id,
            amount_cents=-8000,
        ))
        db.commit()
        cats = spending_by_category(db, owner, "2026-06")
        names = [r["category_name"] for r in cats if r["spent_cents"]]
        assert "Subscriptions" not in names
    finally:
        db.close()


@pytest.mark.area_routes
def test_monthly_trends_row_matches_standalone_cashflow(finance_db_env):
    owner = finance_db_env["owner"]
    db = finance_db_env["session_factory"]()
    try:
        wells = _acct(db, owner, "Wells")
        _tx(db, owner, wells.id, -4000, "GROCERY", cls="spend")
        _tx(db, owner, wells.id, 100000, "PAY", cls="income")
        cf = month_cashflow(db, owner, "2026-06")
        trends = monthly_trends(db, owner, months=8)
        row = next(r for r in trends if r["month"] == "2026-06")
        assert row["income_cents"] == cf["income_cents"]
        assert row["spending_cents"] == cf["spending_cents"]
        assert row["net_spend_cents"] == cf["net_spend_cents"]
    finally:
        db.close()


@pytest.mark.area_routes
def test_include_transfers_still_excludes_void(finance_db_env):
    owner = finance_db_env["owner"]
    db = finance_db_env["session_factory"]()
    try:
        wells = _acct(db, owner, "Wells")
        _tx(db, owner, wells.id, -4000, "GROCERY")
        _tx(db, owner, wells.id, -9000, "VOIDED", status="void")
        lie = month_cashflow(db, owner, "2026-06", include_transfers=True)
        assert lie["spending_cents"] == 4000
    finally:
        db.close()


@pytest.mark.area_routes
def test_net_worth_buckets_by_sign(finance_db_env):
    owner = finance_db_env["owner"]
    db = finance_db_env["session_factory"]()
    try:
        card = FinanceAccount(
            id=str(uuid.uuid4()),
            owner=owner,
            name="Card",
            account_type="credit_card",
            opening_balance_cents=5000,
        )
        db.add(card)
        db.commit()
        worth = net_worth(db, owner)
        assert worth["assets_cents"] == 5000
        assert worth["liabilities_cents"] == 0
    finally:
        db.close()


@pytest.mark.area_routes
def test_spend_by_account_includes_closed_and_sums(finance_db_env):
    owner = finance_db_env["owner"]
    db = finance_db_env["session_factory"]()
    try:
        wells = _acct(db, owner, "Wells")
        old = _acct(db, owner, "Old card")
        old.is_closed = True
        db.commit()
        sub = _cat(db, owner, "Subscriptions")
        _tx(db, owner, wells.id, -8000, "T-MOBILE", cls="spend", category_id=sub.id)
        _tx(db, owner, old.id, -2000, "OLD FEE", cls="spend")
        _tx(db, owner, wells.id, 2000, "REIMBURSE OLD", cls="reimbursement")
        rows = spend_by_account(db, owner, "2026-06")
        ids = {r["account_id"] for r in rows}
        assert old.id in ids
        assert wells.id in ids
        cf = month_cashflow(db, owner, "2026-06")
        assert sum(r["personal_spend_cents"] for r in rows) == cf["personal_spend_cents"]
    finally:
        db.close()


@pytest.mark.area_routes
def test_overlay_surplus_null_when_unclassified_outflows(finance_db_env):
    assert overlay_surplus_cents(50000, 0) == 50000
    assert overlay_surplus_cents(50000, 101) is None
