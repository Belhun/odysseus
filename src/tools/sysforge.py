"""SysForge Business agent tool — shop loop via /api/sysforge loopback."""

from __future__ import annotations

import json
import logging
from decimal import Decimal
from typing import Any, Callable, Dict, Optional

import httpx

from integrations.sysforge.db.money import to_cents
from src.tools._common import _INTERNAL_BASE, _internal_headers, _parse_tool_args
from src.tools.stage_upload import pop_staged
from src.tools.sysforge_constants import (
    ACTION_ALIASES,
    ACTION_PHASE,
    ACTION_TIER,
    action_help_text,
    not_implemented_message,
)

logger = logging.getLogger(__name__)

_API_PREFIX = "/api/sysforge"
_MAX_LIST = 50

Handler = Callable[[dict[str, Any], "ToolCtx"], Any]


class ToolCtx:
    __slots__ = ("owner", "session_id")

    def __init__(self, owner: str, session_id: Optional[str]):
        self.owner = owner
        self.session_id = session_id


def _plugin_error() -> Dict:
    return {
        "error": (
            "Business plugin is not installed. Install from Settings → Integrations, "
            "or ui_control open_panel settings."
        ),
        "exit_code": 1,
    }


def _fmt_cents(cents: int) -> str:
    sign = "-" if cents < 0 else ""
    return f"{sign}${abs(int(cents)) / 100:,.2f}"


def _dollars_to_cents(value: Any, field: str) -> Optional[int]:
    if value is None:
        return None
    d = float(value)
    cents = int(round(d * 100))
    if abs(d * 100 - cents) > 0.001:
        raise ValueError(f"{field}: dollar float drift exceeds 0.001")
    return cents


def _apply_dollar_aliases(args: dict[str, Any]) -> dict[str, Any]:
    out = dict(args)
    pairs = (
        ("unit_price_dollars", "unit_price_cents"),
        ("amount_dollars", "amount_cents"),
        ("tax_dollars", "tax_amount_cents"),
        ("shipping_dollars", "shipping_cents"),
        ("limit_dollars", "limit_cents"),
    )
    for d_key, c_key in pairs:
        if d_key in out and c_key not in out:
            out[c_key] = _dollars_to_cents(out[d_key], d_key)
    return out


def _enrich_money(obj: Any) -> Any:
    if isinstance(obj, dict):
        out = {k: _enrich_money(v) for k, v in obj.items()}
        for key, val in list(out.items()):
            if key.endswith("_cents") and isinstance(val, int):
                fmt_key = key.replace("_cents", "_formatted")
                if fmt_key not in out:
                    out[fmt_key] = _fmt_cents(val)
        return out
    if isinstance(obj, list):
        return [_enrich_money(x) for x in obj]
    return obj


def _ok(
    response: str,
    *,
    data: Any = None,
    ui_hint: Optional[dict] = None,
    exit_code: int = 0,
) -> Dict:
    payload: Dict[str, Any] = {"response": response, "exit_code": exit_code}
    if data is not None:
        payload["data"] = _enrich_money(data)
    if ui_hint:
        payload["ui_hint"] = ui_hint
    return payload


def _err(error: str, *, exit_code: int = 1) -> Dict:
    return {"error": error, "exit_code": exit_code}


async def _sf_request(
    method: str,
    path: str,
    owner: str,
    *,
    params: Optional[dict] = None,
    json_body: Any = None,
    files: Any = None,
    data: Any = None,
) -> tuple[int, Any]:
    if not path.startswith("/"):
        path = "/" + path
    url = f"{_INTERNAL_BASE}{path}"
    headers = _internal_headers(owner=owner)
    async with httpx.AsyncClient(timeout=60) as client:
        resp = await client.request(
            method.upper(),
            url,
            params=params,
            json=json_body if json_body is not None and files is None else None,
            files=files,
            data=data,
            headers=headers,
        )
    if resp.status_code == 204:
        return resp.status_code, {}
    try:
        body = resp.json()
    except Exception:
        body = {"detail": (resp.text or "")[:2000]}
    return resp.status_code, body


async def _sf_get(path: str, owner: str, params: Optional[dict] = None) -> tuple[int, Any]:
    return await _sf_request("GET", path, owner, params=params)


async def _sf_post(path: str, owner: str, json_body: Any = None, **kw) -> tuple[int, Any]:
    return await _sf_request("POST", path, owner, json_body=json_body, **kw)


async def _sf_put(path: str, owner: str, json_body: Any = None) -> tuple[int, Any]:
    return await _sf_request("PUT", path, owner, json_body=json_body)


async def _sf_patch(path: str, owner: str, json_body: Any = None) -> tuple[int, Any]:
    return await _sf_request("PATCH", path, owner, json_body=json_body)


async def _sf_delete(path: str, owner: str) -> tuple[int, Any]:
    return await _sf_request("DELETE", path, owner)


def _http_error(status: int, body: Any, action: str) -> Dict:
    detail = body
    if isinstance(body, dict):
        detail = body.get("detail") or body.get("message") or body
    return _err(f"{action} failed (HTTP {status}): {detail}")


def _require_gate(
    action: str,
    args: dict,
    ctx: ToolCtx,
    *,
    tier: int,
) -> Optional[str]:
    if tier < 2:
        return None
    from src.confirmation_gates import consume_confirmation, require_confirmed_action

    gate_args = {k: v for k, v in args.items() if k != "confirmation_token"}
    gate_args["action"] = action
    err = require_confirmed_action(
        session_id=ctx.session_id,
        owner=ctx.owner,
        domain="sysforge",
        tool_name="manage_sysforge",
        action=action,
        tool_args=gate_args,
        confirmation_token=args.get("confirmation_token"),
    )
    if err:
        return err
    token = str(args.get("confirmation_token") or "").strip()
    if token and ctx.session_id:
        consume_confirmation(
            token=token,
            session_id=ctx.session_id,
            owner=ctx.owner,
            consume_all=tier >= 3,
        )
    return None


def _build_line_items(raw: Any) -> list[dict]:
    if not isinstance(raw, list):
        return []
    items = []
    for i, row in enumerate(raw):
        if not isinstance(row, dict):
            continue
        item = {
            "part_id": row.get("part_id"),
            "part_name": row.get("part_name") or row.get("description") or "Item",
            "sku": row.get("sku"),
            "quantity_milliunits": int(row.get("quantity_milliunits") or row.get("quantity", 1) * 1000),
            "unit_price_cents": int(row.get("unit_price_cents") or 0),
            "discount_type": row.get("discount_type") or "None",
            "discount_value": int(row.get("discount_value") or 0),
            "is_taxable": bool(row.get("is_taxable", True)),
            "sort_order": int(row.get("sort_order", i)),
            "item_type": row.get("item_type") or "Part",
            "supplier_id": row.get("supplier_id"),
        }
        if row.get("unit_price_dollars") is not None and not row.get("unit_price_cents"):
            item["unit_price_cents"] = _dollars_to_cents(row["unit_price_dollars"], "unit_price_dollars")
        items.append(item)
    return items


def _draft_to_invoice_body(args: dict) -> dict:
    draft = args.get("draft") or args
    meta = draft.get("metadata") or {}
    body = {
        "client_id": draft.get("client_id") or args.get("client_id"),
        "client_info": draft.get("client_snapshot") or draft.get("client_info"),
        "name": meta.get("draft_name") or draft.get("name"),
        "tax_rate_bps": int(meta.get("tax_rate_bps") or args.get("tax_rate_bps") or 775),
        "shipping_rate_cents": int(meta.get("shipping_cents") or args.get("shipping_cents") or 0),
        "items": _build_line_items(draft.get("line_items") or args.get("line_items") or []),
    }
    if args.get("status"):
        body["status"] = args["status"]
    return body


# --- Handlers ---


async def _h_action_help(args: dict, ctx: ToolCtx) -> Dict:
    topic = (args.get("topic") or args.get("action") or "clients").strip()
    return _ok(action_help_text(topic))


async def _h_status(args: dict, ctx: ToolCtx) -> Dict:
    status, body = await _sf_get(f"{_API_PREFIX}/status", ctx.owner)
    if status >= 400:
        return _http_error(status, body, "status")
    schema = body.get("schema") or {}
    lines = ["SysForge Business status:"]
    if body.get("version"):
        lines.append(f"- Plugin version: {body['version']}")
    if schema.get("latest_id") is not None:
        lines.append(f"- Schema migration: {schema.get('latest_id')}")
    return _ok("\n".join(lines), data=body)


async def _h_diagnostics(args: dict, ctx: ToolCtx) -> Dict:
    status, body = await _sf_get(f"{_API_PREFIX}/diagnostics", ctx.owner)
    if status >= 400:
        return _http_error(status, body, "diagnostics")
    summary = body.get("summary") or {}
    lines = ["Diagnostics:"]
    for k, v in list(summary.items())[:12]:
        lines.append(f"- {k}: {v}")
    return _ok("\n".join(lines), data=body)


async def _h_client_search(args: dict, ctx: ToolCtx) -> Dict:
    q = (args.get("q") or args.get("query") or "").strip()
    if not q:
        return _err("client_search requires q")
    status, body = await _sf_get(f"{_API_PREFIX}/clients/search", ctx.owner, params={"q": q})
    if status >= 400:
        return _http_error(status, body, "client_search")
    clients = body if isinstance(body, list) else body.get("clients") or body.get("results") or []
    if not clients:
        return _ok(f"No clients match '{q}'.")
    lines = [f"Clients matching '{q}':"]
    for c in clients[:_MAX_LIST]:
        name = c.get("display_name") or f"{c.get('first_name','')} {c.get('last_name','')}".strip()
        lines.append(f"- [{c.get('id')}] {name} | {c.get('phone_number') or ''} | {c.get('email') or ''}")
    return _ok("\n".join(lines), data={"clients": clients})


async def _h_client_list(args: dict, ctx: ToolCtx) -> Dict:
    status, body = await _sf_get(f"{_API_PREFIX}/clients", ctx.owner)
    if status >= 400:
        return _http_error(status, body, "client_list")
    clients = body if isinstance(body, list) else body.get("clients") or []
    lines = [f"Clients ({len(clients)}):"]
    for c in clients[:_MAX_LIST]:
        lines.append(f"- [{c.get('id')}] {c.get('display_name')}")
    return _ok("\n".join(lines), data={"clients": clients})


async def _h_client_recent(args: dict, ctx: ToolCtx) -> Dict:
    status, body = await _sf_get(f"{_API_PREFIX}/clients/recent", ctx.owner)
    if status >= 400:
        return _http_error(status, body, "client_recent")
    clients = body if isinstance(body, list) else body.get("clients") or []
    lines = ["Recent clients:"]
    for c in clients[:20]:
        lines.append(f"- [{c.get('id')}] {c.get('display_name')}")
    return _ok("\n".join(lines), data={"clients": clients})


async def _h_client_get(args: dict, ctx: ToolCtx) -> Dict:
    cid = args.get("client_id") or args.get("id")
    if not cid:
        return _err("client_get requires client_id")
    status, body = await _sf_get(f"{_API_PREFIX}/clients/{cid}", ctx.owner)
    if status >= 400:
        return _http_error(status, body, "client_get")
    name = body.get("display_name") or body.get("id")
    return _ok(f"Client {name} [{body.get('id')}]", data=body)


async def _h_client_create(args: dict, ctx: ToolCtx) -> Dict:
    payload = {k: args.get(k) for k in (
        "first_name", "last_name", "nickname", "phone_number", "email",
        "address", "company", "notes", "is_incomplete",
    ) if k in args}
    if not payload.get("first_name") and not payload.get("last_name"):
        return _err("client_create requires first_name or last_name")
    status, body = await _sf_post(f"{_API_PREFIX}/clients", ctx.owner, payload)
    if status >= 400:
        return _http_error(status, body, "client_create")
    return _ok(f"Created client [{body.get('id')}] {body.get('display_name')}", data=body)


async def _h_client_update(args: dict, ctx: ToolCtx) -> Dict:
    cid = args.get("client_id") or args.get("id")
    if not cid:
        return _err("client_update requires client_id")
    payload = {k: v for k, v in args.items() if k not in ("action", "client_id", "id", "confirmation_token")}
    status, body = await _sf_put(f"{_API_PREFIX}/clients/{cid}", ctx.owner, payload)
    if status >= 400:
        return _http_error(status, body, "client_update")
    return _ok(f"Updated client [{cid}]", data=body)


async def _h_client_touch(args: dict, ctx: ToolCtx) -> Dict:
    cid = args.get("client_id") or args.get("id")
    if not cid:
        return _err("client_touch requires client_id")
    status, body = await _sf_post(f"{_API_PREFIX}/clients/{cid}/touch", ctx.owner, {})
    if status >= 400:
        return _http_error(status, body, "client_touch")
    return _ok(f"Touched client [{cid}]", data=body)


async def _h_client_link_dossier(args: dict, ctx: ToolCtx) -> Dict:
    from src.tools.dossier import do_manage_dossier

    person_id = args.get("person_id")
    client_id = args.get("client_id") or args.get("sysforge_client_id")
    if not person_id or not client_id:
        return _err("client_link_dossier requires person_id and client_id")
    result = await do_manage_dossier(
        json.dumps({
            "action": "update_person",
            "person_id": person_id,
            "sysforge_client_id": str(client_id),
        }),
        owner=ctx.owner,
    )
    if result.get("exit_code") != 0:
        return result
    status, body = await _sf_get(f"{_API_PREFIX}/clients/{client_id}", ctx.owner)
    client_name = body.get("display_name") if status < 400 else str(client_id)
    return _ok(
        f"Linked dossier person {person_id} → SysForge client {client_name} [{client_id}]",
        data={"person_id": person_id, "sysforge_client_id": str(client_id), "client": body if status < 400 else None},
    )


async def _h_client_unlink_dossier(args: dict, ctx: ToolCtx) -> Dict:
    from src.tools.dossier import do_manage_dossier

    person_id = args.get("person_id")
    if not person_id:
        return _err("client_unlink_dossier requires person_id")
    result = await do_manage_dossier(
        json.dumps({"action": "update_person", "person_id": person_id, "sysforge_client_id": ""}),
        owner=ctx.owner,
    )
    return result if result.get("exit_code") != 0 else _ok(f"Unlinked SysForge client from person {person_id}")


async def _h_outstanding_list(args: dict, ctx: ToolCtx) -> Dict:
    status, body = await _sf_get(f"{_API_PREFIX}/invoices/outstanding", ctx.owner)
    if status >= 400:
        return _http_error(status, body, "outstanding_list")
    invoices = body.get("invoices") or []
    total = sum(int(i.get("balance_cents") or i.get("outstanding_cents") or 0) for i in invoices)
    lines = [f"Outstanding invoices ({len(invoices)}), total {_fmt_cents(total)}:"]
    for inv in invoices[:_MAX_LIST]:
        bal = int(inv.get("balance_cents") or inv.get("outstanding_cents") or 0)
        lines.append(
            f"- #{inv.get('id')} {inv.get('client_name') or inv.get('name') or ''} "
            f"| {_fmt_cents(bal)} | {inv.get('status') or ''}"
        )
    return _ok(
        "\n".join(lines),
        data={"invoices": invoices, "total_outstanding_cents": total, "total_outstanding_formatted": _fmt_cents(total)},
        ui_hint={"panel": "business", "route": "invoices-outstanding"},
    )


async def _h_invoice_list(args: dict, ctx: ToolCtx) -> Dict:
    cid = args.get("client_id")
    if not cid:
        return _err("invoice_list requires client_id")
    status, body = await _sf_get(f"{_API_PREFIX}/invoices", ctx.owner, params={"client_id": cid})
    if status >= 400:
        return _http_error(status, body, "invoice_list")
    invoices = body.get("invoices") or []
    lines = [f"Invoices for client {cid} ({len(invoices)}):"]
    for inv in invoices[:_MAX_LIST]:
        total = int(inv.get("final_total_cents") or 0)
        lines.append(f"- #{inv.get('id')} {inv.get('status')} | {_fmt_cents(total)}")
    return _ok("\n".join(lines), data={"invoices": invoices})


async def _h_invoice_get(args: dict, ctx: ToolCtx) -> Dict:
    iid = args.get("invoice_id") or args.get("id")
    if not iid:
        return _err("invoice_get requires invoice_id")
    status, body = await _sf_get(f"{_API_PREFIX}/invoices/{iid}", ctx.owner)
    if status >= 400:
        return _http_error(status, body, "invoice_get")
    total = int(body.get("final_total_cents") or 0)
    return _ok(f"Invoice #{iid} | {body.get('status')} | {_fmt_cents(total)}", data=body)


async def _h_invoice_validate(args: dict, ctx: ToolCtx) -> Dict:
    from integrations.sysforge.services.invoice_validation import (
        InvoiceValidationError,
        validate_invoice,
        validate_invoice_items,
    )

    body = _draft_to_invoice_body(args)
    try:
        validate_invoice(body)
        validate_invoice_items(body.get("items") or [])
    except InvoiceValidationError as exc:
        return _err(str(exc))
    return _ok("Invoice draft is valid.", data={"valid": True, "draft": body})


async def _h_invoice_preview(args: dict, ctx: ToolCtx) -> Dict:
    body = _draft_to_invoice_body(args)
    items = body.get("items") or []
    parts = sum(int(i.get("unit_price_cents") or 0) * int(i.get("quantity_milliunits") or 1000) // 1000 for i in items)
    tax_bps = int(body.get("tax_rate_bps") or 0)
    tax = parts * tax_bps // 10000
    shipping = int(body.get("shipping_rate_cents") or 0)
    final = parts + tax + shipping
    preview = {
        "parts_subtotal_cents": parts,
        "tax_amount_cents": tax,
        "shipping_cost_cents": shipping,
        "final_total_cents": final,
    }
    return _ok(
        f"Preview: parts {_fmt_cents(parts)}, tax {_fmt_cents(tax)}, "
        f"shipping {_fmt_cents(shipping)}, total {_fmt_cents(final)}",
        data=preview,
    )


async def _h_invoice_create(args: dict, ctx: ToolCtx) -> Dict:
    body = _draft_to_invoice_body(args)
    status, resp = await _sf_post(f"{_API_PREFIX}/invoices", ctx.owner, body)
    if status >= 400:
        return _http_error(status, resp, "invoice_create")
    iid = resp.get("id")
    total = int(resp.get("final_total_cents") or 0)
    return _ok(f"Created invoice #{iid} | {_fmt_cents(total)}", data=resp)


async def _h_invoice_update(args: dict, ctx: ToolCtx) -> Dict:
    iid = args.get("invoice_id") or args.get("id")
    if not iid:
        return _err("invoice_update requires invoice_id")
    body = _draft_to_invoice_body(args)
    status, resp = await _sf_put(f"{_API_PREFIX}/invoices/{iid}", ctx.owner, body)
    if status >= 400:
        return _http_error(status, resp, "invoice_update")
    return _ok(f"Updated invoice #{iid}", data=resp)


async def _h_part_search(args: dict, ctx: ToolCtx) -> Dict:
    q = (args.get("q") or args.get("query") or "").strip()
    if not q:
        return _err("part_search requires q")
    status, body = await _sf_get(f"{_API_PREFIX}/parts/search", ctx.owner, params={"q": q})
    if status >= 400:
        return _http_error(status, body, "part_search")
    parts = body if isinstance(body, list) else body.get("parts") or []
    lines = [f"Parts matching '{q}':"]
    for p in parts[:_MAX_LIST]:
        price = int(p.get("base_price_cents") or 0)
        lines.append(f"- [{p.get('id')}] {p.get('sku') or ''} {p.get('name')} | {_fmt_cents(price)}")
    return _ok("\n".join(lines), data={"parts": parts})


async def _h_part_create(args: dict, ctx: ToolCtx) -> Dict:
    payload = {k: args.get(k) for k in (
        "name", "base_price_cents", "description", "sku", "supplier_id",
        "preferred_supplier_id", "is_placeholder",
    ) if k in args}
    if not payload.get("name"):
        return _err("part_create requires name")
    status, body = await _sf_post(f"{_API_PREFIX}/parts", ctx.owner, payload)
    if status >= 400:
        return _http_error(status, body, "part_create")
    return _ok(f"Created part [{body.get('id')}] {body.get('name')}", data=body)


async def _h_supplier_create(args: dict, ctx: ToolCtx) -> Dict:
    payload = {k: args.get(k) for k in ("name", "contact_info", "website", "primary_phone", "primary_email") if k in args}
    if not payload.get("name"):
        return _err("supplier_create requires name")
    status, body = await _sf_post(f"{_API_PREFIX}/suppliers", ctx.owner, payload)
    if status >= 400:
        return _http_error(status, body, "supplier_create")
    return _ok(f"Created supplier [{body.get('id')}] {body.get('name')}", data=body)


async def _h_report_sales(args: dict, ctx: ToolCtx) -> Dict:
    params = {}
    if args.get("from") or args.get("date_from"):
        params["from"] = args.get("from") or args.get("date_from")
    if args.get("to") or args.get("date_to"):
        params["to"] = args.get("to") or args.get("date_to")
    status, body = await _sf_get(f"{_API_PREFIX}/reports/sales", ctx.owner, params=params or None)
    if status >= 400:
        return _http_error(status, body, "report_sales")
    summary = body.get("summary") or body
    return _ok("Sales report retrieved.", data=summary if isinstance(summary, dict) else body)


async def _h_report_aging(args: dict, ctx: ToolCtx) -> Dict:
    status, body = await _sf_get(f"{_API_PREFIX}/reports/aging", ctx.owner)
    if status >= 400:
        return _http_error(status, body, "report_aging")
    buckets = body.get("buckets") or body
    lines = ["Aging report (days since invoice created):"]
    for name, rows in (buckets.items() if isinstance(buckets, dict) else []):
        total = sum(int(r.get("balance_cents") or 0) for r in (rows or []))
        lines.append(f"- {name}: {len(rows or [])} invoices, {_fmt_cents(total)}")
    return _ok("\n".join(lines), data=body)


async def _h_health_digest(args: dict, ctx: ToolCtx) -> Dict:
    from src.tools.sysforge_digest import compose_health_digest

    digest = await compose_health_digest(ctx.owner)
    lines = ["Shop health digest:"]
    for section, text in digest.get("sections", {}).items():
        lines.append(f"- **{section}**: {text}")
    return _ok("\n".join(lines), data=digest)


async def _h_project_photo_add(args: dict, ctx: ToolCtx) -> Dict:
    project_id = args.get("project_id")
    token = args.get("upload_token")
    if not project_id or not token:
        return _err("project_photo_add requires project_id and upload_token")
    try:
        staged = pop_staged(str(token), owner=ctx.owner)
    except (LookupError, PermissionError) as exc:
        return _err(str(exc))
    files = {"file": (staged["filename"], staged["data"], staged["mime_type"])}
    data = {"phase": args.get("phase") or "Before"}
    status, body = await _sf_request(
        "POST",
        f"{_API_PREFIX}/projects/{project_id}/photos",
        ctx.owner,
        files=files,
        data=data,
    )
    if status >= 400:
        return _http_error(status, body, "project_photo_add")
    return _ok(f"Photo added to project {project_id}", data=body)


async def _h_invoice_pdf_fetch(args: dict, ctx: ToolCtx) -> Dict:
    iid = args.get("invoice_id") or args.get("id")
    out_path = (args.get("path") or args.get("workspace_path") or "").strip()
    if not iid or not out_path:
        return _err("invoice_pdf_fetch requires invoice_id and path")
    url = f"{_INTERNAL_BASE}{_API_PREFIX}/invoices/{iid}/pdf"
    headers = _internal_headers(owner=ctx.owner)
    async with httpx.AsyncClient(timeout=60) as client:
        resp = await client.get(url, headers=headers)
    if resp.status_code >= 400:
        return _err(f"invoice_pdf_fetch failed HTTP {resp.status_code}")
    from pathlib import Path

    dest = Path(out_path)
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(resp.content)
    return _ok(f"Wrote invoice PDF to {dest}", data={"path": str(dest), "size_bytes": len(resp.content)})


async def _h_backup_restore_preview(args: dict, ctx: ToolCtx) -> Dict:
    backup_id = args.get("backup_id")
    if not backup_id:
        return _err("backup_restore_preview requires backup_id")
    status, body = await _sf_get(f"{_API_PREFIX}/backup/{backup_id}/manifest", ctx.owner)
    if status >= 400:
        return _http_error(status, body, "backup_restore_preview")
    manifest = body.get("manifest") or {}
    contents = manifest.get("contents") or []
    lines = [
        f"Backup {backup_id} ({body.get('kind')}, {body.get('size_bytes')} bytes):",
        f"- Schema: {manifest.get('schema_version', 'unknown')}",
        f"- Contents: {', '.join(contents) if contents else 'sysforge.db'}",
    ]
    if body.get("has_config"):
        lines.append("- Includes plugin config.json")
    if body.get("has_drafts"):
        lines.append("- Includes drafts/")
    return _ok("\n".join(lines), data=body)


async def _h_backup_restore(args: dict, ctx: ToolCtx) -> Dict:
    restore_config = bool(args.get("restore_config", False))
    backup_id = args.get("backup_id")
    token = args.get("upload_token")

    if token:
        try:
            staged = pop_staged(str(token), owner=ctx.owner)
        except (LookupError, PermissionError) as exc:
            return _err(str(exc))
        files = {"file": (staged["filename"], staged["data"], staged["mime_type"])}
        data = {"restore_config": "true" if restore_config else "false"}
        status, body = await _sf_request(
            "POST",
            f"{_API_PREFIX}/backup/restore",
            ctx.owner,
            files=files,
            data=data,
        )
    elif backup_id:
        status, body = await _sf_post(
            f"{_API_PREFIX}/backup/restore",
            ctx.owner,
            {"backup_id": str(backup_id), "restore_config": restore_config},
        )
    else:
        return _err("backup_restore requires backup_id or upload_token (stage_upload purpose=backup_zip)")

    if status >= 400:
        return _http_error(status, body, "backup_restore")
    msg = body.get("message") or "Restore completed."
    if body.get("safety_backup_id"):
        msg += f" Safety backup: {body['safety_backup_id']}."
    return _ok(msg, data=body)


async def _h_invoice_batch_validate(args: dict, ctx: ToolCtx) -> Dict:
    from integrations.sysforge.services import invoice_batch as batch

    entries = args.get("invoices") or args.get("entries") or []
    if not entries:
        return _err("invoice_batch_validate requires invoices[]")
    result = batch.validate_batch(entries)
    lines = [
        f"Batch validation: {result['would_create']} would create, "
        f"{result['would_skip']} would skip, "
        f"revenue {_fmt_cents(int(result.get('total_revenue_cents') or 0))}.",
    ]
    for warn in (result.get("warnings") or [])[:5]:
        lines.append(f"- Warning: {warn}")
    for err in (result.get("errors") or [])[:8]:
        lines.append(f"- Error: {err}")
    if result.get("valid"):
        return _ok("\n".join(lines), data=result)
    return _err("\n".join(lines), exit_code=1)


async def _h_invoice_batch_create(args: dict, ctx: ToolCtx) -> Dict:
    batch_id = args.get("batch_id")
    dry_run = bool(args.get("dry_run", True)) if batch_id is None else False
    entries = args.get("invoices") or args.get("entries") or []

    if batch_id:
        status, body = await _sf_post(
            f"{_API_PREFIX}/invoices/batch/{batch_id}/commit",
            ctx.owner,
            {},
        )
    else:
        if not entries:
            return _err("invoice_batch_create requires invoices[] or batch_id from dry_run preview")
        status, body = await _sf_post(
            f"{_API_PREFIX}/invoices/batch",
            ctx.owner,
            {"dry_run": dry_run, "invoices": entries},
        )

    if status >= 400:
        return _http_error(status, body, "invoice_batch_create")

    if dry_run or body.get("dry_run"):
        rev = int(body.get("total_revenue_cents") or 0)
        return _ok(
            f"Dry run: {body.get('would_create', 0)} create, {body.get('would_skip', 0)} skip, "
            f"revenue {_fmt_cents(rev)}. batch_id={body.get('batch_id')}",
            data=body,
        )

    created = int(body.get("created_count") or len(body.get("created") or []))
    skipped = int(body.get("skipped_count") or len(body.get("skipped") or []))
    return _ok(
        f"Batch create: {created} created, {skipped} skipped.",
        data=body,
    )


async def _h_supplier_bulk_upsert(args: dict, ctx: ToolCtx) -> Dict:
    batch_id = args.get("batch_id")
    dry_run = bool(args.get("dry_run", True)) if batch_id is None else False
    suppliers = args.get("suppliers") or args.get("rows") or []

    if batch_id and not dry_run:
        status, body = await _sf_post(
            f"{_API_PREFIX}/suppliers/bulk/{batch_id}/commit",
            ctx.owner,
            {},
        )
    else:
        status, body = await _sf_post(
            f"{_API_PREFIX}/suppliers/bulk",
            ctx.owner,
            {"dry_run": dry_run, "suppliers": suppliers},
        )

    if status >= 400:
        return _http_error(status, body, "supplier_bulk_upsert")
    if dry_run or body.get("dry_run"):
        return _ok(
            f"Dry run: {body.get('would_create', 0)} create, {body.get('would_update', 0)} update. "
            f"batch_id={body.get('batch_id')}",
            data=body,
        )
    return _ok(
        f"Suppliers bulk: {body.get('created', 0)} created, {body.get('updated', 0)} updated.",
        data=body,
    )


async def _h_placeholder_bulk_convert(args: dict, ctx: ToolCtx) -> Dict:
    batch_id = args.get("batch_id")
    dry_run = bool(args.get("dry_run", True)) if batch_id is None else False
    mappings = args.get("mappings") or args.get("rows") or []

    if batch_id and not dry_run:
        status, body = await _sf_post(
            f"{_API_PREFIX}/placeholders/bulk-convert/{batch_id}/commit",
            ctx.owner,
            {},
        )
    else:
        status, body = await _sf_post(
            f"{_API_PREFIX}/placeholders/bulk-convert",
            ctx.owner,
            {
                "dry_run": dry_run,
                "mappings": mappings,
                "skip_conflicts": bool(args.get("skip_conflicts", False)),
            },
        )

    if status >= 400:
        return _http_error(status, body, "placeholder_bulk_convert")
    if dry_run or body.get("dry_run"):
        return _ok(
            f"Dry run: {body.get('would_convert', 0)} would convert. batch_id={body.get('batch_id')}",
            data=body,
        )
    return _ok(f"Converted {body.get('converted', 0)} placeholders.", data=body)


async def _h_suggest_payment_plan(args: dict, ctx: ToolCtx) -> Dict:
    """Advisory-only installment schedule (no DB persistence)."""
    from datetime import date, timedelta

    iid = args.get("invoice_id") or args.get("id")
    if not iid:
        return _err("suggest_payment_plan requires invoice_id")
    installments = int(args.get("installments") or args.get("num_installments") or 3)
    if installments < 1 or installments > 24:
        return _err("installments must be between 1 and 24")
    interval_days = int(args.get("interval_days") or 30)
    if interval_days < 1:
        return _err("interval_days must be positive")

    status, inv = await _sf_get(f"{_API_PREFIX}/invoices/{iid}", ctx.owner)
    if status >= 400:
        return _http_error(status, inv, "suggest_payment_plan")

    balance = int(inv.get("balance_cents") or inv.get("final_total_cents") or 0)
    if balance <= 0:
        pay_status, payments = await _sf_get(f"{_API_PREFIX}/invoices/{iid}/payments", ctx.owner)
        if pay_status < 400:
            paid = sum(int(p.get("amount_cents") or 0) for p in (payments or []))
            balance = max(0, int(inv.get("final_total_cents") or 0) - paid)

    if balance <= 0:
        return _ok(f"Invoice #{iid} has no balance due; payment plan not needed.", data={"invoice_id": iid})

    base = balance // installments
    remainder = balance - base * installments
    start = date.today()
    schedule = []
    for n in range(installments):
        amount = base + (1 if n < remainder else 0)
        due = start + timedelta(days=interval_days * n)
        schedule.append(
            {
                "installment": n + 1,
                "due_date": due.isoformat(),
                "amount_cents": amount,
                "amount_formatted": _fmt_cents(amount),
            }
        )

    lines = [
        f"Advisory payment plan for invoice #{iid} ({_fmt_cents(balance)} over {installments} payments):",
        "This is a suggestion only; payment_plan_* persistence is not enabled yet.",
    ]
    for row in schedule:
        lines.append(f"- #{row['installment']}: {row['due_date']} | {row['amount_formatted']}")

    return _ok(
        "\n".join(lines),
        data={
            "advisory_only": True,
            "invoice_id": int(iid),
            "balance_cents": balance,
            "installments": installments,
            "interval_days": interval_days,
            "schedule": schedule,
        },
    )


HANDLERS: dict[str, Handler] = {
    "action_help": _h_action_help,
    "status": _h_status,
    "diagnostics": _h_diagnostics,
    "client_search": _h_client_search,
    "client_list": _h_client_list,
    "client_recent": _h_client_recent,
    "client_get": _h_client_get,
    "client_create": _h_client_create,
    "client_update": _h_client_update,
    "client_touch": _h_client_touch,
    "client_link_dossier": _h_client_link_dossier,
    "client_unlink_dossier": _h_client_unlink_dossier,
    "outstanding_list": _h_outstanding_list,
    "invoice_list": _h_invoice_list,
    "invoice_get": _h_invoice_get,
    "invoice_validate": _h_invoice_validate,
    "invoice_preview": _h_invoice_preview,
    "invoice_create": _h_invoice_create,
    "invoice_update": _h_invoice_update,
    "part_search": _h_part_search,
    "part_create": _h_part_create,
    "supplier_create": _h_supplier_create,
    "report_sales": _h_report_sales,
    "report_aging": _h_report_aging,
    "health_digest": _h_health_digest,
    "project_photo_add": _h_project_photo_add,
    "invoice_pdf_fetch": _h_invoice_pdf_fetch,
    "backup_restore_preview": _h_backup_restore_preview,
    "backup_restore": _h_backup_restore,
    "invoice_batch_validate": _h_invoice_batch_validate,
    "invoice_batch_create": _h_invoice_batch_create,
    "supplier_bulk_upsert": _h_supplier_bulk_upsert,
    "placeholder_bulk_convert": _h_placeholder_bulk_convert,
    "suggest_payment_plan": _h_suggest_payment_plan,
}


def _resolve_path(path_tpl: str, args: dict) -> str:
    path = path_tpl
    for key in (
        "client_id", "invoice_id", "part_id", "supplier_id", "project_id",
        "draft_id", "payment_id", "work_order_id", "screw_map_id", "batch_id",
        "backup_id",
    ):
        placeholder = "{" + key + "}"
        if placeholder in path:
            val = args.get(key) or args.get("id")
            if val is None:
                raise ValueError(f"{key} is required")
            path = path.replace(placeholder, str(val))
    return path


def _make_proxy_handler(
    action: str,
    method: str,
    path_tpl: str,
    body_keys: Optional[tuple[str, ...]] = None,
) -> Handler:
    async def handler(args: dict, ctx: ToolCtx) -> Dict:
        try:
            path = _resolve_path(path_tpl, args)
        except ValueError as exc:
            return _err(str(exc))
        params = {
            k: args[k]
            for k in ("q", "from", "to", "date_from", "date_to", "include_archived")
            if k in args
        }
        skip = frozenset({"action", "confirmation_token", "id"})
        if body_keys:
            json_body = {k: args[k] for k in body_keys if k in args}
        elif method in ("POST", "PUT", "PATCH"):
            json_body = {
                k: v for k, v in args.items()
                if k not in skip and not k.endswith("_id") and k != "invoice_id"
            }
        else:
            json_body = None

        if action == "invoice_accept" and method == "POST":
            iid = args.get("invoice_id")
            if not iid:
                return _err("invoice_accept requires invoice_id")
            json_body = {
                "invoice_id": int(iid),
                "bump_status_to_invoiced": bool(args.get("bump_status_to_invoiced", True)),
            }
            path = "/work-orders/from-accepted-estimate"

        full = f"{_API_PREFIX}{path}"
        if method == "GET":
            st, body = await _sf_get(full, ctx.owner, params=params or None)
        elif method == "POST":
            st, body = await _sf_post(full, ctx.owner, json_body or {})
        elif method == "PUT":
            st, body = await _sf_put(full, ctx.owner, json_body or {})
        elif method == "PATCH":
            st, body = await _sf_patch(full, ctx.owner, json_body or {})
        else:
            st, body = await _sf_delete(full, ctx.owner)
        if st >= 400:
            return _http_error(st, body, action)
        if st == 204:
            return _ok(f"{action} completed.")
        return _ok(f"{action} OK.", data=body)

    return handler


_PROXY_MAPPINGS: list[tuple[str, str, str, Optional[tuple[str, ...]]]] = [
    ("client_duplicates", "POST", "/clients/duplicates", ("phone", "email", "name", "exclude_id")),
    ("client_list_invoices", "GET", "/clients/{client_id}/invoices", None),
    ("client_merge_preview", "GET", "/clients/merge/candidates", None),
    ("client_merge", "POST", "/clients/merge", ("survivor_id", "loser_id")),
    ("client_delete", "DELETE", "/clients/{client_id}", None),
    ("invoice_price_compare", "GET", "/invoices/{invoice_id}/price-compare", None),
    ("payment_list", "GET", "/invoices/{invoice_id}/payments", None),
    ("payment_record", "POST", "/invoices/{invoice_id}/payments", ("amount_cents", "method", "reference", "notes")),
    ("payment_void", "POST", "/payments/{payment_id}/void", ("reason",)),
    ("invoice_delete", "DELETE", "/invoices/{invoice_id}", None),
    ("invoice_email", "POST", "/invoices/{invoice_id}/email", ("to", "subject", "body")),
    ("invoice_accept", "POST", "/work-orders/from-accepted-estimate", ("invoice_id", "bump_status_to_invoiced")),
    ("invoice_devices_get", "GET", "/invoices/{invoice_id}/devices", None),
    ("invoice_devices_set", "PUT", "/invoices/{invoice_id}/devices", ("devices",)),
    ("invoice_update_prices_preview", "POST", "/invoices/{invoice_id}/update-prices/preview", ("choices",)),
    ("invoice_update_prices_apply", "POST", "/invoices/{invoice_id}/update-prices/apply", ("items",)),
    ("draft_list", "GET", "/drafts", None),
    ("draft_get", "GET", "/drafts/{draft_id}", None),
    ("draft_save", "POST", "/drafts", None),
    ("draft_delete", "DELETE", "/drafts/{draft_id}", None),
    ("part_list", "GET", "/parts", None),
    ("part_get", "GET", "/parts/{part_id}", None),
    ("part_update", "PATCH", "/parts/{part_id}", None),
    ("part_delete", "DELETE", "/parts/{part_id}", None),
    ("part_usage", "GET", "/parts/{part_id}/usage", None),
    ("part_stock_get", "GET", "/parts/{part_id}/stock", None),
    ("part_stock_set", "PUT", "/parts/{part_id}/stock", ("quantity_on_hand", "notes")),
    ("supplier_list", "GET", "/suppliers", None),
    ("supplier_search", "GET", "/suppliers/search", None),
    ("supplier_get", "GET", "/suppliers/{supplier_id}", None),
    ("supplier_update", "PUT", "/suppliers/{supplier_id}", None),
    ("supplier_delete", "DELETE", "/suppliers/{supplier_id}", None),
    ("supplier_parts", "GET", "/suppliers/{supplier_id}/parts", None),
    ("placeholder_list", "GET", "/placeholders", None),
    ("placeholder_groups", "GET", "/placeholders/groups", None),
    ("placeholder_convert", "POST", "/parts/placeholders/{part_id}/convert", None),
    ("placeholder_merge", "POST", "/placeholders/merge", ("target_part_id", "source_part_ids")),
    ("project_hub", "GET", "/projects/hub", None),
    ("project_list", "GET", "/projects", None),
    ("project_get", "GET", "/projects/{project_id}", None),
    ("project_create_from_invoice", "POST", "/projects/from-invoice", None),
    ("work_order_get", "GET", "/work-orders/{work_order_id}", None),
    ("work_order_from_estimate", "POST", "/work-orders/from-accepted-estimate", ("invoice_id",)),
    ("screw_map_get", "GET", "/projects/{project_id}/screw-map", None),
    ("settings_get", "GET", "/settings", None),
    ("settings_update", "PUT", "/settings", None),
    ("backup_list", "GET", "/backup/list", None),
    ("backup_create", "POST", "/backup/create", ("include_drafts",)),
    ("companion_status", "GET", "/companion/status", None),
    ("companion_inbox_list", "GET", "/companion/inbox", None),
    ("part_search_rebuild", "POST", "/parts/search/rebuild", None),
    ("part_import", "POST", "/parts/import", None),
    ("part_import_commit", "POST", "/parts/import/{batch_id}/commit", None),
    ("part_enrich", "POST", "/parts/enrich", None),
]

for _act, _meth, _path, _keys in _PROXY_MAPPINGS:
    if _act not in HANDLERS:
        HANDLERS[_act] = _make_proxy_handler(_act, _meth, _path, _keys)


async def do_manage_sysforge(
    content: str,
    owner: Optional[str] = None,
    session_id: Optional[str] = None,
) -> Dict:
    from src.plugins.registry import is_plugin_active

    if not is_plugin_active("sysforge"):
        return _plugin_error()

    try:
        args = _parse_tool_args(content)
    except ValueError:
        return {"error": "Invalid JSON arguments", "exit_code": 1}

    args = _apply_dollar_aliases(args)
    action = (args.get("action") or "status").replace("-", "_").strip().lower()
    action = ACTION_ALIASES.get(action, action)

    ctx = ToolCtx(owner=owner or "", session_id=session_id)

    if action == "action_help":
        topic = (args.get("topic") or "clients").strip()
        return _ok(action_help_text(topic))

    if action not in HANDLERS:
        phase = ACTION_PHASE.get(action, 99)
        if phase > 7:
            return _err(
                f"Unknown action '{action}'. Use action_help. "
                f"Valid actions include: status, client_search, outstanding_list, invoice_create."
            )
        return _err(not_implemented_message(action))

    tier = ACTION_TIER.get(action, 0)
    if args.get("dry_run") is True and tier == 2:
        tier = 0
    gate_err = _require_gate(action, args, ctx, tier=tier)
    if gate_err:
        return _err(gate_err)

    try:
        return await HANDLERS[action](args, ctx)
    except ValueError as exc:
        return _err(str(exc))
    except Exception as exc:
        logger.exception("manage_sysforge %s failed", action)
        return _err(str(exc))
