"""Source guard and unit tests for local store IMAP fetch."""

from __future__ import annotations

from pathlib import Path

from routes.email_helpers import _group_uid_fetch_records, _uid_from_fetch_meta
from routes.email_local_store import _parse_body_fetch_grouped

GMAIL_BODY_RESPONSE = [
    (b"1 (UID 1 BODY.PEEK[] {11}", b"hello world"),
    b" FLAGS (\\Seen))",
]


def test_no_rfc822_full_fetch_in_local_store():
    text = Path("routes/email_local_store.py").read_text(encoding="utf-8")
    assert '"(RFC822 FLAGS)"' not in text
    assert "BODY.PEEK[]" in text


def test_parse_body_fetch_grouped_gmail_flags():
    grouped = _parse_body_fetch_grouped(GMAIL_BODY_RESPONSE)
    assert len(grouped) == 1
    uid, flags, raw = grouped[0]
    assert uid == 1
    assert raw == b"hello world"
    assert "\\Seen" in flags


def test_group_uid_fetch_records_gmail():
    grouped = _group_uid_fetch_records(GMAIL_BODY_RESPONSE)
    assert len(grouped) == 1
    meta_b, payload = grouped[0]
    assert _uid_from_fetch_meta(meta_b) == "1"
    assert payload == b"hello world"
    assert b"\\Seen" in meta_b
