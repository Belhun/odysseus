"""Isolated SQLite database for the Finance plugin."""

from __future__ import annotations

import json
from pathlib import Path

from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

from integrations.finance.models import FinanceBase, FinanceCategory
from integrations.finance.services.categories import dedupe_categories
from src.plugins.registry import plugin_data_dir


def finance_db_path() -> Path:
    return plugin_data_dir("finance") / "finance.db"


def finance_config_path() -> Path:
    return plugin_data_dir("finance") / "config.json"


_engine = None
SessionLocal = None


def _sqlite_url(path: Path) -> str:
    return f"sqlite:///{path.as_posix()}"


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
        def _set_sqlite_pragma(dbapi_conn, _connection_record):
            cursor = dbapi_conn.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()

    return _engine


def get_session_factory():
    global SessionLocal
    if SessionLocal is None:
        SessionLocal = sessionmaker(bind=get_engine(), autoflush=False, autocommit=False)
    return SessionLocal


def init_finance_db() -> None:
    """Create plugin tables if missing."""
    FinanceBase.metadata.create_all(bind=get_engine())
    db = get_session_factory()()
    try:
        owners = [row[0] for row in db.query(FinanceCategory.owner).distinct().all()]
        for owner in owners:
            dedupe_categories(db, owner)
    finally:
        db.close()


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
