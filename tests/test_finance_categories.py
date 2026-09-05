"""Finance category seeding and deduplication tests."""

import uuid

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import NullPool

import integrations.finance.database as finance_db
from integrations.finance.install import run_install
from integrations.finance.models import FinanceAccount, FinanceCategory, FinanceTransaction
from integrations.finance.services.categories import (
    create_category_for_owner,
    deduplicate_categories,
    ensure_default_categories,
    format_category_path,
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


@pytest.mark.area_routes
def test_ensure_default_categories_is_idempotent(finance_db_env):
    owner = finance_db_env["owner"]
    db = finance_db_env["session_factory"]()
    try:
        ensure_default_categories(db, owner)
        first_count = db.query(FinanceCategory).filter(FinanceCategory.owner == owner).count()
        ensure_default_categories(db, owner)
        second_count = db.query(FinanceCategory).filter(FinanceCategory.owner == owner).count()
        assert first_count == second_count == 12
    finally:
        db.close()


@pytest.mark.area_routes
def test_deduplicate_categories_merges_duplicate_names(finance_db_env):
    owner = finance_db_env["owner"]
    db = finance_db_env["session_factory"]()
    try:
        keep = FinanceCategory(
            id=str(uuid.uuid4()),
            owner=owner,
            name="Dining",
            is_income=False,
            display_order=0,
        )
        dupe = FinanceCategory(
            id=str(uuid.uuid4()),
            owner=owner,
            name="Dining",
            is_income=False,
            display_order=1,
        )
        acct = FinanceAccount(
            id="acct-1",
            owner=owner,
            name="Checking",
            account_type="checking",
        )
        db.add_all([keep, dupe, acct])
        db.add(FinanceTransaction(
            id=str(uuid.uuid4()),
            owner=owner,
            account_id="acct-1",
            date=__import__("datetime").date(2026, 6, 30),
            amount_cents=-1000,
            payee="PIZZA",
            dedup_hash="hash1",
            category_id=dupe.id,
        ))
        db.commit()

        removed = deduplicate_categories(db, owner)
        assert removed == 1

        names = [
            c.name
            for c in db.query(FinanceCategory).filter(FinanceCategory.owner == owner).all()
        ]
        assert names.count("Dining") == 1

        tx = db.query(FinanceTransaction).filter(FinanceTransaction.payee == "PIZZA").one()
        assert tx.category_id == keep.id
    finally:
        db.close()


@pytest.mark.area_routes
def test_create_subcategory_under_parent(finance_db_env):
    owner = finance_db_env["owner"]
    db = finance_db_env["session_factory"]()
    try:
        parent = FinanceCategory(
            id="dining-id",
            owner=owner,
            name="Dining",
            is_income=False,
        )
        db.add(parent)
        db.commit()

        child = create_category_for_owner(db, owner, "Fast Food", parent_id=parent.id)
        assert child.parent_id == parent.id
        assert child.is_income is False

        with pytest.raises(ValueError, match="already exists"):
            create_category_for_owner(db, owner, "Fast Food", parent_id=parent.id)

        other_top = create_category_for_owner(db, owner, "Fast Food")
        assert other_top.parent_id is None
    finally:
        db.close()


@pytest.mark.area_routes
def test_format_category_path_shows_parent(finance_db_env):
    owner = finance_db_env["owner"]
    db = finance_db_env["session_factory"]()
    try:
        parent = FinanceCategory(id="p1", owner=owner, name="Dining", is_income=False)
        child = FinanceCategory(id="c1", owner=owner, name="Pizza", parent_id="p1", is_income=False)
        db.add_all([parent, child])
        db.commit()
        cats_by_id = {"p1": parent, "c1": child}
        assert format_category_path(child, cats_by_id) == "Dining › Pizza"
    finally:
        db.close()
