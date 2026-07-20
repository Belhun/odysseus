# Gap plan: Plugin backup/restore + BUG-018 reindex

| Field | Value |
|-------|--------|
| **Issue id** | `backup-restore-post-import-reindex` |
| **Title** | Plugin backup/restore + BUG-018 reindex |
| **Phase** | **P2** (MASTER §5 Phase 5 — Reliability & backup) |
| **Priority** | high |
| **Domain** | backup |
| **Effort** | **M** |
| **Depends on** | `business-settings-mvp`, `clients-crud-fts-duplicates` |
| **Sources** | gap-manifest · MASTER §4 / §5 Phase 5 / §8.6 · chats [c2396042](../chat-reviews/c2396042-bc18-4c3a-a32f-d6b6def918df.md), [55127af8](../chat-reviews/55127af8-5c1c-45ed-8f64-b1558712f3cf.md), [784da76d](../chat-reviews/784da76d-e4c8-44bb-9eca-59d99e1b0980.md) · SysForge `BackupService` / `BackupModels` / `ScheduledBackupService` · `docs/research/sysforge/features/settings-backup.md` · feature-gap-matrix §8 |

**Constraint for this doc:** planning only. No product code changes in this workstream write-up.

---

## Goal / success

Ship a **SysForge-scoped** backup, restore, and portable JSON import/export path for Business data under `data/plugins/sysforge/`, with **BUG-018** search sync on every bulk client path.

### Success criteria (exit)

1. Shop can create a plugin backup and restore Business data without touching Odysseus global export (`/api/export`, `/api/import`) or `scripts/odysseus-backup`.
2. Portable JSON round-trip covers clients, invoices, invoice items, parts, and plugin settings (`SysForgeExportData` v1.0 shape).
3. After any JSON import with clients in scope, **name search** finds fixture clients (e.g. Maria / id `90001`) on both client-list search and invoice-calculator client search.
4. **Skip / 0 imported still reindexes:** re-import with conflict `Skip` and `clients_imported == 0` rebuilds search; stale index recovers. Restart alone is **not** the recovery story.
5. Diagnostics / “list all clients” is **never** accepted as proof that search works.
6. Full DB-file restore (`.db` snapshot) runs integrity check + safety backup, then **rebuilds client search** before claiming success (closes the desktop gap left open in c2396042).
7. **Unchecked SQL dump import is not ported** (no `ExecuteSqlScript` / arbitrary-SQL restore surface).
8. Settings Backup UI lives inside Business settings (from `business-settings-mvp`), clearly labeled as Business-only.
9. Automated tests mirror desktop BUG-018 cases; manual walkthrough covers name search after first import and Skip re-import.

---

## Current state

### SysForge desktop (source of truth)

| Piece | Status | Notes |
|-------|--------|--------|
| `BackupService` | Done | Manual `.db` + config sidecar; restore with `PRAGMA integrity_check`, pre-restore safety backup, WAL checkpoint, pool clear |
| Portable JSON | Done | `SysForgeExportData` `exportVersion` `1.0`; selective tables; Skip / Overwrite / Merge in service |
| SQL dump export | Done | `ExportToSqlDump` |
| SQL dump import | Done in service | `ImportFromSqlDump` runs dump text statement-by-statement — **do not port this import path** |
| Scheduled backups | Done | `ScheduledBackupService` + config interval/retention/includeDrafts |
| Settings UI | Partial | Create / Restore / Export JSON / Export SQL / Import JSON / schedule; **no** SQL import button, conflict UI, auto-restart, custom folder (Q-05 deferred) |
| BUG-018 | Fixed 2026-05-19 | Rebuild Lucene when `options.ImportClients` after commit, **even if every row skipped**; post-commit rebuild failure → `Success=false` + re-import message |
| `.db` restore → search | Open on desktop | Restore replaces DB; non-empty stale Lucene may survive restart (`InitializeAsync(rebuildIfMissing: true)` only) |
| Per-invoice JSON backup | Partial | Write on update; **no restore UI** |

Key BUG-018 behavior in desktop code (`ImportFromJson`):

```csharp
// After transaction.Commit():
if (_searchService != null && options.ImportClients)
{
    _searchService.RebuildSearchIndexAsync().GetAwaiter().GetResult();
    // NOT gated on result.ClientsImported > 0
}
```

### odysseus-sysforge today

| Piece | Status |
|-------|--------|
| Plugin install | Creates `data/plugins/sysforge/{sysforge.db, config.json, drafts/, backups/}` |
| Domain schema / CRUD / search | Missing until P0/P1 workstreams |
| Plugin backup APIs / UI | Missing — only empty `backups/` directory |
| Host global backup | Present — `routes/backup_routes.py` (`/api/export`, `/api/import` for memories/presets/skills/settings/features/prefs); `scripts/odysseus-backup` tarball of `data/` |
| Plugin routes | `/api/sysforge/status` only |

**Verdict:** Host backup protects Odysseus state (and may incidentally copy `data/plugins/sysforge/` inside a full `data/` tarball). That is **not** a shop-facing Business backup/restore product. Matrix §8: Settings/plugin backup = **Stub**.

---

## Scope

### In scope

1. **Plugin-scoped snapshot backup** of `sysforge.db` (+ optional `config.json`, optional `drafts/`) into `data/plugins/sysforge/backups/` with timestamped names.
2. **Restore from validated `.db` snapshot** with integrity check, pre-restore safety backup, connection/pool hygiene, then **mandatory client search rebuild**.
3. **Portable JSON export/import** matching desktop `SysForgeExportData` v1.0 (clients, invoices, items, parts, settings), with selective flags and conflict mode (Settings ships **Skip** default; service may support Overwrite for tests/fixtures).
4. **BUG-018 contract** on every bulk path that writes clients outside normal CRUD indexing:
   - JSON import with `import_clients=true`
   - `.db` restore
   - Any future bulk seed/fixture load that bypasses CRUD
5. **Scheduled plugin backups** (enable / interval days / retention) stored in plugin `config.json`; prefer host `task_scheduler` or an asyncio timer owned by the plugin — document choice in implementation PR.
6. **Business Settings → Backup & restore** UI panel (create, list, download, restore, export JSON, import JSON, schedule toggles).
7. **Sample fixture** port of `SysForge.Tests/TestData/sample-export.json` (Maria Chen `90001`, Walsh shared phone, Jenkins shared email) under `tests/fixtures/sysforge/` or `integrations/sysforge/testdata/`.
8. Thin follow-up **in same settings surface or adjacent ticket:** per-invoice backup restore UI (desktop Partial → Done). May ship as a checkbox item after core round-trip if calendar slips.

### Out of scope

| Item | Why |
|------|-----|
| **Unchecked SQL dump import** (`ImportFromSqlDump` / execute arbitrary SQL text) | Explicit migration rule; RCE/corruption risk on a web host |
| SQL dump **export** button | Optional later; not required for P2 exit (JSON + `.db` enough) |
| Merging Business data into `/api/export` / `/api/import` | Different product surface; keeps secrets/settings/memories mixed with shop DB |
| Changing `scripts/odysseus-backup` semantics | Global host tool stays as-is; document that full `data/` snapshots *include* plugin files as disaster recovery only |
| Desktop Avalonia Settings parity chrome | Web Business settings patterns from `business-settings-mvp` |
| Import conflict **full** UI (Overwrite/Merge pickers) | Match desktop Q-05 deferral unless product pulls it forward |
| Auto-reload / “restart app” after restore | Web: soft reload of Business panel + clear caches; no OS restart |
| Custom backup folder picker | Defer (desktop deferred) |
| Client merge tool | Separate deferred workstream |
| Importing a live desktop `%LOCALAPPDATA%\SysForge\sysforge.db` as MVP onboarding | MASTER: fresh plugin DB; no desktop DB import in MVP |
| Finance plugin backup | Different plugin id / data dir |

### Explicit non-port: SQL dump import

Do **not** expose an API or UI that:

- reads a `.sql` file and runs it against the live or temp DB via multi-statement execute, or
- wraps desktop `ImportFromSqlDump` without a strict allowlist.

If a future need appears for “full schema+data text restore,” require a **new** design (validated `.db` only, or versioned structured import). Until then: **reject `.sql` uploads** with a clear 400 message pointing users to JSON or `.db` snapshot restore.

---

## Dependencies

| Dependency | Why blocked without it |
|------------|------------------------|
| `schema-money-utc-foundation` (P0) | Real `sysforge.db` schema, migrations, money/UTC types for export rows |
| `business-settings-mvp` (P1) | Settings shell where Backup expander lives; plugin `config.json` keys |
| `clients-crud-fts-duplicates` (P1) | Client search implementation (FTS5 or other) that BUG-018 must rebuild; Diagnostics vs search split |
| Invoice/parts CRUD (P1 streams) | Meaningful JSON import of invoices/items/parts; can stage clients-only import earlier if needed |

**Soft dependency:** invoice calculator + client dashboard UIs for manual QA of name search (same as desktop walkthrough). APIs alone can prove BUG-018 in pytest.

**Ordering tip:** Implement backup service + reindex hooks as soon as client search exists; wire Settings UI when `business-settings-mvp` lands.

---

## Concrete steps

### Step 0 — Lock format decisions (½ day)

1. **Primary interchange:** portable JSON `exportVersion: "1.0"` (camelCase), same entities as desktop.
2. **Snapshot format:** copy of `sysforge.db` after SQLite backup/checkpoint; companion `*-config.json` when including settings; optional drafts folder sibling.
3. **Archive wrapper (recommended):** ZIP containing `sysforge.db`, optional `config.json`, optional `drafts/`, and `manifest.json` (`plugin_id`, `created_at`, `schema_version`, `contents[]`). Download one file from the browser.
4. Write a one-paragraph ADR in the PR: “Business backup ≠ Odysseus `/api/export`.”

### Step 1 — Backup service module

Add `integrations/sysforge/backup_service.py` (or `src/sysforge/backup.py` if domain code lives under `src/` — follow whatever layout `schema-money-utc-foundation` chose).

Implement:

| Method | Behavior |
|--------|----------|
| `create_backup(*, include_drafts=False)` | Checkpoint/backup API copy of DB → `backups/sysforge-backup-<ts>.db` (+ config/drafts/ZIP) |
| `list_backups()` | Metadata: name, size, mtime |
| `validate_database_file(path)` | `PRAGMA integrity_check` → `ok` |
| `restore_backup(path, *, restore_config=False)` | Safety backup → validate → replace live DB → reload config if requested → **rebuild client search** → return counts/message |
| `export_to_json(path_or_bytes)` | Read live DB → `SysForgeExportData` |
| `import_from_json(data, options)` | Version check → transactional upserts → commit → **if `import_clients`: rebuild search** (ignore imported count) |
| `cleanup_old_backups(retention_days)` | Delete aged files under plugin `backups/` only |

Reuse desktop semantics for conflict Skip/Overwrite on id match. Map enums/statuses as **text** for CHECK parity (55127af8).

### Step 2 — Search rebuild helper (BUG-018)

Centralize one function used by import **and** restore:

```text
rebuild_client_search(*, reason: str) -> None
```

Rules:

1. Call after successful commit/file replace whenever the operation **intended** to sync clients (`import_clients=true` or full DB restore).
2. **Do not** skip when `clients_imported == 0` / all skipped.
3. If rebuild fails after DB commit: mark overall operation failed; message tells user to re-import / re-run restore or hit “Rebuild search” (if exposed). Do not roll back a committed transaction.
4. Startup must not be the only heal path; document that a non-empty stale index is not fixed by process restart alone.

If search is FTS5 inside SQLite, rebuild = `INSERT INTO clients_fts(...)` / `rebuild` trigger strategy chosen in `clients-crud-fts-duplicates`. If a sidecar index exists, wipe+rebuild from DB.

### Step 3 — HTTP API under `/api/sysforge`

Gate all routes with existing `_require_sysforge_plugin`. Admin (or shop-owner) auth consistent with other mutating Business routes.

See [API/UI contracts](#apiui-contracts).

### Step 4 — Settings UI

Under Business Settings → **Backup & restore**:

- Create backup (optional include drafts)
- List + download + restore (confirm dialog: destructive, safety backup created)
- Export JSON / Import JSON (file picker; show imported/skipped counts)
- Schedule: enabled, interval days, retention days, include drafts
- Footer note: “Business data only. Odysseus app export is separate (Settings → … / docs/backup-restore.md).”

Toast / inline errors for integrity failure, version mismatch, rebuild failure.

### Step 5 — Scheduling

Wire config keys (mirror desktop `Backup` section):

```json
"backup": {
  "schedule_enabled": false,
  "schedule_interval_days": 7,
  "retention_days": 30,
  "include_drafts": false
}
```

On enable/save: register recurring job. On disable: unregister. Retention runs after successful scheduled backup.

### Step 6 — Reject SQL dump import; optional export later

- Upload content-type / extension `.sql` → 400 with explicit message.
- Do not call any “run script” helper on user-supplied SQL.
- Leave SQL dump **export** unimplemented unless a follow-up asks; prefer ZIP+JSON.

### Step 7 — Tests + fixture + walkthrough

Port sample JSON; add pytest cases listed in [Tests / verification](#tests--verification). Add a short section to `integrations/sysforge/README.md` and a Manual QA checklist (BUG-018 name search).

### Step 8 — Per-invoice restore UI (thin follow-up)

If time remains in the same PR train: Settings or Invoice Edit → “Restore from invoice backup JSON.” Otherwise open a checklist item under this workstream id and keep Phase 5 exit for **plugin** backup green first.

---

## Files

### Create

| Path | Role |
|------|------|
| `integrations/sysforge/backup_service.py` (or `src/sysforge/backup_service.py`) | Core backup/restore/import/export + reindex hooks |
| `integrations/sysforge/backup_models.py` | Dataclasses / TypedDicts for export v1.0, options, results |
| `integrations/sysforge/routes_backup.py` or extend `routes.py` | FastAPI endpoints |
| `integrations/sysforge/static/js/settings_backup.js` (or section in settings module) | UI actions |
| `tests/fixtures/sysforge/sample-export.json` | Port of desktop sample |
| `tests/test_sysforge_backup.py` | Service + API + BUG-018 tests |
| `docs/migration-audit/gap-plans/backup-restore-post-import-reindex.md` | This plan |

### Modify

| Path | Role |
|------|------|
| `integrations/sysforge/routes.py` | Mount backup router |
| `integrations/sysforge/install.py` | Ensure `backups/` exists (already); optionally seed backup config defaults |
| Plugin settings UI (from `business-settings-mvp`) | Backup expander |
| Client search module (from `clients-crud-fts-duplicates`) | Expose `rebuild_client_search` |
| `integrations/sysforge/README.md` | Document Business vs global backup |
| `tests/test_sysforge_plugin.py` | Keep install/404; don’t overload — new file for backup |

### Desktop reference (read-only)

| Path | Use |
|------|-----|
| `SysForge/Services/BackupService.cs` | Semantics |
| `SysForge/Services/BackupModels.cs` | JSON schema |
| `SysForge/Services/ScheduledBackupService.cs` | Schedule/retention |
| `SysForge.Tests/Services/BackupServiceTests.cs` | Test vectors |
| `SysForge.Tests/TestData/sample-export.json` | Fixture |
| `Plans/Manual-Test-Walkthrough.md` § BUG-018 | QA script |
| `Plans/Open-Bugs-And-Investigations.md` BUG-018 | Root-cause notes |

### Do not copy

| Path / behavior | Reason |
|-----------------|--------|
| `ImportFromSqlDump` + `ExecuteSqlScript` | Unchecked SQL |
| Lucene folder copy from desktop | Wrong engine; rebuild from DB instead |

---

## API / UI contracts

Prefix: `/api/sysforge`. All require active plugin. Prefer admin for mutate.

### Endpoints

| Method | Path | Body / query | Response (shape) |
|--------|------|--------------|------------------|
| `GET` | `/backup/list` | — | `{ ok, backups: [{ id, filename, size_bytes, created_at, has_config, has_drafts }] }` |
| `POST` | `/backup/create` | `{ include_drafts?: bool }` | `{ ok, backup, message }` |
| `GET` | `/backup/download/{id}` | — | ZIP or `.db` file download |
| `POST` | `/backup/restore` | multipart file **or** `{ backup_id }` + `{ restore_config?: bool }` | `{ ok, message, safety_backup_id, search_rebuilt: true }` |
| `GET` | `/backup/export.json` | — | downloadable JSON (`exportVersion`, entities) |
| `POST` | `/backup/import.json` | multipart JSON + `{ import_clients, import_invoices, import_invoice_items, import_parts, import_settings, conflict: "skip"\|"overwrite" }` | `{ ok, message, clients_imported, clients_skipped, …, search_rebuilt: bool }` |
| `POST` | `/backup/search/rebuild` | — | `{ ok }` manual heal (ops / recovery) |
| `GET`/`PUT` | `/backup/schedule` | schedule config | current schedule |

### Error contracts

| Case | Status | Message intent |
|------|--------|----------------|
| Plugin inactive | 404 | Existing plugin gate |
| Integrity check fail | 400 | Restore aborted; live DB unchanged |
| Unknown `exportVersion` | 400 | Unsupported export version |
| `.sql` upload | 400 | SQL dump import not supported; use JSON or `.db` backup |
| Rebuild fail after commit | 200 with `ok: false` **or** 500 with explicit body | Data saved / DB replaced but search stale; retry import/rebuild |
| Missing backup id | 404 | Not found |

### UI contracts

- Place under **Business → Settings → Backup & restore**, not Odysseus global Integrations export.
- Confirm restore: “Replaces Business database. A safety backup is created first.”
- Import result always shows imported **and** skipped counts; if `search_rebuilt` false / `ok` false, show failure styling even when counts look fine.
- Disable double-submit on restore/import (busy flag).

---

## UX contracts (BUG-018)

These are acceptance rules, not optional polish.

1. **Reindex when Skip imports 0.** If the user imports JSON with clients enabled and conflict Skip, and every client id already exists (`clients_imported == 0`, `clients_skipped > 0`), the product still rebuilds client search and name queries succeed.
2. **Diagnostics ≠ search.** A green “clients listed” diagnostics/API check does not close the bug. QA must call the **search** endpoint / UI with a **name** query (`Maria`, `Chen`). Phone-only success is insufficient (digit fallback can mask stale index).
3. **Two surfaces.** After import, verify client dashboard search **and** invoice calculator client search (or their API equivalents).
4. **Failure honesty.** If DB write succeeds and search rebuild fails, do not toast “Import completed successfully.” Tell the user to re-import or run Rebuild search.
5. **Recovery copy.** Docs/README: after deploying the fix, one JSON re-import (or Rebuild search) heals stale indexes; restart alone may not.
6. **Restore path.** After `.db` restore, search must match restored clients without requiring a second JSON import.
7. **Label separation.** Copy must say “Business backup” vs “Odysseus app backup” so users do not assume `/api/export` restored invoices.

---

## Tests / verification

### Automated (pytest)

Port intent from `BackupServiceTests`:

| Test | Asserts |
|------|---------|
| `test_create_backup_writes_db_and_config` | Files under plugin `backups/`; integrity ok |
| `test_restore_rejects_invalid_db` | Live DB unchanged |
| `test_restore_round_trip` | Safety backup created; data restored; `search_rebuilt` |
| `test_import_json_sample_export` | Counts match fixture (12 clients, etc.) |
| `test_import_json_invalid_version` | 400 / raises |
| `test_import_conflict_skip_no_overwrite` | Existing row preserved |
| `test_import_conflict_overwrite_updates` | Row updated |
| `test_import_fk_violation_rolls_back` | No partial commit |
| `test_import_then_search_finds_maria` | Search API finds id `90001` by name |
| `test_import_skip_rebuilds_stale_index` | Seed stale index → Skip re-import → `Maria` found (**BUG-018**) |
| `test_sql_upload_rejected` | `.sql` → 400 |
| `test_global_export_unchanged_by_plugin_backup` | `/api/export` body has no Business tables requirement; plugin backup files not required for Odysseus export success |
| `test_backup_routes_404_when_plugin_inactive` | Gate |

### Manual QA (from desktop BUG-018 walkthrough)

1. Import `sample-export.json` (clients on, Skip).
2. Diagnostics/list shows Maria Chen.
3. Search **`Maria`** and **`Chen`** on client UI and invoice calculator UI → hit.
4. Re-import same file with Skip (0 imported) → search still finds Maria; server log shows rebuild.
5. Create backup → change data → restore → search matches backup; Business panel reloads.
6. Confirm Odysseus Settings export still only covers host memories/settings/etc.

### MASTER §8.6 checklist mapping

- [ ] Plugin backup ZIP/JSON restore round-trip  
- [ ] Import fixture; after import **including skip-all**, search finds clients  
- [ ] Diagnostics list ≠ search proof  

---

## Risks

| Risk | Mitigation |
|------|------------|
| **Porting `ImportFromSqlDump`** “for parity” | Hard out-of-scope; reject in review; test forbids `.sql` |
| Users confuse Business backup with Odysseus export | Distinct nav + README + toast labels; do not add shop tables to `/api/export` in this workstream |
| BUG-018 regresses via `if imported_count > 0` guard | Dedicated Skip/stale-index test; code review checklist item |
| Restore leaves stale sidecar search index | Rebuild on restore; optional startup mismatch detect later (not required for exit) |
| Long rebuild blocks request | Run rebuild async with job status **or** accept sync for MVP shop sizes; document limit |
| Partial ZIP extract / path traversal | Validate members stay under temp dir; reject `..` / absolute paths (mirror `odysseus-backup` restore rules) |
| Schedule + Docker sleep | Document; use host cron + API create if timer unreliable |
| Sync-over-async rebuild (desktop `.GetAwaiter().GetResult()`) | Prefer async `await rebuild_client_search()` in FastAPI |
| Enum/CHECK failures on import | Text status mapping tests with sample fixture |
| Per-invoice restore slipping | Keep core plugin backup as Phase 5 exit; invoice restore as follow-up checkbox |

---

## Effort

**M** (medium)

Rough breakdown:

| Slice | Size |
|-------|------|
| Service + models + ZIP/`.db` + JSON import/export | M |
| BUG-018 rebuild wiring + restore reindex | S |
| API + Settings UI + schedule | S–M |
| Tests + fixture + docs | S |
| Per-invoice restore UI | S (optional follow-up) |

**Not L** if SQL dump import stays out and conflict UI stays deferred. Becomes **L** only if the workstream absorbs full Q-05 conflict UI + SQL export + per-invoice restore + startup index healer in one pass — avoid that bundling.

---

## Implementation checklist (for the coding PR)

1. [ ] ADR: SysForge-scoped vs Odysseus global backup  
2. [ ] `backup_service` create / list / validate / restore / JSON export / JSON import / cleanup  
3. [ ] `rebuild_client_search` shared helper; no `imported == 0` early return  
4. [ ] Routes + inactive 404 + `.sql` rejected  
5. [ ] Settings Backup UI + schedule config  
6. [ ] `sample-export.json` fixture  
7. [ ] pytest suite including `test_import_skip_rebuilds_stale_index`  
8. [ ] README + manual QA notes  
9. [ ] (Optional) per-invoice restore UI or tracked follow-up  

---

## Traceability

| Requirement | Source |
|-------------|--------|
| Plugin-scoped backup/restore; shop can restore Business data | MASTER Phase 5; gap-manifest summary |
| BUG-018 on every bulk import; skip-all | MASTER §4; c2396042; Open-Bugs BUG-018 |
| Diagnostics ≠ search | c2396042 Odyssey checklist |
| Q-05 port; JSON entities; schedule | 55127af8; BackupModels |
| Do not confuse with host backup routes | 784da76d Odyssey checklist; `docs/backup-restore.md` |
| Defer SQL import button / conflict UI | 55127af8; 784da76d; Plans Q-05 deferred |
| **Do not port unchecked SQL dump import** | This workstream charter + web threat model |
| Depends on settings + client search | gap-manifest `depends_on` |
