"""SysForge Business agent tool — action registry, tiers, phases, help."""

from __future__ import annotations

from typing import Any

# Risk tiers: 0=read, 1=safe write, 2=financial/bulk, 3=destructive, 4=admin catastrophe
ACTION_TIER: dict[str, int] = {
    "action_help": 0,
    "status": 0,
    "diagnostics": 0,
    "client_list": 0,
    "client_search": 0,
    "client_recent": 0,
    "client_get": 0,
    "client_duplicates": 0,
    "client_list_invoices": 0,
    "client_merge_preview": 0,
    "client_link_dossier": 1,
    "client_unlink_dossier": 1,
    "client_create": 1,
    "client_update": 1,
    "client_touch": 1,
    "client_delete": 3,
    "client_merge": 3,
    "invoice_list": 0,
    "invoice_get": 0,
    "outstanding_list": 0,
    "invoice_price_compare": 0,
    "invoice_validate": 0,
    "invoice_preview": 0,
    "invoice_create": 1,
    "invoice_update": 1,
    "invoice_devices_get": 0,
    "invoice_devices_set": 1,
    "invoice_update_prices_preview": 0,
    "invoice_update_prices_apply": 2,
    "invoice_delete": 3,
    "invoice_save_as_new": 2,
    "invoice_accept": 2,
    "invoice_email": 3,
    "invoice_pdf_fetch": 0,
    "invoice_batch_validate": 0,
    "invoice_batch_create": 2,
    "suggest_payment_plan": 0,
    "draft_list": 0,
    "draft_get": 0,
    "draft_save": 1,
    "draft_autosave": 1,
    "draft_pin": 1,
    "draft_rename": 1,
    "draft_delete": 2,
    "draft_retention_preview": 0,
    "draft_retention_cleanup": 2,
    "payment_list": 0,
    "payment_record": 2,
    "payment_void": 3,
    "report_sales": 0,
    "report_aging": 0,
    "part_list": 0,
    "part_search": 0,
    "part_get": 0,
    "part_usage": 0,
    "part_stock_get": 0,
    "part_stock_set": 1,
    "part_price_history_list": 0,
    "part_price_history_add": 1,
    "part_create": 1,
    "part_update": 1,
    "part_delete": 3,
    "part_import": 2,
    "part_import_commit": 2,
    "part_enrich": 2,
    "part_search_rebuild": 2,
    "supplier_list": 0,
    "supplier_search": 0,
    "supplier_get": 0,
    "supplier_parts": 0,
    "supplier_create": 1,
    "supplier_update": 1,
    "supplier_delete": 3,
    "supplier_bulk_upsert": 2,
    "placeholder_list": 0,
    "placeholder_groups": 0,
    "placeholder_convert": 2,
    "placeholder_merge_preview": 0,
    "placeholder_merge": 3,
    "placeholder_bulk_convert": 2,
    "project_hub": 0,
    "project_list": 0,
    "project_get": 0,
    "project_update": 1,
    "project_status_set": 1,
    "project_notes_set": 1,
    "project_from_invoice_preflight": 0,
    "project_create_from_invoice": 1,
    "project_photo_add": 1,
    "project_photo_fetch": 0,
    "work_order_get": 0,
    "work_order_from_estimate": 1,
    "screw_map_get": 0,
    "screw_map_create": 1,
    "screw_map_image_add": 1,
    "screw_map_image_fetch": 0,
    "screw_map_screw_upsert": 1,
    "screw_map_screw_delete": 2,
    "screw_map_note_add": 1,
    "settings_get": 0,
    "settings_update": 2,
    "backup_create": 2,
    "backup_list": 0,
    "backup_restore_preview": 0,
    "backup_restore": 4,
    "companion_status": 0,
    "companion_pair": 2,
    "companion_inbox_list": 0,
    "health_digest": 0,
    "business_navigate": 0,
}

ACTION_PHASE: dict[str, int] = {
    "action_help": 0,
    "status": 0,
    "diagnostics": 1,
    "client_list": 1,
    "client_search": 1,
    "client_recent": 1,
    "client_get": 1,
    "client_duplicates": 1,
    "client_list_invoices": 1,
    "client_link_dossier": 1,
    "client_unlink_dossier": 1,
    "client_create": 1,
    "client_update": 1,
    "client_touch": 1,
    "invoice_list": 1,
    "invoice_get": 1,
    "outstanding_list": 1,
    "invoice_price_compare": 1,
    "payment_list": 1,
    "report_sales": 1,
    "part_list": 1,
    "part_search": 1,
    "part_get": 1,
    "part_usage": 1,
    "part_stock_get": 1,
    "part_price_history_list": 1,
    "part_create": 1,
    "part_update": 1,
    "supplier_list": 1,
    "supplier_search": 1,
    "supplier_get": 1,
    "supplier_parts": 1,
    "supplier_create": 1,
    "supplier_update": 1,
    "placeholder_list": 1,
    "placeholder_groups": 1,
    "invoice_validate": 2,
    "invoice_preview": 2,
    "invoice_create": 2,
    "invoice_update": 2,
    "invoice_devices_get": 2,
    "invoice_devices_set": 2,
    "invoice_update_prices_preview": 2,
    "draft_list": 2,
    "draft_get": 2,
    "draft_save": 2,
    "draft_autosave": 2,
    "draft_pin": 2,
    "draft_rename": 2,
    "part_stock_set": 2,
    "part_price_history_add": 2,
    "placeholder_convert": 2,
    "project_hub": 2,
    "project_list": 2,
    "project_get": 2,
    "project_update": 2,
    "project_status_set": 2,
    "project_notes_set": 2,
    "project_from_invoice_preflight": 2,
    "project_create_from_invoice": 2,
    "work_order_get": 2,
    "work_order_from_estimate": 2,
    "screw_map_get": 2,
    "client_merge_preview": 3,
    "client_merge": 3,
    "client_delete": 3,
    "invoice_delete": 3,
    "invoice_save_as_new": 3,
    "invoice_accept": 3,
    "invoice_email": 3,
    "invoice_update_prices_apply": 3,
    "payment_record": 3,
    "payment_void": 3,
    "part_delete": 3,
    "supplier_delete": 3,
    "placeholder_merge_preview": 3,
    "placeholder_merge": 3,
    "draft_delete": 3,
    "project_photo_add": 4,
    "project_photo_fetch": 4,
    "screw_map_create": 4,
    "screw_map_image_add": 4,
    "screw_map_image_fetch": 4,
    "screw_map_screw_upsert": 4,
    "screw_map_screw_delete": 4,
    "screw_map_note_add": 4,
    "invoice_pdf_fetch": 4,
    "part_import": 5,
    "part_import_commit": 5,
    "part_enrich": 5,
    "supplier_bulk_upsert": 5,
    "placeholder_bulk_convert": 5,
    "part_search_rebuild": 5,
    "settings_get": 6,
    "settings_update": 6,
    "backup_create": 6,
    "backup_list": 6,
    "backup_restore_preview": 6,
    "backup_restore": 6,
    "draft_retention_preview": 6,
    "draft_retention_cleanup": 6,
    "companion_status": 6,
    "companion_pair": 6,
    "companion_inbox_list": 6,
    "report_aging": 7,
    "health_digest": 7,
    "invoice_batch_validate": 7,
    "invoice_batch_create": 7,
    "suggest_payment_plan": 7,
    "business_navigate": 7,
}

ALL_ACTIONS: tuple[str, ...] = tuple(sorted(set(ACTION_TIER.keys())))

ACTION_ALIASES: dict[str, str] = {
    "clients": "client_list",
    "client": "client_get",
    "parts": "part_list",
    "suppliers": "supplier_list",
    "invoices": "invoice_list",
    "outstanding": "outstanding_list",
    "help": "action_help",
    "sales_report": "report_sales",
    "aging": "report_aging",
    "digest": "health_digest",
}

ACTION_HELP: dict[str, str] = {
    "client_search": (
        "Search clients by name, phone, or email fragment. "
        "Tier T0. Example: {\"action\":\"client_search\",\"q\":\"555\"}"
    ),
    "outstanding_list": (
        "List invoices with balance due. Tier T0. "
        "Example: {\"action\":\"outstanding_list\"}"
    ),
    "invoice_validate": (
        "Validate a DraftDocument before create. Tier T0. "
        "Always run before invoice_create."
    ),
    "invoice_create": (
        "Create invoice from validated draft. Tier T1. "
        "Run invoice_validate first."
    ),
    "client_merge": (
        "Merge duplicate clients. Tier T3. "
        "Call client_merge_preview, then ask_user with confirmation_token."
    ),
    "payment_record": (
        "Record payment on invoice. Tier T2. Requires confirmation_token."
    ),
    "part_import": (
        "Bulk import parts CSV/rows. Tier T2. "
        "Always dry_run:true first, then part_import_commit with token."
    ),
    "backup_restore": (
        "Restore database from staged ZIP. Tier T4. "
        "Requires confirmation_token and explicit user phrase."
    ),
    "health_digest": (
        "One-call shop briefing: schema, outstanding, drafts, backups. Tier T0."
    ),
    "invoice_batch_validate": (
        "Validate N client invoice drafts before batch create. Tier T0. "
        "Pass invoices[] with client_id, period or name, line_items."
    ),
    "invoice_batch_create": (
        "Create N invoices from template lines. Tier T2. "
        "dry_run:true first, then batch_id commit or dry_run:false with confirmation_token."
    ),
    "suggest_payment_plan": (
        "Advisory installment schedule for an invoice balance. Tier T0 read-only; "
        "does not persist payment plans (payment_plan_* deferred)."
    ),
    "backup_restore_preview": (
        "Read backup ZIP manifest without applying. Tier T0. Requires backup_id."
    ),
}

DOMAIN_HELP: dict[str, str] = {
    "clients": "client_search, client_get, client_create, client_update, client_merge",
    "invoices": "invoice_list, outstanding_list, invoice_validate, invoice_create, payment_record",
    "parts": "part_search, part_create, part_import, placeholder_convert",
    "projects": "project_list, project_create_from_invoice, project_photo_add",
    "admin": "settings_get, backup_create, diagnostics, companion_status",
}


def action_help_text(topic: str) -> str:
    key = topic.replace("-", "_").strip().lower()
    if key in ACTION_HELP:
        tier = ACTION_TIER.get(key, 0)
        return f"**{key}** (T{tier})\n\n{ACTION_HELP[key]}"
    if key in DOMAIN_HELP:
        return f"**{topic} domain**\n\nActions: {DOMAIN_HELP[key]}"
    if key in ACTION_TIER:
        tier = ACTION_TIER[key]
        phase = ACTION_PHASE.get(key, "?")
        return f"**{key}** — tier T{tier}, ships phase {phase}. No extended help yet."
    return f"Unknown topic '{topic}'. Try a domain: clients, invoices, parts, projects, admin."


def not_implemented_message(action: str) -> str:
    phase = ACTION_PHASE.get(action, 99)
    return (
        f"Action '{action}' is reserved for phase {phase}. "
        f"Use action_help or check the SysForge AI phase plan."
    )
