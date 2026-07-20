"""SysForge confirmation gate validators."""

from __future__ import annotations

from typing import Any, Optional


def _match_id(payload: dict, tool_args: dict, key: str) -> Optional[str]:
    expected = payload.get(key)
    actual = tool_args.get(key)
    if expected is not None and actual is not None and str(expected) != str(actual):
        return f"Confirmed {key} does not match tool call"
    return None


def _validate_generic(payload: dict[str, Any], tool_args: dict[str, Any]) -> Optional[str]:
    for key in ("client_id", "invoice_id", "part_id", "supplier_id", "payment_id", "batch_id"):
        err = _match_id(payload, tool_args, key)
        if err:
            return err
    if payload.get("action") and tool_args.get("action") and payload["action"] != tool_args["action"]:
        return "Confirmed action does not match tool call"
    return None


def _validate_client_merge(payload: dict[str, Any], tool_args: dict[str, Any]) -> Optional[str]:
    for key in ("survivor_id", "loser_id"):
        err = _match_id(payload, tool_args, key)
        if err:
            return err
    return None


def _validate_payment_record(payload: dict[str, Any], tool_args: dict[str, Any]) -> Optional[str]:
    err = _match_id(payload, tool_args, "invoice_id")
    if err:
        return err
    if payload.get("amount_cents") is not None:
        if int(payload["amount_cents"]) != int(tool_args.get("amount_cents") or 0):
            return "Confirmed payment amount does not match"
    return None


GATED_ACTIONS = {
    "payment_record": _validate_payment_record,
    "payment_void": _validate_generic,
    "client_merge": _validate_client_merge,
    "client_delete": _validate_generic,
    "invoice_delete": _validate_generic,
    "invoice_email": _validate_generic,
    "invoice_accept": _validate_generic,
    "invoice_save_as_new": _validate_generic,
    "invoice_update_prices_apply": _validate_generic,
    "part_delete": _validate_generic,
    "supplier_delete": _validate_generic,
    "placeholder_merge": _validate_generic,
    "draft_delete": _validate_generic,
    "settings_update": _validate_generic,
    "backup_create": _validate_generic,
    "backup_restore": _validate_generic,
    "companion_pair": _validate_generic,
    "draft_retention_cleanup": _validate_generic,
    "part_import": _validate_generic,
    "part_import_commit": _validate_generic,
    "part_enrich": _validate_generic,
    "supplier_bulk_upsert": _validate_generic,
    "placeholder_bulk_convert": _validate_generic,
    "part_search_rebuild": _validate_generic,
    "screw_map_screw_delete": _validate_generic,
    "invoice_batch_create": _validate_generic,
    "placeholder_convert": _validate_generic,
}
