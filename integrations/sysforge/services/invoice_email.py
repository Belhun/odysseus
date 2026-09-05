"""Email invoice PDF via Odysseus host SMTP (no plugin SMTP stack)."""

from __future__ import annotations

import logging
import re
import uuid
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import formataddr, make_msgid
from typing import Any, Callable

from integrations.sysforge.db import connection as db_connection
from integrations.sysforge.db.utc import format_storage
from integrations.sysforge.pdf_invoice import suggested_pdf_filename
from integrations.sysforge.services import invoice_documents
from integrations.sysforge.services import invoices as invoice_service
from integrations.sysforge.services.invoices import InvoiceNotFoundError

logger = logging.getLogger(__name__)


class InvoiceEmailError(ValueError):
    """Validation or host-mail configuration failure."""


def _default_subject(invoice: dict[str, Any]) -> str:
    label = invoice.get("display_label") or invoice.get("name") or f"Invoice #{invoice.get('id')}"
    return f"Invoice: {label}"


def _default_body(invoice: dict[str, Any]) -> str:
    label = invoice.get("display_label") or invoice.get("name") or f"#{invoice.get('id')}"
    return (
        f"Please find attached invoice {label}.\n\n"
        f"Total: ${int(invoice.get('final_total_cents') or 0) / 100:.2f}\n"
    )


def mark_invoice_sent(
    invoice_id: int,
    *,
    bump_estimate_to_invoiced: bool = True,
) -> dict[str, Any]:
    """Set SentAt (UTC). Optionally promote Estimate → Invoiced."""
    conn = db_connection.connect()
    try:
        row = conn.execute(
            "SELECT Id, Status, SentAt FROM Invoices WHERE Id = ?",
            (invoice_id,),
        ).fetchone()
        if row is None:
            raise InvoiceNotFoundError(f"Invoice {invoice_id} not found")
        now = format_storage()
        status = row["Status"] or "Estimate"
        if bump_estimate_to_invoiced and status == "Estimate":
            status = "Invoiced"
        conn.execute(
            "UPDATE Invoices SET SentAt = ?, Status = ? WHERE Id = ?",
            (now, status, invoice_id),
        )
        conn.commit()
    finally:
        conn.close()
    inv = invoice_service.get_invoice(invoice_id)
    if inv is None:
        raise InvoiceNotFoundError(f"Invoice {invoice_id} not found")
    return inv


def _stage_compose_upload(pdf_bytes: bytes, file_name: str) -> str:
    """Write PDF into host compose uploads dir; return attachment token."""
    from routes.email_helpers import COMPOSE_UPLOADS_DIR

    COMPOSE_UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
    safe_name = re.sub(r"[^\w\s\-.]", "_", file_name or "invoice.pdf").strip() or "invoice.pdf"
    token = f"{uuid.uuid4().hex}_{safe_name}"
    path = COMPOSE_UPLOADS_DIR / token
    path.write_bytes(pdf_bytes)
    return token


def _send_via_host(
    *,
    to: str,
    subject: str,
    body: str,
    body_html: str | None,
    account_id: str | None,
    owner: str,
    attachment_token: str,
) -> dict[str, Any]:
    """Build MIME and deliver through host SMTP helpers (same stack as /api/email/send)."""
    from routes.email_helpers import (
        _attach_compose_uploads,
        _cleanup_compose_uploads,
        _envelope_recipients,
        _normalize_addr_field,
        _send_smtp_message,
    )
    from routes.email_routes import _resolve_send_config, _md_to_email_html, _sanitize_email_html

    try:
        cfg = _resolve_send_config(account_id, owner=owner)
    except Exception as exc:
        raise InvoiceEmailError(str(exc) or "No SMTP-capable email account configured") from exc

    to_norm = _normalize_addr_field(to or "")
    if not to_norm.strip():
        raise InvoiceEmailError("Recipient (to) is required")

    outer = MIMEMultipart("mixed")
    body_container = MIMEMultipart("alternative")
    outer["From"] = formataddr((cfg.get("display_name") or "", cfg["from_address"]))
    outer["To"] = to_norm
    outer["Subject"] = subject
    outer["Message-ID"] = make_msgid(domain="odysseus.local")

    body_container.attach(MIMEText(body or "", "plain", "utf-8"))
    html = (_sanitize_email_html(body_html) if body_html else None) or _md_to_email_html(body or "")
    body_container.attach(MIMEText(html, "html", "utf-8"))
    outer.attach(body_container)
    _attach_compose_uploads(outer, [attachment_token])

    recipients = _envelope_recipients(to_norm, "", "")
    try:
        _send_smtp_message(cfg, cfg["from_address"], recipients, outer.as_string())
    except Exception as exc:
        _cleanup_compose_uploads([attachment_token])
        raise InvoiceEmailError(str(exc) or "SMTP send failed") from exc
    _cleanup_compose_uploads([attachment_token])
    return {
        "ok": True,
        "message_id": outer["Message-ID"],
        "from_address": cfg["from_address"],
    }


def send_invoice_email(
    invoice_id: int,
    *,
    to: str | None = None,
    subject: str | None = None,
    body: str | None = None,
    body_html: str | None = None,
    account_id: str | None = None,
    owner: str = "",
    send_fn: Callable[..., dict[str, Any]] | None = None,
    persist_pdf: bool = True,
) -> dict[str, Any]:
    """Generate PDF, attach, send via host mail, set SentAt on success."""
    if persist_pdf:
        pdf_bytes, invoice, doc = invoice_documents.generate_and_persist(invoice_id)
    else:
        from integrations.sysforge.pdf_invoice import generate_invoice_pdf

        pdf_bytes, invoice = generate_invoice_pdf(invoice_id)
        doc = None

    recipient = (to or "").strip()
    if not recipient:
        client = invoice.get("client") or {}
        recipient = (client.get("email") or "").strip()
    if not recipient:
        raise InvoiceEmailError("Recipient (to) is required")

    subj = (subject or "").strip() or _default_subject(invoice)
    plain = body if body is not None else _default_body(invoice)
    file_name = suggested_pdf_filename(invoice)
    token = _stage_compose_upload(pdf_bytes, file_name)

    deliver = send_fn or _send_via_host
    try:
        result = deliver(
            to=recipient,
            subject=subj,
            body=plain,
            body_html=body_html,
            account_id=account_id,
            owner=owner,
            attachment_token=token,
        )
    except InvoiceEmailError:
        raise
    except Exception as exc:
        raise InvoiceEmailError(str(exc) or "Email send failed") from exc

    if not result.get("ok", True) and result.get("error"):
        raise InvoiceEmailError(str(result["error"]))

    updated = mark_invoice_sent(invoice_id)
    return {
        "ok": True,
        "message_id": result.get("message_id"),
        "sent_at": updated.get("sent_at"),
        "status": updated.get("status"),
        "to": recipient,
        "document_id": doc["id"] if doc else None,
        "file_name": file_name,
    }


__all__ = [
    "InvoiceEmailError",
    "InvoiceNotFoundError",
    "mark_invoice_sent",
    "send_invoice_email",
]
