"""
tool_implementations.py

Extracted tool implementation functions (do_* and helpers) from agent_tools.py.
These handle the actual execution logic for each tool type.
"""

import logging
from datetime import datetime
from typing import Dict, Optional

from src.tool_utils import get_mcp_manager  # re-exported: tests patch src.tool_implementations.get_mcp_manager

# System-domain tools were extracted to src/tools/system.py (slice 1,
# #4082/#4071); the admin manage_* tools live in src/agent_tools/admin_tools
# after the upstream registry migration (#3629). Re-imported here so this
# module stays a working facade.
from src.tools.system import (  # noqa: F401
    do_manage_skills, _skill_dump, do_manage_tasks,
    do_api_call, do_app_api,
    _APP_API_BLOCKLIST_PREFIXES, _APP_API_BLOCKLIST_METHOD_PATH,
)
# Admin manage_* tools (endpoints/mcp/webhooks/tokens/settings) live in
# src/agent_tools/admin_tools after the upstream registry migration (#3629).
# Re-exported lazily via __getattr__: src.agent_tools.__init__ imports this
# facade at top level, so a eager `from src.agent_tools.admin_tools import`
# here would re-enter the partially-initialized agent_tools package (circular).
_ADMIN_TOOL_SYMBOLS = (
    "do_manage_endpoints", "do_manage_mcp", "do_manage_webhooks",
    "do_manage_tokens", "do_manage_settings",
    "_MCP_DENIED_COMMANDS", "_validate_mcp_command", "_mcp_allowed_commands",
)


def __getattr__(name):
    if name in _ADMIN_TOOL_SYMBOLS:
        from src.agent_tools import admin_tools
        return getattr(admin_tools, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
# Cookbook (model serving) domain extracted to src/tools/cookbook.py
# (slice 1, #4082/#4071). Re-imported here so this module stays a working
# facade. cookbook.py pulls `_internal_headers` / `_INTERNAL_BASE` back
# function-locally from this facade (which re-exports them from _common).
from src.tools.cookbook import (  # noqa: F401
    do_download_model, do_serve_model, do_list_served_models,
    do_stop_served_model, do_tail_serve_output, do_list_downloads,
    do_cancel_download, do_search_hf_models, do_adopt_served_model,
    do_list_cookbook_servers, do_list_serve_presets, do_serve_preset,
    do_list_cached_models,
    _cookbook_servers, _resolve_cookbook_host, _cookbook_env_for_host,
    _infer_serve_port, _infer_serve_host, _ensure_served_endpoint,
    _cookbook_register_task, _cookbook_apply_retry_suggestion,
    _scan_running_model_processes, _cookbook_kill_session,
    _MODEL_PROCESS_PATTERNS,
    _string_arg, _validate_cookbook_ssh_target,
)
# Search domain extracted to src/tools/search.py (slice 1, #4082/#4071).
# Re-imported here so this module stays a working facade.
from src.tools.search import do_search_chats  # noqa: F401
# Notes domain extracted to src/tools/notes.py (slice 1, #4082/#4071).
from src.tools.notes import do_manage_notes  # noqa: F401
# Calendar domain extracted to src/tools/calendar.py (slice 1, #4082/#4071).
from src.tools.calendar import do_manage_calendar  # noqa: F401
from src.tools.finance import do_manage_finance  # noqa: F401
# Image domain extracted to src/tools/image.py (slice 1, #4082/#4071).
from src.tools.image import do_edit_image  # noqa: F401
# Research domain extracted to src/tools/research.py (slice 1, #4082/#4071).
from src.tools.research import do_manage_research, do_trigger_research  # noqa: F401
# Contacts domain extracted to src/tools/contacts.py (slice 1, #4082/#4071).
from src.tools.contacts import do_resolve_contact, do_manage_contact  # noqa: F401
# Vault domain extracted to src/tools/vault.py (slice 1, #4082/#4071).
from src.tools.vault import (  # noqa: F401
    _load_vault_config, _run_bw,
    do_vault_search, do_vault_get, do_vault_unlock,
)
# Shared helpers live in src/tools/_common.py. Re-exported here so the
# function-local `from src.tool_implementations import _INTERNAL_BASE` (and
# friends) used by domain files still resolve through this facade.
from src.tools._common import _parse_tool_args, _INTERNAL_BASE, _internal_headers  # noqa: F401

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Active email state
# ---------------------------------------------------------------------------

# When the user has an email reader window open, the frontend tells the
# backend about it on each chat submit. Email tools can resolve "this email"
# without guessing a UID. Cleared between requests by chat_routes.
_active_email_ref: Optional[Dict[str, str]] = None


def set_active_email(uid: Optional[str], folder: Optional[str] = None, account: Optional[str] = None,
                     subject: Optional[str] = None, sender: Optional[str] = None) -> None:
    """Stash the email currently open in the UI. None clears it."""
    global _active_email_ref
    if not uid:
        _active_email_ref = None
        return
    _active_email_ref = {
        "uid": str(uid),
        "folder": str(folder or "INBOX"),
        "account": str(account or ""),
        "subject": str(subject or ""),
        "from": str(sender or ""),
    }


def get_active_email() -> Optional[Dict[str, str]]:
    return _active_email_ref


def clear_active_email() -> None:
    global _active_email_ref
    _active_email_ref = None


def _format_untrusted_email_block(label: str, body: str) -> str:
    from src.prompt_security import UNTRUSTED_CONTEXT_HEADER
    text = body or ""
    return (
        f"{UNTRUSTED_CONTEXT_HEADER}\n"
        f"Source: {label}\n\n"
        "<<<UNTRUSTED_SOURCE_DATA>>>\n"
        f"{text}\n"
        "<<<END_UNTRUSTED_SOURCE_DATA>>>"
    )


async def do_read_local_emails(content: str, owner: Optional[str] = None) -> Dict:
    """Query the local email mirror (list or full body by row id)."""
    import asyncio
    from routes.calendar_routes import parse_due_for_user
    from routes.email_local_store import (
        get_local_email,
        query_local_emails,
        resolve_account_id,
    )

    try:
        args = _parse_tool_args(content)
    except ValueError:
        return {"error": "Invalid JSON arguments", "exit_code": 1}

    folder = args.get("folder") or "INBOX"
    account_sel = args.get("account")
    account_id = resolve_account_id(account_sel, owner=owner or "") if account_sel else None
    if account_sel and not account_id:
        return {"error": f"Email account not found for {account_sel!r}", "exit_code": 1}

    if args.get("full"):
        if args.get("id") is None:
            return {"error": "full=true requires id", "exit_code": 1}
        try:
            row_id = int(args["id"])
        except (TypeError, ValueError):
            return {"error": f"Invalid id: {args.get('id')!r}", "exit_code": 1}
        row = await asyncio.to_thread(get_local_email, owner or "", row_id)
        if not row:
            return {"error": f"Local email id {args['id']} not found", "exit_code": 1}
        untrusted_lines = [
            f"Local id: {row['id']}",
            f"UID: {row['uid']}",
            f"Account id: {row['account_id']}",
            f"Folder: {row['folder']}",
            f"Subject: {row.get('subject', '')}",
            f"From: {row.get('from_name', '')} <{row.get('from_addr', '')}>",
            f"Date: {row.get('date_raw', '')}",
        ]
        if row.get("attachments"):
            untrusted_lines.append(f"\nAttachments ({len(row['attachments'])}):")
            for a in row["attachments"]:
                extra = ""
                if a.get("skipped_reason"):
                    extra = f" [skipped: {a['skipped_reason']}]"
                elif a.get("local_path"):
                    extra = f" → {a['local_path']}"
                untrusted_lines.append(
                    f"  - [{a.get('idx')}] {a.get('filename')} "
                    f"({a.get('content_type')}, {a.get('size', 0)} bytes){extra}"
                )
        body_parts = []
        if row.get("body_text"):
            body_parts.append(row["body_text"])
        if row.get("body_html") and row.get("body_html") not in (row.get("body_text") or ""):
            body_parts.append(f"[HTML body]\n{row['body_html']}")
        if body_parts:
            untrusted_lines.append("")
            untrusted_lines.append("\n\n---\n\n".join(body_parts))
        output = _format_untrusted_email_block(
            "local email",
            "\n".join(untrusted_lines),
        )
        return {"output": output, "exit_code": 0}

    try:
        limit = max(1, min(500, int(args.get("limit") or 10)))
    except (TypeError, ValueError):
        return {"error": f"Invalid limit: {args.get('limit')!r}", "exit_code": 1}
    try:
        offset = max(0, int(args.get("offset") or 0))
    except (TypeError, ValueError):
        return {"error": f"Invalid offset: {args.get('offset')!r}", "exit_code": 1}
    since_epoch = None
    until_epoch = None
    if args.get("since"):
        try:
            since_epoch = datetime.fromisoformat(parse_due_for_user(str(args["since"]))).timestamp()
        except Exception as e:
            return {"error": f"Invalid since date: {e}", "exit_code": 1}
    if args.get("until"):
        try:
            until_epoch = datetime.fromisoformat(parse_due_for_user(str(args["until"]))).timestamp()
        except Exception as e:
            return {"error": f"Invalid until date: {e}", "exit_code": 1}

    rows = await asyncio.to_thread(
        query_local_emails,
        owner or "",
        account_id=account_id,
        folder=folder,
        limit=limit,
        offset=offset,
        since=since_epoch,
        until=until_epoch,
    )
    if not rows:
        return {"output": "No local emails found for that query.", "exit_code": 0}
    list_lines = []
    for i, r in enumerate(rows, 1):
        read_mark = "read" if r.get("is_read") else "unread"
        att = " 📎" if r.get("has_attachments") else ""
        list_lines.append(
            f"{i}. [id={r['id']}] UID {r['uid']} account={r.get('account_id')} — "
            f"{r.get('subject', '(no subject)')} "
            f"— {r.get('from_name') or r.get('from_addr')} — {r.get('date_raw', '')} ({read_mark}){att}"
        )
        if r.get("snippet"):
            list_lines.append(f"   {r['snippet'][:200]}")
    header = f"Local emails ({folder}, limit={limit}, offset={offset}):"
    output = header + "\n" + _format_untrusted_email_block(
        "local email list",
        "\n".join(list_lines),
    )
    output += "\n\nUse read_local_emails with full=true and id=<local id> for full body + attachment paths."
    return {"output": output, "exit_code": 0}


async def do_sync_local_emails(content: str, owner: Optional[str] = None) -> Dict:
    """Trigger a local email mirror sync on demand."""
    import asyncio
    from routes.email_local_store import resolve_account_id, sync_all

    try:
        args = _parse_tool_args(content)
    except ValueError:
        return {"error": "Invalid JSON arguments", "exit_code": 1}

    account_sel = args.get("account")
    account_id = resolve_account_id(account_sel, owner=owner or "") if account_sel else None
    if account_sel and not account_id:
        return {"error": f"Email account not found for {account_sel!r}", "exit_code": 1}
    accounts = [account_id] if account_id else None
    full = bool(args.get("full", False))
    result = await asyncio.to_thread(sync_all, owner or "", accounts=accounts, full=full)
    if not result.get("ok"):
        return {"error": result.get("error") or "sync failed", "exit_code": 1}
    lines = ["Local email sync results:"]
    for item in result.get("results") or []:
        if item.get("error"):
            lines.append(f"- {item.get('account', item.get('account_id'))}/{item.get('folder')}: ERROR {item['error']}")
        else:
            lines.append(
                f"- {item.get('account', item.get('account_id'))}/{item.get('folder')}: "
                f"+{item.get('new', 0)} new, {item.get('backfilled', 0)} backfilled, "
                f"{item.get('flags_updated', 0)} flags updated, "
                f"backfill_complete={item.get('backfill_complete', False)}"
            )
    return {"output": "\n".join(lines), "exit_code": 0}
