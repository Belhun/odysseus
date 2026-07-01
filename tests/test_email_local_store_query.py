"""Query/pagination tests for the local email store."""

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


def _seed_message(store, *, owner="", account_id="acc1", folder="INBOX", uid=1, date_epoch=1000.0):
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
                owner, account_id, folder, uid, 42,
                f"Subject {uid}", "Alice", "alice@example.com",
                date_epoch, "Mon, 1 Jan 2024 00:00:00 +0000",
                f"snippet {uid}", f"body {uid}", 100,
                0, 0, 0, 0, "2024-01-01T00:00:00",
            ),
        )
        conn.commit()
    finally:
        conn.close()


def test_latest_n_and_offset_paging(local_db):
    store = local_db
    for i in range(25):
        _seed_message(store, uid=i + 1, date_epoch=2000.0 - i)

    page1 = store.query_local_emails("", folder="INBOX", limit=10, offset=0)
    page2 = store.query_local_emails("", folder="INBOX", limit=10, offset=10)

    assert len(page1) == 10
    assert len(page2) == 10
    ids1 = {r["id"] for r in page1}
    ids2 = {r["id"] for r in page2}
    assert ids1.isdisjoint(ids2)

    epochs1 = [r["date_epoch"] for r in page1]
    epochs2 = [r["date_epoch"] for r in page2]
    assert epochs1 == sorted(epochs1, reverse=True)
    assert epochs2 == sorted(epochs2, reverse=True)
    assert page1[0]["date_epoch"] > page2[0]["date_epoch"]


def test_since_until_range(local_db):
    store = local_db
    _seed_message(store, uid=1, date_epoch=1000.0)
    _seed_message(store, uid=2, date_epoch=2000.0)
    _seed_message(store, uid=3, date_epoch=3000.0)

    mid = store.query_local_emails("", folder="INBOX", since=1500.0, until=2500.0)
    assert len(mid) == 1
    assert mid[0]["uid"] == 2


def test_owner_scoping(local_db):
    store = local_db
    _seed_message(store, owner="user-a", uid=1, date_epoch=1000.0)
    _seed_message(store, owner="user-b", uid=2, date_epoch=2000.0)

    rows = store.query_local_emails("user-a", folder="INBOX", limit=10)
    assert len(rows) == 1
    assert rows[0]["uid"] == 1


def test_sent_folder_alias_resolves_stored_name(local_db):
    store = local_db
    _seed_message(
        store,
        folder="[Gmail]/Sent Mail",
        uid=1,
        date_epoch=1000.0,
    )
    rows = store.query_local_emails("", folder="Sent", limit=10)
    assert len(rows) == 1
    assert rows[0]["uid"] == 1
