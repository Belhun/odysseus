"""Isolated SQLite database for the Finance plugin."""

from __future__ import annotations

import json
import logging
import sqlite3
from pathlib import Path

from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import sessionmaker

from integrations.finance.models import FinanceBase
from src.plugins.registry import plugin_data_dir


def finance_db_path() -> Path:
    return plugin_data_dir("finance") / "finance.db"


def finance_config_path() -> Path:
    return plugin_data_dir("finance") / "config.json"


_engine = None
SessionLocal = None


def _sqlite_url(path: Path) -> str:
    return f"sqlite:///{path.as_posix()}"


logger = logging.getLogger(__name__)


def _set_sqlite_pragma(dbapi_conn, _connection_record):
    cursor = dbapi_conn.cursor()
    # busy_timeout must come first so later pragmas (notably journal_mode=WAL,
    # which needs a brief exclusive lock) wait instead of failing immediately.
    cursor.execute("PRAGMA busy_timeout=5000")
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.execute("PRAGMA synchronous=NORMAL")
    try:
        # WAL is persistent once set, so a failure here is harmless as long as
        # some earlier or later connection succeeds. Don't 500 the request.
        cursor.execute("PRAGMA journal_mode=WAL")
    except sqlite3.OperationalError as exc:
        logger.warning("Could not switch finance DB to WAL (continuing): %s", exc)
    finally:
        cursor.close()


def attach_sqlite_pragmas(engine) -> None:
    """Attach production SQLite pragmas (foreign_keys=ON) to a test or file engine."""
    event.listen(engine, "connect", _set_sqlite_pragma)


def _migrate_unique_dedup_index(engine) -> None:
    """Ensure (account_id, dedup_hash) index is UNIQUE; dedupe existing rows first."""
    with engine.connect() as conn:
        row = conn.execute(
            text(
                "SELECT sql FROM sqlite_master "
                "WHERE type='index' AND name='ix_finance_tx_account_dedup'"
            )
        ).fetchone()
        if row and row[0] and "UNIQUE" in str(row[0]).upper():
            return

        conn.execute(
            text(
                "DELETE FROM finance_transactions "
                "WHERE rowid NOT IN ("
                "  SELECT MIN(rowid) FROM finance_transactions "
                "  GROUP BY account_id, dedup_hash"
                ")"
            )
        )
        conn.execute(text("DROP INDEX IF EXISTS ix_finance_tx_account_dedup"))
        conn.execute(
            text(
                "CREATE UNIQUE INDEX ix_finance_tx_account_dedup "
                "ON finance_transactions (account_id, dedup_hash)"
            )
        )
        conn.commit()


def get_engine():
    global _engine
    if _engine is None:
        path = finance_db_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        _engine = create_engine(
            _sqlite_url(path),
            connect_args={"check_same_thread": False},
        )

        @event.listens_for(_engine, "connect")
        def _on_connect(dbapi_conn, connection_record):
            _set_sqlite_pragma(dbapi_conn, connection_record)

    return _engine


def get_session_factory():
    global SessionLocal
    if SessionLocal is None:
        SessionLocal = sessionmaker(bind=get_engine(), autoflush=False, autocommit=False)
    return SessionLocal


def _table_columns(conn, table: str) -> set[str]:
    rows = conn.execute(text(f"PRAGMA table_info({table})")).fetchall()
    return {str(r[1]) for r in rows}


def _table_exists(conn, table: str) -> bool:
    row = conn.execute(
        text("SELECT name FROM sqlite_master WHERE type='table' AND name=:name"),
        {"name": table},
    ).fetchone()
    return bool(row)


def _ensure_column(conn, table: str, column: str, ddl: str) -> None:
    if not _table_exists(conn, table):
        return
    if column in _table_columns(conn, table):
        return
    conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {column} {ddl}"))


def _ensure_index(conn, name: str, sql: str) -> None:
    row = conn.execute(
        text("SELECT name FROM sqlite_master WHERE type='index' AND name=:name"),
        {"name": name},
    ).fetchone()
    if row:
        return
    conn.execute(text(sql))


def _migrate_trustworthy_books_schema(engine) -> None:
    """Add trustworthy-books columns/indexes to existing finance.db files."""
    with engine.connect() as conn:
        _ensure_column(conn, "finance_accounts", "purpose", "TEXT NOT NULL DEFAULT 'operating'")
        _ensure_column(conn, "finance_accounts", "rail", "TEXT")
        _ensure_column(conn, "finance_accounts", "posted_pin_cents", "INTEGER")
        _ensure_column(conn, "finance_accounts", "posted_pin_as_of", "DATE")
        _ensure_column(conn, "finance_accounts", "available_cents", "INTEGER")
        _ensure_column(conn, "finance_accounts", "available_as_of", "DATE")

        _ensure_column(conn, "finance_transactions", "source", "TEXT DEFAULT 'import'")
        _ensure_column(conn, "finance_transactions", "movement_class", "TEXT")
        _ensure_column(conn, "finance_transactions", "movement_group_id", "TEXT")
        _ensure_column(conn, "finance_transactions", "match_hash", "TEXT")
        _ensure_column(conn, "finance_transactions", "daily_balance_cents", "INTEGER")
        _ensure_column(conn, "finance_transactions", "statement_start", "DATE")
        _ensure_column(conn, "finance_transactions", "statement_end", "DATE")
        _ensure_column(conn, "finance_transactions", "source_statement", "TEXT")

        _ensure_column(conn, "finance_recurring_series", "category_id", "TEXT")
        _ensure_column(conn, "finance_recurring_series", "movement_class", "TEXT")
        _ensure_column(conn, "finance_categorization_rules", "movement_class", "TEXT")

        if _table_exists(conn, "finance_transactions"):
            conn.execute(
                text(
                    "UPDATE finance_transactions SET source = 'import' "
                    "WHERE source IS NULL OR TRIM(source) = ''"
                )
            )
            conn.execute(
                text(
                    "UPDATE finance_transactions SET status = lower(trim(status)) "
                    "WHERE status IS NOT NULL"
                )
            )
            _ensure_index(
                conn,
                "ix_finance_tx_owner_class_date",
                "CREATE INDEX ix_finance_tx_owner_class_date "
                "ON finance_transactions (owner, movement_class, date)",
            )
            _ensure_index(
                conn,
                "ix_finance_tx_owner_group",
                "CREATE INDEX ix_finance_tx_owner_group "
                "ON finance_transactions (owner, movement_group_id)",
            )
            _ensure_index(
                conn,
                "ix_finance_tx_account_date",
                "CREATE INDEX ix_finance_tx_account_date "
                "ON finance_transactions (account_id, date)",
            )

        conn.commit()


def _merge_default_config_keys() -> None:
    path = finance_config_path()
    if not path.is_file():
        return
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return
    if not isinstance(data, dict):
        return
    changed = False
    if "transfer_day_gap" not in data:
        data["transfer_day_gap"] = 3
        changed = True
    if changed:
        path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def init_finance_db() -> None:
    """Create plugin tables if missing."""
    engine = get_engine()
    FinanceBase.metadata.create_all(bind=engine)
    _migrate_unique_dedup_index(engine)
    _migrate_trustworthy_books_schema(engine)
    _merge_default_config_keys()


def write_default_config() -> None:
    path = finance_config_path()
    if path.is_file():
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "currency": "USD",
                "default_import_preset": "auto",
                "transfer_day_gap": 3,
            },
            indent=2,
        ),
        encoding="utf-8",
    )


def reset_engine_cache() -> None:
    """Test helper — drop cached engine between test runs."""
    global _engine, SessionLocal
    if _engine is not None:
        _engine.dispose()
    _engine = None
    SessionLocal = None
