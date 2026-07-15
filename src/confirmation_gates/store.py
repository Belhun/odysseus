"""Durable store for pending user confirmations (token mint → approve → consume)."""

from __future__ import annotations

import json
import logging
import os
import threading
import time
from typing import Any, Optional

from core.atomic_io import atomic_write_json
from src.constants import DATA_DIR

logger = logging.getLogger(__name__)

CONFIRMATION_PENDING_FILE = os.path.join(DATA_DIR, "confirmation_pending.json")
_LOCK = threading.Lock()


def _load() -> dict[str, Any]:
    if not os.path.isfile(CONFIRMATION_PENDING_FILE):
        return {"tokens": {}}
    try:
        with open(CONFIRMATION_PENDING_FILE, encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict) and isinstance(data.get("tokens"), dict):
            return data
    except Exception as exc:
        logger.warning("confirmation_pending load failed: %s", exc)
    return {"tokens": {}}


def _save(data: dict[str, Any]) -> None:
    atomic_write_json(CONFIRMATION_PENDING_FILE, data, indent=2)


def _prune_expired(tokens: dict[str, Any]) -> None:
    now = time.time()
    expired = [tok for tok, rec in tokens.items() if float(rec.get("expires_at") or 0) <= now]
    for tok in expired:
        tokens.pop(tok, None)


def put_record(token: str, record: dict[str, Any]) -> None:
    with _LOCK:
        data = _load()
        tokens = data.setdefault("tokens", {})
        _prune_expired(tokens)
        tokens[token] = record
        _save(data)


def get_record(token: str) -> Optional[dict[str, Any]]:
    with _LOCK:
        data = _load()
        tokens = data.get("tokens") or {}
        _prune_expired(tokens)
        rec = tokens.get(token)
        if rec and float(rec.get("expires_at") or 0) <= time.time():
            tokens.pop(token, None)
            _save(data)
            return None
        return rec


def update_record(token: str, **fields: Any) -> Optional[dict[str, Any]]:
    with _LOCK:
        data = _load()
        tokens = data.get("tokens") or {}
        _prune_expired(tokens)
        rec = tokens.get(token)
        if not rec:
            return None
        rec.update(fields)
        tokens[token] = rec
        _save(data)
        return rec


def delete_record(token: str) -> None:
    with _LOCK:
        data = _load()
        tokens = data.get("tokens") or {}
        if token in tokens:
            tokens.pop(token, None)
            _save(data)


def reset_store_for_tests() -> None:
    """Test helper — clear all pending confirmations."""
    with _LOCK:
        if os.path.isfile(CONFIRMATION_PENDING_FILE):
            os.remove(CONFIRMATION_PENDING_FILE)
