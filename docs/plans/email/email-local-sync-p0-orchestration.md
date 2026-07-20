# Phase 0: local email sync orchestration

**Status:** Implemented (Phase 0+1, 2026-07-01)  
**Scope:** `routes/email_local_store.py` orchestration + callers (cron, API, agent tool, CLI)  
**Goal:** make incremental sync predictable, non-overlapping per owner, and easy to detect when a sync is already running.

## Implementation notes

| Shipped | Location / behavior |
|---------|---------------------|
| Cap incremental `forward_uids` to `backfill_batch` when `stored_max` is set | `sync_account_folder` in `routes/email_local_store.py` |
| Per-owner non-blocking `sync_all` lock | `_owner_sync_all_lock` wraps `sync_all` |
| Top-level `{ok: false, busy: true}` on overlap | `sync_all` early return |
| `format_sync_all_log` busy branch | `routes/email_local_store.py` |
| Cron → `TaskNoop` on busy | `action_sync_local_emails` in `src/builtin_actions.py` |
| Agent tool busy handling | `do_sync_local_emails` in `src/tool_implementations.py` |
| CLI exit code 2 on busy | `scripts/odysseus-mail sync-local` |

| Deferred | Notes |
|----------|-------|
| Cross-process / distributed lock | In-process lock only |
| HTTP `409` for busy | API returns JSON `busy: true` |
| Frontend `emailLibrary.js` busy UI | Not built |
| Parallel folder sync within one `sync_all` | Still sequential |
| Metrics / structured phase logging | Follow-up |
| `tool_schemas.py` `full` default description fix | Documented in settings plan |

The sections below describe the original design; behavior matches the shipped items above.

---

## Summary

Four coordinated changes tighten the local email mirror sync pipeline before later phases (UI, observability, multi-folder expansion):

| # | Item | Problem today | Target behavior |
|---|------|---------------|-----------------|
| 1 | Cap `forward_uids` | Incremental forward fetch can pull **all** new UIDs in one pass when `stored_max` exists | Cap forward phase to `backfill_batch` unless `full=True` |
| 2 | Per-owner `sync_all` lock | Only per-folder locks exist; two `sync_all` calls for the same owner overlap | One non-blocking global lock per owner around `sync_all` |
| 3 | Top-level busy response | Overlap returns `ok: true` with per-folder `"sync already in progress"` errors | Return `ok: false, busy: true` at the top level |
| 4 | Caller updates | Cron, API, tool, and CLI don't interpret busy distinctly | Each entry point handles busy consistently |

---

## Current architecture (pre-implementation baseline)

### Locking (today)

```text
_SYNC_LOCKS: dict[(owner, account_id, folder), threading.Lock]

sync_all(owner)
  └─ for each account × folder (sequential)
       └─ sync_account_folder(...)
            └─ _folder_lock(owner, account_id, folder).acquire(blocking=False)
                 └─ on fail: item.error = "sync already in progress"
```

- **Folder lock** is non-blocking and works for a single folder.
- **No owner-wide lock** on `sync_all`, so two callers (cron + API, API + tool, etc.) can each acquire different folder locks and run IMAP work in parallel for the same owner.
- When the second caller hits a folder already syncing, it gets a per-folder error while `sync_all` still returns `ok: true`.

### Batch caps (today)

In `sync_account_folder` (`routes/email_local_store.py`):

| Phase | `full=False` | `full=True` |
|-------|--------------|-------------|
| Forward (no `stored_max`) | capped `[:backfill_batch]` | capped `[:backfill_batch]` |
| Forward (`stored_max` set) | **uncapped** (all UIDs > max) | **uncapped** |
| Backfill | capped | loop until done |
| Gap repair | capped | loop until done |

The gap is lines 1310–1314: first-time forward is capped, but incremental forward after `stored_max` is not.

### Callers (today)

| Caller | File | `full` | Busy handling |
|--------|------|--------|---------------|
| Cron (`*/20 * * * *`) | `src/builtin_actions.py` → `action_sync_local_emails` | `False` | Treats all `not ok` as failure string or `TaskNoop` for "no accounts" |
| Agent tool | `src/tool_implementations.py` → `do_sync_local_emails` | arg, default `False` | `not ok` → generic error |
| HTTP API | `routes/email_routes.py` `POST /local/sync` | body `full`, default `False` | Returns raw `sync_all` dict |
| CLI | `scripts/odysseus-mail sync-local` | always `True` | `not ok` → exit 1 |

Scheduler registration: `src/task_scheduler.py` line 245 (`sync_local_emails`, cron `*/20 * * * *`, `ship_paused: True`).

---

## Item 1: Cap `forward_uids` to `backfill_batch`

### Problem

After the mirror has any stored mail (`stored_max` is set), a burst of new server UIDs (large catch-up, vacation backlog, imported mailbox) triggers a single forward pass that fetches **every** new UID. Backfill and gap repair are already batch-limited; forward is not, so one incremental cron tick can run for minutes and starve other work.

### Proposed change

In `sync_account_folder`, after computing newer UIDs:

```python
# Today (incremental, stored_max set):
forward_uids = sorted([u for u in server_uids if u > int(stored_max)], reverse=True)

# Proposed:
newer = sorted([u for u in server_uids if u > int(stored_max)], reverse=True)
forward_uids = newer if full else newer[:backfill_batch]
```

Keep the existing first-sync branch unchanged (already capped):

```python
forward_uids = list(reversed(server_uids))[:backfill_batch] if server_uids else []
```

When `full=True`, forward may remain uncapped **or** be capped per pass with the outer `sync_all` caller re-invoking; recommend **uncapped when `full=True`** to match backfill/gap semantics (one run completes history). Document this in the function docstring.

### Acceptance criteria

- With 50 new UIDs, `backfill_batch=10`, `full=False`: `forward_fetched == 10`, `new <= 10`.
- With `full=True`: all new UIDs fetched in one forward phase (existing full-sync tests still pass).
- `format_sync_folder_log` output unchanged except `forward_fetched` counts.

### Tests to add

`tests/test_email_local_store_sync.py`:

- `test_forward_batch_caps_incremental_new_mail` — seed mailbox with UIDs 1–20, sync once, add UIDs 21–40 on server, incremental sync with `backfill_batch=5` asserts `forward_fetched == 5`.

---

## Item 2: Per-owner global `sync_all` lock

### Problem

Folder locks serialize concurrent access to one folder, but `sync_all` spans many folders and accounts. Overlapping `sync_all` invocations for the same owner cause duplicate IMAP connections, SQLite write contention, and ambiguous partial results.

### Proposed design

Add a second lock map alongside `_SYNC_LOCKS`:

```python
_SYNC_ALL_LOCKS: dict[str, threading.Lock] = {}  # key = owner or ""
_SYNC_ALL_GUARD = threading.Lock()

def _owner_sync_all_lock(owner: str) -> threading.Lock:
    key = owner or ""
    with _SYNC_ALL_GUARD:
        if key not in _SYNC_ALL_LOCKS:
            _SYNC_ALL_LOCKS[key] = threading.Lock()
        return _SYNC_ALL_LOCKS[key]
```

Wrap **`sync_all` only** (not `sync_account_folder`):

```python
def sync_all(...) -> dict[str, Any]:
    owner_key = owner or ""
    lock = _owner_sync_all_lock(owner_key)
    if not lock.acquire(blocking=False):
        return {
            "ok": False,
            "busy": True,
            "error": "sync already in progress",
            "results": [],
        }
    try:
        ...  # existing body
    finally:
        lock.release()
```

### Semantics

| Property | Value |
|----------|-------|
| Granularity | One lock per `owner` string (`""` for unscoped/default) |
| Blocking | **Non-blocking** (`acquire(blocking=False)`) |
| Scope | `sync_all` entry/exit only |
| Cross-owner | Different owners sync in parallel (unchanged) |
| `sync_account_folder` direct calls | Unaffected (tests still call it directly); production only goes through `sync_all` |

### Folder lock interaction

With the global lock, `sync_all` never overlaps for the same owner, so folder-level `"sync already in progress"` should not appear in normal `sync_all` results. Keep folder locks as defense-in-depth for tests and any future direct `sync_account_folder` use.

### Acceptance criteria

- Two concurrent `sync_all(owner="alice")` calls: first runs, second returns busy immediately without IMAP work.
- `sync_all(owner="alice")` and `sync_all(owner="bob")` can run concurrently.
- Lock is always released on success, error, or exception (use `try/finally`).

### Tests to add

`tests/test_email_local_store_sync.py` (or new `tests/test_email_local_store_sync_orchestration.py`):

- `test_sync_all_owner_lock_non_blocking` — monkeypatch slow `sync_account_folder`, start `sync_all` in a thread, call again from main thread, assert second result has `busy: True` and `ok: False`.
- `test_sync_all_different_owners_parallel` — two owners don't block each other.

Implementation note: use a `threading.Event` or inject a sleep in `sync_account_folder` for the slow-path test.

---

## Item 3: Top-level busy response contract

### Problem

Today, overlapping syncs produce:

```json
{
  "ok": true,
  "results": [
    {"account_id": "...", "folder": "INBOX", "error": "sync already in progress"},
    ...
  ],
  "duration_seconds": 0.01
}
```

Callers cannot distinguish "sync skipped because busy" from "sync ran and succeeded with folder errors" without scanning `results`.

### Proposed response shapes

**Busy (global lock not acquired):**

```json
{
  "ok": false,
  "busy": true,
  "error": "sync already in progress",
  "results": []
}
```

**Disabled / config error (unchanged, no `busy`):**

```json
{
  "ok": false,
  "error": "email_local_sync_enabled is false",
  "results": []
}
```

**Success (unchanged):**

```json
{
  "ok": true,
  "results": [...],
  "duration_seconds": 1.23,
  "folder_count": 4,
  "account_count": 2
}
```

**Partial folder failure (real errors, not busy):** keep `ok: true` with per-folder `error` fields. Only **orchestration-level** overlap uses `busy`.

### `format_sync_all_log` update

In `format_sync_all_log`:

```python
if not result.get("ok"):
    if result.get("busy"):
        return "Local email sync skipped: sync already in progress"
    err = result.get("error") or "sync failed"
    return f"Local email sync failed: {err}"
```

### HTTP status code (API)

`POST /email/local/sync` should return **JSON body as source of truth** (`ok` / `busy`). HTTP status options:

| Option | Behavior |
|--------|----------|
| **A (recommended)** | Always `200`; clients read `ok` / `busy` |
| B | `409 Conflict` when `busy: true` |

Pick **A** for consistency with other email routes that return `{ok: ...}` in body. Document in plan; implementer can add `409` later without breaking JSON contract.

### Acceptance criteria

- Busy response never has `ok: true`.
- Busy response always includes `busy: true` and empty `results`.
- `format_sync_all_log` produces a clear "skipped" message for busy.

### Tests to add

`tests/test_email_local_store_sync_log.py`:

- `test_format_sync_all_log_busy` — input `{"ok": false, "busy": true, "error": "sync already in progress", "results": []}`.

---

## Item 4: Caller updates

Each entry point should treat `busy` distinctly from hard failures and from success.

### 4a. `src/builtin_actions.py` — `action_sync_local_emails`

**Current** (lines 2252–2257):

```python
result = await asyncio.to_thread(sync_all, owner, full=False)
if not result.get("ok"):
    err = result.get("error") or "sync failed"
    if "no email accounts" in str(err).lower():
        raise TaskNoop(err)
    return err, False
```

**Proposed:**

```python
result = await asyncio.to_thread(sync_all, owner, full=False)
if result.get("busy"):
    raise TaskNoop("sync already in progress")
if not result.get("ok"):
    err = result.get("error") or "sync failed"
    if "no email accounts" in str(err).lower():
        raise TaskNoop(err)
    return err, False
```

**Rationale:** Cron overlap should be a silent skip (Activity log: "skipped — sync already in progress"), matching `skill audit already running` and scheduler `TaskNoop` handling (`src/task_scheduler.py` lines 862–884). Do **not** use `TaskDeferred` unless we want to retry within the same cron window; non-blocking skip is enough.

### 4b. `src/tool_implementations.py` — `do_sync_local_emails`

**Proposed:**

```python
result = await asyncio.to_thread(sync_all, owner or "", accounts=accounts, full=full)
if result.get("busy"):
    return {
        "output": "Local email sync skipped: another sync is already running for this owner.",
        "busy": True,
        "exit_code": 0,
    }
if not result.get("ok"):
    return {"error": result.get("error") or "sync failed", "exit_code": 1}
```

**Rationale:** Busy is not an agent mistake; `exit_code: 0` avoids retry loops. Include `busy: True` in the dict for programmatic callers. Optional: mention in `src/tool_schemas.py` description that the tool may return a skip message when sync is in progress.

### 4c. `routes/email_routes.py` — `POST /local/sync`

**Current:** returns raw `sync_all` result.

**Proposed:** no transformation needed if `sync_all` returns the busy dict. Optionally add a one-line docstring on the route:

```python
"""Trigger local mirror sync. Returns {ok, busy?, results, ...}. busy=true when a sync is already running for this owner."""
```

No change to auth or body parsing. Consider future UI handling in a later phase (out of scope here).

### 4d. `scripts/odysseus-mail` — `cmd_sync_local`

**Current:**

```python
result = sync_all(owner=args.owner or "", full=True)
emit(result, args)
if not result.get("ok"):
    sys.exit(1)
```

**Proposed:**

```python
result = sync_all(owner=args.owner or "", full=True)
emit(result, args)
if result.get("busy"):
    sys.exit(2)   # distinct exit code: overlap, not hard failure
if not result.get("ok"):
    sys.exit(1)
```

Document exit codes in the `sync-local` subparser help text:

- `0` — success  
- `1` — sync failed (config, IMAP, etc.)  
- `2` — busy (another sync running)

Cron operators can treat exit `2` as benign (like `poll-scheduled` idempotency).

### Caller matrix (after implementation)

| Caller | `busy` behavior | User-visible outcome |
|--------|-----------------|----------------------|
| Cron / `action_sync_local_emails` | `TaskNoop` | Activity: skipped |
| `do_sync_local_emails` | `exit_code: 0`, skip message | Agent sees friendly skip text |
| `POST /local/sync` | JSON `ok: false, busy: true` | API client checks `busy` |
| `odysseus-mail sync-local` | exit `2` | Shell/cron can ignore |

---

## Implementation order

Recommended sequence minimizes rework and keeps tests green at each step:

```text
1. forward_uids cap          (isolated, no API contract change)
2. owner sync_all lock       (introduces busy dict from sync_all)
3. format_sync_all_log busy  (logging follows contract)
4. caller updates            (builtin_actions → tool → routes doc → CLI)
5. tests                     (add alongside each step)
```

Estimated touch surface: **~6 files**, **~80–120 LOC** changed, **~5–8 new tests**.

---

## Files to modify

| File | Changes |
|------|---------|
| `routes/email_local_store.py` | `forward_uids` cap; `_owner_sync_all_lock`; wrap `sync_all`; `format_sync_all_log` busy branch |
| `src/builtin_actions.py` | `action_sync_local_emails` busy → `TaskNoop` |
| `src/tool_implementations.py` | `do_sync_local_emails` busy branch |
| `routes/email_routes.py` | Route docstring (optional comment only) |
| `scripts/odysseus-mail` | `cmd_sync_local` exit code 2; help text |
| `tests/test_email_local_store_sync.py` | forward cap + lock tests |
| `tests/test_email_local_store_sync_log.py` | busy log test |

**No changes required** (verify only):

- `src/task_scheduler.py` — cron registration unchanged; `TaskNoop` path already exists
- `src/settings.py` — `email_local_sync_backfill_batch` already controls cap
- `src/tool_security.py` / `src/tool_schemas.py` — optional description tweak only

---

## Test plan (full)

### Unit: `sync_account_folder`

- [ ] `test_forward_batch_caps_incremental_new_mail` (new)
- [ ] Existing `test_backfill_batch_limits_older_per_pass` still passes (regression)

### Unit: `sync_all` orchestration

- [ ] `test_sync_all_owner_lock_non_blocking` (new)
- [ ] `test_sync_all_different_owners_parallel` (new, optional)
- [ ] Disabled sync still returns `ok: false` without `busy`

### Unit: logging

- [ ] `test_format_sync_all_log_busy` (new)
- [ ] Existing folder busy log line kept for direct `sync_account_folder` calls

### Integration (manual / follow-up)

- [ ] Trigger `POST /local/sync` twice quickly; second response has `busy: true`
- [ ] Run `odysseus-mail sync-local` while cron task is mid-sync; exit code `2`
- [ ] Agent `sync_local_emails` during active sync returns skip message, `exit_code: 0`

Run: `pytest tests/test_email_local_store_sync.py tests/test_email_local_store_sync_log.py -q`

---

## Edge cases and risks

| Scenario | Handling |
|----------|----------|
| Long-running `full=True` CLI sync blocks cron for same owner | Expected; cron gets `TaskNoop` skip |
| Server crash mid-sync | `finally: lock.release()` prevents stuck lock |
| Empty owner `""` vs explicit owner | Normalize with `owner or ""` everywhere (already done in folder lock) |
| `sync_account_folder` in tests while `sync_all` runs | Rare; folder lock may still report per-folder busy; tests should not overlap `sync_all` |
| Multi-worker deployment (multiple processes) | In-process `threading.Lock` only; **does not** protect across processes. Document as known limitation; Redis/file lock is a future phase if needed |

---

## Out of scope (later phases)

- Cross-process distributed lock
- HTTP `409` for busy (optional enhancement)
- Frontend `emailLibrary.js` sync button busy UI
- Changing CLI `sync-local` default from `full=True` to incremental
- Fixing `tool_schemas.py` `full` default description vs `do_sync_local_emails` default `False`
- Metrics / structured logging for sync phases
- Parallel folder sync within one `sync_all`

---

## Definition of done

- [x] Incremental forward fetch respects `email_local_sync_backfill_batch` when `stored_max` is set and `full=False`
- [x] At most one `sync_all` runs per owner at a time (in-process)
- [x] Overlapping `sync_all` returns `{ok: false, busy: true, error: "sync already in progress", results: []}`
- [x] Cron, tool, API, and CLI each handle `busy` per the caller matrix
- [x] New tests pass; existing sync tests pass
