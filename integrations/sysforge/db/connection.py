"""Plugin SQLite connection helper.

Single-writer assumption: one Odysseus process owns the plugin DB.
Uses WAL + foreign_keys + busy_timeout (desktop DatabaseService parity).
Public helpers are async-friendly via asyncio.to_thread.
"""

from __future__ import annotations

import asyncio
import json
import sqlite3
from collections.abc import Callable
from pathlib import Path
from typing import Any, TypeVar

from src.plugins import registry

T = TypeVar("T")

DEFAULT_BUSY_TIMEOUT_MS = 5000


def db_path() -> Path:
    """Absolute path to the plugin Business database."""
    return registry.plugin_data_dir("sysforge") / "sysforge.db"


def _busy_timeout_ms() -> int:
    config_path = registry.plugin_data_dir("sysforge") / "config.json"
    if not config_path.is_file():
        return DEFAULT_BUSY_TIMEOUT_MS
    try:
        data = json.loads(config_path.read_text(encoding="utf-8"))
        value = data.get("busy_timeout_ms", DEFAULT_BUSY_TIMEOUT_MS)
        return int(value)
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        return DEFAULT_BUSY_TIMEOUT_MS


def apply_pragmas(conn: sqlite3.Connection, busy_timeout_ms: int | None = None) -> None:
    timeout = DEFAULT_BUSY_TIMEOUT_MS if busy_timeout_ms is None else busy_timeout_ms
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute(f"PRAGMA busy_timeout={timeout}")


def connect(path: Path | None = None) -> sqlite3.Connection:
    """Open a sync connection with desktop-parity pragmas."""
    target = path if path is not None else db_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(target), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    apply_pragmas(conn, _busy_timeout_ms())
    return conn


async def connect_async(path: Path | None = None) -> sqlite3.Connection:
    """Async open — runs connect() in a worker thread."""
    return await asyncio.to_thread(connect, path)


async def run_in_thread(fn: Callable[..., T], *args: Any, **kwargs: Any) -> T:
    """Run a blocking DB callable off the event loop."""
    return await asyncio.to_thread(fn, *args, **kwargs)
