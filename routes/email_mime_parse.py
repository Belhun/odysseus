"""Sync-only single-pass MIME parsing for the local email mirror.

Behavioral contract: tests/test_email_mime_parse_golden.py. Mirrors
_list_attachments_from_msg,
_extract_text, and _extract_html rules without importing those helpers in
the hot walk loop.
"""

from __future__ import annotations

import email
import email.utils
import html
import re
from dataclasses import dataclass
from datetime import timezone
from typing import Any

from routes.email_helpers import _decode_header


def _html_to_plain(raw_html: str) -> str:
    text = re.sub(r"<br\s*/?>", "\n", raw_html, flags=re.I)
    text = re.sub(r"<[^>]+>", "", text)
    return html.unescape(text).strip()


def _decode_part_payload(part) -> str | None:
    payload = part.get_payload(decode=True)
    if not payload:
        return None
    charset = part.get_content_charset() or "utf-8"
    return payload.decode(charset, errors="replace")


def _is_attached_rfc822(part) -> bool:
    cd = str(part.get("Content-Disposition", "")).lower()
    return part.get_content_type() == "message/rfc822" and (
        "attachment" in cd or part.get_filename()
    )


def _resolve_attachment_filename(part, idx: int, ct: str) -> str:
    filename = part.get_filename()
    if filename:
        filename = _decode_header(filename)
        if ct == "message/rfc822" and not re.search(r"\.[A-Za-z0-9]{1,8}$", filename):
            filename = f"{filename}.eml"
        return filename
    ext = "eml" if ct == "message/rfc822" else (ct.split("/")[-1] if "/" in ct else "bin")
    return f"attachment_{idx}.{ext}"


def _decode_attachment_payload(part, ct: str) -> bytes:
    payload = part.get_payload(decode=True)
    if payload is None and ct == "message/rfc822":
        try:
            payload = part.as_bytes()
        except Exception:
            payload = b""
    if payload is None:
        payload = b""
    return payload


@dataclass(frozen=True)
class AttachmentPart:
    index: int
    filename: str
    content_type: str
    size: int
    is_inline: bool
    payload: bytes | None


@dataclass(frozen=True)
class ParsedMimeForStore:
    message_id: str
    in_reply_to: str
    references_hdr: str
    from_name: str
    from_addr: str
    to_addrs: str
    cc_addrs: str
    subject: str
    date_epoch: float
    date_raw: str
    body_text: str
    body_html: str
    snippet: str
    size: int
    has_attachments: bool
    attachments_meta: list[dict[str, Any]]
    attachment_parts: dict[int, AttachmentPart]


def parse_mime_for_local_store(
    raw_bytes: bytes,
    *,
    snippet_len: int = 300,
) -> ParsedMimeForStore:
    msg = email.message_from_bytes(raw_bytes)
    subject = _decode_header(msg.get("Subject", ""))
    from_raw = _decode_header(msg.get("From", ""))
    from_name, from_addr = email.utils.parseaddr(from_raw)
    to_addrs = _decode_header(msg.get("To", ""))
    cc_addrs = _decode_header(msg.get("Cc", ""))
    date_raw = msg.get("Date", "") or ""
    parsed_date = email.utils.parsedate_to_datetime(date_raw) if date_raw else None
    if parsed_date and parsed_date.tzinfo is None:
        parsed_date = parsed_date.replace(tzinfo=timezone.utc)
    date_epoch = parsed_date.timestamp() if parsed_date else 0.0

    if not msg.is_multipart():
        ct = msg.get_content_type()
        decoded = _decode_part_payload(msg) or ""
        if ct == "text/html":
            body_html = decoded
            body_text = decoded
        else:
            body_text = decoded
            body_html = ""
        snippet = body_text[:snippet_len] if body_text else ""
        return ParsedMimeForStore(
            message_id=(msg.get("Message-ID") or "").strip(),
            in_reply_to=(msg.get("In-Reply-To") or "").strip(),
            references_hdr=(msg.get("References") or "").strip(),
            from_name=from_name or from_addr,
            from_addr=from_addr,
            to_addrs=to_addrs,
            cc_addrs=cc_addrs,
            subject=subject or "(no subject)",
            date_epoch=date_epoch,
            date_raw=date_raw,
            body_text=body_text,
            body_html=body_html,
            snippet=snippet,
            size=len(raw_bytes),
            has_attachments=False,
            attachments_meta=[],
            attachment_parts={},
        )

    plain_parts: list[str] = []
    html_payload: str | None = None
    attachments: list[AttachmentPart] = []
    att_idx = 0

    for part in msg.walk():
        if part.is_multipart() and not _is_attached_rfc822(part):
            continue
        cd = str(part.get("Content-Disposition", "")).lower()
        ct = part.get_content_type()
        if ct in ("text/plain", "text/html") and "attachment" not in cd:
            decoded = _decode_part_payload(part)
            if ct == "text/plain" and decoded:
                plain_parts.append(decoded)
            elif ct == "text/html" and html_payload is None and decoded:
                html_payload = decoded
            continue
        filename = _resolve_attachment_filename(part, att_idx, ct)
        payload = _decode_attachment_payload(part, ct)
        attachments.append(
            AttachmentPart(
                index=att_idx,
                filename=filename,
                content_type=ct,
                size=len(payload),
                is_inline="inline" in cd,
                payload=payload,
            )
        )
        att_idx += 1

    body_html = html_payload or ""
    if plain_parts:
        body_text = "\n".join(plain_parts)
    elif html_payload:
        body_text = _html_to_plain(html_payload)
    else:
        body_text = _decode_part_payload(msg) or ""

    if body_text:
        snippet = body_text[:snippet_len]
    elif body_html:
        snippet = _html_to_plain(body_html)[:snippet_len]
    else:
        snippet = ""

    attachments_meta = [
        {
            "index": p.index,
            "filename": p.filename,
            "content_type": p.content_type,
            "size": p.size,
            "is_inline": p.is_inline,
        }
        for p in attachments
    ]
    attachment_parts = {p.index: p for p in attachments}

    return ParsedMimeForStore(
        message_id=(msg.get("Message-ID") or "").strip(),
        in_reply_to=(msg.get("In-Reply-To") or "").strip(),
        references_hdr=(msg.get("References") or "").strip(),
        from_name=from_name or from_addr,
        from_addr=from_addr,
        to_addrs=to_addrs,
        cc_addrs=cc_addrs,
        subject=subject or "(no subject)",
        date_epoch=date_epoch,
        date_raw=date_raw,
        body_text=body_text,
        body_html=body_html,
        snippet=snippet,
        size=len(raw_bytes),
        has_attachments=bool(attachments),
        attachments_meta=attachments_meta,
        attachment_parts=attachment_parts,
    )
