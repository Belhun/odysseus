"""In-memory upload staging for agent workspace files → upload_token."""

from __future__ import annotations

import mimetypes
import secrets
import time
from pathlib import Path
from typing import Any, Dict, Optional

from src.tools._common import _parse_tool_args

_MAX_BYTES = 25 * 1024 * 1024
_TTL_SECONDS = 3600
_store: dict[str, dict[str, Any]] = {}


def _purge_expired() -> None:
    now = time.time()
    expired = [k for k, v in _store.items() if v.get("expires_at", 0) < now]
    for k in expired:
        _store.pop(k, None)


def stage_file(
    path: str,
    *,
    purpose: str = "generic",
    owner: Optional[str] = None,
) -> dict[str, Any]:
    _purge_expired()
    p = Path(path).expanduser()
    if not p.is_file():
        raise FileNotFoundError(f"File not found: {path}")
    size = p.stat().st_size
    if size > _MAX_BYTES:
        raise ValueError(f"File exceeds {_MAX_BYTES} byte staging limit")
    data = p.read_bytes()
    token = secrets.token_urlsafe(24)
    mime, _ = mimetypes.guess_type(p.name)
    entry = {
        "token": token,
        "filename": p.name,
        "data": data,
        "size_bytes": size,
        "mime_type": mime or "application/octet-stream",
        "purpose": purpose,
        "owner": owner or "",
        "expires_at": time.time() + _TTL_SECONDS,
    }
    _store[token] = entry
    return {
        "upload_token": token,
        "filename": p.name,
        "size_bytes": size,
        "mime_type": entry["mime_type"],
        "purpose": purpose,
        "expires_at": int(entry["expires_at"]),
    }


def consume_staged(token: str, *, owner: Optional[str] = None) -> dict[str, Any]:
    _purge_expired()
    entry = _store.get(token)
    if not entry:
        raise LookupError("Upload token expired or invalid")
    if owner and entry.get("owner") and entry["owner"] != owner:
        raise PermissionError("Upload token owner mismatch")
    return entry


def pop_staged(token: str, *, owner: Optional[str] = None) -> dict[str, Any]:
    entry = consume_staged(token, owner=owner)
    _store.pop(token, None)
    return entry


def reset_staging_for_tests() -> None:
    _store.clear()


async def do_stage_upload(content: str, owner: Optional[str] = None, session_id: Optional[str] = None) -> Dict:
    try:
        args = _parse_tool_args(content)
    except ValueError:
        return {"error": "Invalid JSON arguments", "exit_code": 1}

    path = (args.get("path") or "").strip()
    if not path:
        return {"error": "stage_upload requires path (workspace file)", "exit_code": 1}
    purpose = (args.get("purpose") or "generic").strip()
    try:
        meta = stage_file(path, purpose=purpose, owner=owner)
    except FileNotFoundError as exc:
        return {"error": str(exc), "exit_code": 1}
    except ValueError as exc:
        return {"error": str(exc), "exit_code": 1}

    return {
        "response": (
            f"Staged {meta['filename']} ({meta['size_bytes']} bytes). "
            f"Use upload_token in manage_sysforge commit action."
        ),
        "data": meta,
        "exit_code": 0,
    }
