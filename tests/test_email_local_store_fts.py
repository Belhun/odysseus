"""FTS search tests for the local email store."""

from __future__ import annotations

import pytest


@pytest.fixture()
def local_db(tmp_path, monkeypatch):
    db_path = tmp_path / "email_store.db"
    monkeypatch.setattr("routes.email_local_store.LOCAL_STORE_DB", db_path)
    monkeypatch.setattr("routes.email_local_store.DATA_DIR", tmp_path)
    import routes.email_local_store as store

    store._init_local_store_db()
    return store


def _insert(store, *, owner="", uid=1, subject="", body="", from_addr="a@example.com"):
    conn = store._connect()
    try:
        conn.execute(
            """
            INSERT INTO messages (
                owner, account_id, folder, uid, uidvalidity,
                subject, from_name, from_addr, date_epoch, date_raw,
                snippet, body_text, size, is_read, is_answered, is_flagged,
                has_attachments, synced_at
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                owner, "acc1", "INBOX", uid, 42,
                subject, "Alice", from_addr,
                2000.0 - uid, "Mon, 1 Jan 2024 00:00:00 +0000",
                subject[:80], body, 50,
                0, 0, 0, 0, "2024-01-01T00:00:00",
            ),
        )
        conn.commit()
    finally:
        conn.close()


def test_fts_backfill_and_search(local_db):
    store = local_db
    _insert(store, uid=1, subject="Quarterly report", body="Revenue grew")
    _insert(store, uid=2, subject="Team lunch", body="Pizza Friday")

    emails, total, folder = store.search_local_emails("", "report", folder="INBOX")
    assert folder == "INBOX"
    assert total >= 1
    assert any("report" in (e.get("subject") or "").lower() for e in emails)
    assert not any("lunch" in (e.get("subject") or "").lower() for e in emails)


def test_fts_owner_scoping(local_db):
    store = local_db
    _insert(store, owner="user-a", uid=1, subject="secret project alpha")
    _insert(store, owner="user-b", uid=2, subject="secret project beta")

    emails, total, _ = store.search_local_emails("user-a", "secret", folder="INBOX")
    assert total == 1
    assert emails[0]["subject"] == "secret project alpha"


def test_fts_like_fallback_when_no_match(local_db):
    store = local_db
    _insert(store, uid=1, subject="XYZZY uncommon token", body="nothing else")

    emails, total, _ = store.search_local_emails("", "XYZZY", folder="INBOX")
    assert total == 1
    assert emails[0]["uid"] == "1"


def test_normalize_local_list_row_shape(local_db):
    store = local_db
    _insert(store, uid=5, subject="Shape test")
    rows = store.query_local_emails("", folder="INBOX", limit=1)
    normalized = store.normalize_local_list_row(rows[0], "INBOX")
    assert "from_address" in normalized
    assert "date_display" in normalized
    assert "folder" in normalized
    assert normalized["from_address"] == "a@example.com"
