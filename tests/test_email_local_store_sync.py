"""Sync pipeline tests for the local email store (fake IMAP)."""

from __future__ import annotations

import email
from email.mime.application import MIMEApplication
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

import pytest


def _make_message(subject: str, body: str = "hello", attachment: bytes | None = None) -> bytes:
    if attachment is None:
        msg = MIMEText(body, "plain", "utf-8")
        msg["Subject"] = subject
        msg["From"] = "bob@example.com"
        msg["To"] = "alice@example.com"
        msg["Date"] = "Mon, 1 Jan 2024 12:00:00 +0000"
        return msg.as_bytes()
    outer = MIMEMultipart()
    outer["Subject"] = subject
    outer["From"] = "bob@example.com"
    outer["To"] = "alice@example.com"
    outer["Date"] = "Mon, 1 Jan 2024 12:00:00 +0000"
    outer.attach(MIMEText(body, "plain", "utf-8"))
    part = MIMEApplication(attachment, Name="file.bin")
    part.add_header("Content-Disposition", "attachment", filename="file.bin")
    outer.attach(part)
    return outer.as_bytes()


class FakeIMAP:
    def __init__(self, messages: dict[int, bytes], uidvalidity: int = 100):
        self.messages = dict(messages)
        self.uidvalidity = uidvalidity
        self.flags: dict[int, str] = {uid: "" for uid in messages}
        self.logged_out = False
        self.readonly = True

    def login(self, user, password):
        return "OK", [b"logged in"]

    def select(self, folder, readonly=True):
        self.readonly = bool(readonly)
        return "OK", [str(len(self.messages)).encode()]

    def response(self, code):
        if str(code).upper() == "UIDVALIDITY":
            return "UIDVALIDITY", [str(self.uidvalidity).encode()]
        return "NO", [None]

    def uid(self, cmd, arg1, arg2=None, arg3=None):
        if cmd == "SEARCH":
            uids = sorted(self.messages.keys())
            payload = b" ".join(str(u).encode() for u in uids) if uids else b""
            return "OK", [payload]
        if cmd == "FETCH":
            uid_spec = arg1.decode() if isinstance(arg1, bytes) else str(arg1)
            want_flags_only = arg2 == "(FLAGS)" or (isinstance(arg2, str) and arg2 == "(FLAGS)")
            uids = [int(x) for x in uid_spec.split(",") if x.strip().isdigit()]
            out = []
            for uid in uids:
                if uid not in self.messages:
                    continue
                flags = self.flags.get(uid, "")
                if want_flags_only:
                    meta = f"{uid} (UID {uid} FLAGS ({flags}))".encode()
                    out.append((meta, None))
                else:
                    raw = self.messages[uid]
                    meta = f"{uid} (UID {uid} FLAGS ({flags}) RFC822 {{{len(raw)}}}".encode()
                    out.append((meta, raw))
                    out.append(b")")
            return "OK", out
        if cmd == "STORE":
            if self.readonly:
                return "NO", [b"readonly"]
            uid_spec = arg1.decode() if isinstance(arg1, bytes) else str(arg1)
            op = arg2
            flag = arg3.decode() if isinstance(arg3, bytes) else str(arg3)
            uid = int(uid_spec)
            if uid not in self.messages:
                return "NO", [b"missing"]
            current = self.flags.get(uid, "")
            parts = [p for p in current.split() if p]
            if op == "+FLAGS" and flag not in parts:
                parts.append(flag)
            elif op == "-FLAGS" and flag in parts:
                parts.remove(flag)
            self.flags[uid] = " ".join(parts)
            meta = f"{uid} (UID {uid} FLAGS ({self.flags[uid]}))".encode()
            return "OK", [(meta, None)]
        return "NO", [b""]

    def logout(self):
        self.logged_out = True


@pytest.fixture()
def local_db(tmp_path, monkeypatch):
    db_path = tmp_path / "email_store.db"
    att_dir = tmp_path / "mail-attachments"
    att_dir.mkdir()
    monkeypatch.setattr("routes.email_local_store.LOCAL_STORE_DB", db_path)
    monkeypatch.setattr("routes.email_local_store.DATA_DIR", tmp_path)
    monkeypatch.setattr("routes.email_local_store.ATTACHMENTS_DIR", att_dir)
    monkeypatch.setattr("routes.email_helpers.ATTACHMENTS_DIR", att_dir)
    import routes.email_local_store as store

    store._init_local_store_db()
    return store


def test_read_uidvalidity_from_imaplib_response(local_db):
    store = local_db

    class ImaplibStyleFake:
        uidvalidity = 424242

        def response(self, code):
            if str(code).upper() == "UIDVALIDITY":
                return "UIDVALIDITY", [b"424242"]
            return "NO", [None]

        def status(self, folder, parts):
            return "OK", [f'{folder} (UIDVALIDITY {self.uidvalidity})'.encode()]

    fake = ImaplibStyleFake()
    assert store._read_uidvalidity(fake, [b"49133"]) == 424242
    assert store._read_uidvalidity(fake, [], "INBOX") == 424242


def test_upsert_dedup_on_resync(local_db, monkeypatch):
    store = local_db
    msgs = {5: _make_message("First")}
    fake = FakeIMAP(msgs)

    monkeypatch.setattr(store, "_imap_connect", lambda account_id, owner="": fake)

    r1 = store.sync_account_folder("acc1", "INBOX", "", backfill_batch=10, full=True)
    assert r1["error"] is None
    assert r1["new"] >= 1

    conn = store._connect()
    count1 = conn.execute("SELECT COUNT(*) FROM messages").fetchone()[0]
    conn.close()
    assert count1 == 1

    r2 = store.sync_account_folder("acc1", "INBOX", "", backfill_batch=10, full=True)
    conn = store._connect()
    count2 = conn.execute("SELECT COUNT(*) FROM messages").fetchone()[0]
    conn.close()
    assert count2 == 1
    assert r2["new"] == 0


def test_uidvalidity_change_purges_and_reloads(local_db, monkeypatch):
    store = local_db
    msgs = {1: _make_message("Old")}
    fake = FakeIMAP(msgs, uidvalidity=10)
    monkeypatch.setattr(store, "_imap_connect", lambda account_id, owner="": fake)

    store.sync_account_folder("acc1", "INBOX", "", backfill_batch=10, full=True)
    fake.uidvalidity = 99
    fake.messages = {2: _make_message("New")}
    fake.flags = {2: ""}

    store.sync_account_folder("acc1", "INBOX", "", backfill_batch=10, full=True)
    conn = store._connect()
    rows = conn.execute("SELECT uid, subject FROM messages").fetchall()
    conn.close()
    assert len(rows) == 1
    assert rows[0][0] == 2
    assert rows[0][1] == "New"


def test_backfill_batch_limits_older_per_pass(local_db, monkeypatch):
    store = local_db
    msgs = {i: _make_message(f"Msg {i}") for i in range(1, 11)}
    fake = FakeIMAP(msgs)
    monkeypatch.setattr(store, "_imap_connect", lambda account_id, owner="": fake)

    r1 = store.sync_account_folder("acc1", "INBOX", "", backfill_batch=3, full=False)
    assert r1["new"] == 3
    assert r1["backfilled"] == 3
    # forward (3) + backfill (3) + gap repair (3) in one incremental pass
    assert r1["stored"] == 9
    assert r1["backfill_complete"] is False

    r2 = store.sync_account_folder("acc1", "INBOX", "", backfill_batch=3, full=False)
    assert r2["new"] == 0
    assert r2["backfilled"] == 1
    conn = store._connect()
    total = conn.execute("SELECT COUNT(*) FROM messages").fetchone()[0]
    conn.close()
    assert total == 10
    assert r2["backfill_complete"] is True


def test_refresh_flags_without_body_refetch(local_db, monkeypatch):
    store = local_db
    msgs = {7: _make_message("Flag test")}
    fake = FakeIMAP(msgs)
    fake.flags[7] = ""
    monkeypatch.setattr(store, "_imap_connect", lambda account_id, owner="": fake)

    store.sync_account_folder("acc1", "INBOX", "", backfill_batch=10, full=True)
    conn = store._connect()
    assert conn.execute("SELECT is_read FROM messages WHERE uid=7").fetchone()[0] == 0
    conn.close()

    fake.flags[7] = "\\Seen"
    updated = store.refresh_flags(fake, "INBOX", "", "acc1", window=10)
    assert updated >= 1

    conn = store._connect()
    assert conn.execute("SELECT is_read FROM messages WHERE uid=7").fetchone()[0] == 1
    conn.close()


def test_sync_flags_pushes_local_read_to_imap(local_db, monkeypatch):
    store = local_db
    msgs = {8: _make_message("Push read")}
    fake = FakeIMAP(msgs)
    fake.flags[8] = ""
    monkeypatch.setattr(store, "_imap_connect", lambda account_id, owner="": fake)

    store.sync_account_folder("acc1", "INBOX", "", backfill_batch=10, full=True)
    conn = store._connect()
    conn.execute("UPDATE messages SET is_read=1 WHERE uid=8")
    conn.commit()
    conn.close()
    assert fake.flags[8] == ""

    result = store.sync_flags(fake, "INBOX", "", "acc1", window=10)
    assert result["pushed"] >= 1
    assert "\\Seen" in fake.flags[8]

    conn = store._connect()
    assert conn.execute("SELECT is_read FROM messages WHERE uid=8").fetchone()[0] == 1
    assert conn.execute("SELECT read_dirty FROM messages WHERE uid=8").fetchone()[0] == 0
    conn.close()


def test_sync_flags_pulls_imap_read_without_dirty(local_db, monkeypatch):
    store = local_db
    msgs = {9: _make_message("Pull read")}
    fake = FakeIMAP(msgs)
    fake.flags[9] = "\\Seen"
    monkeypatch.setattr(store, "_imap_connect", lambda account_id, owner="": fake)

    store.sync_account_folder("acc1", "INBOX", "", backfill_batch=10, full=True)
    conn = store._connect()
    conn.execute("UPDATE messages SET is_read=0, read_dirty=0 WHERE uid=9")
    conn.commit()
    conn.close()

    result = store.sync_flags(fake, "INBOX", "", "acc1", window=10)
    assert result["pushed"] == 0
    assert result["pulled"] >= 1

    conn = store._connect()
    assert conn.execute("SELECT is_read FROM messages WHERE uid=9").fetchone()[0] == 1
    conn.close()


def test_sync_flags_pushes_dirty_unread_to_imap(local_db, monkeypatch):
    store = local_db
    msgs = {10: _make_message("Push unread")}
    fake = FakeIMAP(msgs)
    fake.flags[10] = "\\Seen"
    monkeypatch.setattr(store, "_imap_connect", lambda account_id, owner="": fake)

    store.sync_account_folder("acc1", "INBOX", "", backfill_batch=10, full=True)
    store.set_local_read_state("", "acc1", "INBOX", 10, False, dirty=True)

    result = store.sync_flags(fake, "INBOX", "", "acc1", window=10)
    assert result["pushed"] >= 1
    assert fake.flags[10] == ""

    conn = store._connect()
    assert conn.execute("SELECT is_read FROM messages WHERE uid=10").fetchone()[0] == 0
    conn.close()


def test_attachment_written_and_oversized_skipped(local_db, monkeypatch, tmp_path):
    store = local_db
    small = b"x" * 100
    big = b"y" * 2000
    msgs = {
        1: _make_message("With att", attachment=small),
        2: _make_message("Big att", attachment=big),
    }
    fake = FakeIMAP(msgs)
    monkeypatch.setattr(store, "_imap_connect", lambda account_id, owner="": fake)

    store.sync_account_folder(
        "acc1", "INBOX", "",
        backfill_batch=10,
        full=True,
        max_attachment_bytes=500,
        attachment_budget_bytes=10_000,
    )
    conn = store._connect()
    rows = conn.execute(
        "SELECT m.uid, a.local_path, a.skipped_reason FROM attachments a "
        "JOIN messages m ON m.id=a.message_row_id ORDER BY m.uid"
    ).fetchall()
    conn.close()

    assert len(rows) == 2
    assert rows[0][1] is not None
    assert rows[0][2] is None
    assert rows[1][1] is None
    assert rows[1][2] == "too_large"


def test_full_backfill_terminates_after_incremental(local_db, monkeypatch):
    """Regression: full=True must not loop forever when sync_state has stale min_uid."""
    store = local_db
    msgs = {i: _make_message(f"Msg {i}") for i in range(1, 11)}
    fake = FakeIMAP(msgs)
    monkeypatch.setattr(store, "_imap_connect", lambda account_id, owner="": fake)

    store.sync_account_folder("acc1", "INBOX", "", backfill_batch=3, full=False)
    conn = store._connect()
    conn.execute(
        """
        INSERT INTO sync_state (owner, account_id, folder, uidvalidity, min_uid, max_uid, backfill_complete)
        VALUES ('', 'acc1', 'INBOX', 100, 4, 10, 0)
        ON CONFLICT(owner, account_id, folder) DO UPDATE SET min_uid=4, max_uid=10
        """,
    )
    conn.commit()
    conn.close()

    r = store.sync_account_folder("acc1", "INBOX", "", backfill_batch=3, full=True)
    assert r["error"] is None
    conn = store._connect()
    total = conn.execute("SELECT COUNT(*) FROM messages").fetchone()[0]
    conn.close()
    assert total == 10
    assert r.get("backfill_complete") is True


def test_gap_repair_fills_missing_interior_uid(local_db, monkeypatch):
    store = local_db
    msgs = {i: _make_message(f"Msg {i}") for i in range(1, 11)}
    fake = FakeIMAP(msgs)
    monkeypatch.setattr(store, "_imap_connect", lambda account_id, owner="": fake)

    store.sync_account_folder("acc1", "INBOX", "", backfill_batch=20, full=True)
    conn = store._connect()
    conn.execute("DELETE FROM messages WHERE uid=6")
    conn.commit()
    conn.close()

    r = store.sync_account_folder("acc1", "INBOX", "", backfill_batch=5, full=False)
    assert r["error"] is None
    assert r["stored"] >= 1

    conn = store._connect()
    row = conn.execute("SELECT uid FROM messages WHERE uid=6").fetchone()
    total = conn.execute("SELECT COUNT(*) FROM messages").fetchone()[0]
    conn.close()
    assert row is not None
    assert total == 10
    assert r.get("backfill_complete") is True


def test_uidvalidity_purge_without_sync_state(local_db, monkeypatch):
    store = local_db
    conn = store._connect()
    conn.execute(
        """
        INSERT INTO messages (
            owner, account_id, folder, uid, uidvalidity, subject,
            from_name, from_addr, date_epoch, date_raw, snippet, body_text,
            size, is_read, is_answered, is_flagged, has_attachments, synced_at
        ) VALUES ('', 'acc1', 'INBOX', 1, 10, 'Orphan', 'Bob', 'bob@example.com',
                  1000, '', 's', 'b', 10, 0, 0, 0, 0, '2024-01-01')
        """,
    )
    conn.commit()
    conn.close()

    msgs = {2: _make_message("New")}
    fake = FakeIMAP(msgs, uidvalidity=99)
    monkeypatch.setattr(store, "_imap_connect", lambda account_id, owner="": fake)

    store.sync_account_folder("acc1", "INBOX", "", backfill_batch=10, full=True)
    conn = store._connect()
    rows = conn.execute("SELECT uid, uidvalidity FROM messages").fetchall()
    conn.close()
    assert len(rows) == 1
    assert rows[0][0] == 2
    assert rows[0][1] == 99


def test_purge_unlinks_attachment_files(local_db, monkeypatch, tmp_path):
    store = local_db
    small = b"x" * 100
    msgs = {1: _make_message("With att", attachment=small)}
    fake = FakeIMAP(msgs)
    monkeypatch.setattr(store, "_imap_connect", lambda account_id, owner="": fake)

    store.sync_account_folder("acc1", "INBOX", "", backfill_batch=10, full=True)
    conn = store._connect()
    path = conn.execute("SELECT local_path FROM attachments").fetchone()[0]
    conn.close()
    assert path and Path(path).exists()

    conn = store._connect()
    store._purge_folder(conn, "", "acc1", "INBOX")
    conn.commit()
    conn.close()
    assert not Path(path).exists()


def test_dotdot_attachment_name_rejected(local_db, tmp_path, monkeypatch):
    store = local_db
    outer = MIMEMultipart()
    outer["Subject"] = "Traversal"
    outer["From"] = "bob@example.com"
    outer["To"] = "alice@example.com"
    outer.attach(MIMEText("body", "plain"))
    part = MIMEApplication(b"evil", Name="..")
    part.add_header("Content-Disposition", "attachment", filename="..")
    outer.attach(part)
    msgs = {9: outer.as_bytes()}
    fake = FakeIMAP(msgs)
    monkeypatch.setattr(store, "_imap_connect", lambda account_id, owner="": fake)

    store.sync_account_folder("acc1", "INBOX", "", backfill_batch=5, full=True)
    conn = store._connect()
    row = conn.execute(
        "SELECT local_path, filename FROM attachments"
    ).fetchone()
    conn.close()
    assert row is not None
    assert ".." not in (row[0] or "")
    assert row[1] == ".."
