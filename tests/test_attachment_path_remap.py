"""Cross-platform remap of Windows mail-attachment local_path values."""

from __future__ import annotations

from pathlib import Path


def test_resolve_keeps_existing_windows_or_local_file(tmp_path):
    from routes.email_helpers import resolve_stored_attachment_path

    existing = tmp_path / "already-here.pdf"
    existing.write_bytes(b"ok")
    assert resolve_stored_attachment_path(str(existing)) == existing


def test_resolve_remaps_missing_windows_path(tmp_path, monkeypatch):
    from routes import email_helpers as eh

    att_root = tmp_path / "mail-attachments"
    dest = att_root / "INBOX_42" / "doc.pdf"
    dest.parent.mkdir(parents=True)
    dest.write_bytes(b"hello")
    monkeypatch.setattr(eh, "ATTACHMENTS_DIR", att_root)
    monkeypatch.setattr(eh, "DATA_DIR", tmp_path)

    stored = r"E:\odysseus\data\mail-attachments\INBOX_42\doc.pdf"
    assert dest.exists()
    assert not Path(stored).is_file()
    assert eh.resolve_stored_attachment_path(stored) == dest.resolve()


def test_resolve_uses_odysseus_data_dir(tmp_path, monkeypatch):
    from routes import email_helpers as eh

    data = tmp_path / "data"
    dest = data / "mail-attachments" / "Sent_9" / "a.png"
    dest.parent.mkdir(parents=True)
    dest.write_bytes(b"png")
    monkeypatch.setattr(eh, "ATTACHMENTS_DIR", tmp_path / "unused-atts")
    monkeypatch.setattr(eh, "DATA_DIR", tmp_path / "unused-data")
    monkeypatch.setenv("ODYSSEUS_DATA_DIR", str(data))

    stored = r"E:\odysseus\data\mail-attachments\Sent_9\a.png"
    assert eh.resolve_stored_attachment_path(stored) == dest.resolve()


def test_resolve_rejects_traversal(tmp_path, monkeypatch):
    from routes import email_helpers as eh

    att_root = tmp_path / "mail-attachments"
    att_root.mkdir()
    secret = tmp_path / "secret.txt"
    secret.write_text("nope")
    monkeypatch.setattr(eh, "ATTACHMENTS_DIR", att_root)
    monkeypatch.setattr(eh, "DATA_DIR", tmp_path)

    stored = r"E:\odysseus\data\mail-attachments\..\secret.txt"
    assert eh.resolve_stored_attachment_path(stored) is None


def test_can_reuse_attachments_follows_remapped_path(tmp_path, monkeypatch):
    from routes import email_helpers as eh
    from routes.email_local_store import _can_reuse_attachments

    att_root = tmp_path / "mail-attachments"
    dest = att_root / "INBOX_1" / "file.bin"
    dest.parent.mkdir(parents=True)
    dest.write_bytes(b"12345")
    monkeypatch.setattr(eh, "ATTACHMENTS_DIR", att_root)
    monkeypatch.setattr(eh, "DATA_DIR", tmp_path)

    rows = [{
        "idx": 0,
        "filename": "file.bin",
        "content_type": "application/octet-stream",
        "is_inline": 0,
        "skipped_reason": None,
        "extracted": 1,
        "local_path": r"E:\odysseus\data\mail-attachments\INBOX_1\file.bin",
        "size": 5,
    }]
    meta = [{
        "index": 0,
        "filename": "file.bin",
        "size": 5,
        "content_type": "application/octet-stream",
        "is_inline": False,
    }]
    assert _can_reuse_attachments(rows, meta) is True
