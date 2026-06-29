"""Finance category deduplication tests."""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import NullPool

import integrations.finance.database as finance_db
from integrations.finance.models import FinanceAccount, FinanceBase, FinanceCategory, FinanceTransaction
from integrations.finance.services.categories import dedupe_categories, ensure_default_categories


@pytest.fixture()
def finance_db_session(monkeypatch, tmp_path):
    finance_db.reset_engine_cache()
    db_path = tmp_path / "finance.db"
    monkeypatch.setattr(finance_db, "finance_db_path", lambda: db_path)
    engine = create_engine(
        f"sqlite:///{db_path}",
        connect_args={"check_same_thread": False},
        poolclass=NullPool,
    )
    FinanceBase.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    db = session_factory()
    try:
        yield db
    finally:
        db.close()
        finance_db.reset_engine_cache()


@pytest.mark.area_routes
def test_dedupe_categories_merges_duplicates_and_repoints_transactions(finance_db_session):
    db = finance_db_session
    keep = FinanceCategory(id="cat-a", owner="alice", name="Groceries", display_order=0)
    dupe = FinanceCategory(id="cat-b", owner="alice", name="Groceries", display_order=1)
    acct = FinanceAccount(id="acct-1", owner="alice", name="Checking", account_type="checking")
    db.add_all([keep, dupe, acct])
    db.add(FinanceTransaction(
        id="tx-1",
        owner="alice",
        account_id="acct-1",
        date=__import__("datetime").date(2026, 6, 1),
        amount_cents=-100,
        payee="STORE",
        dedup_hash="h1",
        category_id=dupe.id,
    ))
    db.commit()

    removed = dedupe_categories(db, "alice")
    assert removed == 1
    names = [c.name for c in db.query(FinanceCategory).filter(FinanceCategory.owner == "alice").all()]
    assert names.count("Groceries") == 1
    tx = db.query(FinanceTransaction).filter(FinanceTransaction.id == "tx-1").one()
    assert tx.category_id == keep.id


@pytest.mark.area_routes
def test_ensure_default_categories_idempotent_after_race(finance_db_session):
    db = finance_db_session
    ensure_default_categories(db, "alice")
    ensure_default_categories(db, "alice")
    count = db.query(FinanceCategory).filter(FinanceCategory.owner == "alice").count()
    assert count == 12
