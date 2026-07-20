"""Compose health_digest from existing SysForge endpoints."""

from __future__ import annotations

from typing import Any

import httpx

from src.tools._common import _INTERNAL_BASE, _internal_headers

_PREFIX = "/api/sysforge"


async def _get(path: str, owner: str) -> dict[str, Any]:
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.get(
            f"{_INTERNAL_BASE}{path}",
            headers=_internal_headers(owner=owner),
        )
    if resp.status_code >= 400:
        return {"error": resp.status_code}
    try:
        return resp.json()
    except Exception:
        return {}


async def compose_health_digest(owner: str) -> dict[str, Any]:
    sections: dict[str, str] = {}
    status = await _get(f"{_PREFIX}/status", owner)
    if status.get("schema"):
        sections["schema"] = f"migration {status['schema'].get('latest_id', '?')}"
    outstanding = await _get(f"{_PREFIX}/invoices/outstanding", owner)
    invs = outstanding.get("invoices") or []
    total = sum(int(i.get("balance_cents") or i.get("outstanding_cents") or 0) for i in invs)
    sections["outstanding"] = f"{len(invs)} invoices, ${total/100:,.2f} due"
    drafts = await _get(f"{_PREFIX}/drafts", owner)
    draft_rows = drafts if isinstance(drafts, list) else drafts.get("drafts") or []
    sections["drafts"] = f"{len(draft_rows)} open drafts"
    placeholders = await _get(f"{_PREFIX}/placeholders", owner)
    ph = placeholders if isinstance(placeholders, list) else placeholders.get("placeholders") or []
    sections["placeholders"] = f"{len(ph)} in queue"
    backups = await _get(f"{_PREFIX}/backup/list", owner)
    blist = backups.get("backups") or []
    if blist:
        latest = blist[0]
        sections["backup"] = f"latest {latest.get('id', '?')} at {latest.get('created_at', '?')}"
    else:
        sections["backup"] = "no backups yet"
    companion = await _get(f"{_PREFIX}/companion/status", owner)
    sections["companion"] = companion.get("summary") or ("paired" if companion.get("paired") else "not paired")
    inbox = await _get(f"{_PREFIX}/companion/inbox", owner)
    inbox_rows = inbox.get("items") or inbox.get("inbox") or []
    if inbox_rows:
        sections["companion_inbox"] = f"{len(inbox_rows)} pending uploads"
    return {"sections": sections, "raw": {"status": status, "outstanding_count": len(invs)}}
