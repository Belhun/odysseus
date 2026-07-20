# Read-only Business diagnostics panel

| Field | Value |
|-------|-------|
| **Issue id** | `diagnostics-readonly-panel` |
| **Title** | Read-only Business diagnostics panel |
| **Phase** | P2 |
| **Effort** | **S** (health + schema snapshot); **M** if raw client/invoice grids ship in the same PR |
| **Priority** | medium (`gap-manifest.json`) |
| **Domain** | settings |
| **Primary sources** | SysForge `DiagnosticsViewModel` / `DiagnosticsView.axaml` / `DatabaseDiagnostics.cs`; research `docs/research/sysforge/features/diagnostics.md`; MASTER §5 Phase 2; feature-gap-matrix §1 Diagnostics; chat [b89af01b](../chat-reviews/b89af01b-df9a-4314-9192-0f96200cf8e3.md) (keep **Diagnostics** product UI; do **not** port `DebugLog`) |
| **Manifest** | `gap-plans/gap-manifest.json` → `diagnostics-readonly-panel` |
| **Master plan** | `synthesis/MASTER-MIGRATION-PLAN.md` → Phase 2 exit: “Diagnostics read-only \| Migration version / DB health (no secrets)” |

---

## Goal / success

Give Business operators (and admins on multi-user Odysseus) a **read-only** snapshot of the **plugin** SQLite database so they can answer: “Did migrations apply?” and “What is actually stored?” without editing data or trusting search UIs.

**Done when:**

1. With the plugin installed and schema foundation applied, a user can open **Business → Diagnostics** (sidebar item and/or dashboard card) and see:
   - Latest applied migration id / schema version (from `SchemaVersion`)
   - DB health: file present, readable, size, optional integrity hint (`ok` / `missing` / `error`)
   - Row counts for clients and invoices (at minimum)
2. `GET /api/sysforge/diagnostics` returns the same snapshot as JSON for scripted checks (research contract).
3. Response and UI **never leak secrets** on shared hosts: no API keys, no host admin tokens, no other users’ paths; absolute DB path is redacted or admin-gated (see UX / API contracts).
4. Panel is **read-only**: no create/update/delete, no SQL console, no import/export buttons in this workstream.
5. Product rule from chat **b89af01b**: ship the **Diagnostics** inspector; do **not** port `DebugLog`, `.cursor/debug.log` `AppendAllText` instrumentation, or session NDJSON debug writers.
6. QA docs and tests state explicitly: **Diagnostics list ≠ search proof** (BUG-018 / MASTER §4 / §8.6).

**Optional same-pass (only if projects settings already land):**

- Setting surface for “include archived in search”
- Diagnostics-only hard-delete with confirm + “Don’t ask again today” (Projects plan) — otherwise defer to projects workstream

---

## Current state

### SysForge desktop (source of truth)

| Piece | Role |
|-------|------|
| `SysForge/ViewModels/DiagnosticsViewModel.cs` | Read-only inspector: path, size, client/invoice counts, raw `Clients` + `Invoices` collections; `Refresh` / `InitializeAsync` |
| `SysForge/Views/DiagnosticsView.axaml` | Header + Refresh; summary strip; two read-only DataGrids (“Clients (raw)”, “Invoices (raw)”) |
| `SysForge/Database/DatabaseDiagnostics.cs` | Offline utility: `DetectMixedTimezones` (UTC format scan). **Not** wired into the Diagnostics UI today |
| `MainWindowViewModel` nav | Sidebar item **Diagnostics** → `DiagnosticsViewModel` (Order 4) |

**Desktop refresh behavior (port this, not DebugLog):**

- Resolve DB path (desktop currently uses `%LOCALAPPDATA%\SysForge\sysforge.db` for size display)
- Show size or `(missing)`
- `GetAllClientsAsync` → fill grid + `ClientCount`
- Per client, `GetInvoicesByClientAsync(..., includeIncomplete: true)` → fill invoice grid + `InvoiceCount`
- Log via `ILogger` only; cancel on leave (`OnViewDeactivated` cancels CTS)

**Chat b89af01b (Failed-fix audit) — port decision:**

- `DebugLog` / `SysForge.DebugSession` wrote NDJSON to a hardcoded path and ran on hot paths (nav, calculator, **Diagnostics** Loaded handlers, PRAGMA table_info used only for debug).
- Removing `DebugLog` was correct: **no user-visible feature loss**.
- After cleanup, Diagnostics still loads path/size/counts/grids; `DiagnosticsView.axaml.cs` is a plain shell.
- **Odyssey rule:** keep the Diagnostics **product** panel; strip any “agent debug session” writers. Do not invent a web `DebugLog`.

### Odysseus web (target today)

| Piece | Status |
|-------|--------|
| Plugin install | Touches empty `plugins/sysforge/sysforge.db`; no migrations / no `SchemaVersion` yet (`integrations/sysforge/install.py`) |
| API | `GET /api/sysforge/status` only (`integrations/sysforge/routes.py`) |
| UI | Stub modal + “Installed v…” (`integrations/sysforge/static/js/index.js`); **no** Diagnostics route/panel |
| Host diagnostics | Separate: `routes/diagnostics_routes.py` (`/api/diagnostics/services`, `/api/diagnostics/logs`, `/api/db/stats`) — **host** admin tools, not Business plugin DB |
| Research | `features/diagnostics.md`: admin page + `GET /api/sysforge/diagnostics`; Effort **S**; risk = path/secret leakage |

### Gap

No plugin-scoped health/schema endpoint or UI. After Phase 0 migrations land, operators still cannot confirm schema version or raw row presence without opening the SQLite file by hand. Host `/api/diagnostics/*` does not cover `plugins/sysforge/sysforge.db`.

---

## Scope

### In scope

- Backend: `GET /api/sysforge/diagnostics` (plugin-gated; prefer admin for absolute paths / raw dumps).
- Backend helper: read `SchemaVersion`, DB file stats, client/invoice counts from the **plugin** DB path (`plugin_data_dir("sysforge") / "sysforge.db"`).
- Frontend: `#sysforge/diagnostics` panel (or Business settings subsection) with Refresh; summary fields matching desktop intent.
- Raw client/invoice tables **when** list APIs exist (same fields as desktop grids, truncated/paginated for large DBs).
- Auth + redaction policy for multi-user Odysseus (see contracts).
- Tests: route gate, schema fields, redaction, uninstall → 404.
- Docs note: Diagnostics ≠ search proof; link BUG-018 workstream for reindex.

### Out of scope

- **`DebugLog`**, `.cursor/debug.log` file appenders, browser `console` spam as a “diagnostics product,” NDJSON session probes, PRAGMA dumps used only for agent debug.
- Host Odysseus diagnostics (`/api/diagnostics/*`, RAG/Chroma health) — do not merge into Business Diagnostics.
- Writes: edit clients/invoices, SQL runner, vacuum/repair buttons, backup/restore (separate `backup-restore-post-import-reindex`).
- `DatabaseDiagnostics.DetectMixedTimezones` UI (optional later; not required for P2 exit).
- Desktop DB import into plugin DB.
- Hard delete / “Don’t ask again today” / include-archived search **unless** projects settings already ship in the same pass (otherwise own ticket under projects).
- Treating this panel as acceptance for Lucene/FTS search after import.

---

## Dependencies

| Depends on | Why |
|------------|-----|
| `schema-money-utc-foundation` | `SchemaVersion` rows + real tables must exist before “migration version” is meaningful |
| `business-shell-dashboard-router` | Place to hang `#sysforge/diagnostics` nav item / card without the stub-only modal |

| Soft / parallel | Why |
|-----------------|-----|
| `clients-crud-fts-duplicates` | Raw client grid + accurate counts via service APIs |
| Invoice list APIs (Phase 1) | Raw invoice grid parity with desktop |
| Admin auth (`require_admin` or Business role) | Absolute path + raw PII dumps on multi-user hosts |
| `backup-restore-post-import-reindex` | Shares “Diagnostics ≠ search” QA rule; does not block this panel |

**Blocks:** Nothing critical in the shop loop; this is P2 polish/ops. Still valuable right after Phase 0 so schema apply failures are visible.

---

## Concrete steps

### 1. Freeze the product vs non-product split (b89af01b)

Document in code comments / README snippet:

| Port | Skip |
|------|------|
| Diagnostics panel + refresh + DB snapshot | `DebugLog` class / session NDJSON |
| `ILogger` / server logs | `File.AppendAllText` to `.cursor/debug.log` |
| Optional later: timezone scan utility | DiagnosticsView Loaded handlers that only logged |

Add a one-line checklist item on the implementing PR: “No DebugLog equivalent.”

### 2. Define diagnostics DTO (server)

Shape (illustrative; keep field names stable for UI + tests):

```json
{
  "ok": true,
  "plugin_id": "sysforge",
  "db": {
    "exists": true,
    "readable": true,
    "size_bytes": 12345,
    "size_display": "12.1 KB",
    "path_display": "plugins/sysforge/sysforge.db",
    "path_absolute": null
  },
  "schema": {
    "latest_migration_id": "0015_...",
    "applied_count": 14,
    "applied": [
      {"id": "0002_...", "applied_at": "2026-..."}
    ]
  },
  "counts": {
    "clients": 3,
    "invoices": 5,
    "parts": null
  },
  "health": "ok"
}
```

Rules:

- `path_display`: always relative to plugin data root (safe default).
- `path_absolute`: only when caller is admin **and** query `?reveal_path=1` (or omit entirely on multi-user builds).
- `applied` list may be truncated in UI; API can return full list or last N + count.
- On missing DB: `health: "missing"`, counts zero, schema empty; HTTP 200 with `ok: true` still (plugin installed) **or** 200 with `health` degraded — pick one and test it; prefer 200 + `health` so the panel can render.

### 3. Implement `GET /api/sysforge/diagnostics`

File: extend `integrations/sysforge/routes.py` (or `integrations/sysforge/diagnostics.py` imported by routes).

Steps:

1. Keep existing `_require_sysforge_plugin` dependency (404 when uninstalled).
2. Resolve `db_path = plugin_data_dir("sysforge") / "sysforge.db"`.
3. Stat file; open SQLite read-only if present.
4. Query `SchemaVersion` (table from foundation workstream). If table missing → `health: "schema_pending"` and message “Migrations not applied.”
5. Count rows: `Clients` where not deleted (match desktop `GetAllClientsAsync` semantics), `Invoices` (include incomplete). Use SQL counts for the summary strip; avoid N+1 for counts.
6. Optional query param `?include_rows=1` (admin): return capped arrays for UI grids (e.g. max 500 each) with the desktop column set.
7. Never include `config.json` secrets, host env, or other plugins’ paths.

### 4. Wire UI panel

Under Business shell router (dependency):

1. Register route key `diagnostics` → panel module `integrations/sysforge/static/js/diagnostics.js` (or `static/js/sysforge/diagnostics.js` once research paths are normalized to `integrations/`).
2. Nav: sidebar **Diagnostics** + optional dashboard card (mirror desktop Order / tools icon).
3. Layout (match desktop, Odysseus styling):
   - Title + **Refresh**
   - Subtitle: “Live snapshot of what is stored in the Business database.”
   - Summary: path_display, size, client count, invoice count, **latest migration id**
   - Tables (when `include_rows` / list APIs ready): Clients (raw), Invoices (raw), read-only
4. On activate: fetch diagnostics; on deactivate: abort in-flight fetch (async-from-day-one / cancel-on-leave).
5. Empty / error states: missing DB, schema pending, permission denied for absolute path.

### 5. Auth / multi-user policy

| Audience | Sees |
|----------|------|
| Plugin active, normal Business user (single-user / owner) | Summary + counts + relative path; raw tables OK if shop is single-tenant |
| Multi-user Odysseus | Require admin for raw rows and absolute path; non-admin gets counts + migration id + relative path only |
| Plugin not installed | 404 (existing gate) |

Reuse `require_admin` from host diagnostics where appropriate; do not expose Business raw PII on `/api/diagnostics/logs`.

### 6. Optional same-pass projects knobs (gate explicitly)

Only if `projects-work-orders` settings UI is already in the PR:

- Toggle “Include archived in search” in Business settings (not Diagnostics).
- Hard delete entry points **only** on Diagnostics, confirm modal, session “Don’t ask again today.”

Otherwise leave a stub comment in the plan ticket: deferred to projects workstream.

### 7. Cross-link BUG-018

In panel footer or help text (one sentence):

> Showing rows here means they are in SQLite. Client search may still miss them until search reindex runs after import/restore.

Do not add a “Rebuild search” button here unless backup/reindex workstream owns that control.

---

## Files

| Path | Action |
|------|--------|
| `integrations/sysforge/routes.py` | Add `GET /diagnostics` |
| `integrations/sysforge/diagnostics.py` (new, optional) | Collect schema/health/counts; keep routes thin |
| `integrations/sysforge/static/js/diagnostics.js` (new) | Panel UI + Refresh |
| `integrations/sysforge/static/js/index.js` / shell router | Register route + nav entry |
| `integrations/sysforge/README.md` | Document endpoint + redaction policy |
| `tests/test_sysforge_plugin.py` or `tests/test_sysforge_diagnostics.py` (new) | API + gate + redaction tests |
| `docs/research/sysforge/features/diagnostics.md` | Optional: mark port notes / path `integrations/` (docs hygiene) |

**Do not touch:** host `routes/diagnostics_routes.py` for Business data; do not add `DebugLog`-style writers under plugin static or Python.

**Desktop reference only (read, don’t copy debug leftovers):**

- `SysForge/ViewModels/DiagnosticsViewModel.cs`
- `SysForge/Views/DiagnosticsView.axaml`
- `SysForge/Database/DatabaseDiagnostics.cs`

---

## API / UI contracts

### `GET /api/sysforge/diagnostics`

| Rule | Detail |
|------|--------|
| Gate | Plugin inactive → **404** (same as `/status`) |
| Auth | At least authenticated session; admin for `reveal_path` / `include_rows` on multi-user |
| Method | GET only |
| Side effects | None (read-only connection; no writes, no reindex) |
| Errors | DB locked / corrupt → 200 with `health: "error"` + message, or 503; pick one and test. Prefer structured 200 for panel rendering |
| Secrets | No tokens, no other users’ DATA_DIR contents, no full host env |

### Optional `GET /api/sysforge/diagnostics/rows` (if split)

Same gates; returns `{ clients: [...], invoices: [...] }` capped. Prefer single endpoint with `include_rows` unless payload size forces a split.

### UI route

| Intent | Route | Notes |
|--------|-------|-------|
| Open diagnostics | `#sysforge/diagnostics` | Read-only; Refresh button |
| Deep link | Same hash | Works after shell open |

Column set for raw grids (parity with desktop when rows included):

**Clients:** Id, Nickname, First, Last, Phone, Email, Company, Deleted, Display  
**Invoices:** Id, Name, ClientId, Client Info, Date, Total, Status, Finalized, Sent

### Explicit non-contracts

- Not a substitute for `GET /api/sysforge/clients/search`
- Not a logger / log viewer (use host `/api/diagnostics/logs` for app.log)
- Not a migration runner UI (migrations run on install/upgrade in foundation workstream)

---

## UX contracts

Copy into the implementation ticket:

- [ ] Diagnostics is clearly labeled as a **live DB snapshot**, not search.
- [ ] **Refresh** reloads schema + counts (+ rows if shown); busy state disables double-submit.
- [ ] Leaving the panel cancels in-flight refresh (no stale overwrite after navigate away).
- [ ] Absolute filesystem paths are hidden by default on multi-user; relative `plugins/sysforge/sysforge.db` is enough for most users.
- [ ] Raw grids are **read-only**; no inline edit, no context-menu delete in this workstream.
- [ ] Empty DB after fresh install: show zeros + latest migration (or `schema_pending`), not a blank error page.
- [ ] Sidebar/card entry survives shell nav lifecycle (same-panel re-apply must not kill handlers — see `nav-lifecycle-view-edit-routes`).
- [ ] No DebugLog / agent NDJSON / `.cursor/debug.log` writers introduced for this feature (b89af01b).

---

## Tests / verification

### Automated

| Test | Expect |
|------|--------|
| Plugin inactive → `GET /api/sysforge/diagnostics` | 404 |
| Fresh install + migrations applied → diagnostics | `health` ok/schema_pending as designed; `applied_count` ≥ 1; `latest_migration_id` set |
| Missing `sysforge.db` file | `exists: false`, safe display, no crash |
| Non-admin (multi-user fixture) | No `path_absolute`; no raw PII rows (or 403 on `include_rows`) |
| Admin + `reveal_path=1` | Absolute path present (single-user/dev OK) |
| Response JSON | No keys matching secret patterns (`api_key`, `token`, `password`) |
| Uninstall | Diagnostics 404 again |

### Manual

1. Install plugin → open Business → Diagnostics → confirm migration id after Phase 0.
2. Create a client + invoice in UI → Refresh → counts increment; raw rows appear if enabled.
3. Confirm search separately after a mock import (or note “blocked on reindex workstream”); do **not** pass QA on Diagnostics alone.
4. Multi-user / admin: verify path redaction.
5. Regression: host Settings → Diagnostics / `/api/diagnostics/services` still host-scoped, unchanged.

### Out-of-scope verification (do not fail this ticket)

- Lucene/FTS finds imported clients (BUG-018 / backup workstream)
- Hard delete / don’t-ask-again (projects)

---

## Risks

| Risk | Mitigation |
|------|------------|
| Absolute DB path leaks host layout / usernames | Default to relative `path_display`; gate absolute path |
| Raw grids expose PII on shared Odysseus | Admin gate + optional omit rows for non-admin |
| Large shops: loading all invoices like desktop N+1 | Use SQL `COUNT(*)` for summary; cap/paginate row payloads |
| Confusing with host `/api/diagnostics/*` | Namespace under `/api/sysforge/`; UI title “Business Diagnostics” |
| Implementers reintroduce DebugLog-style file probes | PR checklist + b89af01b citation; code review reject |
| Shipping before `SchemaVersion` exists | Soft-depend foundation; show `schema_pending` rather than lying |
| Operators trust Diagnostics as search proof | Footer copy + QA checklist item |

---

## Effort

| Slice | Size | Includes |
|-------|------|----------|
| **MVP (recommended first PR)** | **S** | `GET /diagnostics` schema + health + counts; panel summary + Refresh; tests; redaction |
| **Parity+** | **M** | Raw client/invoice grids, pagination, admin row gate, dashboard card polish |
| **Projects extras** | separate | Archive search setting + hard delete / don’t-ask-again |

**Manifest alignment:** P2 / medium. Research card Effort **S** matches the MVP slice. Do not block invoice MVP on parity grids.

---

## Acceptance checklist (ticket paste)

- [ ] `GET /api/sysforge/diagnostics` works only when plugin active
- [ ] UI shows latest migration + DB health + counts
- [ ] No secrets / careful path display on multi-user
- [ ] Read-only; Refresh works; cancel on leave
- [ ] No DebugLog / `.cursor/debug.log` port (b89af01b)
- [ ] Docs/tests state Diagnostics ≠ search proof
- [ ] Host diagnostics routes untouched
