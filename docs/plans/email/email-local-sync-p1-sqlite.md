# Phase 1: SQLite optimizations for local email sync

**Status:** Implemented (Phase 0+1, 2026-07-01)  
**Scope:** `routes/email_local_store.py` sync hot path only.  
**Out of scope:** IMAP changes, schema migrations beyond indexes, UI/API, multi-phase refactors.  
**Goal:** Reduce per-sync CPU, memory, and disk I/O for large folders without changing observable sync behavior.

## Implementation notes

| Shipped | Location / behavior |
|---------|---------------------|
| SQL anti-join gap detection via temp table | `_missing_uids_anti_join`, `_ensure_server_uid_temp` |
| `RETURNING id` in `_upsert_message` | Removes post-upsert `SELECT id` |
| `executemany` for attachment inserts | `_upsert_message` |
| Index `ix_attachments_message_row_id` | `_init_local_store_db` |
| Skip attachment re-extract when metadata unchanged + files on disk | `_can_reuse_attachments`, `reuse_attachments` in `_store_uids` |
| Regression anchor | `test_gap_repair_fills_missing_interior_uid` still passes |

| Deferred | Notes |
|----------|-------|
| Composite `ix_messages_sync_uid` on `(owner, account_id, folder, uidvalidity, uid)` | Skipped; implicit unique index covers anti-join probes |
| EXPLAIN QUERY PLAN gate documentation in PR | Index not added after measurement |
| Batch `_upsert_message` in single transaction | Future work (see end of doc) |

The sections below describe the original design and implementation order.

---

## Context

`sync_account_folder()` runs three fetch phases per pass:

1. **Forward** — UIDs above local `MAX(uid)`
2. **Backfill** — UIDs below local `MIN(uid)` (older mail)
3. **Gap repair** — interior UIDs present on server but missing locally

Each fetched UID flows through `_store_uids()` → `_parse_message_for_store()` → `_extract_attachments_for_store()` → `_upsert_message()`.

### Current pain points

| Location | Issue |
|----------|-------|
| `_gap_repair_once()` (L1362–1384) | `_stored_uid_set()` loads **every** stored UID into a Python `set`, then filters `server_uids` in memory |
| `sync_account_folder()` summary (L1447–1452) | Second full `_stored_uid_set()` for `missing_count` / `stale_local_count` |
| `_upsert_message()` (L584–649) | `SELECT id` before upsert **and** after upsert |
| `_upsert_message()` (L651–664) | One `INSERT` per attachment in a loop |
| `_upsert_message()` existing path (L589–603) | Always unlinks all attachment files before re-extract, even when content unchanged |
| Indexes | No index on `attachments(message_row_id)`; sync filter index coverage unverified |

### Regression anchor

`tests/test_email_local_store_sync.py::test_gap_repair_fills_missing_interior_uid` must keep passing unchanged:

- Full sync 10 messages → delete local row for UID 6 → incremental sync (`backfill_batch=5`) → UID 6 restored, `total == 10`, `backfill_complete is True`.

---

## Implementation order

Work in this sequence; each item is independently shippable but later items assume earlier ones land cleanly.

1. Indexes (items 4–5) — low risk, measurable baseline for EXPLAIN
2. `RETURNING id` in `_upsert_message` (item 2)
3. `executemany` for attachments (item 3)
4. SQL anti-join gap detection (item 1)
5. Attachment skip-on-unchanged (item 6) — highest behavioral risk; last

---

## Item 1: SQL anti-join gap detection (temp table)

### Problem

```479:493:routes/email_local_store.py
def _stored_uid_set(
    conn: sqlite3.Connection,
    owner: str,
    account_id: str,
    folder: str,
    uidvalidity: int,
) -> set[int]:
    rows = conn.execute(
        """
        SELECT uid FROM messages
        WHERE owner=? AND account_id=? AND folder=? AND uidvalidity=?
        """,
        (owner or "", account_id, folder, uidvalidity),
    ).fetchall()
    return {int(r[0]) for r in rows}
```

Called in `_gap_repair_once()` (hot path) and again at end of sync for summary stats. For a folder with 50k stored messages, this allocates a 50k-element Python set twice per sync pass.

### Design

Introduce `_ensure_server_uid_temp(conn)` and `_missing_uids_anti_join(...)` that:

1. Create a **session-scoped temp table** once per sync connection:

   ```sql
   CREATE TEMP TABLE IF NOT EXISTS _sync_server_uids (
       uid INTEGER PRIMARY KEY
   ) WITHOUT ROWID;
   ```

2. **Populate once** after `server_uids` is known in `sync_account_folder()` (after IMAP `SEARCH`):

   ```python
   conn.execute("DELETE FROM _sync_server_uids")
   conn.executemany(
       "INSERT INTO _sync_server_uids (uid) VALUES (?)",
       [(u,) for u in server_uids],
   )
   ```

   Use a single populate per sync pass; reuse for gap repair **and** summary.

3. **Gap repair query** — server UIDs with no matching local row, ordered DESC (matches current `sorted(..., reverse=True)` batch priority):

   ```sql
   SELECT s.uid
   FROM _sync_server_uids AS s
   LEFT JOIN messages AS m
     ON m.owner = ?
    AND m.account_id = ?
    AND m.folder = ?
    AND m.uidvalidity = ?
    AND m.uid = s.uid
   WHERE m.uid IS NULL
   ORDER BY s.uid DESC
   LIMIT ?
   ```

   Pass `backfill_batch` as limit when `full=False`; omit limit when `full=True` (or use a very large cap if needed for safety).

4. **Summary queries** on the same temp table (replace second `_stored_uid_set`):

   - `missing_count`:

     ```sql
     SELECT COUNT(*) FROM _sync_server_uids s
     LEFT JOIN messages m ON ... AND m.uid = s.uid
     WHERE m.uid IS NULL
     ```

   - `stale_local_count` (local UIDs not on server):

     ```sql
     SELECT COUNT(*) FROM messages m
     LEFT JOIN _sync_server_uids s ON s.uid = m.uid
     WHERE m.owner=? AND m.account_id=? AND m.folder=? AND m.uidvalidity=?
       AND s.uid IS NULL
     ```

### API changes

| Function | Action |
|----------|--------|
| `_stored_uid_set` | Keep as private helper for tests/debug **or** delete if fully superseded |
| `_gap_repair_once()` | Replace set diff with `_missing_uids_anti_join(..., limit=backfill_batch)` |
| End-of-sync summary | Replace `stored_set` / `server_uid_set` set diffs with SQL counts above |
| `backfill_complete` | Derive from `missing_count == 0` plus existing `min_uid <= server_min` check (unchanged logic) |

### Files to touch

- `routes/email_local_store.py` — new helpers, refactor `_gap_repair_once`, refactor summary block (~L1447–1464)

### Tests

- **Must pass:** `test_gap_repair_fills_missing_interior_uid`
- **Also run:** `test_backfill_batch_limits_older_per_pass`, `test_stale_local_count_when_server_message_expunged` (summary counts), `test_full_backfill_terminates_after_incremental`
- **Optional new test:** `_missing_uids_anti_join` unit test with pre-seeded DB + temp table, assert `[6]` when UID 6 deleted from 1..10

### Rollback / safety

- Temp table is connection-scoped; no persistent schema change
- If anti-join batch ordering differs, gap repair may fetch different UIDs first but still converges; preserve `ORDER BY s.uid DESC` to match current behavior

---

## Item 2: `RETURNING id` in `_upsert_message`

### Problem

```584:649:routes/email_local_store.py
    existing = conn.execute(
        "SELECT id FROM messages WHERE owner=? AND account_id=? AND folder=? AND uid=? AND uidvalidity=?",
        (owner or "", account_id, folder, uid, uidvalidity),
    ).fetchone()
    is_new = existing is None
    ...
    conn.execute("""INSERT INTO messages ... ON CONFLICT ... DO UPDATE SET ...""", (...))
    row = conn.execute(
        "SELECT id FROM messages WHERE owner=? AND account_id=? AND folder=? AND uid=? AND uidvalidity=?",
        (owner or "", account_id, folder, uid, uidvalidity),
    ).fetchone()
    message_row_id = int(row[0])
```

Every stored message pays **two** keyed lookups on the unique constraint. The post-upsert `SELECT` is redundant.

### Design

1. **Keep** the pre-upsert `SELECT id` — still required to:
   - Set `is_new`
   - Load old attachment paths for unlink (item 6 may refine this)

2. **Replace** post-upsert `SELECT` with `RETURNING id`:

   ```sql
   INSERT INTO messages (...)
   VALUES (...)
   ON CONFLICT(owner, account_id, folder, uid, uidvalidity) DO UPDATE SET
       ...
   RETURNING id
   ```

   ```python
   row = conn.execute(upsert_sql, params).fetchone()
   message_row_id = int(row[0])
   ```

3. **SQLite version:** Python 3.12 stdlib ships SQLite ≥ 3.35 (`RETURNING` supported). No extra dependency.

4. **`is_new` semantics:** Unchanged — still `existing is None` from first SELECT. Do not infer insert vs update from `RETURNING` or `sqlite3.Connection.total_changes`.

### Files to touch

- `routes/email_local_store.py` — `_upsert_message()` only

### Tests

- `test_upsert_dedup_on_resync` — `is_new` / row counts
- `test_upsert_message_unlinks_old_attachment_on_update` — still returns valid `message_row_id`
- All sync tests (implicit coverage)

### Edge cases

- `ON CONFLICT DO UPDATE` with `RETURNING` returns the **updated** row's `id` (same as before)
- If upsert ever fails, behavior unchanged (exception before attachment insert)

---

## Item 3: `executemany` for attachment inserts

### Problem

```650:664:routes/email_local_store.py
    conn.execute("DELETE FROM attachments WHERE message_row_id=?", (message_row_id,))
    for att in attachment_rows:
        conn.execute(
            """
            INSERT INTO attachments (...)
            VALUES (?,?,?,?,?,?,?,?,?)
            """,
            (...),
        )
```

N attachments ⇒ N round trips through the SQLite VM.

### Design

```python
conn.execute("DELETE FROM attachments WHERE message_row_id=?", (message_row_id,))
if attachment_rows:
    conn.executemany(
        """
        INSERT INTO attachments (
            message_row_id, idx, filename, content_type, size,
            is_inline, local_path, extracted, skipped_reason
        ) VALUES (?,?,?,?,?,?,?,?,?)
        """,
        [
            (
                message_row_id,
                att["idx"],
                att["filename"],
                att["content_type"],
                att["size"],
                att["is_inline"],
                att.get("local_path"),
                att.get("extracted", 0),
                att.get("skipped_reason"),
            )
            for att in attachment_rows
        ],
    )
```

- Preserve tuple order and `att.get("local_path")` / `att.get("extracted", 0)` defaults exactly
- Empty `attachment_rows` → skip `executemany` (DELETE still runs to clear stale rows)

### Files to touch

- `routes/email_local_store.py` — `_upsert_message()` only

### Tests

- `test_attachment_written_and_oversized_skipped` — mixed extracted/skipped rows
- `test_upsert_message_unlinks_old_attachment_on_update`
- `test_purge_unlinks_attachment_files`

### Notes

- `executemany` runs in a single transaction with surrounding statements (already inside sync's commit boundary)
- No change to attachment row shape or FK behavior

---

## Item 4: Composite index `ix_messages_sync_uid` (EXPLAIN-gated)

### Problem

Sync queries repeatedly filter:

```sql
WHERE owner=? AND account_id=? AND folder=? AND uidvalidity=?
```

often joined or extended with `uid`.

### Existing coverage

Schema already defines:

```sql
UNIQUE(owner, account_id, folder, uid, uidvalidity)
```

SQLite creates an implicit index on the full unique key. Anti-join pattern:

```sql
... ON m.owner=? AND m.account_id=? AND m.folder=? AND m.uidvalidity=? AND m.uid=s.uid
```

should use that index for the `uid` probe once equality prefixes match.

### Design (measure first, add only if needed)

1. **Before implementation**, capture baseline on a representative DB (or test fixture with 10k+ rows):

   ```sql
   EXPLAIN QUERY PLAN
   SELECT s.uid FROM _sync_server_uids s
   LEFT JOIN messages m ON m.owner=? AND m.account_id=? AND m.folder=? AND m.uidvalidity=? AND m.uid=s.uid
   WHERE m.uid IS NULL
   ORDER BY s.uid DESC LIMIT 200;
   ```

   Repeat for:

   - `_min_stored_uid` / `_max_stored_uid`
   - Pre-upsert `SELECT id ... AND uid=? AND uidvalidity=?`

2. **Add index only if** EXPLAIN shows `SCAN messages` on sync-sized tables:

   ```sql
   CREATE INDEX IF NOT EXISTS ix_messages_sync_uid
       ON messages(owner, account_id, folder, uidvalidity, uid);
   ```

   This duplicates the unique index column order — **likely redundant**. Document EXPLAIN output in PR; skip creation if planner already uses `sqlite_autoindex_messages_1` or equivalent.

3. **Alternative index** (only if MIN/MAX scans are slow and gap join is fine):

   ```sql
   CREATE INDEX IF NOT EXISTS ix_messages_sync_bounds
       ON messages(owner, account_id, folder, uidvalidity, uid);
   ```

   Same columns — one index serves both. Do not add two.

4. Add index DDL in `_init_local_store_db()` next to existing `ix_messages_*` definitions so new and upgraded DBs get it.

### Files to touch

- `routes/email_local_store.py` — `_init_local_store_db()` (conditional on EXPLAIN decision)
- Optional: `tests/test_email_local_store_sync.py` — EXPLAIN smoke test (assert no `SCAN messages` on anti-join with seeded data)

### Acceptance

- PR includes EXPLAIN QUERY PLAN screenshots or pasted output before/after
- If unique index suffices, PR states "index not added" with evidence

---

## Item 5: Index on `attachments(message_row_id)`

### Problem

Hot statements:

```sql
SELECT local_path FROM attachments WHERE message_row_id=?
DELETE FROM attachments WHERE message_row_id=?
SELECT ... FROM attachments a JOIN messages m ON m.id = a.message_row_id WHERE ...
```

Without an index, DELETE/SELECT by `message_row_id` scan the attachments table. Re-sync of messages with attachments amplifies cost.

### Design

Add to `_init_local_store_db()`:

```sql
CREATE INDEX IF NOT EXISTS ix_attachments_message_row_id
    ON attachments(message_row_id);
```

- **No migration script required** — `IF NOT EXISTS` on init is consistent with existing index pattern
- FK `REFERENCES messages(id) ON DELETE CASCADE` does **not** auto-index the child column in SQLite

### Files to touch

- `routes/email_local_store.py` — `_init_local_store_db()`

### Tests

- Existing attachment tests continue to pass
- Optional EXPLAIN on `DELETE FROM attachments WHERE message_row_id=?` → should show `USING INDEX ix_attachments_message_row_id`

### Risk

Low. Index maintenance cost on insert is negligible vs sync frequency.

---

## Item 6: Skip attachment re-extract when metadata unchanged + file exists

### Problem

On every re-upsert of an existing UID, `_upsert_message()`:

1. Unlinks **all** prior attachment files (L591–603)
2. `_store_uids()` always calls `_extract_attachments_for_store()` (MIME walk + disk write)

Gap repair re-fetches a missing UID that was only deleted from SQLite (file may still exist) or re-syncs unchanged mail — wasteful and increases `resync_attachments_unlinked` noise.

### Safe scope

| Scenario | Behavior |
|----------|----------|
| New UID (first insert) | Full extract (unchanged) |
| Existing UID, attachment metadata fingerprint matches DB, file on disk, size matches | **Reuse** DB rows + paths; skip MIME extract and skip unlink |
| Existing UID, metadata differs (filename, size, count, content_type, is_inline) | Full re-extract; unlink old files (current behavior) |
| Existing UID, metadata matches but file missing or size mismatch | Re-extract that attachment only |
| Previously `skipped_reason` (too_large, pass_budget, etc.) | Re-evaluate skip rules; do not reuse `extracted=0` rows as cached |
| UIDVALIDITY purge | Unaffected (folder wiped) |

**Do not** skip body upsert — only short-circuit attachment extraction and file rewrite.

### Metadata fingerprint

Define a stable tuple from **parsed MIME metadata** (not file bytes):

```python
def _attachments_meta_fingerprint(meta: list[dict]) -> tuple:
    return tuple(
        sorted(
            (
                int(m["index"]),
                m.get("filename") or "",
                m.get("content_type") or "",
                int(m.get("size") or 0),
                1 if m.get("is_inline") else 0,
            )
            for m in meta
        )
    )
```

Load existing rows:

```python
def _existing_attachment_fingerprint(rows: list[sqlite3.Row]) -> tuple:
    # same shape; use idx, filename, content_type, size, is_inline
```

### Reuse validation (per row)

For each existing row with `extracted=1` and `local_path` set:

```python
p = Path(local_path)
ok = p.is_file() and p.stat().st_size == int(row["size"])
```

If **all** extracted rows pass and fingerprints match → reuse list of dicts compatible with `_upsert_message` attachment insert.

### Integration points

**Option A (recommended):** Branch in `_store_uids()` before extract:

```python
existing_id_row = db.execute("SELECT id FROM messages WHERE ...", ...).fetchone()
if existing_id_row:
    existing_atts = db.execute(
        "SELECT idx, filename, content_type, size, is_inline, local_path, extracted, skipped_reason "
        "FROM attachments WHERE message_row_id=? ORDER BY idx",
        (existing_id_row[0],),
    ).fetchall()
    if _can_reuse_attachments(existing_atts, parsed.get("attachments_meta") or []):
        attachment_rows = [dict(r) for r in existing_atts]  # normalized keys
    else:
        attachment_rows = _extract_attachments_for_store(...)
else:
    attachment_rows = _extract_attachments_for_store(...)
```

**Option B:** Pass a `reuse_attachments: bool` into `_upsert_message` to skip unlink block — only if extract was skipped.

Adjust `_upsert_message` unlink guard:

```python
if existing is not None and not reuse_attachments:
    # unlink old paths
```

When reusing, skip `DELETE FROM attachments` + re-insert if rows identical — **or** still DELETE+insert same rows (simpler, index item 5 keeps it cheap). Prefer skip DELETE+insert when reusing unchanged rows to avoid churn.

### Tests

| Test | Expectation |
|------|-------------|
| `test_upsert_message_unlinks_old_attachment_on_update` | Still unlinks when filename/content changes |
| `test_attachment_written_and_oversized_skipped` | Unchanged |
| `test_gap_repair_fills_missing_interior_uid` | Passes; if UID 6 row deleted but files remain, reuse is acceptable; if files gone, re-extract |
| **New:** `test_resync_skips_attachment_extract_when_unchanged` | Sync once with attachment → sync again → assert `attachments_written_bytes` not incremented, same `local_path`, file mtime stable |
| **New:** `test_resync_reextracts_when_attachment_file_missing` | Delete file on disk, re-sync → file restored |

### Risks and mitigations

| Risk | Mitigation |
|------|------------|
| Stale file content, same size/metadata | Rare; accept for Phase 1. Phase 2 could add content hash in DB |
| Budget accounting | When reusing, do not decrement `budget_state["remaining"]` again |
| `deletion_state["resync_attachments_unlinked"]` | Should stay 0 on reuse path |
| Partial attachment set change | Fingerprint compares full set; any mismatch triggers full re-extract |

---

## Cross-cutting verification

### Test command

```bash
pytest tests/test_email_local_store_sync.py tests/test_email_local_store_sync_log.py -q
```

### Manual EXPLAIN checklist (dev with large mailbox)

1. Populate temp table with server UIDs
2. Run anti-join EXPLAIN — no full table scan on `messages`
3. Run attachment DELETE EXPLAIN — uses `ix_attachments_message_row_id`

### Metrics to compare (before/after)

Record from sync summary dict / logs on a folder with ≥5k messages:

- Sync pass duration (`sync_all` `duration_seconds`)
- `attachments_written_bytes` on incremental pass with no new mail (should drop after item 6)
- Peak memory during gap repair (should drop after item 1)

---

## File change summary

| File | Items |
|------|-------|
| `routes/email_local_store.py` | 1–6 (all) |
| `tests/test_email_local_store_sync.py` | New tests for items 1, 6; optional EXPLAIN for 4 |
| `docs/plans/email/email-local-sync-p1-sqlite.md` | This document |

No changes to `tests/test_email_local_store_sync.py::test_gap_repair_fills_missing_interior_uid` expected — behavior preserved.

---

## Suggested PR breakdown

1. **PR 1:** Indexes (item 5 + EXPLAIN gate for item 4) + `RETURNING` + `executemany`
2. **PR 2:** Temp-table anti-join (item 1)
3. **PR 3:** Attachment reuse (item 6) with new tests

Single PR is acceptable if review size is manageable; split reduces rollback blast radius.

---

## Future work (not Phase 1)

- Replace temp-table populate with SQLite recursive/generate series for UID ranges (only if server sends compact UID ranges instead of full SEARCH lists)
- Content-hash column on attachments for stronger reuse guarantees
- Batch `_upsert_message` in a single transaction with deferred attachment writes
- `server_uids` kept in memory as list — anti-join still needs temp table or inline VALUES clause; consider `VALUES (1),(2),...` for small folders without temp DDL
