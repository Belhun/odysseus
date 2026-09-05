# Follow-up: iCloud BODY.PEEK[] local sync integration test

**Status:** Implemented  
**Scope:** `tests/test_email_local_store_sync.py`  
**Related:** #1961, `docs/plans/email-local-sync-p0-imap.md`, `tests/test_icloud_imap_full_fetch.py`

## Problem

iCloud IMAP returns `OK` for bare `(RFC822)` full-message fetches but omits the body literal; only `(BODY.PEEK[])` returns the message bytes. The local store was fixed to use `BODY.PEEK[]` (source guard in `test_email_local_store_imap_fetch.py`), but no sync-level test proved that a full `sync_account_folder` pass stores non-empty `body_text` / `snippet` when the fake server mimics iCloud.

## Approach

1. Reuse `FakeIMAP` in `test_email_local_store_sync.py`, which already returns metadata-only for bare `RFC822` and the real bytes for `BODY.PEEK[]`.
2. Add `test_sync_icloud_body_peek_not_empty`: sync one message with a known plain body, then assert `body_text` and `snippet` are non-empty and contain that body.
3. If someone regresses to `(RFC822 FLAGS)`, the fake returns no body literal, parse yields empty text, and the test fails.

## Out of scope

- Live iCloud server test (covered by MCP `test_icloud_imap_full_fetch.py` source guard).
- Gmail post-literal FLAGS (covered by `test_sync_stores_gmail_post_literal_flags`).
