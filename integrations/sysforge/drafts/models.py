"""DraftData / DraftItem helpers — camelCase JSON on disk (desktop parity)."""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from typing import Any

from integrations.sysforge.db import utc

AUTOSAVE_NAME = "AUTOSAVE"
UNKNOWN_CLIENT = "Unknown Client"
UNTITLED_DRAFT = "Untitled Draft"


def _parse_dt(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return utc.to_utc(value) if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if not isinstance(value, str):
        return None
    text = value.strip()
    if not text:
        return None
    try:
        if "T" in text or text.endswith("Z"):
            raw = text.replace("Z", "+00:00")
            dt = datetime.fromisoformat(raw)
            return utc.to_utc(dt)
        return utc.parse_storage(text)
    except (ValueError, TypeError):
        return None


def _format_dt(dt: datetime | None) -> str | None:
    if dt is None:
        return None
    aware = utc.to_utc(dt)
    return aware.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


def _local_date_time_parts(created_at: datetime | None) -> tuple[str, str]:
    """Local MM/dd/yyyy and HH:mm for DRAFT-07 naming."""
    if created_at is None:
        created_at = utc.utc_now()
    local = utc.to_local(utc.to_utc(created_at))
    return local.strftime("%m/%d/%Y"), local.strftime("%H:%M")


def generate_default_name_from_draft(draft: dict[str, Any]) -> str:
    """Service normalize path: Unknown Client when client missing (desktop DraftService)."""
    created = _parse_dt(draft.get("createdAt")) or utc.utc_now()
    date_s, time_s = _local_date_time_parts(created)
    client = (draft.get("clientName") or "").strip() or UNKNOWN_CLIENT
    return f"{client} - {date_s} {time_s}"


def display_name(draft: dict[str, Any]) -> str:
    """UI display: Name, else client + time, else Untitled Draft + time."""
    name = (draft.get("name") or "").strip()
    if name:
        return name
    created = _parse_dt(draft.get("createdAt")) or utc.utc_now()
    date_s, time_s = _local_date_time_parts(created)
    client = (draft.get("clientName") or "").strip()
    if client:
        return f"{client} - {date_s} {time_s}"
    return f"{UNTITLED_DRAFT} - {date_s} {time_s}"


def normalize_draft_name(draft: dict[str, Any]) -> None:
    """Ensure name is non-empty on write (Unknown Client / client + date time)."""
    if not (draft.get("name") or "").strip():
        draft["name"] = generate_default_name_from_draft(draft)


def empty_item() -> dict[str, Any]:
    return {
        "partId": None,
        "partName": "",
        "sku": None,
        "quantity": 1,
        "unitPrice": 0,
        "discountType": "None",
        "discountValue": 0,
        "isTaxable": True,
        "itemType": "Part",
        "sortOrder": 0,
    }


def empty_draft() -> dict[str, Any]:
    now = utc.utc_now()
    return {
        "id": "",
        "name": "",
        "createdAt": _format_dt(now),
        "lastModifiedAt": _format_dt(now),
        "isAutosave": False,
        "invoiceWasSaved": False,
        "pinned": False,
        "clientId": None,
        "clientName": None,
        "clientPhone": None,
        "clientEmail": None,
        "items": [],
        "includeTax": True,
        "includeShipping": True,
        "taxRate": 7.75,
        "shippingRate": 0,
        "partsSubtotal": 0,
        "laborCost": 0,
        "shippingCost": 0,
        "taxAmount": 0,
        "finalTotal": 0,
    }


def _coerce_item(raw: Any, index: int) -> dict[str, Any]:
    base = empty_item()
    if not isinstance(raw, dict):
        base["sortOrder"] = index
        return base
    item = {**base, **{k: v for k, v in raw.items() if k in base or k == "sku"}}
    # Accept desktop SKU casing if present
    if "SKU" in raw and item.get("sku") is None:
        item["sku"] = raw["SKU"]
    item["sortOrder"] = int(item.get("sortOrder") if item.get("sortOrder") is not None else index)
    try:
        item["quantity"] = float(item.get("quantity", 1))
    except (TypeError, ValueError):
        item["quantity"] = 1.0
    try:
        item["unitPrice"] = float(item.get("unitPrice", 0))
    except (TypeError, ValueError):
        item["unitPrice"] = 0.0
    try:
        item["discountValue"] = float(item.get("discountValue", 0))
    except (TypeError, ValueError):
        item["discountValue"] = 0.0
    item["partName"] = str(item.get("partName") or "")
    item["discountType"] = str(item.get("discountType") or "None")
    item["itemType"] = str(item.get("itemType") or "Part")
    item["isTaxable"] = bool(item.get("isTaxable", True))
    return item


def coerce_draft(raw: Any) -> dict[str, Any]:
    """Normalize a dict into DraftData shape (camelCase keys)."""
    base = empty_draft()
    if not isinstance(raw, dict):
        return base
    draft = deepcopy(base)
    for key in (
        "id",
        "name",
        "clientName",
        "clientPhone",
        "clientEmail",
    ):
        if key in raw and raw[key] is not None:
            draft[key] = raw[key]
    draft["id"] = str(draft.get("id") or "")
    draft["name"] = str(draft.get("name") or "")

    created = _parse_dt(raw.get("createdAt"))
    modified = _parse_dt(raw.get("lastModifiedAt"))
    if created:
        draft["createdAt"] = _format_dt(created)
    if modified:
        draft["lastModifiedAt"] = _format_dt(modified)

    draft["isAutosave"] = bool(raw.get("isAutosave", False))
    draft["invoiceWasSaved"] = bool(raw.get("invoiceWasSaved", False))
    draft["pinned"] = bool(raw.get("pinned", False))

    if "clientId" in raw:
        cid = raw["clientId"]
        if cid is None or cid == "":
            draft["clientId"] = None
        else:
            try:
                draft["clientId"] = int(cid)
            except (TypeError, ValueError):
                draft["clientId"] = None

    for key in (
        "includeTax",
        "includeShipping",
    ):
        if key in raw:
            draft[key] = bool(raw[key])

    for key in (
        "taxRate",
        "shippingRate",
        "partsSubtotal",
        "laborCost",
        "shippingCost",
        "taxAmount",
        "finalTotal",
    ):
        if key in raw and raw[key] is not None:
            try:
                draft[key] = float(raw[key])
            except (TypeError, ValueError):
                pass

    items_raw = raw.get("items")
    if isinstance(items_raw, list):
        draft["items"] = [_coerce_item(it, i) for i, it in enumerate(items_raw)]
    else:
        draft["items"] = []

    return draft


def list_item_dto(draft: dict[str, Any]) -> dict[str, Any]:
    """API list row — no filesystem paths."""
    items = draft.get("items") or []
    return {
        "id": draft.get("id") or "",
        "name": draft.get("name") or "",
        "displayName": display_name(draft),
        "createdAt": draft.get("createdAt"),
        "lastModifiedAt": draft.get("lastModifiedAt"),
        "isAutosave": bool(draft.get("isAutosave")),
        "invoiceWasSaved": bool(draft.get("invoiceWasSaved")),
        "pinned": bool(draft.get("pinned")),
        "clientId": draft.get("clientId"),
        "clientName": draft.get("clientName"),
        "clientPhone": draft.get("clientPhone"),
        "itemCount": len(items) if isinstance(items, list) else 0,
        "finalTotal": draft.get("finalTotal", 0),
        "partsSubtotal": draft.get("partsSubtotal", 0),
    }


def parse_last_modified(draft: dict[str, Any]) -> datetime:
    dt = _parse_dt(draft.get("lastModifiedAt"))
    if dt is not None:
        return dt
    return datetime.min.replace(tzinfo=timezone.utc)
