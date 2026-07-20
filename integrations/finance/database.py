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


def init_finance_db() -> None:
    """Create plugin tables if missing."""
    engine = get_engine()
    FinanceBase.metadata.create_all(bind=engine)
    _migrate_unique_dedup_index(engine)


def write_default_config() -> None:
    path = finance_config_path()
    if path.is_file():
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({"currency": "USD", "default_import_preset": "auto"}, indent=2),
        encoding="utf-8",
    )


def reset_engine_cache() -> None:
    """Test helper — drop cached engine between test runs."""
    global _engine, SessionLocal
    if _engine is not None:
        _engine.dispose()
    _engine = None
    SessionLocal = None
