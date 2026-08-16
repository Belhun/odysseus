"""Movement class, linking, and detection tests."""

import uuid
from datetime import date

import pytest
import integrations.finance.database as finance_db
from integrations.finance.install import run_install
from integrations.finance.models import FinanceAccount, FinanceTransaction
from integrations.finance.services.movements import (
    apply_payee_heuristics,
    classify_transaction,
    detect_movements,
    effective_movement_class,
    link_movements,
    unlink_movement,
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


def _acct(db, owner, name, purpose="operating", rail=None, acct_id=None):
    acct = FinanceAccount(
        id=acct_id or str(uuid.uuid4()),
        owner=owner,
        name=name,
        account_type="checking",
        purpose=purpose,
        rail=rail,
    )
    db.add(acct)
    db.commit()
    return acct


def _tx(db, owner, account_id, amount, payee, day=1, cls=None, tx_id=None):
    tx = FinanceTransaction(
        id=tx_id or str(uuid.uuid4()),
        owner=owner,
        account_id=account_id,
        date=date(2026, 6, day),
        amount_cents=amount,
        payee=payee,
        dedup_hash=str(uuid.uuid4()),
        status="cleared",
        source="import",
        movement_class=cls,
    )
    db.add(tx)
    db.commit()
    return tx


@pytest.mark.area_routes
def test_effective_class_fail_open():
    tx = FinanceTransaction(amount_cents=-4000, movement_class=None)
    assert effective_movement_class(tx) == "spend"
    tx.amount_cents = 4000
    assert effective_movement_class(tx) == "income"
    tx.movement_class = "transfer"
    assert effective_movement_class(tx) == "transfer"


@pytest.mark.area_routes
def test_classify_unpaired_reimbursement(finance_db_env):
    owner = finance_db_env["owner"]
    db = finance_db_env["session_factory"]()
    try:
        wells = _acct(db, owner, "Wells")
        tx = _tx(db, owner, wells.id, 4000, "ZELLE FROM MOM")
        classify_transaction(db, owner, tx.id, "reimbursement")
        db.refresh(tx)
        assert tx.movement_class == "reimbursement"
        assert tx.movement_group_id is None
    finally:
        db.close()


@pytest.mark.area_routes
def test_link_two_operating_legs_are_transfer(finance_db_env):
    owner = finance_db_env["owner"]
    db = finance_db_env["session_factory"]()
    try:
        wells = _acct(db, owner, "Wells")
        trip = _acct(db, owner, "Trip", purpose="trip")
        a = _tx(db, owner, wells.id, -50000, "NAVY FEDERAL")
        b = _tx(db, owner, trip.id, 50000, "WELLS FARGO")
        group = link_movements(db, owner, [a.id, b.id])
        db.refresh(a)
        db.refresh(b)
        assert a.movement_group_id == b.movement_group_id == group
        assert a.movement_class == "transfer"
        assert b.movement_class == "transfer"
        cleared = unlink_movement(db, owner, tx_id=a.id)
        assert cleared == 2
        db.refresh(a)
        assert a.movement_group_id is None
        assert a.movement_class == "transfer"
    finally:
        db.close()


@pytest.mark.area_routes
def test_link_processor_legs_are_pass_through(finance_db_env):
    owner = finance_db_env["owner"]
    db = finance_db_env["session_factory"]()
    try:
        wells = _acct(db, owner, "Wells")
        paypal = _acct(db, owner, "PayPal", purpose="processor", rail="paypal")
        google = _acct(db, owner, "Google", purpose="processor", rail="google")
        spend = _tx(db, owner, google.id, -1299, "GOOGLE ONE")
        paypal_leg = _tx(db, owner, paypal.id, 1299, "GOOGLE")
        wells_leg = _tx(db, owner, wells.id, -1299, "PAYPAL INST XFER")
        group = link_movements(db, owner, [spend.id, paypal_leg.id, wells_leg.id])
        db.refresh(spend)
        db.refresh(paypal_leg)
        db.refresh(wells_leg)
        assert spend.movement_group_id == group
        assert spend.movement_class == "spend"
        assert paypal_leg.movement_class == "pass_through"
        assert wells_leg.movement_class == "pass_through"
    finally:
        db.close()


@pytest.mark.area_routes
def test_link_rejects_same_account_and_same_sign(finance_db_env):
    owner = finance_db_env["owner"]
    db = finance_db_env["session_factory"]()
    try:
        wells = _acct(db, owner, "Wells")
        a = _tx(db, owner, wells.id, -500, "A")
        b = _tx(db, owner, wells.id, 500, "B")
        with pytest.raises(ValueError, match="different accounts"):
            link_movements(db, owner, [a.id, b.id])
        trip = _acct(db, owner, "Trip", purpose="trip")
        c = _tx(db, owner, trip.id, -500, "C")
        with pytest.raises(ValueError, match="opposite equal"):
            link_movements(db, owner, [a.id, c.id])
    finally:
        db.close()


@pytest.mark.area_routes
def test_detect_unique_same_day_auto_link(finance_db_env):
    owner = finance_db_env["owner"]
    db = finance_db_env["session_factory"]()
    try:
        wells = _acct(db, owner, "Wells")
        trip = _acct(db, owner, "Trip", purpose="trip")
        _tx(db, owner, wells.id, -50000, "NAVY FEDERAL")
        _tx(db, owner, trip.id, 50000, "WELLS")
        result = detect_movements(db, owner, auto_link=True)
        assert len(result["auto_linked"]) == 1
        txs = db.query(FinanceTransaction).filter(FinanceTransaction.owner == owner).all()
        assert all(tx.movement_group_id for tx in txs)
        assert all(tx.movement_class == "transfer" for tx in txs)
    finally:
        db.close()


@pytest.mark.area_routes
def test_detect_ambiguous_peers_are_suggestions_only(finance_db_env):
    owner = finance_db_env["owner"]
    db = finance_db_env["session_factory"]()
    try:
        wells = _acct(db, owner, "Wells")
        trip = _acct(db, owner, "Trip", purpose="trip")
        other = _acct(db, owner, "Other")
        _tx(db, owner, wells.id, -50000, "NAVY FEDERAL")
        _tx(db, owner, trip.id, 50000, "WELLS A")
        _tx(db, owner, other.id, 50000, "WELLS B")
        result = detect_movements(db, owner, auto_link=True)
        assert result["auto_linked"] == []
        assert result["suggestions"]
        grouped = db.query(FinanceTransaction).filter(
            FinanceTransaction.owner == owner,
            FinanceTransaction.movement_group_id.isnot(None),
        ).count()
        assert grouped == 0
    finally:
        db.close()


@pytest.mark.area_routes
def test_paypal_inst_xfer_unmatched_gets_class(finance_db_env):
    owner = finance_db_env["owner"]
    db = finance_db_env["session_factory"]()
    try:
        wells = _acct(db, owner, "Wells")
        tx = _tx(db, owner, wells.id, -1299, "PAYPAL INST XFER")
        result = detect_movements(db, owner, auto_link=True)
        db.refresh(tx)
        assert tx.movement_class in ("transfer", "pass_through")
        assert tx.movement_group_id is None
        assert result["unmatched_funding"]
    finally:
        db.close()


@pytest.mark.area_routes
def test_zelle_from_mom_is_not_guessed_as_reimbursement(finance_db_env):
    owner = finance_db_env["owner"]
    db = finance_db_env["session_factory"]()
    try:
        wells = _acct(db, owner, "Wells")
        inflow = _tx(db, owner, wells.id, 4000, "ZELLE FROM JANE SMITH")
        chipin = _tx(db, owner, wells.id, -15000, "ZELLE TO MOM")
        apply_payee_heuristics(db, owner)
        db.refresh(inflow)
        db.refresh(chipin)
        assert inflow.movement_class != "reimbursement"
        assert chipin.movement_class is None
        assert effective_movement_class(chipin) == "spend"
    finally:
        db.close()


@pytest.mark.area_routes
def test_venmo_cashout_without_venmo_book_stays_income(finance_db_env):
    owner = finance_db_env["owner"]
    db = finance_db_env["session_factory"]()
    try:
        wells = _acct(db, owner, "Wells")
        tx = _tx(db, owner, wells.id, 12000, "VENMO CASHOUT")
        result = detect_movements(db, owner, auto_link=True)
        db.refresh(tx)
        assert tx.movement_class == "income"
        assert result["unmatched_inflow"]
    finally:
        db.close()


@pytest.mark.area_routes
def test_one_sided_transfer_pairs_unique_opposite_peer(finance_db_env):
    owner = finance_db_env["owner"]
    db = finance_db_env["session_factory"]()
    try:
        wells = _acct(db, owner, "Wells")
        trip = _acct(db, owner, "Trip", purpose="trip")
        out_leg = _tx(db, owner, wells.id, -50000, "ONLINE TRANSFER")
        in_leg = _tx(db, owner, trip.id, 50000, "WELLS FARGO")
        apply_payee_heuristics(db, owner)
        db.refresh(out_leg)
        db.refresh(in_leg)
        assert out_leg.movement_class == "transfer"
        assert in_leg.movement_class == "transfer"
    finally:
        db.close()


@pytest.mark.area_routes
def test_two_outflows_one_inflow_produces_no_auto_link(finance_db_env):
    owner = finance_db_env["owner"]
    db = finance_db_env["session_factory"]()
    try:
        wells = _acct(db, owner, "Wells")
        trip = _acct(db, owner, "Trip", purpose="trip")
        other = _acct(db, owner, "Other")
        _tx(db, owner, wells.id, -50000, "TO TRIP A")
        _tx(db, owner, other.id, -50000, "TO TRIP B")
        _tx(db, owner, trip.id, 50000, "FROM WELLS")
        result = detect_movements(db, owner, auto_link=True)
        assert result["auto_linked"] == []
        assert len(result["suggestions"]) == 2
        grouped = db.query(FinanceTransaction).filter(
            FinanceTransaction.owner == owner,
            FinanceTransaction.movement_group_id.isnot(None),
        ).count()
        assert grouped == 0
    finally:
        db.close()


@pytest.mark.area_routes
def test_rollback_batch_demotes_surviving_linked_peer(finance_db_env):
    from integrations.finance.models import FinanceImportBatch
    from integrations.finance.services.import_service import rollback_import_batch
    from integrations.finance.services.reports import month_cashflow

    owner = finance_db_env["owner"]
    db = finance_db_env["session_factory"]()
    try:
        wells = _acct(db, owner, "Wells")
        trip = _acct(db, owner, "Trip", purpose="trip")
        batch = FinanceImportBatch(
            id="batch-trip",
            owner=owner,
            account_id=trip.id,
            filename="trip.csv",
        )
        db.add(batch)
        db.commit()
        wells_leg = _tx(db, owner, wells.id, -50000, "NAVY FEDERAL")
        trip_leg = _tx(db, owner, trip.id, 50000, "WELLS")
        trip_leg.import_batch_id = batch.id
        db.commit()
        link_movements(db, owner, [wells_leg.id, trip_leg.id])
        rollback_import_batch(db, owner, batch.id)
        db.refresh(wells_leg)
        assert wells_leg.movement_group_id is None
        assert wells_leg.movement_class is None
        cf = month_cashflow(db, owner, "2026-06")
        assert cf["net_spend_cents"] == 50000
        assert cf["income_cents"] == 0
    finally:
        db.close()


@pytest.mark.area_routes
def test_maybe_backfill_runs_once_per_owner(finance_db_env, monkeypatch):
    from integrations.finance.services import movements as movements_mod

    owner = finance_db_env["owner"]
    db = finance_db_env["session_factory"]()
    calls = {"n": 0}

    def _fake_detect(*args, **kwargs):
        calls["n"] += 1
        return {
            "suggestions": [],
            "auto_linked": [],
            "unmatched_funding": [],
            "unmatched_inflow": [],
            "p2p_inflows": [],
            "heuristics_applied": 0,
            "day_gap": 3,
            "unmatched_count": 0,
        }

    monkeypatch.setattr(movements_mod, "detect_movements", _fake_detect)
    monkeypatch.setattr(movements_mod, "apply_payee_heuristics", lambda *a, **k: 0)
    try:
        wells = _acct(db, owner, "Wells")
        _tx(db, owner, wells.id, -400, "Coffee")
        movements_mod.maybe_backfill_movements(db, owner)
        movements_mod.maybe_backfill_movements(db, owner)
        assert calls["n"] == 1
    finally:
        db.close()


@pytest.mark.area_routes
def test_detect_indexes_opposite_amount_among_many_unmatched(finance_db_env):
    owner = finance_db_env["owner"]
    db = finance_db_env["session_factory"]()
    try:
        wells = _acct(db, owner, "Wells")
        trip = _acct(db, owner, "Trip", purpose="trip")
        for i in range(80):
            _tx(db, owner, wells.id, -(1000 + i), f"Spend {i}", day=1 + (i % 28))
            _tx(db, owner, trip.id, 2000 + i, f"In {i}", day=1 + (i % 28))
        _tx(db, owner, wells.id, -50000, "NAVY FEDERAL", day=10)
        _tx(db, owner, trip.id, 50000, "WELLS", day=10)
        result = detect_movements(db, owner, auto_link=True)
        assert len(result["auto_linked"]) == 1
        linked = db.query(FinanceTransaction).filter(
            FinanceTransaction.owner == owner,
            FinanceTransaction.movement_group_id.isnot(None),
        ).count()
        assert linked == 2
    finally:
        db.close()
