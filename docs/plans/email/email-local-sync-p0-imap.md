# Phase 0: Local email sync IMAP hardening

**Status:** Implemented (Phase 0+1, 2026-07-01)  
**Scope:** `routes/email_local_store.py` sync pipeline  
**Related issues/patterns:** #1961 (iCloud `RFC822`), #1613 (poisoned socket after `SEARCH ALL`), Gmail post-literal FLAGS (`test_email_gmail_fetch_flags.py`)

## Implementation notes

| Shipped | Location / behavior |
|---------|---------------------|
| `(BODY.PEEK[] FLAGS)` instead of `(RFC822 FLAGS)` | `_fetch_body_batch` in `routes/email_local_store.py` |
| Shared `_group_uid_fetch_records` (Gmail post-literal FLAGS) | `routes/email_helpers.py`; imported by local store and routes |
| Reconnect on poisoned socket after `UID SEARCH ALL` | `_imap_uid_search_all` |
| Reconnect on batched / per-UID `UID FETCH` failure | `_fetch_body_batch` |
| Tests | `tests/test_email_local_store_sync.py`, `tests/test_email_local_store_imap_fetch.py`, `tests/test_email_gmail_fetch_flags.py` |

| Deferred | Notes |
|----------|-------|
| — | All planned P0 IMAP items shipped |

The sections below describe the original design and pre-implementation baseline.

## Summary

Three tightly related fixes for the local SQLite mirror sync:

1. Fetch full messages with `(BODY.PEEK[] FLAGS)` instead of `(RFC822 FLAGS)`.
2. Parse batched FETCH responses with `_group_uid_fetch_records` (shared with `email_routes.py`) instead of `_parse_fetch_items`.
3. Reconnect on poisoned IMAP sockets after failed `UID SEARCH ALL` and batched `UID FETCH`, using the `_latest_inbox_fallback_uids` pattern from `email_pollers.py`.

Together these fix iCloud silent empty bodies, Gmail lost FLAGS on batch fetch, and large-mailbox SEARCH timeouts that leave unread bytes on the socket.

---

## Current state (pre-implementation baseline)

### Message body fetch

```687:706:routes/email_local_store.py
def _fetch_rfc822_batch(conn_imap, uids: list[int]) -> tuple[list[tuple[int, str, bytes]], str | None]:
    ...
        status, data = conn_imap.uid("FETCH", uid_set, "(RFC822 FLAGS)")
    ...
            st, one = conn_imap.uid("FETCH", str(uid), "(RFC822 FLAGS)")
```

- Uses bare `RFC822`, which iCloud ignores (returns `OK` + `(UID n)` only, no literal). Same class of bug fixed in `mcp_servers/email_server.py` (#1961).
- `RFC822` can implicitly set `\Seen` on some servers; `BODY.PEEK[]` does not (matches `read_email` in `email_routes.py` line ~1356).

### Response parsing

```668:684:routes/email_local_store.py
def _parse_fetch_items(data: list) -> list[tuple[int, str, bytes]]:
    for item in data:
        if not isinstance(item, tuple) or len(item) < 2:
            continue
        ...
```

- Only inspects `(meta, literal)` tuples; drops bare `bytes` continuations.
- Gmail sends `FLAGS` **after** the body literal as a bare element (see `test_email_gmail_fetch_flags.py`). Result: every synced Gmail message stores `is_read=0` even when `\Seen` is set server-side.
- `email_routes.py` already has the correct grouper:

```291:320:routes/email_routes.py
def _group_uid_fetch_records(msg_data) -> list:
    ...
```

### UID SEARCH (no reconnect)

```1264:1267:routes/email_local_store.py
        status, data = conn_imap.uid("SEARCH", None, "ALL")
        server_uids = []
        if status == "OK" and data and data[0]:
            server_uids = sorted(int(x) for x in data[0].split())
```

- No try/except; no reconnect on timeout mid-response (#1613).
- Contrast `email_pollers._latest_inbox_fallback_uids` (lines 113–141): on failure, `logout()` poisoned conn, return fresh conn from `reconnect()`.

### Duplicate helpers

| Symbol | `email_local_store.py` | `email_routes.py` |
|--------|------------------------|-------------------|
| `_uid_from_fetch_meta` | returns `int \| None` (L150–152) | returns `str` (L283–285) |
| `_flags_from_fetch_meta` | L155–159 | inline regex in routes |
| fetch grouping | `_parse_fetch_items` | `_group_uid_fetch_records` |

### Tests today

- `tests/test_email_local_store_sync.py` — `FakeIMAP` simulates Dovecot-style `(RFC822 {n}` + bare `b")"`; all sync tests pass through `_fetch_rfc822_batch`.
- `tests/test_email_gmail_fetch_flags.py` — covers `_group_uid_fetch_records` only in routes context (header fetch shape).
- `tests/test_email_fallback_reconnect.py` — reconnect pattern for poller SEARCH only.
- `tests/test_icloud_imap_full_fetch.py` — source guard on `email_server.py`, not local store.

---

## Implementation order (within this bundle)

Execute in this sequence to keep each step testable and avoid circular imports.

| Step | What | Why this order |
|------|------|----------------|
| **0** | Extract shared IMAP fetch helpers | Unblocks local store without importing `email_routes` |
| **1** | Switch parse path to `_group_uid_fetch_records` | Can land with a test-only fetch item change first |
| **2** | Change fetch item to `(BODY.PEEK[] FLAGS)` | Depends on grouping; rename `_fetch_rfc822_batch` |
| **3** | Add reconnect for `SEARCH ALL` + FETCH batches | Threads `conn` through callers; independent of parse semantics but touches same functions |

Steps 1+2 can be one commit if preferred; step 0 should land first.

---

## Step 0: Extract shared helper (recommended: `email_helpers.py`)

### Rationale

- `email_local_store` must **not** import `email_routes` at module level (`email_routes` lazily imports local store inside route setup ~L3733).
- `email_routes.py` header comment already states non-route logic belongs in `email_helpers.py`.

### Move these symbols from `email_routes.py` → `email_helpers.py`

| Symbol | Current lines (`email_routes.py`) |
|--------|----------------------------------|
| `_FETCH_SEQ_RE` | 288 |
| `_group_uid_fetch_records` | 291–320 |
| `_uid_from_fetch_meta` | 283–285 (str return) |

### Call-site updates

| File | Change |
|------|--------|
| `routes/email_routes.py` | `from routes.email_helpers import _group_uid_fetch_records, _uid_from_fetch_meta`; delete moved definitions |
| `routes/email_local_store.py` | Import `_group_uid_fetch_records`, `_flags_from_fetch_meta` helper (new or moved) from `email_helpers` |
| `tests/test_email_gmail_fetch_flags.py` | Import from `email_helpers` instead of `email_routes` |

### `_uid_from_fetch_meta` type unification

- Keep **one** implementation in `email_helpers` returning `str` (matches routes/tests).
- In `email_local_store.py`, replace local `_uid_from_fetch_meta` (L150–152) with `int(_uid_from_fetch_meta(meta_b) or 0)` at use sites, or a thin `def _uid_int_from_meta(meta_b) -> int | None` wrapper in local store only.
- Keep `_flags_from_fetch_meta` in `email_helpers` (move from local store L155–159) so grouping + flag extraction share one module.

**Estimated diff:** ~45 lines added to `email_helpers.py`, ~40 removed from `email_routes.py`, ~15 changed in tests.

---

## Step 1: Replace `_parse_fetch_items` with grouped parse

### Delete

- `_parse_fetch_items` (`email_local_store.py` L668–684)

### Add (in `email_local_store.py`)

```python
def _parse_body_fetch_grouped(data: list) -> list[tuple[int, str, bytes]]:
    """Turn imaplib UID FETCH data into (uid, flags_str, raw_bytes) records."""
    out: list[tuple[int, str, bytes]] = []
    for meta_b, raw in _group_uid_fetch_records(data):
        if not raw:
            continue
        uid_s = _uid_from_fetch_meta(meta_b)
        if not uid_s:
            continue
        flags = _flags_from_fetch_meta(meta_b)
        out.append((int(uid_s), flags, raw))
    return out
```

### Notes

- Grouping fixes Gmail FLAGS regardless of fetch item (`RFC822.HEADER` vs `BODY.PEEK[]`).
- `_fetch_imap_flags` (L787–804) has the **same** tuple-only bug but is **out of scope** for P0 unless we add a one-line note in a follow-up; flag sync window uses `(FLAGS)` only and is less affected. Optional P0.1: apply grouping there too (~10 lines).

**Estimated diff:** ~25 lines changed in `email_local_store.py`.

---

## Step 2: `RFC822` → `BODY.PEEK[] FLAGS`

### Functions to change

| Function | Lines | Action |
|----------|-------|--------|
| `_fetch_rfc822_batch` | 687–706 | Rename → `_fetch_body_batch`; change fetch string; call `_parse_body_fetch_grouped` |
| `_store_uids` | 725 | Call `_fetch_body_batch` instead of `_fetch_rfc822_batch` |

### Line-level edits in `_fetch_body_batch` (formerly `_fetch_rfc822_batch`)

1. **L695:** `"(RFC822 FLAGS)"` → `"(BODY.PEEK[] FLAGS)"`
2. **L701:** per-UID fallback same change
3. **L697, L703:** `_parse_fetch_items` → `_parse_body_fetch_grouped`
4. After step 3 (reconnect): extend return type to include possibly replaced `conn` (see below)

### Behavioral expectations

- **iCloud:** body literal present where `RFC822` returned none.
- **Gmail / Dovecot:** same bytes as before; `email.message_from_bytes` unchanged downstream.
- **Read state:** sync already runs `sync_flags` after store; `BODY.PEEK[]` avoids accidental `\Seen` during fetch (RFC822 risk removed).
- **Attachments / `_parse_message_for_store`:** unchanged; still full MIME blob.

### Optional source guard (new test file)

Mirror `tests/test_icloud_imap_full_fetch.py` but target `routes/email_local_store.py`:

- Assert no `"(RFC822)"` in `conn_imap.uid("FETCH"` calls for full-message sync.
- Assert at least one `"(BODY.PEEK[]"` in the batch fetch function.

**Estimated diff:** ~20 lines in `email_local_store.py`, ~30 lines new test.

---

## Step 3: Reconnect on poisoned socket

### Reference pattern

```113:141:routes/email_pollers.py
def _latest_inbox_fallback_uids(conn, reconnect):
    try:
        conn.select("INBOX", readonly=True)
        status, data = conn.uid("SEARCH", None, "ALL")
        ...
        return uids, conn
    except Exception as _e:
        logger.warning(...)
        try:
            conn.logout()
        except Exception:
            pass
        return [], reconnect()
```

### New helpers in `email_local_store.py`

#### `_imap_safe_logout(conn) -> None`

- try/except wrapper around `conn.logout()` (copy poller style).

#### `_imap_uid_search_all(conn, folder, *, reconnect) -> tuple[list[int], Any]`

**Used by:** `sync_account_folder` (replaces inline L1264–1267).

**Algorithm:**

1. `try`:
   - `conn.uid("SEARCH", None, "ALL")` (folder already SELECTed readonly in caller).
   - On `OK` + data: return `sorted(int(...) ...)`, `conn`.
   - On non-OK without exception: return `[]`, `conn` (log warning; no reconnect unless exception).
2. `except Exception as e`:
   - `logger.warning("UID SEARCH ALL failed for %s: %s; reconnecting", folder, e)`
   - `_imap_safe_logout(conn)`
   - `fresh = reconnect()`
   - `fresh.select(_q(folder), readonly=True)` — required before retry
   - Retry SEARCH once; return uids, `fresh`
3. If retry also fails: return `[]`, `fresh` (caller sets `summary["error"]` or proceeds with empty mailbox).

**Reconnect lambda** (constructed in `sync_account_folder`):

```python
def _reconnect():
    return _imap_connect(account_id, owner=owner)
```

#### `_fetch_body_batch(..., folder, reconnect) -> tuple[list, str | None, Any]`

**Extend signature** to return `(records, last_error, conn)`.

**Per chunk** (`_FETCH_CHUNK` = 50):

1. `try` batch `UID FETCH uid_set (BODY.PEEK[] FLAGS)`.
2. On success: extend with `_parse_body_fetch_grouped(data)`.
3. `except Exception`:
   - logout, `conn = reconnect()`, `conn.select(_q(folder), readonly=True)`, retry same chunk once.
4. On non-OK status (no exception): existing per-UID fallback loop; wrap each single-UID fetch in same try/reconnect/retry once pattern if exception.

**Thread `conn` through:**

| Caller | Change |
|--------|--------|
| `_store_uids` | Accept optional `reconnect`; return `(stored, new_count, conn)` or mutate via list holder |
| `sync_account_folder` | `conn_imap, server_uids = ...` from search helper; reassign after `_store_uids` / each phase |

Minimal-invasive pattern: use a one-element list `conn_box = [conn_imap]` mutated by helpers, or explicit reassignment:

```python
fetched, err, conn_imap = _fetch_body_batch(conn_imap, uids, folder=folder, reconnect=_reconnect)
```

Apply reconnect wrapper at **two** call sites in `sync_account_folder`:

- Initial `UID SEARCH ALL` (after first successful SELECT + uidvalidity read).
- All `_store_uids` invocations (forward, backfill, gap repair) — reconnect propagates inside `_fetch_body_batch`.

**Do not** reconnect on every benign `NO` response; only on **exceptions** (timeout, protocol parse error, broken pipe). Matches #1613 and `test_email_fallback_reconnect.py`.

**Estimated diff:** ~70–90 lines in `email_local_store.py`.

---

## Test plan

### Update existing: `tests/test_email_local_store_sync.py`

#### `FakeIMAP.uid` FETCH branch (L59–76)

- Detect full-body fetch via `"(BODY.PEEK[]"` in `arg2` (and keep accepting `"(RFC822"` temporarily during transition if doing incremental PRs).
- Emit meta like: `f"{seq} (UID {uid} BODY.PEEK[] {{{len(raw)}}}"` instead of `RFC822`.
- For Gmail regression, add optional `gmail_style=True` constructor flag:
  - After each `(meta, raw)` tuple, append bare `rb" FLAGS (\Seen))"` or `rb" FLAGS ())"` **without** FLAGS in meta (copy shapes from `test_email_gmail_fetch_flags.py`).

#### New tests in same file

| Test | Asserts |
|------|---------|
| `test_sync_stores_gmail_post_literal_flags` | `FakeIMAP(gmail_style=True)`, one message with `\Seen`; after sync `is_read=1` |
| `test_sync_icloud_body_peek_not_empty_rfc822` | Fake returns `(UID n)` only for `RFC822` but body for `BODY.PEEK[]`; sync stores body text |
| `test_search_all_reconnects_on_failure` | First conn raises on SEARCH; reconnect factory returns second conn; sync completes |
| `test_fetch_batch_reconnects_on_failure` | SEARCH ok; first FETCH chunk raises; reconnect + re-select; message still stored |

### New file: `tests/test_email_local_store_imap_fetch.py` (optional split)

- Source guard: no bare `(RFC822)` full fetch in `email_local_store.py` (like `test_icloud_imap_full_fetch.py`).
- Unit test `_parse_body_fetch_grouped` with imported `GMAIL_RESPONSE` adapted for `BODY.PEEK[]` meta strings.

### Update: `tests/test_email_gmail_fetch_flags.py`

- Import `_group_uid_fetch_records` from `email_helpers` after extraction (tests should still pass unchanged).

### Reuse patterns from

- `tests/test_email_fallback_reconnect.py` — `_FakeConn` with `raise_on_search`, reconnect call count, `logged_out` flag.

**Estimated diff:** ~120–180 lines test changes/additions.

---

## Provider risks

| Provider | Risk | Mitigation |
|----------|------|------------|
| **iCloud** | Bare `RFC822` returns no body (primary bug) | `BODY.PEEK[]` (proven in `email_server.py`) |
| **Gmail** | FLAGS after literal; huge `SEARCH ALL` timeout poisons socket | Grouping + reconnect |
| **Dovecot / self-hosted** | FLAGS before literal (current `FakeIMAP` shape) | Existing Dovecot tests + grouping tests |
| **Outlook / M365** | Generally supports `BODY.PEEK[]` | Manual smoke on one account post-merge |
| **Yahoo / legacy** | Rare non-PEEK quirks | Per-UID fallback already exists; log failures in `sync_state.last_error` |
| **Readonly SELECT** | Reconnect must re-`select(readonly=True)` before FETCH | Explicit in helper |

### Not in P0 scope (document for later)

- `_fetch_imap_flags` tuple-only parse (Gmail flag **sync window** may still miss post-literal FLAGS).
- `email_pollers.py` still uses `(RFC822)` for auto-summarize (L330) — separate slice.
- `email_routes.py` attachment endpoints still use `(RFC822)` (L1604, 1621, 1657, 1927).

---

## Rollback

| Scenario | Action |
|----------|--------|
| Single commit bundle | `git revert` the merge commit |
| Partial failure (BODY.PEEK rejected by one provider) | Revert fetch string only; keep grouping + reconnect |
| Reconnect causes connection storm | Guard: max **one** reconnect per SEARCH and per FETCH chunk; no loop |
| Data impact | None destructive; worst case skips messages for one sync pass (`last_error` set). Re-sync recovers. |
| SQLite schema | No migration |

No feature flag required; changes are protocol-correctness fixes aligned with existing UI/MCP paths.

---

## Estimated total diff size

| Area | Lines (approx.) |
|------|-----------------|
| `routes/email_helpers.py` | +50 |
| `routes/email_routes.py` | −40, +5 imports |
| `routes/email_local_store.py` | +100 / −50 net (~80–120 touched) |
| `tests/test_email_local_store_sync.py` | +100–130 |
| `tests/test_email_gmail_fetch_flags.py` | ~5 |
| New test file(s) | +40–60 |
| **Total** | **~250–350 lines** across **5–6 files** |

---

## Verification checklist (post-implementation)

- [x] `pytest tests/test_email_local_store_sync.py tests/test_email_gmail_fetch_flags.py tests/test_email_fallback_reconnect.py -q`
- [x] New reconnect + Gmail FLAGS + iCloud BODY tests green (`tests/test_email_local_store_imap_fetch.py`)
- [x] `rg 'RFC822 FLAGS' routes/email_local_store.py` → no matches
- [ ] Manual: one Gmail account — sync INBOX, confirm `is_read` matches server for recent mail
- [ ] Manual (if available): iCloud account — sync stores `body_text` / snippet (not empty)
- [ ] Large mailbox: run sync after simulated timeout; confirm no `unexpected response` on subsequent SELECT

---

## File touch list (implementation)

| File | Role |
|------|------|
| `routes/email_helpers.py` | Shared `_group_uid_fetch_records`, `_uid_from_fetch_meta`, `_flags_from_fetch_meta` |
| `routes/email_routes.py` | Import shared helpers; remove duplicates |
| `routes/email_local_store.py` | BODY.PEEK fetch, grouped parse, SEARCH/FETCH reconnect |
| `tests/test_email_local_store_sync.py` | FakeIMAP + integration tests |
| `tests/test_email_gmail_fetch_flags.py` | Update import path |
| `tests/test_email_local_store_imap_fetch.py` (new, optional) | Source guard + parse unit tests |

**Not modified in P0:** `routes/email_pollers.py` (reference only), `mcp_servers/email_server.py` (already fixed).
