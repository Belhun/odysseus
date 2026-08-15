"""Movement class, linking, and detection tests."""

import uuid
from datetime import date

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import NullPool

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
    db_path = plugins_root / "finance" / "finance.db"
    engine = create_engine(
        f"sqlite:///{db_path}",
        connect_args={"check_same_thread": False},
        poolclass=NullPool,
    )
    session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    yield {"owner": "alice", "session_factory": session_factory}
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
def test_zelle_from_mom_is_reimbursement_zelle_to_mom_chipin_is_not(finance_db_env):
    owner = finance_db_env["owner"]
    db = finance_db_env["session_factory"]()
    try:
        wells = _acct(db, owner, "Wells")
        inflow = _tx(db, owner, wells.id, 4000, "ZELLE FROM MOM T-MOBILE")
        chipin = _tx(db, owner, wells.id, -15000, "ZELLE TO MOM")
        apply_payee_heuristics(db, owner)
        db.refresh(inflow)
        db.refresh(chipin)
        assert inflow.movement_class == "reimbursement"
        assert chipin.movement_class is None
        assert effective_movement_class(chipin) == "spend"
    finally:
        db.close()
