"""Tests for local email sync log formatting."""

from __future__ import annotations

from routes.email_local_store import format_sync_all_log, format_sync_folder_log


def test_format_sync_folder_log_idle_pass():
    item = {
        "account": "Work Email",
        "folder": "INBOX",
        "server_total": 4521,
        "server_min_uid": 42,
        "server_max_uid": 98432,
        "local_total": 4521,
        "local_min_uid": 42,
        "local_max_uid": 98432,
        "missing_count": 0,
        "uidvalidity": 1,
        "folder_purged": False,
        "full": False,
        "backfill_batch": 200,
        "flag_window": 200,
        "forward_fetched": 0,
        "new": 0,
        "backfill_fetched": 0,
        "backfilled": 0,
        "gap_fetched": 0,
        "gap_new": 0,
        "flags_updated": 0,
        "flags_pushed": 0,
        "flags_pulled": 0,
        "attachments_extracted": 0,
        "attachments_skipped": 0,
        "attachments_written_bytes": 0,
        "stored": 0,
        "backfill_complete": True,
    }
    text = format_sync_folder_log(item=item)
    assert "Work Email / INBOX" in text
    assert "4,521 on server" in text
    assert "forward: 0 fetched (0 new)" in text
    assert "backfill_complete=yes" in text
    assert "no messages fetched" in text


def test_format_sync_folder_log_active_pass():
    item = {
        "account": "Main",
        "folder": "[Gmail]/Sent Mail",
        "server_total": 1200,
        "server_min_uid": 1,
        "server_max_uid": 5000,
        "local_total": 1185,
        "local_min_uid": 1,
        "local_max_uid": 4980,
        "missing_count": 15,
        "uidvalidity": 2,
        "folder_purged": False,
        "full": False,
        "backfill_batch": 50,
        "flag_window": 100,
        "forward_fetched": 12,
        "new": 10,
        "backfill_fetched": 50,
        "backfilled": 45,
        "gap_fetched": 3,
        "gap_new": 3,
        "flags_updated": 4,
        "flags_pushed": 2,
        "flags_pulled": 2,
        "attachments_extracted": 2,
        "attachments_skipped": 1,
        "attachments_written_bytes": 2048,
        "stored": 58,
        "backfill_complete": False,
    }
    text = format_sync_folder_log(item=item)
    assert "forward: 12 fetched (10 new)" in text
    assert "backfill: 50 fetched (45 new)" in text
    assert "gap repair: 3 fetched (3 new)" in text
    assert "2 extracted (2.0 KB written" in text
    assert "58 message(s) processed" in text
    assert "backfill_complete=no" in text


def test_format_sync_folder_log_error_and_busy():
    err = format_sync_folder_log(item={"account": "A", "folder": "INBOX", "error": "SELECT failed"})
    assert "ERROR SELECT failed" in err
    busy = format_sync_folder_log(
        item={"account": "A", "folder": "INBOX", "error": "sync already in progress"},
    )
    assert "skipped (sync already in progress)" in busy


def test_format_sync_all_log_header():
    result = {
        "ok": True,
        "duration_seconds": 12.3,
        "results": [
            {
                "account": "Personal",
                "folder": "INBOX",
                "server_total": 0,
                "local_total": 0,
                "missing_count": 0,
                "forward_fetched": 0,
                "new": 0,
                "backfill_fetched": 0,
                "backfilled": 0,
                "gap_fetched": 0,
                "gap_new": 0,
                "flags_updated": 0,
                "flags_pushed": 0,
                "flags_pulled": 0,
                "attachments_extracted": 0,
                "attachments_skipped": 0,
                "attachments_written_bytes": 0,
                "stored": 0,
                "backfill_complete": True,
                "backfill_batch": 200,
                "flag_window": 200,
                "full": False,
            },
        ],
    }
    text = format_sync_all_log(result, duration_seconds=12.3)
    assert "1 folder(s) across 1 account(s)" in text
    assert "12.3s" in text
    assert "Personal / INBOX" in text


def test_format_sync_folder_log_uidvalidity_purge():
    item = {
        "account": "Work",
        "folder": "INBOX",
        "server_total": 1,
        "server_min_uid": 2,
        "server_max_uid": 2,
        "local_total": 1,
        "local_min_uid": 2,
        "local_max_uid": 2,
        "missing_count": 0,
        "uidvalidity": 99,
        "folder_purged": True,
        "purge_messages_removed": 3,
        "purge_attachments_removed": 2,
        "purge_attachment_files_unlinked": 2,
        "resync_attachments_unlinked": 0,
        "stale_local_count": 0,
        "full": True,
        "backfill_batch": 200,
        "flag_window": 200,
        "forward_fetched": 1,
        "new": 1,
        "backfill_fetched": 0,
        "backfilled": 0,
        "gap_fetched": 0,
        "gap_new": 0,
        "flags_updated": 0,
        "flags_pushed": 0,
        "flags_pulled": 0,
        "attachments_extracted": 1,
        "attachments_skipped": 0,
        "attachments_written_bytes": 512,
        "stored": 1,
        "backfill_complete": True,
    }
    text = format_sync_folder_log(item=item)
    assert "folder purged and rebuilt" in text
    assert "UIDVALIDITY purge — 3 message(s), 2 attachment record(s), 2 file(s) removed" in text


def test_format_sync_folder_log_stale_local_not_removed():
    item = {
        "account": "Main",
        "folder": "INBOX",
        "server_total": 8,
        "server_min_uid": 1,
        "server_max_uid": 10,
        "local_total": 10,
        "local_min_uid": 1,
        "local_max_uid": 10,
        "missing_count": 0,
        "uidvalidity": 1,
        "folder_purged": False,
        "purge_messages_removed": 0,
        "purge_attachments_removed": 0,
        "purge_attachment_files_unlinked": 0,
        "resync_attachments_unlinked": 0,
        "stale_local_count": 2,
        "full": False,
        "backfill_batch": 200,
        "flag_window": 200,
        "forward_fetched": 0,
        "new": 0,
        "backfill_fetched": 0,
        "backfilled": 0,
        "gap_fetched": 0,
        "gap_new": 0,
        "flags_updated": 0,
        "flags_pushed": 0,
        "flags_pulled": 0,
        "attachments_extracted": 0,
        "attachments_skipped": 0,
        "attachments_written_bytes": 0,
        "stored": 0,
        "backfill_complete": False,
    }
    text = format_sync_folder_log(item=item)
    assert "2 local message(s) no longer on server" in text
    assert "sync does not remove them" in text


def test_format_sync_folder_log_resync_attachment_replacement():
    item = {
        "account": "Main",
        "folder": "INBOX",
        "server_total": 5,
        "server_min_uid": 1,
        "server_max_uid": 5,
        "local_total": 5,
        "local_min_uid": 1,
        "local_max_uid": 5,
        "missing_count": 0,
        "uidvalidity": 1,
        "folder_purged": False,
        "purge_messages_removed": 0,
        "purge_attachments_removed": 0,
        "purge_attachment_files_unlinked": 0,
        "resync_attachments_unlinked": 1,
        "stale_local_count": 0,
        "full": False,
        "backfill_batch": 200,
        "flag_window": 200,
        "forward_fetched": 1,
        "new": 0,
        "backfill_fetched": 0,
        "backfilled": 0,
        "gap_fetched": 0,
        "gap_new": 0,
        "flags_updated": 0,
        "flags_pushed": 0,
        "flags_pulled": 0,
        "attachments_extracted": 1,
        "attachments_skipped": 0,
        "attachments_written_bytes": 100,
        "stored": 1,
        "backfill_complete": True,
    }
    text = format_sync_folder_log(item=item)
    assert "1 attachment file(s) replaced during message re-sync" in text


def test_format_sync_all_log_busy():
    result = {
        "ok": False,
        "busy": True,
        "error": "sync already in progress",
        "results": [],
    }
    text = format_sync_all_log(result)
    assert "skipped: sync already in progress" in text


def test_format_sync_all_log_partial_budget():
    result = {
        "ok": True,
        "partial": True,
        "budget_hit": True,
        "max_sync_seconds": 180,
        "folders_planned": 4,
        "folders_synced": 2,
        "folders_skipped": 2,
        "duration_seconds": 180.0,
        "skipped": [
            {"account": "Work", "folder": "Sent", "reason": "time_budget"},
        ],
        "results": [
            {
                "account": "Work",
                "account_id": "acc1",
                "folder": "INBOX",
                "server_total": 1,
                "local_total": 1,
                "missing_count": 0,
                "forward_fetched": 0,
                "new": 0,
                "backfill_fetched": 0,
                "backfilled": 0,
                "gap_fetched": 0,
                "gap_new": 0,
                "flags_updated": 0,
                "flags_pushed": 0,
                "flags_pulled": 0,
                "attachments_extracted": 0,
                "attachments_skipped": 0,
                "attachments_written_bytes": 0,
                "stored": 0,
                "backfill_complete": True,
                "backfill_batch": 50,
                "flag_window": 100,
                "full": False,
            },
        ],
    }
    text = format_sync_all_log(result, duration_seconds=180.0)
    assert "(partial)" in text
    assert "stopped at time budget (180s)" in text
    assert "skipped (time budget exhausted before this folder)" in text
