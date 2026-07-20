# Phase 1: Email local sync settings and scheduling

**Status:** Implemented (Phase 0+1, 2026-07-01)

Plan for tuning default sync behavior, bounding cron pass duration, adding IMAP pacing, and improving partial-run logging.

## Implementation notes

| Shipped | Location / behavior |
|---------|---------------------|
| Lowered defaults: batch 50, flag window 100, max attachment 15 MB, budget 384 MB | `src/settings.py` `DEFAULT_SETTINGS` |
| `email_local_sync_max_sync_seconds` (180) | `sync_all` wall-clock budget on incremental path |
| `email_local_sync_account_delay_ms` (500), `email_local_sync_chunk_delay_ms` (150) | `sync_all` + `_fetch_body_batch` |
| Partial-run metadata (`partial`, `budget_hit`, `skipped`) | `sync_all` result dict |
| `format_sync_all_log` partial header and truncation | `routes/email_local_store.py` |
| Agent `full=True` bypasses budget | `src/tool_implementations.py` |
| Tests | `tests/test_email_local_store_sync.py`, `tests/test_email_local_store_sync_log.py` |

| Deferred | Notes |
|----------|-------|
| Cron interval change | Still `*/20 * * * *` |
| `ship_paused: True` on built-in task | Unchanged; admins unpause manually |
| Settings admin UI panel | JSON/API only |
| Intra-folder phase interruption | Budget stops between folders, not mid-phase |
| `tool_schemas.py` `full` default description vs code | Follow-up |
| `docs/setup.md` settings documentation | Follow-up |

The sections below describe the original baseline and proposed values (now shipped defaults).

## Context

The local email mirror is driven by:

| Layer | Role |
|-------|------|
| `src/settings.py` | `DEFAULT_SETTINGS` keys merged into `data/settings.json` |
| `routes/email_local_store.py` | `sync_all()` → `sync_account_folder()`; log formatters |
| `src/builtin_actions.py` | `action_sync_local_emails` — cron/task path (`full=False`) |
| `src/tool_implementations.py` | `do_sync_local_emails` — agent on-demand path |
| `src/task_scheduler.py` | `HOUSEKEEPING_DEFAULTS["sync_local_emails"]` seeds the built-in task |

### Current behavior (pre-implementation baseline)

**Settings defaults** (`src/settings.py` lines 187–193):

| Key | Current default | Notes |
|-----|-----------------|-------|
| `email_local_sync_backfill_batch` | `200` | Caps forward/backfill/gap UIDs per incremental pass |
| `email_local_sync_flag_refresh_window` | `200` | Recent messages for bidirectional `\Seen` sync |
| `email_local_sync_max_attachment_bytes` | `52_428_800` (50 MB) | Per-file extract cap |
| `email_local_sync_attachment_budget_bytes` | `2_147_483_648` (2 GB) | Per-folder pass attachment write budget |

**Cron task** (`src/task_scheduler.py` line 245):

```python
"sync_local_emails": {
    "name": "Email Local Sync",
    "schedule": "cron",
    "cron_expression": "*/20 * * * *",
    "ship_paused": True,
}
```

**Execution paths:**

- **Cron / built-in task:** `action_sync_local_emails` → `asyncio.to_thread(sync_all, owner, full=False)` — incremental only, all enabled accounts, folders from settings.
- **Agent tool:** `do_sync_local_emails` → `sync_all(..., accounts=..., full=bool(args.get("full", False)))` — optional single account, optional full backfill.

**Sync loop** (`sync_all`): accounts sequentially → folders sequentially (after Sent-folder resolution). No wall-clock cap, no pacing sleeps. IMAP fetch batches use hardcoded `_FETCH_CHUNK = 50` with no delay between chunks.

**Logging:** `format_sync_all_log` concatenates full `format_sync_folder_log` output for every folder. `TaskRun.result` is stored at up to **4000** characters (`task_scheduler._set_run_progress` / run completion). `sync_local_emails` is in `_SILENT_ACTIONS` (no assistant chat pollution); Activity log is the primary surface.

**Settings UI:** No dedicated admin UI for email-local-sync keys today. Values are editable via `POST /settings` (admin) or `data/settings.json`. New keys work without UI if added to `DEFAULT_SETTINGS`.

---

## Goals (Phase 1)

1. Lower recommended defaults to reduce IMAP/disk load per pass.
2. Add a per-pass wall-clock budget on the **cron incremental** path (`full=False`).
3. Add configurable pacing delays (account and IMAP chunk).
4. Make `format_sync_all_log` report partial/truncated runs clearly when the budget is hit.
5. Decide scheduling policy: change cron interval, keep `ship_paused`, or both.

**Non-goals (Phase 1):**

- Settings admin UI panel (JSON/API only).
- Intra-folder phase interruption (stop mid-`sync_account_folder` between forward/backfill/gap).
- Parallel account sync.
- Changing `email_local_sync_enabled` default.
- Fixing `tool_schemas.py` `full` default mismatch (`description` says default true; code uses `False`) — note as follow-up.

---

## Recommended default values

Pick single shipped defaults (mid-range of requested bands):

| Key | Current | **Proposed default** | Rationale |
|-----|---------|----------------------|-----------|
| `email_local_sync_backfill_batch` | 200 | **50** | ~4× less work per incremental pass; backfill still progresses over repeated cron runs |
| `email_local_sync_flag_refresh_window` | 200 | **100** | Flags on 100 recent messages is enough for typical read/unread churn |
| `email_local_sync_max_attachment_bytes` | 50 MB | **15 MB** (`15_728_640`) | Middle of 10–25 MB band; skips huge attachments without blocking metadata sync |
| `email_local_sync_attachment_budget_bytes` | 2 GB | **384 MB** (`402_653_184`) | Middle of 256–512 MB band; limits disk spike per folder per pass |

**Migration note:** `load_settings()` merges saved file over defaults. Existing installs **keep** old values until keys are removed from `data/settings.json` or admin updates them. Only fresh installs and keys-not-present get new defaults. Document in changelog; optional one-time migration script is out of scope for P1.

**Also update fallback literals** in:

- `sync_all()` `settings.get(..., <fallback>)` calls (lines 1560–1563)
- `sync_account_folder()` parameter defaults (lines 1196–1199)

Keep fallbacks aligned with `DEFAULT_SETTINGS` so direct function calls match settings-driven behavior.

---

## New settings (Phase 1)

| Key | Type | **Proposed default** | Applies when |
|-----|------|----------------------|--------------|
| `email_local_sync_max_sync_seconds` | int | **180** | `sync_all(..., full=False)` and `max_sync_seconds` not explicitly overridden |
| `email_local_sync_account_delay_ms` | int | **500** | Between accounts in `sync_all` when value > 0 |
| `email_local_sync_chunk_delay_ms` | int | **150** | Between IMAP fetch chunks in `_fetch_rfc822_batch` when value > 0 |

### Semantics

**`email_local_sync_max_sync_seconds`**

- `0` = unlimited (same as today).
- Measured with `time.monotonic()` from start of `sync_all` until return.
- Checked **before** starting each account's folder loop (account boundary). If budget exhausted, skip remaining accounts entirely.
- Checked **before** each `sync_account_folder` call (folder boundary). If exhausted, skip remaining folders for current and future accounts.
- **Not applied** when `full=True` (manual full backfill via agent tool) unless caller explicitly passes a positive `max_sync_seconds`.
- Cron path: `action_sync_local_emails` does not pass override → setting applies.
- Agent tool: `do_sync_local_emails` with `full=True` → no budget (or pass `max_sync_seconds=0`). With `full=False`, apply setting (same as cron).

**Pacing delays**

- `email_local_sync_account_delay_ms`: `time.sleep(ms / 1000)` after each account's folders complete (not after the last account).
- `email_local_sync_chunk_delay_ms`: sleep after each `_FETCH_CHUNK` slice in `_fetch_rfc822_batch`, including the last chunk (acceptable overhead; keeps logic simple).
- Apply on **all** `sync_all` runs when > 0 (cron and manual). Pacing is a politeness knob, not a safety gate.
- Thread `chunk_delay_ms` through: `sync_all` → `sync_account_folder` → `_store_uids` → `_fetch_rfc822_batch` (new optional param).

### Validation (`routes/auth_routes.py`)

Extend `_INT_RANGES` for admin `POST /settings`:

| Key | Range |
|-----|-------|
| `email_local_sync_backfill_batch` | 1–500 |
| `email_local_sync_flag_refresh_window` | 10–5000 |
| `email_local_sync_max_attachment_bytes` | 1_048_576 (1 MB)–104_857_600 (100 MB) |
| `email_local_sync_attachment_budget_bytes` | 10_485_760 (10 MB)–10_737_418_240 (10 GB) |
| `email_local_sync_max_sync_seconds` | 0–3600 |
| `email_local_sync_account_delay_ms` | 0–60_000 |
| `email_local_sync_chunk_delay_ms` | 0–5_000 |

---

## Implementation design

### 1. Settings (`src/settings.py`)

Add three new keys to `DEFAULT_SETTINGS` under the existing local-email comment block. Update four existing defaults. Add inline comments documenting units and cron-only vs all-path behavior.

### 2. `sync_all()` (`routes/email_local_store.py`)

**New signature kwargs:**

```python
def sync_all(
    owner: str | None = None,
    accounts: list[str] | None = None,
    folders: list[str] | None = None,
    *,
    full: bool = False,
    max_sync_seconds: int | None = None,  # None = resolve from settings when full=False
) -> dict[str, Any]:
```

**Result dict additions:**

```python
{
    "ok": True,
    "partial": False,           # True if stopped early (time budget or future reasons)
    "budget_hit": False,          # True specifically when time budget caused stop
    "max_sync_seconds": 180,      # effective budget (0 if unlimited)
    "folders_planned": 4,
    "folders_synced": 2,
    "folders_skipped": 2,
    "skipped": [                  # compact entries for skipped work
        {"account_id": "...", "account": "Work", "folder": "INBOX", "reason": "time_budget"},
    ],
    # ... existing keys ...
}
```

**Loop pseudocode:**

```python
t0 = time.monotonic()
deadline = None
if not full:
    budget = max_sync_seconds if max_sync_seconds is not None else int(settings.get("email_local_sync_max_sync_seconds", 0))
    if budget > 0:
        deadline = t0 + budget

account_delay = int(settings.get("email_local_sync_account_delay_ms", 0))
chunk_delay = int(settings.get("email_local_sync_chunk_delay_ms", 0))

for acc_idx, acc in enumerate(acct_rows):
    for folder in resolved_folders:
        if deadline and time.monotonic() >= deadline:
            record skipped folders (current + rest)
            set partial=True, budget_hit=True
            break out
        item = sync_account_folder(..., chunk_delay_ms=chunk_delay)
        results.append(item)
    if budget_hit:
        break
    if account_delay > 0 and acc_idx < len(acct_rows) - 1:
        time.sleep(account_delay / 1000)
```

**Skipped-folder planning:** Before the loop, build the full planned list `(account, folder)` pairs so skipped entries can be computed without re-deriving Sent-folder names.

### 3. `sync_account_folder()` / `_fetch_rfc822_batch()`

- Add `chunk_delay_ms: int = 0` param; pass to `_fetch_rfc822_batch`.
- In `_fetch_rfc822_batch`, after each chunk iteration (except when `chunk_delay_ms == 0`), sleep.
- No time-budget check inside folder for P1 (folder always runs to completion once started).

**Future (P2):** Optional `deadline: float | None` for intra-folder phase checks.

### 4. Cron action (`src/builtin_actions.py`)

No change beyond relying on `sync_all(..., full=False)` default budget resolution. Optionally pass explicit `max_sync_seconds=None` for clarity in a comment.

Do **not** pass a budget from tests of the action unless testing budget behavior.

### 5. Agent tool (`src/tool_implementations.py`)

```python
full = bool(args.get("full", False))
max_sync = 0 if full else None  # None → settings; 0 → unlimited only if we want full to ignore budget
result = await asyncio.to_thread(
    sync_all, owner or "", accounts=accounts, full=full,
    max_sync_seconds=0 if full else None,
)
```

Incremental manual sync (`full=False`) respects the same 180s default as cron.

### 6. Logging (`format_sync_all_log`, `format_sync_folder_log`)

#### `format_sync_all_log` changes

**Header when complete:**

```
Local email sync: 4 folder(s) across 2 account(s) · 45.2s
```

**Header when partial (budget hit):**

```
Local email sync (partial): 2/4 folder(s) across 2 account(s) · 180.0s · stopped at time budget (180s)
```

**Body structure:**

1. Full `format_sync_folder_log` for each completed result in `results`.
2. One-line stubs for each entry in `skipped`:

   ```
   Work / Sent: skipped (time budget exhausted before this folder)
   ```

3. If total output length exceeds **3500** characters (leave headroom under 4000 `TaskRun` cap):
   - Keep header and partial notice intact.
   - Keep all folder stubs (skipped are one line each).
   - Truncate completed folder detail from the **oldest** folders first, replacing with:

     ```
     Personal / INBOX: [log truncated — see folder sync_state in DB]
     ```

   - Append footer: `… 1 folder log(s) truncated for Activity display`.

**`format_sync_folder_log`:** Optional small addition when `item.get("interrupted")` — not needed for P1 folder-boundary stop.

#### Result metadata for formatters

`format_sync_all_log` should read top-level `partial`, `budget_hit`, `max_sync_seconds`, `folders_synced`, `folders_planned`, `skipped` from the `sync_all` return value, not infer from duration alone.

### 7. Scheduling policy (item 5)

#### Recommendation: **keep `ship_paused: True`; keep `*/20` cron**

| Option | Pros | Cons |
|--------|------|------|
| **A. `ship_paused` only (recommended)** | Matches `summarize_emails`, `check_email_urgency`, etc.; user opts in via Tasks UI; safe for large mailboxes | Users must discover and unpause the task |
| B. Remove `ship_paused` | Mirror starts automatically | Surprise IMAP load on upgrade; conflicts with “invasive email tasks ship paused” pattern |
| C. Loosen cron to `*/30` or `0 * * * *` | Less frequent when enabled | Slower catch-up for new mail; marginal benefit once time budget exists |
| D. `ship_paused: False` + lower defaults | Faster “it just works” | Still risky for multi-account / large INBOX first backfill |

**Ship decision:**

- Leave `HOUSEKEEPING_DEFAULTS["sync_local_emails"]` at `ship_paused: True` and `cron_expression: "*/20 * * * *"`.
- With 180s budget + batch 50, a 20-minute cadence is reasonable once the user unpause.
- If product wants less aggressiveness without hiding the feature: optional **C** (`*/30`) is a one-line change affecting only new seeds and `/revert`; existing user tasks keep their cron until reverted.

**Do not** add `old_cron_expressions` unless cron actually changes (pattern used by `check_email_urgency` migration in `ensure_defaults`).

**User enablement checklist (document in task description / help):**

1. `email_local_sync_enabled` is true (default).
2. Tasks → **Email Local Sync** → unpause.
3. Optional: tune `data/settings.json` keys for large deployments.

---

## File change checklist

| File | Changes |
|------|---------|
| `src/settings.py` | New keys + lowered defaults |
| `routes/email_local_store.py` | `sync_all` budget/pacing/skipped; `sync_account_folder` + `_fetch_rfc822_batch` chunk delay; log formatters |
| `src/builtin_actions.py` | Confirm `full=False` path (minimal) |
| `src/tool_implementations.py` | `max_sync_seconds` override when `full=True` |
| `routes/auth_routes.py` | `_INT_RANGES` for new numeric keys |
| `src/task_scheduler.py` | **No change** (unless product picks cron tweak) |
| `tests/test_email_local_store_sync.py` | Budget stop, pacing (mock sleep), skipped metadata |
| `tests/test_email_local_store_sync_log.py` | Partial header, skipped stubs, truncation |
| `tests/test_auth_regressions.py` or new | Settings validation ranges |

**Optional / follow-up:**

| File | Changes |
|------|---------|
| `static/js/settings.js` | Admin “Local email sync” section |
| `src/tool_schemas.py` | Align `full` default description with code |
| `src/agent_loop.py` | Mention time-bounded cron vs unbounded `full` backfill |

---

## Test plan

### Unit: `sync_all` time budget

1. **Stops before Nth folder:** 3 accounts × 2 folders, budget 0.1s, mock `sync_account_folder` to sleep 0.05s each → assert `folders_synced == 2`, `budget_hit`, `partial`, `skipped` length 4.
2. **Unlimited when `full=True`:** Same setup, `full=True`, `max_sync_seconds=0` → all folders run.
3. **Explicit override:** `max_sync_seconds=300` with low setting in mocked settings → uses 300.

### Unit: pacing

1. Mock `time.sleep`; 2 accounts, `account_delay_ms=100` → exactly 1 sleep between accounts.
2. `_fetch_rfc822_batch` with 120 UIDs, `chunk_delay_ms=50`, `_FETCH_CHUNK=50` → 3 chunk sleeps (or 2 if skipping after last — document chosen behavior in test).

### Unit: log formatting

1. `test_format_sync_all_log_partial_budget` — header contains `(partial)` and `stopped at time budget`.
2. Skipped folder one-liners present.
3. Artificially long completed logs → truncation footer and char count < 3600.

### Regression

1. Existing `test_backfill_batch_limits_older_per_pass` still passes with batch=50 default in tests (tests pass explicit batch).
2. `test_ship_paused_housekeeping_stays_paused_by_default` unchanged.
3. Attachment budget test (`attachment_budget_bytes=10_000`) unchanged.

### Manual

1. Fresh install: verify `Email Local Sync` task is **paused**; unpause; run once; Activity shows duration < budget or partial header.
2. Large mailbox: confirm incremental pass completes within budget; next cron continues backfill.
3. Agent `sync_local_emails` with `{"full": true}` runs until complete (no partial header).

---

## Rollout and observability

- **Logging:** `logger.info` in `sync_all` when `budget_hit`: owner, folders_synced, folders_skipped, elapsed.
- **sync_state table:** Skipped folders retain previous `last_sync_at`; no phantom “success” for folders never attempted this pass.
- **Docs:** Short addition to `docs/setup.md` or email docs listing new settings keys and enablement steps.
- **Changelog:** Call out default changes affect new installs only; recommend admins review `data/settings.json`.

---

## Implementation order

1. Settings defaults + validation ranges (low risk, no behavior change until read).
2. `chunk_delay_ms` plumbing + account delay (isolated, testable).
3. `sync_all` time budget + result metadata.
4. `format_sync_all_log` partial/truncation.
5. Wire `tool_implementations.py` full-vs-incremental budget policy.
6. Tests.
7. Confirm scheduling policy (no `task_scheduler.py` change unless cron tweak approved).

Estimated scope: **~250–400 lines** across production code + tests; no migrations, no schema changes.

---

## Open questions (resolved at implementation)

1. **Default `email_local_sync_max_sync_seconds`:** **180s** (shipped).
2. **Truncate completed logs from oldest or newest first?** **Oldest** first (most recent folder stays visible in Activity).
3. **Cron tweak to `*/30`:** **No change**; still `*/20`, `ship_paused: True`.
4. **Admin UI in P1 or P2?** **P2**; JSON/API editing only for now.
