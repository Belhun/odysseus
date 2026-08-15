"""Schema migration tests for trustworthy-books columns."""

from datetime import date

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import NullPool

import integrations.finance.database as finance_db
from integrations.finance.database import init_finance_db
from integrations.finance.install import run_install
from integrations.finance.models import FinanceAccount, FinanceCategory, FinanceTransaction
from integrations.finance.services.categories import ensure_default_categories
from src.plugins.registry import write_installed_record


OLD_ACCOUNTS_SQL = """
CREATE TABLE finance_accounts (
    id VARCHAR NOT NULL,
    owner VARCHAR NOT NULL,
    name VARCHAR NOT NULL,
    institution VARCHAR,
    account_type VARCHAR NOT NULL,
    currency VARCHAR,
    mask_last4 VARCHAR,
    opening_balance_cents INTEGER,
    opening_balance_date DATE,
    credit_limit_cents INTEGER,
    is_closed BOOLEAN,
    display_order INTEGER,
    created_at DATETIME NOT NULL,
    updated_at DATETIME NOT NULL,
    PRIMARY KEY (id)
)
"""

OLD_TX_SQL = """
CREATE TABLE finance_transactions (
    id VARCHAR NOT NULL,
    owner VARCHAR NOT NULL,
    account_id VARCHAR NOT NULL,
    import_batch_id VARCHAR,
    date DATE NOT NULL,
    amount_cents INTEGER NOT NULL,
    payee VARCHAR,
    memo VARCHAR,
    check_number VARCHAR,
    fitid VARCHAR,
    dedup_hash VARCHAR NOT NULL,
    category_id VARCHAR,
    status VARCHAR,
    bank_category VARCHAR,
    created_at DATETIME NOT NULL,
    updated_at DATETIME NOT NULL,
    PRIMARY KEY (id)
)
"""


@pytest.fixture()
def migrated_old_db(monkeypatch, tmp_path):
    finance_db.reset_engine_cache()
    db_path = tmp_path / "finance.db"
    monkeypatch.setattr(finance_db, "finance_db_path", lambda: db_path)
    monkeypatch.setattr(finance_db, "finance_config_path", lambda: tmp_path / "config.json")

    engine = create_engine(
        f"sqlite:///{db_path}",
        connect_args={"check_same_thread": False},
        poolclass=NullPool,
    )
    with engine.connect() as conn:
        conn.execute(text(OLD_ACCOUNTS_SQL))
        conn.execute(text(OLD_TX_SQL))
        conn.execute(
            text(
                "INSERT INTO finance_accounts "
                "(id, owner, name, institution, account_type, currency, "
                "opening_balance_cents, is_closed, display_order, created_at, updated_at) "
                "VALUES ('acct-old', 'alice', 'Wells', '', 'checking', 'USD', "
                "10000, 0, 0, '2026-01-01 00:00:00', '2026-01-01 00:00:00')"
            )
        )
        conn.execute(
            text(
                "INSERT INTO finance_transactions "
                "(id, owner, account_id, date, amount_cents, payee, memo, "
                "dedup_hash, status, created_at, updated_at) "
                "VALUES ('tx-old', 'alice', 'acct-old', '2026-06-01', -4000, "
                "'GROCERY', '', 'hash-old', 'cleared', "
                "'2026-06-01 00:00:00', '2026-06-01 00:00:00')"
            )
        )
        conn.commit()
    engine.dispose()

    init_finance_db()
    yield finance_db.get_session_factory()
    finance_db.reset_engine_cache()


@pytest.mark.area_routes
def test_init_adds_trustworthy_columns_to_old_db(migrated_old_db):
    db = migrated_old_db()
    try:
        acct = db.query(FinanceAccount).filter(FinanceAccount.id == "acct-old").one()
        assert acct.purpose == "operating"
        assert acct.rail is None
        assert acct.posted_pin_cents is None
        assert acct.available_cents is None

        tx = db.query(FinanceTransaction).filter(FinanceTransaction.id == "tx-old").one()
        assert tx.source == "import"
        assert tx.movement_class is None
        assert tx.movement_group_id is None
        assert tx.date == date(2026, 6, 1)
        assert tx.amount_cents == -4000
    finally:
        db.close()


@pytest.mark.area_routes
def test_fresh_create_all_has_new_tables_and_columns(monkeypatch, tmp_path):
    finance_db.reset_engine_cache()
    db_path = tmp_path / "fresh.db"
    monkeypatch.setattr(finance_db, "finance_db_path", lambda: db_path)
    monkeypatch.setattr(finance_db, "finance_config_path", lambda: tmp_path / "config.json")
    init_finance_db()
    engine = finance_db.get_engine()
    with engine.connect() as conn:
        tables = {
            r[0]
            for r in conn.execute(
                text("SELECT name FROM sqlite_master WHERE type='table'")
            ).fetchall()
        }
        acct_cols = {r[1] for r in conn.execute(text("PRAGMA table_info(finance_accounts)")).fetchall()}
        tx_cols = {r[1] for r in conn.execute(text("PRAGMA table_info(finance_transactions)")).fetchall()}
    assert "finance_mutation_log" in tables
    assert "finance_csv_mappings" in tables
    assert "finance_month_settings" in tables
    assert "finance_planned_obligations" in tables
    assert "finance_job_scenarios" in tables
    assert "purpose" in acct_cols
    assert "posted_pin_cents" in acct_cols
    assert "available_cents" in acct_cols
    assert "movement_class" in tx_cols
    assert "source" in tx_cols
    finance_db.reset_engine_cache()


@pytest.mark.area_routes
def test_ensure_default_categories_seeds_support(migrated_old_db):
    db = migrated_old_db()
    try:
        ensure_default_categories(db, "alice")
        names = {
            c.name
            for c in db.query(FinanceCategory).filter(FinanceCategory.owner == "alice").all()
        }
        assert "Support" in names
        ensure_default_categories(db, "alice")
        support_count = (
            db.query(FinanceCategory)
            .filter(FinanceCategory.owner == "alice", FinanceCategory.name == "Support")
            .count()
        )
        assert support_count == 1
    finally:
        db.close()


def _seed_v010_db(db_path):
    engine = create_engine(
        f"sqlite:///{db_path}",
        connect_args={"check_same_thread": False},
        poolclass=NullPool,
    )
    with engine.connect() as conn:
        conn.execute(text(OLD_ACCOUNTS_SQL))
        conn.execute(text(OLD_TX_SQL))
        conn.execute(
            text(
                "INSERT INTO finance_accounts "
                "(id, owner, name, institution, account_type, currency, "
                "opening_balance_cents, is_closed, display_order, created_at, updated_at) "
                "VALUES ('acct-old', 'alice', 'Wells', '', 'checking', 'USD', "
                "10000, 0, 0, '2026-01-01 00:00:00', '2026-01-01 00:00:00')"
            )
        )
        conn.commit()
    engine.dispose()


@pytest.mark.area_routes
def test_run_install_twice_migrates_existing_v010_db(monkeypatch, tmp_path):
    """Already-installed plugins must pick up new columns on a second run_install()."""
    plugins_root = tmp_path / "plugins"
    db_path = plugins_root / "finance" / "finance.db"
    db_path.parent.mkdir(parents=True)
    monkeypatch.setattr("src.plugins.registry.PLUGINS_DATA_ROOT", plugins_root)
    monkeypatch.setattr("src.plugins.registry.plugin_data_dir", lambda pid: plugins_root / pid)
    monkeypatch.setattr(finance_db, "finance_db_path", lambda: db_path)
    monkeypatch.setattr(finance_db, "finance_config_path", lambda: plugins_root / "finance" / "config.json")
    monkeypatch.setattr("src.settings.FEATURES_FILE", str(tmp_path / "features.json"))
    finance_db.reset_engine_cache()

    _seed_v010_db(db_path)
    write_installed_record("finance", "0.1.0")

    first = run_install()
    assert first["ok"] is True
    assert first.get("already_installed") is True

    finance_db.reset_engine_cache()
    second = run_install()
    assert second["ok"] is True
    assert second.get("already_installed") is True

    engine = finance_db.get_engine()
    with engine.connect() as conn:
        acct_cols = {r[1] for r in conn.execute(text("PRAGMA table_info(finance_accounts)")).fetchall()}
        tx_cols = {r[1] for r in conn.execute(text("PRAGMA table_info(finance_transactions)")).fetchall()}
    assert "purpose" in acct_cols
    assert "posted_pin_cents" in acct_cols
    assert "available_cents" in acct_cols
    assert "movement_class" in tx_cols
    assert "source" in tx_cols
    finance_db.reset_engine_cache()
