"""Append-only JSONL performance event emitter."""

from __future__ import annotations

import json
import logging
import os
import threading
import time
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from core.constants import DATA_DIR
from core.perf_context import get_correlation

logger = logging.getLogger(__name__)

_SCHEMA_VERSION = 1
_lock = threading.Lock()
_sink_path: Optional[str] = None
_ring: list[Dict[str, Any]] = []
_RING_MAX = 2000
_installed = False


def perf_enabled() -> bool:
    return os.getenv("ODYSSEUS_PERF", "true").lower() not in ("0", "false", "no", "off")


def _deployment_mode() -> str:
    if os.path.exists("/.dockerenv") or os.getenv("ODYSSEUS_IN_DOCKER") == "1":
        return "docker-compose"
    if getattr(__import__("sys"), "frozen", False):
        return "portable"
    return "native"


def get_sink_path() -> str:
    global _sink_path
    if _sink_path is None:
        log_dir = os.path.join(DATA_DIR, "logs")
        os.makedirs(log_dir, exist_ok=True)
        _sink_path = os.path.join(log_dir, "perf.jsonl")
    return _sink_path


def emit(event: str, **fields: Any) -> None:
    """Write a performance event to perf.jsonl and the in-memory ring."""
    if not perf_enabled():
        return
    try:
        row: Dict[str, Any] = {
            "v": _SCHEMA_VERSION,
            "event": event,
            "ts": datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z"),
            "deployment": _deployment_mode(),
        }
        row.update(get_correlation())
        for key, val in fields.items():
            if val is not None:
                row[key] = val
        line = json.dumps(row, default=str, ensure_ascii=False) + "\n"
        with _lock:
            _ring.append(row)
            if len(_ring) > _RING_MAX:
                del _ring[: len(_ring) - _RING_MAX]
            try:
                with open(get_sink_path(), "a", encoding="utf-8") as f:
                    f.write(line)
            except OSError as e:
                logger.debug("perf emit write failed: %s", e)
    except Exception as e:
        logger.debug("perf emit failed: %s", e)


def tail_events(
    limit: int = 100,
    *,
    event_prefix: Optional[str] = None,
    since_ts: Optional[str] = None,
) -> list[Dict[str, Any]]:
    """Return recent events from ring buffer, optionally filtered."""
    limit = max(1, min(limit, 1000))
    with _lock:
        rows = list(_ring)
    if event_prefix:
        rows = [r for r in rows if str(r.get("event", "")).startswith(event_prefix)]
    if since_ts:
        rows = [r for r in rows if str(r.get("ts", "")) >= since_ts]
    return rows[-limit:]


def read_file_tail(limit: int = 200) -> list[Dict[str, Any]]:
    """Read last N JSON lines from perf.jsonl on disk."""
    limit = max(1, min(limit, 2000))
    path = get_sink_path()
    if not os.path.exists(path):
        return []
    try:
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            lines = f.readlines()
        out = []
        for line in lines[-limit:]:
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                continue
        return out
    except OSError:
        return []


def timed_emit(event_start: str, event_end: str, **start_fields: Any):
    """Context manager that emits start/end events with duration_ms."""

    class _Timer:
        def __enter__(self):
            self._t0 = time.perf_counter()
            emit(event_start, **start_fields)
            return self

        def __exit__(self, exc_type, exc, tb):
            duration_ms = round((time.perf_counter() - self._t0) * 1000, 2)
            status = "error" if exc_type else "ok"
            emit(
                event_end,
                duration_ms=duration_ms,
                status=status,
                error=str(exc) if exc else None,
                **start_fields,
            )
            return False

    return _Timer()
