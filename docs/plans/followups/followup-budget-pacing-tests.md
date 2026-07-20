# Follow-up: budget and pacing unit tests

Closes the test gaps from [email-local-sync-p1-settings.md](email-local-sync-p1-settings.md) after production implementation landed.

## Scope

| Area | File | What to assert |
|------|------|----------------|
| Time budget | `tests/test_email_local_store_sync.py` | `sync_all` stops before Nth folder; `partial`, `budget_hit`, `skipped` metadata |
| Full bypass | same | `full=True` or `max_sync_seconds=0` runs all planned folders |
| Account pacing | same | Mock `time.sleep`; 2 accounts → exactly one inter-account sleep |
| Chunk pacing | same | `_fetch_body_batch` with 120 UIDs → 3 sleeps at `_FETCH_CHUNK=50` |
| Settings validation | `tests/test_email_local_sync_settings_validation.py` | `_INT_RANGES` clamp/reject for new email-local-sync keys |

## Test design

### Time budget (`sync_all`)

- Mock `_enumerate_accounts` → 3 accounts.
- `folders=["INBOX", "Sent"]` → 6 planned pairs.
- Mock `sync_account_folder` to advance a fake `time.monotonic` clock by 0.05s per call (no real sleep).
- Call `sync_all(..., max_sync_seconds=1, full=False)` with fake clock +0.5s per folder.
- Expect: `folders_synced == 2`, `folders_skipped == 4`, `budget_hit`, `partial`, each `skipped[].reason == "time_budget"`.

### Full / unlimited

- Same setup with tight budget in settings.
- `full=True` → all 6 folders synced, `budget_hit` false.
- `max_sync_seconds=0` with `full=False` → all 6 folders synced.

### Account delay

- 2 accounts × 1 folder; `email_local_sync_account_delay_ms=100` in mocked `load_settings`.
- Record `time.sleep` calls in `routes.email_local_store`.
- Expect one sleep of `0.1` seconds (not after last account).

### Chunk delay

- Direct call to `_fetch_body_batch` with 120 UIDs and `chunk_delay_ms=50`.
- Expect 3 sleeps (including after the last chunk; matches P1 spec).

### Settings validation

- Exercise `POST /api/auth/settings` via `setup_auth_routes` with admin session.
- Clamp `email_local_sync_max_sync_seconds` above 3600 → 3600.
- Reject non-integer with HTTP 400.

## Out of scope

- Log formatter tests (already in `test_email_local_store_sync_log.py`).
- Real IMAP or wall-clock timing.

## Run

```bash
pytest tests/test_email_local_store_sync.py tests/test_email_local_store_sync_log.py tests/test_email_local_sync_settings_validation.py -q
```
