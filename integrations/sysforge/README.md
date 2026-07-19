# Business Management (SysForge) plugin

Optional Odysseus plugin for repair-shop systems (clients, invoices, parts, projects).

## Install / uninstall

Settings → Integrations → **Business Management** → Install / Uninstall.

- Install writes `data/plugins/sysforge/installed.json` and sets `features.sysforge = true`.
- Install applies checksummed SQLite migrations `0002`–`0030` into `data/plugins/sysforge/sysforge.db`.
- Uninstall clears the marker, sets the feature flag false, and hides sidebar/rail nav.
- Plugin APIs under `/api/sysforge/*` return 404 when inactive.

## Schema / migrations

- SQL files live in `integrations/sysforge/migrations/`. **Never edit an applied migration.**
- Applied rows are tracked in `SchemaVersion` with SHA-256 checksums (uppercase hex).
- Editing an applied file raises `ChecksumMismatchError` (`MIGR-CHK-001`).
- In development, reset by deleting `data/plugins/sysforge/sysforge.db` and re-running install (or hit `/api/sysforge/status`, which lazy-migrates).
- In production, append a new numbered migration instead of changing applied SQL.

## Money and timestamps

- Store money as integer **cents**, rates as **basis points**, quantities as **milliunits** (`integrations/sysforge/db/money.py`).
- Store all Business DB timestamps as UTC TEXT `yyyy-MM-dd HH:mm:ss` (`integrations/sysforge/db/utc.py`). Convert to local only for display.

## Shell routes (P0 / P1)

Inner router: `static/js/router.js` + `routes-contract.js`. Route ids:

| Route id | View |
|----------|------|
| `dashboard` | Shop home cards |
| `client-dashboard` | **Classic** four-column Client Dashboard (primary Clients entry) |
| `invoice-calculator` | Calculator create/edit (`calculator` alias for nav buttons) |
| `invoice-view` | Read-only viewer (`/:id` path param) |
| `clients` | Clients CRUD / FTS (secondary “All clients”) |
| `client-merge` | Soft-merge duplicate clients (`#sysforge/clients/merge`) |
| `invoices-outstanding` | Unpaid balances (`#sysforge/invoices/outstanding`) |
| `reports-sales` | Sales/tax date-range report + CSV (`#sysforge/reports/sales`) |
| `drafts` | File drafts list + rename / delete |
| `parts` | Parts catalog |
| `placeholder-merge` | Placeholder merge |
| `settings` | Tax / currency / autosave (`business-settings-mvp`) |
| `diagnostics` | Read-only DB health / schema / counts (`diagnostics-readonly-panel`) |

**View / Edit contracts:** View → `invoice-view` + `id`; Edit → `invoice-calculator` + `invoiceId` (never `invoice-edit`). Same-panel re-apply does not tear down handlers.

**Classic Client Dashboard:** invoice cards | in-page preview | projects host | client info (Address/Notes edit). Overlay search: **persistent** recent-6 (`LastInteractedAt` / `GET /clients/recent`), clear keeps selection, query == `display_name` does not auto-open overlay. Empty MRU shows “Interact with a client…” (no GetAll pad). Autoselect last-used on open when `client_mru_autoselect` is true (default). Dashboard **Clients** card → Classic.

## Client MRU + host shortcuts (Future UI polish)

| Method | Path | Purpose |
|--------|------|---------|
| `GET` | `/api/sysforge/clients/recent?limit=` | Persistent MRU (default 6); empty if none touched |
| `POST` | `/api/sysforge/clients/{id}/touch` | Bump `LastInteractedAt` (UTC) |

- Migration: `0026_clients_last_interacted.sql` (`LastInteractedAt` + index). Concurrent siblings: payments `0027`, invoice documents `0028`, part price history `0029`, client merge `0030`.
- Implicit touches: client update, invoice create/update; Classic pick + calculator client select call `POST …/touch`.
- Host shortcut: `open_sysforge` (label “Open Business”, unbound by default) in Settings → Shortcuts; hidden when `features.sysforge` is off. Themes stay Odysseus global.
- Dashboard favorites: `config.json` `dashboard_favorites` card ids; star pins to top. Chrome breadcrumb: `Business › {route title}` (in-session; nav history not persisted across reload).

## Invoices API + calculator save contracts

| Method | Path | Purpose |
|--------|------|---------|
| `POST` | `/api/sysforge/invoices` | Create (name required; ≥1 item; Estimate / not finalized) |
| `GET` | `/api/sysforge/invoices/{id}` | Header + items (+ nested `client` when linked) |
| `GET` | `/api/sysforge/invoices/{id}/price-compare` | Finalized only: line vs catalog cents; estimates → `[]` |
| `PUT` | `/api/sysforge/invoices/{id}` | Same-id update; empty items allowed; omit status fields to preserve |
| `POST` | `/api/sysforge/invoices/{id}/save-as-new` | Clone → new Estimate (name + ≥1 item) |
| `GET` | `/api/sysforge/invoices?client_id=` | List for client |
| `GET` | `/api/sysforge/clients/{id}/invoices` | Same list (client must exist) |
| `DELETE` | `/api/sysforge/invoices/{id}` | Delete + orphan cleanup |
| `GET` | `/api/sysforge/invoices/{id}/pdf` | Generate + download PDF (`application/pdf`); persists `InvoiceDocuments` |
| `POST` | `/api/sysforge/invoices/{id}/email` | Body `{ to?, subject?, body?, account_id? }` — attach PDF via host SMTP; sets `SentAt` |
| `GET` | `/api/sysforge/invoices/outstanding` | Invoices with balance > 0 |
| `GET` | `/api/sysforge/invoices/{id}/payments` | Payments + `balance_cents` |
| `POST` | `/api/sysforge/invoices/{id}/payments` | Record payment (`amount_cents`, `method`, …) |
| `POST` | `/api/sysforge/payments/{id}/void` | Soft-void with `reason` |
| `GET` | `/api/sysforge/reports/sales` | Date-range sales/tax summary; `?format=csv` or `Accept: text/csv` |

**PDF / email (invoice-ops A+B):** Viewer **Download PDF** works without mail. **Email…** prefills client email (override allowed). Uses Odysseus host mail — no plugin SMTP. Outlook/OAuth limits match `docs/email-outlook.md`. On success: `SentAt` set; `Estimate` → `Invoiced`.

**Payments (slice C):** integer cents; methods Cash/Card/Check/Transfer/Other; soft-void only; auto `Paid` when balance ≤ 0 with ≥1 payment. Viewer **Payments** panel records / lists / voids payments and shows balance. Outstanding list: `#sysforge/invoices/outstanding`.

**Client merge (slice D):** `POST /clients/merge` `{ survivor_id, loser_id }` reassigns invoices, work orders, and projects; soft-deletes loser with `MergedIntoClientId`; rebuilds `clients_fts`. Candidates: `GET /clients/merge/candidates` (same phone/email/name signals as duplicate detection — never auto-merges). GET deleted loser → `409` `{ code: "merged", merged_into_client_id, … }`. UI: `#sysforge/clients/merge`.

**Reports (slice E):** `GET /reports/sales?from=&to=` JSON summary + invoice rows; `?format=csv` downloads CSV. UI: `#sysforge/reports/sales` (dashboard **Sales report** card).

**Save identity:** edit keeps the same id and stored name (no rename dialog). Create / save-as-new prompt for a name.

**Return context (BUG-008):** Save-as-new → trim invoice-flow history → viewer → Back lands on Classic with client selected. Edit save → trim → restore origin. Viewer Edit does not wipe origin. Helpers: `navigateToViewerAfterSaveAsNew`, `navigateAfterInvoiceSave`, `invoice-return-context.js`.

**Orphan order:** `DELETE` items → create placeholders → `INSERT` items → **then** orphan cleanup (BUG-006).

**Empty-item policy:** create / save-as-new require ≥1 line; edit may save an empty header.

**Money:** integer cents / bps / milliunits on the wire. Status / item_type / discount_type are strings.

**UI:** `static/js/views/calculator.js` — client typeahead (matches before Add New, edit-load dropdown guard), line grid, tax/shipping, busy flags, drafts autosave hooks. Viewer: `views/invoice-viewer.js` (read-only + price-mismatch flags; **Download PDF** / **Email…** / Payments panel / Edit → calculator).

**Backup:** JSON snapshots under `data/plugins/sysforge/InvoiceBackups/` on update (best-effort; does not block save).

## Business settings API

- `GET` / `PUT` `/api/sysforge/settings` — tax (percent ↔ `tax_rate_bps`), `currency`, `autosave_drafts`, `autosave_interval_seconds`.
- File: `data/plugins/sysforge/config.json` (defaults: 775 bps / USD / autosave on / 60s interval).
- Nested `drafts.auto_delete_old` defaults **false** (DRAFT-08). Retention is optional: Settings → Draft retention + pin; install and startup never delete draft files.
- Nested `drafts` keys: `auto_delete_old`, `retention_months` (1–60), `schedule_enabled`, `schedule_interval_days`, `last_cleanup_at`, `last_cleanup_deleted`.
- Nested `backup` schedule keys: `schedule_enabled`, `schedule_interval_days`, `retention_days`, `include_drafts`, `last_run_at`.
- Python helper: `integrations.sysforge.config.load_config()` / `save_config()`.

## Draft retention (DRAFT-08)

Safe defaults: **off**. Cleanup never runs on install, plugin load, or app boot.

| Method | Path | Purpose |
|--------|------|---------|
| `GET`/`PUT` | `/drafts/retention` | Settings + last cleanup metadata |
| `GET` | `/drafts/retention/preview` | Candidate count (read-only; optional `?months=`) |
| `POST` | `/drafts/retention/cleanup` | Execute when `auto_delete_old`; else `{ deleted: 0, reason: "disabled" }` |
| `PATCH` | `/drafts/{id}/pin` | Keep-forever pin on named drafts (autosaves → 400) |

**Rules:** skip autosaves and pinned drafts; toast after `deleted > 0`; manual “Clean up now” requires the toggle on; lazy weekly schedule (`schedule_enabled`) still gates on `auto_delete_old`.

**UI:** Settings → **Draft retention**; Drafts list **Pin** / **Unpin**.

## Business backup / restore (plugin-scoped)

**ADR:** Business backup is **not** Odysseus `/api/export` / `/api/import` (memories, presets, skills, host settings). Shop backups live under `data/plugins/sysforge/backups/` as ZIP archives (`sysforge.db` + optional `config.json` / `drafts/` + `manifest.json`). Full-host `scripts/odysseus-backup` may copy the plugin folder as disaster recovery only.

| Method | Path | Purpose |
|--------|------|---------|
| `GET` | `/backup/list` | List ZIP/`.db` backups (also runs due scheduled backup) |
| `POST` | `/backup/create` | Create Business ZIP (`include_drafts` optional) |
| `GET` | `/backup/download/{id}` | Download backup file |
| `POST` | `/backup/restore` | Restore from `backup_id` JSON or uploaded `.zip`/`.db` |
| `GET` | `/backup/export.json` | Portable JSON (`exportVersion` `1.0`; includes `payments`, `invoiceDocuments`, `mergedIntoClientId`) |
| `POST` | `/backup/import.json` | Import JSON (multipart; Skip default; Overwrite supported) |
| `POST` | `/backup/search/rebuild` | Manual client FTS rebuild |
| `GET`/`PUT` | `/backup/schedule` | Schedule enable / interval / retention |

**BUG-018:** JSON import with `import_clients` rebuilds `clients_fts` even when conflict Skip imports **0** clients. `.db` restore also rebuilds search before success. Restart alone does not heal a stale index.

**Not ported:** unchecked SQL dump import. `.sql` uploads return 400; use JSON or `.db`/ZIP.

**UI:** Settings → **Backup & restore** (create, list, download, restore, export/import JSON, schedule, rebuild search).

**Scheduler:** lazy due-check on list/status-style access (`maybe_run_scheduled_backup`); host cron can also `POST /backup/create`.

## Business Diagnostics (read-only)

Product inspector for the **plugin** SQLite DB. Not host `/api/diagnostics/*`. No DebugLog / `.cursor/debug.log` writers (chat b89af01b).

| Method | Path | Purpose |
|--------|------|---------|
| `GET` | `/api/sysforge/diagnostics` | Schema version, DB health, client/invoice(/parts) counts |

- UI: `#sysforge/diagnostics` — summary strip + **Refresh**; cancel on leave.
- `path_display` is always relative (`plugins/sysforge/sysforge.db`). Absolute path only when the caller is admin **and** `?reveal_path=1`.
- Response is HTTP 200 with `health`: `ok` / `missing` / `schema_pending` / `error` so the panel can render degraded states.
- **Diagnostics ≠ search proof:** rows here are in SQLite; FTS search may still miss them until reindex after import/restore (BUG-018).
- MVP is summary-only (no raw grids / SQL console / writes).

## Clients CRUD + FTS5 search

Desktop Lucene is **not** ported. Client typeahead uses SQLite **FTS5** in the same plugin DB (`clients_fts` + triggers; migration `0016_clients_fts`).

| Method | Path | Purpose |
|--------|------|---------|
| `GET` | `/api/sysforge/clients` | List active (`?incomplete=1` optional) |
| `GET` | `/api/sysforge/clients/search?q=&limit=` | FTS typeahead (phone/email merge); empty `q` → `[]` |
| `GET` | `/api/sysforge/clients/recent?limit=` | Persistent MRU by `LastInteractedAt` |
| `POST` | `/api/sysforge/clients/{id}/touch` | Bump MRU timestamp |
| `GET` | `/api/sysforge/clients/{id}` | Get one (404 if missing; `409` merged payload if soft-merged) |
| `POST` | `/api/sysforge/clients` | Create |
| `PUT`/`PATCH` | `/api/sysforge/clients/{id}` | Update (also bumps MRU) |
| `DELETE` | `/api/sysforge/clients/{id}` | Soft-delete |
| `POST` | `/api/sysforge/clients/duplicates` | Non-blocking duplicate hints |
| `GET` | `/api/sysforge/clients/merge/candidates` | Detect-only merge candidates (`client_id` / phone / email / name) |
| `POST` | `/api/sysforge/clients/merge` | Soft-merge `{ survivor_id, loser_id }` |

- Domain: `integrations/sysforge/services/clients.py`, `client_query.py`, `client_merge.py` (`normalize_phone`, `parse_client_query`, `rebuild_clients_fts`).
- UI: `#clients` list/create/edit; shared typeahead `static/js/clientSearch.js` (250 ms debounce, AbortController, **matches before Add New**). Merge tool: `#sysforge/clients/merge`.
- Duplicate banner: warn only; **Use this client** / **Create new client anyway** (no uniqueness constraints). Merge is a separate intentional tool.

## Drafts (file-based)

- Folder: `data/plugins/sysforge/drafts/` (`draft_{uuid}.json`, rotating `autosave_1..3.json`).
- Service: `integrations.sysforge.drafts.service.DraftService` (atomic write, list cache, concurrency lock).
- API: `GET/POST /api/sysforge/drafts`, `GET/PUT/PATCH/DELETE /drafts/{id}`, `POST /drafts/delete`, `PUT/GET/DELETE /drafts/autosave*`.
- Naming: `AUTOSAVE`, `Unknown Client - MM/dd/yyyy HH:mm` (normalize), `Untitled Draft - …` (display fallback).
- JS: list UI `static/js/views/drafts.js`; autosave controller `static/js/drafts-autosave.js` (timer, skip-if-busy, leave flush, recovery toast).

Replace a placeholder by registering a real `mount` from the module file:

```js
import * as router from './router.js';
router.register('clients', { title: 'Clients', mount: (el) => mountClients(el) });
```

Lifecycle: bind handlers once on first `mount`; `activate` is idempotent (do not double-bind). Call `deactivate` on leave for abort/autosave later.

**Close modal ≠ destroy cache.** Cache and back stack survive close/reopen until page reload or uninstall.
