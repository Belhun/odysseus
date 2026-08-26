"""Single-use PhoneApp setup codes (QR carries code, not the finance token)."""

from __future__ import annotations

import secrets
import time
from dataclasses import dataclass
from threading import Lock

_CODE_TTL_SECONDS = 300
_MAX_CODES = 64


@dataclass
class _PendingSetup:
    token: str
    user: str
    url: str
    expires_at: float


_lock = Lock()
_pending: dict[str, _PendingSetup] = {}


def mint_setup_code(*, token: str, user: str, url: str) -> str:
    """Return a short-lived code for odyphone://setup?code=..."""
    code = secrets.token_urlsafe(16)
    now = time.time()
    with _lock:
        expired = [k for k, v in _pending.items() if v.expires_at <= now]
        for k in expired:
            _pending.pop(k, None)
        while len(_pending) >= _MAX_CODES:
            _pending.pop(next(iter(_pending)))
        _pending[code] = _PendingSetup(
            token=token,
            user=user,
            url=url.rstrip("/"),
            expires_at=now + _CODE_TTL_SECONDS,
        )
    return code


def exchange_setup_code(code: str) -> dict | None:
    """Consume a setup code and return token metadata, or None if invalid/expired."""
    key = (code or "").strip()
    if not key:
        return None
    now = time.time()
    with _lock:
        entry = _pending.pop(key, None)
    if entry is None or entry.expires_at <= now:
        return None
    return {
        "token": entry.token,
        "user": entry.user,
        "url": entry.url,
    }
