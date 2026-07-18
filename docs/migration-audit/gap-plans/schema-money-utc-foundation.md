# Fill-the-gap plan: `schema-money-utc-foundation`

| Field | Value |
|-------|-------|
| **Issue id** | `schema-money-utc-foundation` |
| **Title** | Checksummed migrations + money/UTC helpers |
| **Phase** | P0 |
| **Priority** | critical |
| **Domain** | other (data infrastructure) |
| **depends_on** | _(none — this is the foundation)_ |
| **Blocks** | `business-shell-dashboard-router`, `clients-crud-fts-duplicates`, `parts-placeholders-merge`, `drafts-service-autosave`, `diagnostics-readonly-panel`, and every later domain API |
| **Sources** | MASTER §5 Phase 0; feature-gap-matrix §8; chats `693ac8c9`, `0aea6b1e`; `Sysforge research/04-data-model-migration.md`; `Sysforge research/features/database-infrastructure.md` |

---

## 1. Goal / success criteria

Give the Business Management plugin a real, checksummed SQLite schema and the same money/UTC conventions as desktop SysForge, so later workstreams can build clients/invoices/parts on a stable foundation.

**Ease-of-use parity (foundation layer):** users do not see this surface, but every quote and save depends on it. Money must round the same as desktop. Timestamps must store UTC and display local. Schema upgrades must refuse silent rewrite of applied SQL.

### Exit criteria (done when all are true)

- [ ] Fresh plugin install creates `data/plugins/sysforge/sysforge.db` and applies migrations `0002`–`0015` in order (not an empty touch file).
- [ ] `SchemaVersion` rows exist for each applied migration with SHA-256 checksums matching the shipped SQL bytes.
- [ ] Re-running install / migrate is idempotent (no double-apply; no schema drift).
- [ ] Editing an already-applied migration file causes a clear checksum-mismatch failure (desktop `MIGR-CHK-001` behavior).
- [ ] Post-`0012` money columns are INTEGER cents / basis points / milliunits (verify `PRAGMA table_info` on `Invoices`, `InvoiceItems`, `Parts`).
- [ ] Python `money` helpers round-trip desktop test vectors (`10.99` ↔ `1099`, `7.25%` ↔ `725`, `2.5` ↔ `2500`, tax/line-total cases).
- [ ] Python UTC helpers store `yyyy-MM-dd HH:mm:ss` UTC strings; display helpers convert for local UI; no local-only writes into the DB.
- [ ] DB connection helper uses WAL + foreign_keys + busy_timeout; async-friendly API shape from day one (`async` connect / execute helpers or `asyncio.to_thread` wrapper — no sync-only service layer to redo later).
- [ ] `/api/sysforge/status` (or a thin schema endpoint) can report latest applied migration id/name for diagnostics follow-on.
- [ ] Unit tests cover runner, checksum mismatch, money, UTC; install test asserts tables exist after `run_install()`.

---

## 2. Current state (desktop vs odysseus)

### Desktop SysForge (Done)

| Piece | Location | Behavior |
|-------|----------|----------|
| Migration runner | `SysForge/Database/MigrationRunner.cs` | Discover embedded `*.sql`, order by id, checksum applied rows, apply pending in a transaction, record `SchemaVersion` |
| Migration model | `Migration.cs` | SHA-256 of UTF-8 SQL via `Convert.ToHexString` (uppercase hex) |
| Checksum mismatch | `MigrationChecksumMismatchException.cs` | Error code `MIGR-CHK-001`; Dev vs Prod recovery copy |
| SQL files | `SysForge/Database/Migrations/0002`–`0021` | Append-only; never edit applied files (`AI_LEARNINGS.md`) |
| Core shop schema | `0002`–`0015` | Settings, suppliers, parts, clients, invoices/items, triggers, **money→cents**, invoice name + last edited |
| Later schema | `0016`–`0021` | Work orders, devices, projects, screw maps — **out of this workstream** |
| Connection | `DatabaseService.cs` | `PRAGMA foreign_keys=ON; journal_mode=WAL; synchronous=NORMAL; busy_timeout=…`; async `CreateConnectionAsync` |
| Money | `Helpers/MoneyHelpers.cs` + tests | Dollars↔cents, %↔bps, qty↔milliunits; tax + line total in cents; `MidpointRounding.AwayFromZero` |
| UTC | `Helpers/DateTimeHelpers.cs` | Store UTC; `ToLocal` / format for display; `ValidateUtc` / `EnsureUtc` |
| Money migration | `0012_money_to_cents.sql` | Rebuild tables NUMERIC → INTEGER cents (historical path; still required for checksum continuity) |

### odysseus-sysforge (Stub)

| Piece | Location | Behavior |
|-------|----------|----------|
| Install | `integrations/sysforge/install.py` | `mkdir` data/drafts/backups; **`sysforge.db.touch()` only**; writes `config.json` (`tax_rate_bps`, `currency`, `autosave_drafts`) |
| API | `integrations/sysforge/routes.py` | Gated `/api/sysforge/status` only |
| UI | `integrations/sysforge/static/js/index.js` | Stub modal + status text |
| Host time | `src/user_time.py` | Browser/user-local for chat prompts — **not** Business DB storage helpers |
| Host SQLite | scattered `sqlite3` in core | No plugin `SchemaVersion` / MigrationRunner |
| Research | `Sysforge research/04-data-model-migration.md` | Spec already says: isolated DB, checksum runner, cents, UTC, no desktop import |

**Gap in one line:** install succeeds; the database has no schema, no money/UTC helpers, and no migration immutability policy.

---

## 3. Scope in / out

### In scope

1. **Copy** desktop SQL `0002`–`0015` into the plugin tree **byte-stable** (no reformatting; checksums are whitespace-sensitive).
2. Python **MigrationRunner** equivalent:
   - Ensure `SchemaVersion(Id, Name, Checksum, AppliedAt)`
   - Discover `NNNN_name.sql` from plugin package dir
   - Verify checksums for applied ids; apply pending in order inside a transaction per migration
   - Record `AppliedAt` as UTC `yyyy-MM-dd HH:mm:ss`
3. Wire runner into **install** and a safe **upgrade/re-migrate** path (idempotent call on plugin load or explicit migrate step).
4. **Database connection** helper scoped to plugin DB path (`plugin_data_dir("sysforge") / "sysforge.db"`).
5. **Money helpers** port (`to_cents` / `from_cents` / basis points / milliunits / `calculate_tax_cents` / `calculate_line_total_cents`).
6. **UTC helpers** port (utcnow for storage, parse DB TEXT as UTC, format local for display contracts used by later UI).
7. Thin **schema status** fields on existing status API (latest migration id, applied count) — no full Diagnostics UI (that is `diagnostics-readonly-panel`).
8. Tests for runner, money, UTC, install→schema.

### Out of scope

- Migrations `0016`–`0021` (projects / WO / screw maps) — later workstreams.
- Business dashboard / `router.js` — `business-shell-dashboard-router`.
- Domain CRUD APIs / FTS / drafts service / calculator UI.
- Desktop `%LOCALAPPDATA%\SysForge` import or backup restore.
- Collapsing `0002`–`0012` into a single “greenfield cents” migration (breaks checksum continuity and desktop parity proofs).
- Merging into Odysseus core `SQLAlchemy` schema.
- Settings UI for tax/currency — `business-settings-mvp` (config.json defaults stay for now).
- Optional `backupOnMigration` full UX — stub a flag in config; real backup UX belongs with backup workstream.
- Porting C# `EnumStringTypeHandler` / Dapper (use plain strings matching CHECK enums).
- Changing host `src/user_time.py` semantics for chat.

---

## 4. Dependencies

### Upstream

- **None** (`depends_on: []`). Plugin install shell already exists.

### Downstream consumers (must not break)

| Workstream | Needs from this |
|------------|-----------------|
| `business-shell-dashboard-router` | DB exists so status/shell can show “ready” |
| `clients-crud-fts-duplicates` | `Clients` table + async DB helper |
| `parts-placeholders-merge` | `Parts` / `Suppliers` + cents columns |
| `drafts-service-autosave` | UTC stamps on draft metadata; plugin data dir |
| `invoice-calculator-save-contracts` | Invoices/items cents schema + money helpers |
| `diagnostics-readonly-panel` | Queryable `SchemaVersion` |

### External / env

- Python stdlib `sqlite3` is enough for sync migrate-on-install; prefer **async wrappers from day one** (`asyncio.to_thread` around sqlite3, or add `aiosqlite` if the team wants native async — decide in step 2; do not ship a sync-only service façade).
- Keep SQL files as package data (not only copied at install).

---

## 5. Concrete steps (ordered)

### Step 1 — Package layout for SQL + modules

Create under `integrations/sysforge/`:

```
db/
  __init__.py
  connection.py      # path + pragmas + async-friendly open
  migration_runner.py
  money.py
  utc.py
  exceptions.py      # ChecksumMismatchError (MIGR-CHK-001)
migrations/
  0002_settings.sql
  … through …
  0015_invoices_last_edited.sql
```

Copy SQL **verbatim** from `F:\Codeing Project\SysForge\SysForge\Database\Migrations\` for `0002`–`0015` only. Verify file hashes match desktop after copy.

### Step 2 — Connection helper

In `connection.py`:

- `db_path() -> Path` via `plugin_data_dir("sysforge") / "sysforge.db"`.
- `connect()` / `connect_async()` applying:
  - `PRAGMA foreign_keys=ON`
  - `PRAGMA journal_mode=WAL`
  - `PRAGMA synchronous=NORMAL`
  - `PRAGMA busy_timeout=5000` (read from `config.json` later if present)
- Document **single-writer** assumption (one Odysseus process owns the plugin DB).

### Step 3 — Checksum + SchemaVersion runner

Port desktop algorithm:

1. `CREATE TABLE IF NOT EXISTS SchemaVersion (Id INTEGER PRIMARY KEY, Name TEXT NOT NULL, Checksum TEXT NOT NULL, AppliedAt TEXT NOT NULL DEFAULT (datetime('now')))`.
2. Load applied map from DB.
3. Discover migrations: files matching `^(\d{4})_.+\.sql$`, sort by int id.
4. For each discovered file that is already applied: compare SHA-256 (UTF-8 bytes → uppercase hex, matching `Convert.ToHexString`) to stored checksum; on mismatch raise `ChecksumMismatchError` with Dev recovery hint (delete plugin DB in development) vs Prod (append corrective migration).
5. For each pending migration: `BEGIN` → `executescript(sql)` → `INSERT INTO SchemaVersion` with UTC `AppliedAt` → `COMMIT`. On failure `ROLLBACK`.
6. Public API: `run_migrations(db_path: Path | None = None) -> MigrationReport` (`applied_now`, `already_applied`, `latest_id`).

**Do not** use a separate `migrations_applied.json` as source of truth (research draft mentioned it); desktop truth is `SchemaVersion` only. Optional JSON sidecar is fine for logging, not authority.

### Step 4 — Wire install (and re-entry)

Update `integrations/sysforge/install.py`:

- Stop treating empty touch as success.
- After data dir ready: ensure DB file exists → `run_migrations()`.
- On **already_installed**: still call `run_migrations()` so plugin upgrades can apply new SQL files without reinstall (idempotent).
- Surface migration step in `steps[]` (`status=ok`, message like `Schema at migration 0015`).

Also call `run_migrations()` from a single module-level “ensure schema” used by future routes (lazy ensure on first API hit is acceptable backup if install was skipped in tests).

### Step 5 — Money helpers

Port `MoneyHelpers.cs` to `db/money.py` with identical rounding:

| Function | Contract |
|----------|----------|
| `to_cents(dollars: Decimal) -> int` | `round(dollars * 100, ROUND_HALF_UP)` AwayFromZero |
| `from_cents(cents: int) -> Decimal` | `cents / 100` |
| `to_basis_points` / `from_basis_points` | ×/÷ 100 |
| `to_milliunits` / `from_milliunits` | ×/÷ 1000 |
| `calculate_tax_cents(subtotal_cents, rate_bps)` | desktop formula |
| `calculate_line_total_cents(qty_mu, unit_cents, discount_type, discount_value)` | `None`/`Percent`/`Amount` |

Use `decimal.Decimal` for inputs; never `float` for money math.

API/JSON convention for later workstreams (document now, enforce in calculator later):

- DB + internal service: integer cents / bps / milliunits.
- HTTP JSON may expose both `*_cents` and display dollars, but **writes** accept cents (or dollars only through helper — pick one and stick; recommend cents in API body to avoid float JSON).

### Step 6 — UTC helpers

Port storage/display split to `db/utc.py`:

| Function | Contract |
|----------|----------|
| `utc_now() -> datetime` | timezone-aware UTC |
| `to_utc(dt) -> datetime` | Kind rules mirrored: Utc pass-through; Local convert; naive treated as local→UTC (match `DateTimeHelpers.ToUtc`) |
| `format_storage(dt) -> str` | `yyyy-MM-dd HH:mm:ss` UTC |
| `parse_storage(text) -> datetime` | Parse as UTC (naive string → assume UTC) |
| `to_local(utc_dt) -> datetime` | For display |
| `format_date` / `format_datetime` / `format_relative` | Match desktop strings where UI will reuse them; OK to use locale later |

Rule to document in module docstring: **all Business DB timestamps are UTC TEXT; convert only at UI / JSON response formatting.**

Do not confuse with `src/user_time.py` (chat relative dates).

### Step 7 — Status API enrichment

Extend `GET /api/sysforge/status` payload:

```json
{
  "ok": true,
  "plugin_id": "sysforge",
  "installed": true,
  "version": "0.1.0",
  "schema": {
    "latest_id": 15,
    "latest_name": "0015_invoices_last_edited",
    "applied_count": 14,
    "db_exists": true
  }
}
```

No secrets, no absolute paths in multi-user responses (path can wait for diagnostics workstream with auth).

### Step 8 — Tests

Add `tests/test_sysforge_migrations.py`, `tests/test_sysforge_money.py`, `tests/test_sysforge_utc.py`; extend `tests/test_sysforge_plugin.py` install assertion.

### Step 9 — Short developer note

Add a brief section to `integrations/sysforge/README.md`: migration immutability, how to reset plugin DB in dev (`delete data/plugins/sysforge/sysforge.db` + reinstall), money/UTC rules. Do not invent a second AI_LEARNINGS file unless asked.

---

## 6. Files to create / modify

### Create

| Path | Purpose |
|------|---------|
| `integrations/sysforge/migrations/0002_settings.sql` … `0015_invoices_last_edited.sql` | Verbatim SQL from desktop |
| `integrations/sysforge/db/__init__.py` | Package exports |
| `integrations/sysforge/db/connection.py` | Plugin DB path + pragmas |
| `integrations/sysforge/db/migration_runner.py` | Checksummed runner |
| `integrations/sysforge/db/exceptions.py` | `ChecksumMismatchError` |
| `integrations/sysforge/db/money.py` | Cents / bps / milliunits |
| `integrations/sysforge/db/utc.py` | UTC storage / local display |
| `tests/test_sysforge_migrations.py` | Runner + checksum + install schema |
| `tests/test_sysforge_money.py` | Desktop vector parity |
| `tests/test_sysforge_utc.py` | Storage/parse/local |

### Modify

| Path | Change |
|------|--------|
| `integrations/sysforge/install.py` | Run migrations; already-installed upgrade path |
| `integrations/sysforge/routes.py` | Schema summary on `/status` |
| `integrations/sysforge/README.md` | Dev reset + conventions |
| `tests/test_sysforge_plugin.py` | Assert tables / SchemaVersion after install |
| `integrations/sysforge/manifest.json` | Bump version when shipping (e.g. `0.2.0`) once schema lands |

### Do not modify

- Existing desktop migration files in SysForge repo (copy only).
- Odysseus core SQLAlchemy models.
- Stub UI layout (shell workstream).

---

## 7. API / UI contracts

### Install / migrate

- `run_install()` must leave a DB where `SELECT COUNT(*) FROM SchemaVersion` equals the number of shipped `0002`–`0015` files (14 files if numbering starts at 0002 with no 0001).
- Second `run_install()` / `run_migrations()` must not error and must not change checksums.
- Checksum mismatch → failed install/migrate with structured error (`error_code: MIGR-CHK-001`, migration id/name, expected vs actual checksum). HTTP mapping for a future admin endpoint: `500` with that payload; install CLI/API returns `ok: false` and step failure.

### Status API

- `GET /api/sysforge/status` remains gated by plugin active.
- Adds `schema` object (see Step 7). Missing DB → `db_exists: false`, `latest_id: null`.

### Money (service contract for P1)

- Columns after migrate: `*Cents`, `*BasisPoints`, `QuantityMilliunits`, etc. (post-`0012` names).
- Helpers are the only conversion path between dollars and storage integers.
- Tax default in empty Settings row follows SQL defaults; plugin `config.json` `tax_rate_bps` is app preference for new invoices (calculator workstream wires it).

### UTC (service contract for P1)

- Inserts/updates use `format_storage(utc_now())` or SQL `datetime('now')` (SQLite `now` is UTC — matches desktop sandbox proof).
- API responses that show times to humans should include ISO-8601 with `Z` or a parallel `*_local` formatted field; raw DB TEXT is UTC without offset suffix (desktop convention).

### UI

- No new UI in this workstream beyond status text if the stub already shows version (optional one-line “Schema 0015”).
- Dashboard cards remain out of scope.

---

## 8. UX contracts that must not be lost

These are foundation-level contracts from MASTER §4; this workstream establishes them so later UI cannot regress:

| Contract | How this workstream enforces it |
|----------|----------------------------------|
| **Migrations immutable** | Checksum verify before apply; refuse edited applied SQL |
| **Money / enums / JSON helpers** | Cents helpers + keep CHECK enum strings (`Estimate`/`Invoiced`/`Paid`, discount types) in SQL as-is |
| **Async from day one** | Connection/migrate APIs shaped for async callers; no sync-only domain service façade |
| **Fresh DB, no desktop import** | Install always migrates empty/new plugin DB; no `%LOCALAPPDATA%\SysForge` path |
| **Ease-of-use: silent money bugs** | Round-trip tests matching desktop; AwayFromZero rounding |

Not owned here but must not be broken by schema choices:

- Invoice status CHECK values stay exact strings (calculator / viewer later).
- `DateCreated` / `LastEdited` TEXT sort lexicographically as chronology (ISO-like UTC format).

---

## 9. Tests / verification checklist

### Automated

- [ ] **Fresh migrate:** empty temp dir → `run_migrations` → tables `Clients`, `Invoices`, `InvoiceItems`, `Parts`, `Suppliers`, `Settings`, `SchemaVersion` exist.
- [ ] **Post-0012 shapes:** `Invoices.FinalTotalCents` / `InvoiceItems.UnitPriceCents` / `Parts.BasePriceCents` are INTEGER (via `PRAGMA table_info`).
- [ ] **Idempotent:** run twice → same `SchemaVersion` count; no error.
- [ ] **Checksum tamper:** flip stored checksum → raises `ChecksumMismatchError` with id + `MIGR-CHK-001`.
- [ ] **File tamper:** after apply, alter a SQL file on disk → next run raises mismatch (temp copy of migrations dir).
- [ ] **Money vectors:** mirror `MoneyHelpersTests.cs` (10.99, 10.995→1100, 7.25%, 2.5, tax $100@7.25%, percent/amount line discounts).
- [ ] **UTC:** `format_storage` / `parse_storage` round-trip; naive parse treated as UTC; `to_local` shifts by local offset.
- [ ] **Install integration:** `run_install()` in tmp `PLUGINS_DATA_ROOT` → SchemaVersion populated; uninstall with `remove_data=False` leaves DB (current behavior) or document expected cleanup.

### Manual

- [ ] Install plugin from Settings → Integrations → open Business stub → status shows schema latest id.
- [ ] Delete `sysforge.db` only → trigger migrate/ensure → schema rebuilds without reinstall marker loss (or documented “delete whole plugin data dir”).
- [ ] Confirm WAL files (`sysforge.db-wal`) appear under plugin data after first write.

### Non-goals for this checklist

- Creating a client or invoice in UI.
- FTS index build.
- Backup ZIP.

---

## 10. Risks & open questions

| Risk / question | Recommendation |
|-----------------|----------------|
| **SQL encoding / line endings** | Copy with LF or CRLF consistently; hash on exact bytes. Prefer copying from SysForge git as-is on Windows without “fix on save.” |
| **Uppercase vs lowercase hex** | Match C# `Convert.ToHexString` → **uppercase**. Document in runner. |
| **No `0001` file** | Desktop starts at `0002`; runner must not require contiguous ids from 1. |
| **`0012` table rebuild on empty DB** | Harmless on empty tables; keep historical SQL for parity. Do not squash. |
| **When to ship `0016+`** | Only with projects/screw-map workstreams; leave files out of the package until then so `latest_id` stays 15 for P0/P1. |
| **aiosqlite vs stdlib** | Prefer stdlib + `asyncio.to_thread` to avoid new dep unless team already wants aiosqlite; either way, public service methods should be `async def`. |
| **Empty pre-existing touch DB** | Current installs may already have a 0-byte `sysforge.db`. Runner must open and migrate that file successfully (SQLite treats it as new DB). |
| **Multi-user Odysseus** | Research mentions optional `owner` column later. **Do not** alter desktop SQL in this pass; track owner scoping as a future additive migration `0022+` if required. |
| **Checksum mismatch in prod** | Never auto-delete DB; only append corrective migrations. Dev docs may say delete plugin DB. |
| **Research `__Migrations` name** | Ignore; use desktop `SchemaVersion`. |
| **Window/settings columns in `0009`/`0010`** | Port SQL as-is even if web ignores window geometry; keeps checksum identity with desktop. |

### Open questions for product owner (non-blocking defaults)

1. Should already-installed users get migrate-on-status (lazy) as well as migrate-on-install? **Default: both.**
2. Expose absolute `db_path` on status? **Default: no** until diagnostics + auth review.
3. Bump plugin semver to `0.2.0` when schema ships? **Default: yes.**

---

## 11. Effort estimate

**M (medium)**

Rough breakdown:

| Chunk | Size |
|-------|------|
| Copy SQL + packaging | S |
| Migration runner + checksum tests | M |
| Install wiring + status schema fields | S |
| Money + UTC helpers + tests | S–M |
| Docs / README | S |

Single focused implementer: ~1–2 days including tests. Do **not** combine with dashboard shell in the same PR if review bandwidth is tight; shell depends on this but can start UI scaffolding once migrate API is merged.

---

## Implementation order reminder

1. This workstream (`schema-money-utc-foundation`)
2. `business-shell-dashboard-router`
3. P1 domain APIs (clients → parts → drafts → calculator)

Ship schema first; every other Business feature assumes cents, UTC, and `SchemaVersion`.
