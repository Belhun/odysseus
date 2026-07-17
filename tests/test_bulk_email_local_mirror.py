"""bulk_email dual-writes live IMAP changes into the local mirror."""

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


def _seed(store, *, owner="alice", account_id="acc1", uid=1, subject="Hello", is_read=0):
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
                owner, account_id, "INBOX", uid, 42,
                subject, "Alice", "alice@example.com",
                1000.0, "Mon, 1 Jan 2024 00:00:00 +0000",
                subject[:40], "body", 100,
                is_read, 0, 0, 0, "2024-01-01T00:00:00",
            ),
        )
        conn.commit()
    finally:
        conn.close()


def test_mirror_imap_read_state_bulk(local_db):
    from routes.email_local_store import mirror_imap_read_state_bulk

    _seed(local_db, uid=1, is_read=0)
    _seed(local_db, uid=2, is_read=0)
    _seed(local_db, uid=3, is_read=0)
    n = mirror_imap_read_state_bulk("alice", "acc1", "INBOX", [1, 2], True)
    assert n == 2
    conn = local_db._connect()
    try:
        rows = {
            int(r["uid"]): int(r["is_read"])
            for r in conn.execute(
                "SELECT uid, is_read FROM messages WHERE owner=? ORDER BY uid",
                ("alice",),
            )
        }
    finally:
        conn.close()
    assert rows == {1: 1, 2: 1, 3: 0}


def test_mirror_imap_remove_messages(local_db):
    from routes.email_local_store import mirror_imap_remove_messages

    _seed(local_db, uid=10, subject="keep")
    _seed(local_db, uid=11, subject="gone-a")
    _seed(local_db, uid=12, subject="gone-b")
    n = mirror_imap_remove_messages("alice", "acc1", "INBOX", ["11", "12"])
    assert n == 2
    conn = local_db._connect()
    try:
        remaining = [
            int(r["uid"])
            for r in conn.execute(
                "SELECT uid FROM messages WHERE owner=? ORDER BY uid",
                ("alice",),
            )
        ]
    finally:
        conn.close()
    assert remaining == [10]


def test_mirror_bulk_local_mark_and_archive(local_db, monkeypatch):
    import mcp_servers.email_server as es

    _seed(local_db, uid=21, is_read=0)
    _seed(local_db, uid=22, is_read=0)
    monkeypatch.setattr(es, "_current_owner", lambda: "alice")
    monkeypatch.setattr(
        es,
        "_load_config",
        lambda account=None: {"account_id": "acc1", "archive_folder": "Archive"},
    )

    marked = es._mirror_local("mark_read", [21, 22], "INBOX", account="acc1")
    assert marked == 2
    removed = es._mirror_local("archive", [21], "INBOX", account="acc1")
    assert removed == 1

    conn = local_db._connect()
    try:
        rows = {
            int(r["uid"]): r["folder"]
            for r in conn.execute("SELECT uid, folder, is_read FROM messages WHERE owner=?", ("alice",))
        }
        read_flags = {
            int(r["uid"]): int(r["is_read"])
            for r in conn.execute("SELECT uid, is_read FROM messages WHERE owner=?", ("alice",))
        }
    finally:
        conn.close()
    assert rows[21] == "Archive"
    assert rows[22] == "INBOX"
    assert read_flags[21] == 1
    assert read_flags[22] == 1


def test_archive_moves_into_archive_folder_even_if_imap_fails(local_db, monkeypatch):
    import mcp_servers.email_server as es
    from routes.email_local_store import list_local_folders

    _seed(local_db, uid=40, subject="keep me")
    monkeypatch.setattr(es, "_current_owner", lambda: "alice")
    monkeypatch.setattr(
        es,
        "_load_config",
        lambda account=None: {"account_id": "acc1", "archive_folder": "Archive"},
    )
    n = es._mirror_local("archive", [40], "INBOX", account="acc1", imap_ok=False)
    assert n == 1
    conn = local_db._connect()
    try:
        row = conn.execute(
            "SELECT folder FROM messages WHERE owner=? AND uid=?",
            ("alice", 40),
        ).fetchone()
    finally:
        conn.close()
    assert row["folder"] == "Archive"
    assert "Archive" in list_local_folders("alice", "acc1")


def test_single_tool_handlers_mirror_local(local_db, monkeypatch):
    """archive/delete/mark_email_read update the local mirror after IMAP success."""
    import mcp_servers.email_server as es

    _seed(local_db, uid=31, is_read=0)
    _seed(local_db, uid=32, is_read=0)
    _seed(local_db, uid=33, is_read=0)

    monkeypatch.setattr(es, "_current_owner", lambda: "alice")
    monkeypatch.setattr(
        es,
        "_load_config",
        lambda account=None: {
            "account_id": "acc1",
            "archive_folder": "Archive",
            "trash_folder": "Trash",
        },
    )
    monkeypatch.setattr(es, "_archive_email", lambda *a, **k: True)
    monkeypatch.setattr(es, "_delete_email", lambda *a, **k: True)
    monkeypatch.setattr(es, "_set_flag", lambda *a, **k: True)

    assert es._set_flag("31", "INBOX", "\\Seen", add=True, account="acc1")
    es._mirror_local("mark_read", ["31"], "INBOX", account="acc1", imap_ok=True)
    assert es._archive_email("32", "INBOX", account="acc1")
    es._mirror_local("archive", ["32"], "INBOX", account="acc1", imap_ok=True)
    assert es._delete_email("33", "INBOX", permanent=False, account="acc1")
    es._mirror_local("delete", ["33"], "INBOX", account="acc1", permanent=False, imap_ok=True)

    conn = local_db._connect()
    try:
        rows = {
            int(r["uid"]): (r["folder"], int(r["is_read"]))
            for r in conn.execute(
                "SELECT uid, folder, is_read FROM messages WHERE owner=? ORDER BY uid",
                ("alice",),
            )
        }
    finally:
        conn.close()
    assert rows[31] == ("INBOX", 1)
    assert rows[32] == ("Archive", 0)
    assert rows[33] == ("Trash", 0)
