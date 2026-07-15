"""Golden tests: parse_mime_for_local_store matches legacy sync parser."""

from __future__ import annotations

import hashlib
from email.header import Header
from email.mime.application import MIMEApplication
from email.mime.image import MIMEImage
from email.mime.message import MIMEMessage
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import pytest

from routes.email_local_store import _parse_message_for_store
from routes.email_mime_parse import parse_mime_for_local_store


def _sha256(data: bytes | None) -> str:
    if not data:
        return ""
    return hashlib.sha256(data).hexdigest()


def _legacy_attachment_payload(msg, index: int) -> bytes | None:
    from routes.email_helpers import _iter_attachment_parts

    for idx, _part, _name, payload in _iter_attachment_parts(msg):
        if idx == index:
            return payload
    return None


def _baseline(raw: bytes) -> dict:
    parsed = _parse_message_for_store(raw)
    msg = parsed.get("msg")
    attachment_hashes = {}
    for meta in parsed.get("attachments_meta") or []:
        idx = meta["index"]
        if parsed.get("attachment_parts"):
            part = parsed["attachment_parts"][idx]
            attachment_hashes[str(idx)] = _sha256(part.payload)
        elif msg is not None:
            attachment_hashes[str(idx)] = _sha256(_legacy_attachment_payload(msg, idx))
        elif meta.get("_payload") is not None:
            attachment_hashes[str(idx)] = _sha256(meta["_payload"])
    return {
        "body_text": parsed["body_text"],
        "body_html": parsed["body_html"],
        "snippet": parsed["snippet"],
        "subject": parsed["subject"],
        "from_addr": parsed["from_addr"],
        "has_attachments": parsed["has_attachments"],
        "attachments_meta": [
            {k: v for k, v in m.items() if k != "_payload"}
            for m in (parsed.get("attachments_meta") or [])
        ],
        "attachment_payload_sha256": attachment_hashes,
    }


def _fixture_plain_only() -> bytes:
    msg = MIMEText("Hello plain world", "plain", "utf-8")
    msg["Subject"] = "Plain only"
    msg["From"] = "bob@example.com"
    msg["To"] = "alice@example.com"
    msg["Date"] = "Mon, 1 Jan 2024 12:00:00 +0000"
    return msg.as_bytes()


def _fixture_html_only() -> bytes:
    outer = MIMEMultipart("alternative")
    outer["Subject"] = "HTML only"
    outer["From"] = "bob@example.com"
    outer["To"] = "alice@example.com"
    outer["Date"] = "Mon, 1 Jan 2024 12:00:00 +0000"
    outer.attach(MIMEText("<p>Hello <b>HTML</b></p>", "html"))
    return outer.as_bytes()


def _fixture_plain_and_html() -> bytes:
    outer = MIMEMultipart("alternative")
    outer["Subject"] = "Both"
    outer["From"] = "bob@example.com"
    outer["To"] = "alice@example.com"
    outer["Date"] = "Mon, 1 Jan 2024 12:00:00 +0000"
    outer.attach(MIMEText("plain body", "plain"))
    outer.attach(MIMEText("<p>html body</p>", "html"))
    return outer.as_bytes()


def _fixture_single_attachment() -> bytes:
    outer = MIMEMultipart()
    outer["Subject"] = "One file"
    outer["From"] = "bob@example.com"
    outer["To"] = "alice@example.com"
    outer["Date"] = "Mon, 1 Jan 2024 12:00:00 +0000"
    outer.attach(MIMEText("see file", "plain"))
    part = MIMEApplication(b"payload-bytes", Name="file.bin")
    part.add_header("Content-Disposition", "attachment", filename="file.bin")
    outer.attach(part)
    return outer.as_bytes()


def _fixture_charset_iso8859_plain() -> bytes:
    text = "caf\u00e9 r\u00e9sum\u00e9"
    msg = MIMEText(text.encode("iso-8859-1"), "plain", "iso-8859-1")
    msg["Subject"] = "Charset"
    msg["From"] = "bob@example.com"
    msg["To"] = "alice@example.com"
    msg["Date"] = "Mon, 1 Jan 2024 12:00:00 +0000"
    return msg.as_bytes()


def _fixture_rfc2047_subject_and_filename() -> bytes:
    outer = MIMEMultipart()
    outer["Subject"] = str(Header("S\u00fcbject", "utf-8"))
    outer["From"] = "bob@example.com"
    outer["To"] = "alice@example.com"
    outer["Date"] = "Mon, 1 Jan 2024 12:00:00 +0000"
    outer.attach(MIMEText("body", "plain"))
    encoded_name = str(Header("r\u00e9sum\u00e9.pdf", "utf-8"))
    part = MIMEApplication(b"pdf-bytes", Name="resume.pdf")
    part.add_header("Content-Disposition", "attachment", filename=encoded_name)
    outer.attach(part)
    return outer.as_bytes()


def _fixture_inline_image_skipped() -> bytes:
    related = MIMEMultipart("related")
    related["Subject"] = "Inline logo"
    related["From"] = "bob@example.com"
    related["To"] = "alice@example.com"
    related["Date"] = "Mon, 1 Jan 2024 12:00:00 +0000"
    related.attach(MIMEText("see logo", "plain"))
    img = MIMEImage(b"fake-png-bytes", _subtype="png")
    img.add_header("Content-Disposition", "inline", filename="logo.png")
    related.attach(img)
    return related.as_bytes()


def _fixture_nested_multipart_related() -> bytes:
    related = MIMEMultipart("related")
    related["Subject"] = "Nested related"
    related["From"] = "bob@example.com"
    related["To"] = "alice@example.com"
    related["Date"] = "Mon, 1 Jan 2024 12:00:00 +0000"
    alternative = MIMEMultipart("alternative")
    alternative.attach(MIMEText("plain part", "plain"))
    alternative.attach(MIMEText("<p>html part</p>", "html"))
    related.attach(alternative)
    return related.as_bytes()


def _fixture_empty_body() -> bytes:
    outer = MIMEMultipart()
    outer["Subject"] = "Empty"
    outer["From"] = "bob@example.com"
    outer["To"] = "alice@example.com"
    outer["Date"] = "Mon, 1 Jan 2024 12:00:00 +0000"
    return outer.as_bytes()


def _fixture_multiple_attachments_order() -> bytes:
    outer = MIMEMultipart()
    outer["Subject"] = "Multiple files"
    outer["From"] = "bob@example.com"
    outer["To"] = "alice@example.com"
    outer["Date"] = "Mon, 1 Jan 2024 12:00:00 +0000"
    outer.attach(MIMEText("see files", "plain"))
    for name, payload in (("first.bin", b"aaa"), ("second.bin", b"bbb")):
        part = MIMEApplication(payload, Name=name)
        part.add_header("Content-Disposition", "attachment", filename=name)
        outer.attach(part)
    return outer.as_bytes()


def _fixture_attached_rfc822() -> bytes:
    outer = MIMEMultipart()
    outer["Subject"] = "Forwarded"
    outer["From"] = "bob@example.com"
    outer["To"] = "alice@example.com"
    outer["Date"] = "Mon, 1 Jan 2024 12:00:00 +0000"
    outer.attach(MIMEText("see attached", "plain"))
    inner = MIMEMultipart("alternative")
    inner.attach(MIMEText("inner", "plain"))
    inner["Subject"] = "Inner"
    rfc822_part = MIMEMessage(inner)
    rfc822_part.add_header("Content-Disposition", "attachment", filename="Forwarded")
    outer.attach(rfc822_part)
    return outer.as_bytes()


FIXTURES = {
    "plain_only": _fixture_plain_only,
    "html_only_alternative": _fixture_html_only,
    "plain_and_html_alternative": _fixture_plain_and_html,
    "single_attachment": _fixture_single_attachment,
    "attached_message_rfc822": _fixture_attached_rfc822,
    "charset_iso8859_plain": _fixture_charset_iso8859_plain,
    "rfc2047_subject_and_filename": _fixture_rfc2047_subject_and_filename,
    "inline_image_skipped": _fixture_inline_image_skipped,
    "nested_multipart_related": _fixture_nested_multipart_related,
    "empty_body": _fixture_empty_body,
    "multiple_attachments_order": _fixture_multiple_attachments_order,
}


@pytest.mark.parametrize("name", sorted(FIXTURES))
def test_golden_matches_legacy_baseline(name, monkeypatch):
    monkeypatch.setattr(
        "src.settings.load_settings",
        lambda: {"email_local_sync_single_pass_mime": False},
    )
    raw = FIXTURES[name]()
    expected = _baseline(raw)
    parsed = parse_mime_for_local_store(raw)
    actual = {
        "body_text": parsed.body_text,
        "body_html": parsed.body_html,
        "snippet": parsed.snippet,
        "subject": parsed.subject,
        "from_addr": parsed.from_addr,
        "has_attachments": parsed.has_attachments,
        "attachments_meta": parsed.attachments_meta,
        "attachment_payload_sha256": {
            str(k): _sha256(v.payload) for k, v in parsed.attachment_parts.items()
        },
    }
    assert actual == expected


def test_single_pass_does_not_call_walk_helpers(monkeypatch):
    import routes.email_helpers as helpers

    def _boom(*args, **kwargs):
        raise AssertionError("legacy walk helper called")

    monkeypatch.setattr(helpers, "_extract_text", _boom)
    monkeypatch.setattr(helpers, "_extract_html", _boom)
    monkeypatch.setattr(helpers, "_list_attachments_from_msg", _boom)
    parse_mime_for_local_store(_fixture_plain_only())


def test_extract_attachments_uses_payloads_not_get_attachment_part(tmp_path, monkeypatch):
    db_path = tmp_path / "email_store.db"
    att_dir = tmp_path / "mail-attachments"
    att_dir.mkdir()
    monkeypatch.setattr("routes.email_local_store.LOCAL_STORE_DB", db_path)
    monkeypatch.setattr("routes.email_local_store.DATA_DIR", tmp_path)
    monkeypatch.setattr("routes.email_local_store.ATTACHMENTS_DIR", att_dir)
    monkeypatch.setattr("routes.email_helpers.ATTACHMENTS_DIR", att_dir)
    import routes.email_local_store as store

    store._init_local_store_db()
    raw = _fixture_single_attachment()
    parsed = parse_mime_for_local_store(raw)
    budget = {"remaining": 1_000_000, "written": 0, "extracted": 0, "skipped": 0}
    rows = store._extract_attachments_for_store(
        None,
        parsed.attachments_meta,
        "INBOX",
        1,
        max_attachment_bytes=52_428_800,
        budget_state=budget,
        attachment_parts=parsed.attachment_parts,
    )
    assert rows[0]["extracted"] == 1
