"""Sync pipeline tests for the local email store (fake IMAP)."""

from __future__ import annotations

import hashlib
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


def _make_alternative_message(subject: str, *, html_only: bool = False) -> bytes:
    outer = MIMEMultipart("alternative")
    outer["Subject"] = subject
    outer["From"] = "bob@example.com"
    outer["To"] = "alice@example.com"
    outer["Date"] = "Mon, 1 Jan 2024 12:00:00 +0000"
    if not html_only:
        outer.attach(MIMEText("plain body", "plain"))
    outer.attach(MIMEText("<p>html body</p>", "html"))
    return outer.as_bytes()


def _sha256_file(path: str | None) -> str:
    if not path:
        return ""
    data = Path(path).read_bytes()
    return hashlib.sha256(data).hexdigest()


def _sync_snapshot(store, db_path: Path) -> dict:
    conn = store._connect()
    messages = {}
    for row in conn.execute(
        """
        SELECT uid, subject, body_text, body_html, snippet, has_attachments
        FROM messages ORDER BY uid
        """
    ).fetchall():
        uid = row[0]
        messages[uid] = {
            "subject": row[1],
            "body_text": row[2],
            "body_html": row[3],
            "snippet": row[4],
            "has_attachments": row[5],
            "attachments": [],
        }
    for row in conn.execute(
        """
        SELECT m.uid, a.idx, a.filename, a.content_type, a.size,
               a.is_inline, a.local_path, a.skipped_reason
        FROM attachments a
        JOIN messages m ON m.id = a.message_row_id
        ORDER BY m.uid, a.idx
        """
    ).fetchall():
        messages[row[0]]["attachments"].append(
            {
                "idx": row[1],
                "filename": row[2],
                "content_type": row[3],
                "size": row[4],
                "is_inline": row[5],
                "local_path_sha256": _sha256_file(row[6]),
                "skipped_reason": row[7],
            }
        )
    conn.close()
    return {"db": str(db_path), "messages": messages}


def _run_sync_with_flag(tmp_path, monkeypatch, messages: dict[int, bytes], *, single_pass: bool):
    suffix = "on" if single_pass else "off"
    db_path = tmp_path / f"email_store_{suffix}.db"
    att_dir = tmp_path / f"mail-attachments_{suffix}"
    att_dir.mkdir()
    monkeypatch.setattr("routes.email_local_store.LOCAL_STORE_DB", db_path)
    monkeypatch.setattr("routes.email_local_store.DATA_DIR", tmp_path)
    monkeypatch.setattr("routes.email_local_store.ATTACHMENTS_DIR", att_dir)
    monkeypatch.setattr("routes.email_helpers.ATTACHMENTS_DIR", att_dir)
    monkeypatch.setattr(
        "src.settings.load_settings",
        lambda: {"email_local_sync_single_pass_mime": single_pass},
    )
    import routes.email_local_store as store

    store._init_local_store_db()
    fake = FakeIMAP(messages)
    monkeypatch.setattr(store, "_imap_connect", lambda account_id, owner="": fake)
    result = store.sync_account_folder("acc1", "INBOX", "", backfill_batch=20, full=True)
    assert result["error"] is None
    return _sync_snapshot(store, db_path)


class FakeIMAP:
    def __init__(self, messages: dict[int, bytes], uidvalidity: int = 100, *, gmail_style: bool = False):
        self.messages = dict(messages)
        self.uidvalidity = uidvalidity
        self.flags: dict[int, str] = {uid: "" for uid in messages}
        self.logged_out = False
        self.readonly = True
        self.gmail_style = gmail_style
        self.search_calls = 0
        self.raise_on_search_after = 0
        self.fetch_failures = 0
        self.reconnect_count = 0

    def login(self, user, password):
        return "OK", [b"logged in"]

    def select(self, folder, readonly=True):
        self.readonly = bool(readonly)
        return "OK", [str(len(self.messages)).encode()]

    def response(self, code):
        if str(code).upper() == "UIDVALIDITY":
            return "UIDVALIDITY", [str(self.uidvalidity).encode()]
        return "NO", [None]

    def _body_fetch_meta(self, uid: int, raw: bytes, flags: str) -> bytes:
        return f"{uid} (UID {uid} BODY.PEEK[] {{{len(raw)}}}".encode()

    def uid(self, cmd, arg1, arg2=None, arg3=None):
        if cmd == "SEARCH":
            self.search_calls += 1
            if self.raise_on_search_after and self.search_calls >= self.raise_on_search_after:
                raise TimeoutError("SEARCH timed out")
            uids = sorted(self.messages.keys())
            payload = b" ".join(str(u).encode() for u in uids) if uids else b""
            return "OK", [payload]
        if cmd == "FETCH":
            if self.fetch_failures > 0:
                self.fetch_failures -= 1
                raise TimeoutError("FETCH timed out")
            uid_spec = arg1.decode() if isinstance(arg1, bytes) else str(arg1)
            fetch_arg = arg2.decode() if isinstance(arg2, bytes) else str(arg2 or "")
            want_flags_only = fetch_arg == "(FLAGS)"
            want_body = "BODY.PEEK[]" in fetch_arg or "RFC822" in fetch_arg
            uids = [int(x) for x in uid_spec.split(",") if x.strip().isdigit()]
            out = []
            for uid in uids:
                if uid not in self.messages:
                    continue
                flags = self.flags.get(uid, "")
                if want_flags_only:
                    meta = f"{uid} (UID {uid} FLAGS ({flags}))".encode()
                    out.append((meta, None))
                    if self.gmail_style:
                        out.append(f" FLAGS ({flags}))".encode())
                elif want_body:
                    raw = self.messages[uid]
                    if "RFC822" in fetch_arg and "BODY.PEEK[]" not in fetch_arg:
                        meta = f"{uid} (UID {uid})".encode()
                        out.append((meta, None))
                        continue
                    meta = self._body_fetch_meta(uid, raw, flags)
                    if self.gmail_style:
                        out.append((meta, raw))
                        out.append(f" FLAGS ({flags}))".encode())
                    else:
                        out.append((meta, raw))
                        out.append(b")")
                else:
                    meta = f"{uid} (UID {uid} FLAGS ({flags}))".encode()
                    out.append((meta, None))
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

    def list(self):
        return "OK", [
            b'(\\HasNoChildren) "/" "INBOX"',
            b'(\\All \\HasNoChildren) "/" "[Gmail]/All Mail"',
            b'(\\Sent \\HasNoChildren) "/" "[Gmail]/Sent Mail"',
        ]


def test_resolve_all_mail_folder_and_sync_folders(local_db):
    store = local_db
    fake = FakeIMAP({1: _make_message("m1")})
    assert store._resolve_all_mail_folder(fake) == "[Gmail]/All Mail"
    resolved = store._resolve_sync_folders(fake, ["__ALL_MAIL__", "Sent", "INBOX"])
    assert resolved[0] == "[Gmail]/All Mail"
    assert resolved[1] == "[Gmail]/Sent Mail"
    assert resolved[2] == "INBOX"


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

    r = store.sync_account_folder("acc1", "INBOX", "", backfill_batch=10, full=True)
    conn = store._connect()
    rows = conn.execute("SELECT uid, subject FROM messages").fetchall()
    conn.close()
    assert len(rows) == 1
    assert rows[0][0] == 2
    assert rows[0][1] == "New"
    assert r["folder_purged"] is True
    assert r["purge_messages_removed"] == 1
    assert r["purge_attachments_removed"] == 0


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


def test_stale_local_count_when_server_message_expunged(local_db, monkeypatch):
    """Server-deleted messages stay in the local mirror; sync reports stale count."""
    store = local_db
    msgs = {i: _make_message(f"Msg {i}") for i in range(1, 6)}
    fake = FakeIMAP(msgs)
    monkeypatch.setattr(store, "_imap_connect", lambda account_id, owner="": fake)

    store.sync_account_folder("acc1", "INBOX", "", backfill_batch=10, full=True)
    del fake.messages[3]
    del fake.messages[5]
    fake.flags = {uid: "" for uid in fake.messages}

    r = store.sync_account_folder("acc1", "INBOX", "", backfill_batch=10, full=False)
    conn = store._connect()
    total = conn.execute("SELECT COUNT(*) FROM messages").fetchone()[0]
    conn.close()
    assert total == 5
    assert r["stale_local_count"] == 2
    assert r["purge_messages_removed"] == 0


def test_upsert_message_unlinks_old_attachment_on_update(local_db, monkeypatch, tmp_path):
    """Re-fetching an existing UID replaces attachment files (not routine sync)."""
    store = local_db
    small = b"x" * 100
    msgs = {1: _make_message("With att", attachment=small)}
    fake = FakeIMAP(msgs)
    monkeypatch.setattr(store, "_imap_connect", lambda account_id, owner="": fake)

    store.sync_account_folder("acc1", "INBOX", "", backfill_batch=10, full=True)
    conn = store._connect()
    old_path = conn.execute("SELECT local_path FROM attachments").fetchone()[0]
    conn.close()
    assert old_path and Path(old_path).exists()

    conn = store._connect()
    deletion_state: dict[str, int] = {"resync_attachments_unlinked": 0}
    budget = {"remaining": 1_000_000, "written": 0, "extracted": 0, "skipped": 0}
    outer = MIMEMultipart()
    outer["Subject"] = "With att v2"
    outer["From"] = "bob@example.com"
    outer["To"] = "alice@example.com"
    outer["Date"] = "Mon, 1 Jan 2024 12:00:00 +0000"
    outer.attach(MIMEText("body", "plain"))
    part = MIMEApplication(b"y" * 100, Name="other.bin")
    part.add_header("Content-Disposition", "attachment", filename="other.bin")
    outer.attach(part)
    raw = outer.as_bytes()
    parsed = store._parse_message_for_store(raw)
    att_rows = store._extract_attachments_for_store(
        parsed["msg"],
        parsed.get("attachments_meta") or [],
        "INBOX",
        1,
        max_attachment_bytes=52_428_800,
        budget_state=budget,
    )
    store._upsert_message(
        conn,
        owner="",
        account_id="acc1",
        folder="INBOX",
        uid=1,
        uidvalidity=100,
        parsed=parsed,
        flags="",
        attachment_rows=att_rows,
        deletion_state=deletion_state,
    )
    conn.commit()
    new_path = conn.execute("SELECT local_path FROM attachments").fetchone()[0]
    conn.close()
    assert deletion_state["resync_attachments_unlinked"] == 1
    assert not Path(old_path).exists()
    assert new_path and Path(new_path).exists()


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


def test_forward_batch_caps_incremental_new_mail(local_db, monkeypatch):
    store = local_db
    msgs = {i: _make_message(f"Msg {i}") for i in range(1, 21)}
    fake = FakeIMAP(msgs)
    monkeypatch.setattr(store, "_imap_connect", lambda account_id, owner="": fake)

    store.sync_account_folder("acc1", "INBOX", "", backfill_batch=20, full=True)
    fake.messages.update({i: _make_message(f"New {i}") for i in range(21, 41)})
    fake.flags.update({uid: "" for uid in range(21, 41)})

    r = store.sync_account_folder("acc1", "INBOX", "", backfill_batch=5, full=False)
    assert r["forward_fetched"] == 5
    assert r["new"] <= 5


def test_sync_stores_gmail_post_literal_flags(local_db, monkeypatch):
    store = local_db
    msgs = {1: _make_message("Seen mail")}
    fake = FakeIMAP(msgs, gmail_style=True)
    fake.flags[1] = "\\Seen"
    monkeypatch.setattr(store, "_imap_connect", lambda account_id, owner="": fake)

    store.sync_account_folder("acc1", "INBOX", "", backfill_batch=10, full=True)
    conn = store._connect()
    assert conn.execute("SELECT is_read FROM messages WHERE uid=1").fetchone()[0] == 1
    conn.close()


def test_sync_icloud_body_peek_not_empty(local_db, monkeypatch):
    """Regression: iCloud ignores bare RFC822; sync must use BODY.PEEK[] for body_text."""
    store = local_db
    body = "iCloud BODY.PEEK sync body content"
    msgs = {42: _make_message("iCloud peek test", body=body)}
    fake = FakeIMAP(msgs)  # bare RFC822 → no literal; BODY.PEEK[] → real bytes
    monkeypatch.setattr(store, "_imap_connect", lambda account_id, owner="": fake)

    r = store.sync_account_folder("acc1", "INBOX", "", backfill_batch=10, full=True)
    assert r["error"] is None
    assert r["new"] >= 1

    conn = store._connect()
    row = conn.execute(
        "SELECT body_text, snippet FROM messages WHERE uid=42"
    ).fetchone()
    conn.close()
    assert row is not None
    stored_body, stored_snippet = row
    assert stored_body and body in stored_body
    assert stored_snippet and body[: len(stored_snippet)] == stored_snippet


def test_search_all_reconnects_on_failure(local_db, monkeypatch):
    store = local_db
    msgs = {1: _make_message("Reconnect")}
    first = FakeIMAP(msgs)
    first.raise_on_search_after = 1
    second = FakeIMAP(msgs)
    calls = {"n": 0}

    def _connect(account_id, owner=""):
        calls["n"] += 1
        if calls["n"] == 1:
            second.reconnect_count += 1
            return first
        second.reconnect_count += 1
        return second

    monkeypatch.setattr(store, "_imap_connect", _connect)
    r = store.sync_account_folder("acc1", "INBOX", "", backfill_batch=10, full=True)
    assert r["error"] is None
    assert first.logged_out
    assert calls["n"] >= 2


def test_fetch_batch_reconnects_on_failure(local_db, monkeypatch):
    store = local_db
    msgs = {1: _make_message("Fetch reconnect")}
    first = FakeIMAP(msgs)
    first.fetch_failures = 1
    second = FakeIMAP(msgs)
    calls = {"n": 0}

    def _connect(account_id, owner=""):
        calls["n"] += 1
        return first if calls["n"] == 1 else second

    monkeypatch.setattr(store, "_imap_connect", _connect)
    r = store.sync_account_folder("acc1", "INBOX", "", backfill_batch=10, full=True)
    assert r["error"] is None
    conn = store._connect()
    assert conn.execute("SELECT COUNT(*) FROM messages").fetchone()[0] == 1
    conn.close()


def test_rfc822_attachment_listed_and_extracted(local_db, monkeypatch):
    from email.mime.message import MIMEMessage

    store = local_db
    outer = MIMEMultipart()
    outer["Subject"] = "Forwarded"
    outer["From"] = "bob@example.com"
    outer["To"] = "alice@example.com"
    outer["Date"] = "Mon, 1 Jan 2024 12:00:00 +0000"
    outer.attach(MIMEText("see attached", "plain"))
    inner = MIMEMultipart("alternative")
    inner.attach(MIMEText("inner body", "plain"))
    inner["Subject"] = "Inner"
    inner["From"] = "inner@example.com"
    rfc822_part = MIMEMessage(inner)
    rfc822_part.add_header("Content-Disposition", "attachment", filename="Forwarded")
    outer.attach(rfc822_part)
    msgs = {3: outer.as_bytes()}
    fake = FakeIMAP(msgs)
    monkeypatch.setattr(store, "_imap_connect", lambda account_id, owner="": fake)

    r = store.sync_account_folder("acc1", "INBOX", "", backfill_batch=10, full=True)
    assert r["error"] is None
    conn = store._connect()
    row = conn.execute(
        "SELECT filename, content_type, local_path, skipped_reason FROM attachments"
    ).fetchone()
    conn.close()
    assert row is not None
    assert row[0].endswith(".eml")
    assert row[1] == "message/rfc822"
    assert row[2] and Path(row[2]).exists()
    assert row[3] is None


def test_resync_skips_attachment_extract_when_unchanged(local_db, monkeypatch):
    store = local_db
    small = b"x" * 100
    msgs = {1: _make_message("With att", attachment=small)}
    fake = FakeIMAP(msgs)
    monkeypatch.setattr(store, "_imap_connect", lambda account_id, owner="": fake)

    r1 = store.sync_account_folder("acc1", "INBOX", "", backfill_batch=10, full=True)
    assert r1["attachments_written_bytes"] > 0
    conn = store._connect()
    path = conn.execute("SELECT local_path FROM attachments").fetchone()[0]
    mtime = Path(path).stat().st_mtime
    conn.close()

    r2 = store.sync_account_folder("acc1", "INBOX", "", backfill_batch=10, full=True)
    assert r2["attachments_written_bytes"] == 0
    assert Path(path).stat().st_mtime == mtime


def test_single_pass_mime_flag_parity(tmp_path, monkeypatch):
    msgs = {
        1: _make_message("Plain only"),
        2: _make_alternative_message("Both parts"),
        3: _make_alternative_message("HTML only", html_only=True),
        4: _make_message("With attachment", attachment=b"attach-payload"),
    }
    off = _run_sync_with_flag(tmp_path, monkeypatch, msgs, single_pass=False)
    on = _run_sync_with_flag(tmp_path, monkeypatch, msgs, single_pass=True)
    assert off["messages"] == on["messages"]


def test_sync_all_owner_lock_non_blocking(local_db, monkeypatch):
    import threading

    store = local_db
    msgs = {1: _make_message("Lock test")}
    fake = FakeIMAP(msgs)
    monkeypatch.setattr(store, "_imap_connect", lambda account_id, owner="": fake)
    monkeypatch.setattr(
        "routes.email_local_store._enumerate_accounts",
        lambda owner, accounts=None: [type("Acc", (), {"id": "acc1", "name": "Main", "imap_user": "u@x.com"})()],
    )

    started = threading.Event()
    release = threading.Event()

    original = store.sync_account_folder

    def slow_sync(*args, **kwargs):
        started.set()
        release.wait(timeout=5)
        return original(*args, **kwargs)

    monkeypatch.setattr(store, "sync_account_folder", slow_sync)
    first_result: dict = {}

    def run_first():
        first_result["r"] = store.sync_all(owner="alice", folders=["INBOX"])

    t = threading.Thread(target=run_first)
    t.start()
    assert started.wait(timeout=5)
    second = store.sync_all(owner="alice", folders=["INBOX"])
    release.set()
    t.join(timeout=10)
    assert second.get("busy") is True
    assert second.get("ok") is False
    assert first_result["r"].get("ok") is True


# ---------------------------------------------------------------------------
# sync_all time budget and pacing (P1 settings)
# ---------------------------------------------------------------------------


def _fake_acc(account_id: str, name: str):
    return type("Acc", (), {"id": account_id, "name": name, "imap_user": f"{account_id}@example.com"})()


def _budget_sync_settings(**overrides):
    base = {
        "email_local_sync_enabled": True,
        "email_local_sync_folders": ["INBOX", "Sent"],
        "email_local_sync_backfill_batch": 50,
        "email_local_sync_flag_refresh_window": 100,
        "email_local_sync_max_attachment_bytes": 15_728_640,
        "email_local_sync_attachment_budget_bytes": 402_653_184,
        "email_local_sync_max_sync_seconds": 180,
        "email_local_sync_account_delay_ms": 0,
        "email_local_sync_chunk_delay_ms": 0,
    }
    base.update(overrides)
    return base


def _three_account_sync_setup(store, monkeypatch, *, accounts=None):
    msgs = {1: _make_message("Budget test")}
    fake = FakeIMAP(msgs)
    monkeypatch.setattr(store, "_imap_connect", lambda account_id, owner="": fake)
    acct_rows = accounts or [
        _fake_acc("acc1", "Work"),
        _fake_acc("acc2", "Personal"),
        _fake_acc("acc3", "Other"),
    ]
    monkeypatch.setattr(
        store,
        "_enumerate_accounts",
        lambda owner, accounts=None: acct_rows,
    )
    return fake


def test_sync_all_stops_at_time_budget(local_db, monkeypatch):
    store = local_db
    _three_account_sync_setup(store, monkeypatch)
    monkeypatch.setattr(
        "src.settings.load_settings",
        lambda: _budget_sync_settings(),
    )

    clock = {"t": 0.0}
    monkeypatch.setattr("time.monotonic", lambda: clock["t"])

    def sync_folder(acc_id, folder, owner, **kwargs):
        clock["t"] += 0.5
        return {"account_id": acc_id, "folder": folder, "error": None}

    monkeypatch.setattr(store, "sync_account_folder", sync_folder)

    result = store.sync_all(
        owner="",
        folders=["INBOX", "Sent"],
        max_sync_seconds=1,
        full=False,
    )

    assert result["ok"] is True
    assert result["partial"] is True
    assert result["budget_hit"] is True
    assert result["max_sync_seconds"] == 1
    assert result["folders_planned"] == 6
    assert result["folders_synced"] == 2
    assert result["folders_skipped"] == 4
    assert len(result["skipped"]) == 4
    assert all(item["reason"] == "time_budget" for item in result["skipped"])


def test_sync_all_full_bypasses_time_budget(local_db, monkeypatch):
    store = local_db
    _three_account_sync_setup(store, monkeypatch)
    monkeypatch.setattr(
        "src.settings.load_settings",
        lambda: _budget_sync_settings(email_local_sync_max_sync_seconds=1),
    )

    clock = {"t": 0.0}
    monkeypatch.setattr("time.monotonic", lambda: clock["t"])

    def sync_folder(acc_id, folder, owner, **kwargs):
        clock["t"] += 0.05
        return {"account_id": acc_id, "folder": folder, "error": None}

    monkeypatch.setattr(store, "sync_account_folder", sync_folder)

    result = store.sync_all(owner="", folders=["INBOX", "Sent"], full=True)

    assert result["ok"] is True
    assert result["budget_hit"] is False
    assert result["partial"] is False
    assert result["folders_planned"] == 6
    assert result["folders_synced"] == 6
    assert result["folders_skipped"] == 0


def test_sync_all_max_sync_seconds_zero_is_unlimited(local_db, monkeypatch):
    store = local_db
    _three_account_sync_setup(store, monkeypatch)
    monkeypatch.setattr(
        "src.settings.load_settings",
        lambda: _budget_sync_settings(email_local_sync_max_sync_seconds=1),
    )

    clock = {"t": 0.0}
    monkeypatch.setattr("time.monotonic", lambda: clock["t"])

    def sync_folder(acc_id, folder, owner, **kwargs):
        clock["t"] += 0.05
        return {"account_id": acc_id, "folder": folder, "error": None}

    monkeypatch.setattr(store, "sync_account_folder", sync_folder)

    result = store.sync_all(
        owner="",
        folders=["INBOX", "Sent"],
        max_sync_seconds=0,
        full=False,
    )

    assert result["ok"] is True
    assert result["budget_hit"] is False
    assert result["folders_synced"] == 6
    assert result["folders_skipped"] == 0


def test_sync_all_account_delay_sleep(local_db, monkeypatch):
    store = local_db
    _three_account_sync_setup(
        store,
        monkeypatch,
        accounts=[_fake_acc("acc1", "A"), _fake_acc("acc2", "B")],
    )
    monkeypatch.setattr(
        "src.settings.load_settings",
        lambda: _budget_sync_settings(email_local_sync_account_delay_ms=100),
    )

    sleeps: list[float] = []
    monkeypatch.setattr(store.time, "sleep", lambda s: sleeps.append(s))
    monkeypatch.setattr(
        store,
        "sync_account_folder",
        lambda acc_id, folder, owner, **kwargs: {
            "account_id": acc_id,
            "folder": folder,
            "error": None,
        },
    )

    result = store.sync_all(owner="", folders=["INBOX"], full=True)

    assert result["ok"] is True
    assert result["folders_synced"] == 2
    assert len(sleeps) == 1
    assert sleeps[0] == pytest.approx(0.1)


def test_fetch_body_batch_chunk_delay(local_db, monkeypatch):
    store = local_db
    sleeps: list[float] = []
    monkeypatch.setattr(store.time, "sleep", lambda s: sleeps.append(s))

    msgs = {i: _make_message(f"Msg {i}") for i in range(1, 121)}
    fake = FakeIMAP(msgs)

    records, err, _conn = store._fetch_body_batch(
        fake,
        list(range(1, 121)),
        folder="INBOX",
        reconnect=lambda: fake,
        chunk_delay_ms=50,
    )

    assert err is None
    assert len(records) == 120
    assert len(sleeps) == 3
    assert all(delay == pytest.approx(0.05) for delay in sleeps)
