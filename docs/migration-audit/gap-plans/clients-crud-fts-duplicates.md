# Clients CRUD, FTS5 search, duplicate warnings

| Field | Value |
|-------|-------|
| **Issue id** | `clients-crud-fts-duplicates` |
| **Title** | Clients CRUD, FTS5 search, duplicate warnings |
| **Phase** | **P1** |
| **Effort** | **M** |
| **Priority** | critical |
| **Domain** | clients |
| **Primary sources** | SysForge `ClientService.cs`, `ClientValidationHelpers.cs`, `ClientQueryParser.cs`, `ClientDocumentMapper.NormalizePhone`, migration `0005_clients.sql`, DB-12 chats [55127af8](../chat-reviews/55127af8-5c1c-45ed-8f64-b1558712f3cf.md) / [784da76d](../chat-reviews/784da76d-e4c8-44bb-9eca-59d99e1b0980.md); research `docs/research/sysforge/features/clients-management.md`, `client-search-lucene.md` |
| **Manifest** | `gap-plans/gap-manifest.json` -> `clients-crud-fts-duplicates` |
| **Master plan** | `synthesis/MASTER-MIGRATION-PLAN.md` -> Phase 1 (Invoice MVP) |

---

## Goal / success

Port the desktop client domain into the Odysseus Business plugin so a tech can create, find, edit, and soft-delete clients in the browser as fast as desktop typeahead, without shipping Lucene/PyLucene.

**Done when:**

1. **CRUD** — create / get / update / soft-delete clients via `/api/sysforge/clients*`; soft-deleted rows excluded from get/search; validation matches desktop (at least one of name, company, phone, email; email format; name length caps).
2. **FTS5 typeahead** — `GET .../clients/search?q=` returns relevance-ranked matches by name/company/nickname/email/address/associates; phone digits still match via normalized phone path (FTS + DB merge, same idea as Lucene + `FindClientsByPhone`).
3. **Matches before Add New** — search UI (and calculator consumer later) lists real matches first, then a single **Add New** sentinel; never Add New above hits.
4. **Debounce + abort** — client search requests debounce (~200–300 ms) and cancel in-flight fetches on new keystrokes / leave.
5. **DB-12 duplicate warnings** — non-blocking; **Use this client** / **Create new client anyway**; no uniqueness constraints on phone/email; merge tool stays deferred.
6. **Index hygiene** — create/update/soft-delete keep `clients_fts` consistent (triggers and/or explicit rebuild helper for later BUG-018 import paths).
7. **Tests green** — API + FTS + duplicate + soft-delete coverage in `tests/`; plugin gate still 404 when inactive.

---

## Current state

### SysForge desktop (source of truth)

| Area | Behavior | Anchor |
|------|----------|--------|
| Schema | `Clients` table: name/contact fields, `Associates` JSON, `IsIncomplete`, `IsDeleted`, UTC-ish `DateAdded`/`LastUpdated`, indexes on name/phone/deleted | `0005_clients.sql` |
| CRUD | `AddClientAsync`, `UpdateClientAsync`, `SoftDeleteClientAsync`, `GetClientByIdAsync` (skips deleted), `GetAllClientsAsync`, `GetIncompleteClientsAsync` | `ClientService.cs` |
| Validation | ≥1 identifier; email regex if present; First/Last ≤100; Company/Nickname ≤200 | `ClientValidationHelpers.cs` |
| Search | Lucene via `SearchService` (limit 20); fallback `LIKE` on name/company/nickname/email + normalized phone; merge phone/email DB hits; dedupe by id | `SearchClientsAsync` |
| Phone | Digits-only normalize; `REPLACE` strip for SQL fallback | `ClientDocumentMapper.NormalizePhone` |
| Query parse | `@` -> email; ≥7 digits after normalize -> phone; else name | `ClientQueryParser` |
| Duplicates | `FindPotentialDuplicatesAsync(phone, email, name, excludeClientId?)` — phone + email + name search, dedupe, no hard block | DB-12 |
| Calculator UX | Typeahead: results then **Add New**; on create / contact-shaped query show warning banner; **Use this client** / **Create new client anyway** | `InvoiceCalculatorViewModel` / `.axaml` |
| Display name | Nickname -> First+Last -> First -> Last -> Company -> `"Unknown"` | `Client.DisplayName` |
| Index hooks | Lucene `IndexClient` / `RemoveClientFromIndex` + `Commit` on write paths | not ported as Lucene |

**Explicit desktop deferrals (do not absorb here):** client merge tool; persistent MRU / `LastInteractedAt`; Classic four-column Client Dashboard (own workstream `classic-client-dashboard`).

### Odysseus web (target today)

| Area | State |
|------|--------|
| Plugin shell | Install/uninstall, `features.sysforge`, gated `/api/sysforge/status` only (`integrations/sysforge/routes.py`) |
| UI | Stub modal status copy (`integrations/sysforge/static/js/index.js`) — no clients panel, no typeahead |
| DB | `install.py` touches empty `data/plugins/sysforge/sysforge.db`; **no** `Clients` table until `schema-money-utc-foundation` |
| Search precedent | Host already uses SQLite **FTS5** for chat (`src/session_search.py`) and email local store (`routes/email_local_store.py` triggers) — reuse patterns (`_sanitize_fts_query`, content-sync triggers, FTS probe) |
| Clients API / UI | **Missing** |

### Gap (one sentence)

Desktop has full client CRUD + Lucene typeahead + soft duplicate warnings; Odysseus has none of that, and the web port must use **FTS5** (not Lucene) so search lives in the same SQLite file as the shop data.

---

## Scope

### In scope

- Python `ClientService` (or `integrations/sysforge/services/clients.py`) mirroring desktop SQL + validation + duplicate helpers.
- REST under `/api/sysforge/clients` (list/get/create/update/soft-delete/search/duplicates).
- SQLite **FTS5** virtual table `clients_fts` (or equivalent) + INSERT/UPDATE/DELETE triggers; phone matching via stored `phone_norm` column and/or dedicated SQL merge (parity with desktop Lucene+phone merge).
- `ClientQueryParser` + `normalize_phone` port (pure Python).
- Minimal **Clients** list/create/edit UI inside Business shell (enough to exercise CRUD + search + soft-delete before Classic dashboard).
- Shared typeahead helper module usable by calculator workstream later (`matches` then `Add New`; debounce/abort).
- Duplicate warning UI on client create (and export hooks for calculator: same API + same copy patterns).
- Unit/API tests; FTS rebuild helper stub callable by future backup/import workstream.
- Docs note in `integrations/sysforge/README.md`: “Clients CRUD + FTS5 search” once shipped.

### Out of scope

- **Client merge tool** (deferred; `invoice-ops-pdf-payments-merge` / MASTER §7).
- **Classic four-column Client Dashboard** (`classic-client-dashboard`).
- **Persistent MRU / recent-6** (`future-ui-mru-shell-polish`); session recent-6 may wait for Classic search overlay.
- **PyLucene / Lucene.NET** port; embedding/semantic client search.
- Invoice calculator full port (consumes this API; owned by `invoice-calculator-save-contracts`).
- Desktop DB import into plugin DB.
- Parts / suppliers FTS (later `parts-search-suppliers-depth`).
- Multi-tenant `owner` column unless P0 schema workstream already adds a plugin-wide ownership pattern; if it does, follow that contract rather than inventing a second one here.

---

## Dependencies

| Depends on | Why |
|------------|-----|
| `schema-money-utc-foundation` | `Clients` table from `0005_clients.sql` (or sequential port), migration runner, UTC helpers for `DateAdded`/`LastUpdated` |
| `business-shell-dashboard-router` | Clients card + inner route to mount list/edit UI; typeahead host surface |

| Soft / parallel | Why |
|-----------------|-----|
| Host FTS helpers (`session_search._sanitize_fts_query`, email FTS triggers) | Copy proven sanitize + trigger patterns; do not couple plugin DB to host chat FTS tables |
| `invoice-calculator-save-contracts` | **Downstream** consumer of search + duplicate APIs; land API first so calculator can wire without rewriting clients |
| `backup-restore-post-import-reindex` | Will call `rebuild_clients_fts()` (BUG-018); this workstream must expose that function |

**Blocked if:** empty `sysforge.db` with no migrations, or Business UI still status-only stub with no router.

---

## Concrete steps

### 1. Schema + FTS5 (after P0 migrations land)

1. Confirm `Clients` exists from ported `0005_clients.sql` (do not edit applied migrations; if FTS was omitted from the first port, add a **new** numbered migration).
2. Add migration (example name) `00NN_clients_fts.sql`:
   - `CREATE VIRTUAL TABLE clients_fts USING fts5(...)` with content sync to `Clients`.
   - Indexed text fields: `nickname`, `firstname`, `lastname`, `company`, `email`, `address`, `associates_text` (JSON array joined to space-separated names, same idea as Lucene mapper).
   - Unindexed/stored helpers as needed: `phone_norm` (digits only) — either as an FTS column with `UNINDEXED` or a regular column on `Clients` maintained by trigger (prefer a maintained `PhoneNorm` column or FTS `UNINDEXED` field so search can `MATCH` names and SQL-filter phones consistently).
   - Triggers: AFTER INSERT/UPDATE/DELETE on `Clients` keep FTS in sync; soft-delete (`IsDeleted=1`) must remove or exclude from FTS (delete from FTS on soft-delete; re-index if undelete ever added — undelete is out of scope).
3. Probe FTS5 availability the same way email/chat do; fail install/migration loudly if FTS5 missing (shop search is required for P1).

### 2. Python domain layer

1. Add `integrations/sysforge/services/clients.py` (name may match repo conventions from P0):
   - `normalize_phone(raw) -> str`
   - `parse_client_query(q) -> (phone|None, email|None, name|None)`
   - `display_name(row) -> str` (desktop priority order)
   - `validate_client(payload)` -> raise HTTP 400 / domain error with desktop messages
   - `add_client`, `update_client`, `soft_delete_client`, `get_client`, `list_clients` (optional `incomplete_only`)
   - `search_clients(q, limit=20)`:
     - empty/whitespace -> `[]`
     - FTS `MATCH` on sanitized query for text
     - always merge `find_by_phone` / `find_by_email` when parser detects them (or when normalized digits ≥7)
     - dedupe by `Id`, preserve FTS rank then phone/email extras
   - `find_potential_duplicates(phone, email, name, exclude_id=None)`
   - `rebuild_clients_fts()` — wipe + rebuild from non-deleted rows (for import/restore later)
2. Prefer **aiosqlite** / async APIs from day one (MASTER: don’t port sync->async twice). Cancel-friendly search used by routes.

### 3. API routes

Extend `integrations/sysforge/routes.py` (or `routes/clients.py` included by setup) behind `_require_sysforge_plugin`:

| Method | Path | Purpose |
|--------|------|---------|
| `GET` | `/api/sysforge/clients` | List active clients (optional `?incomplete=1`) |
| `GET` | `/api/sysforge/clients/search?q=&limit=` | Typeahead search |
| `GET` | `/api/sysforge/clients/{id}` | Get one (404 if missing/deleted) |
| `POST` | `/api/sysforge/clients` | Create |
| `PUT`/`PATCH` | `/api/sysforge/clients/{id}` | Update |
| `DELETE` | `/api/sysforge/clients/{id}` | Soft-delete |
| `POST` | `/api/sysforge/clients/duplicates` | Body: `{phone,email,name,exclude_id?}` -> `{duplicates:[...]}` |

Keep JSON field names **snake_case** in the web API (`first_name`, `phone_number`, …) even if SQL columns stay PascalCase like desktop; document the mapping in one place.

### 4. UI (minimal Clients surface + shared typeahead)

1. Business dashboard **Clients** card -> `#sysforge/clients` (or router id from shell workstream).
2. List view: search box, results table/rows, open edit, soft-delete with confirm.
3. Create/edit form: fields matching desktop model; show validation errors inline.
4. Extract `integrations/sysforge/static/js/clientSearch.js`:
   - `debounce` 250 ms default
   - `AbortController` per request
   - build dropdown model: `[{kind:'match', client}, …, {kind:'add_new', query}]` — **matches first**
5. Duplicate banner component (reusable):
   - Copy: `"N existing client(s) share this phone or email. Select one or create a new client anyway."`
   - Actions: **Use this client** (select), **Create new client anyway** (proceed)
   - Never block save at DB layer

### 5. Wire write-path index consistency

1. Rely on SQL triggers for normal CRUD.
2. After soft-delete, assert search no longer returns the id (test).
3. Export `rebuild_clients_fts` from the service module; call it from a private/dev route only if useful for QA — production callers are backup/import later.

### 6. Docs / hygiene

1. Update `integrations/sysforge/README.md` with endpoints and FTS decision (FTS5, not Lucene).
2. Cross-link this plan from gap-plans README when that index exists.

---

## Files

| Path | Action |
|------|--------|
| `SysForge/.../Migrations/0005_clients.sql` | **Read-only** reference for table shape |
| Plugin migrations dir (from P0) + new `*clients_fts*.sql` | **Add** FTS5 + triggers |
| `integrations/sysforge/services/clients.py` (new) | Domain service |
| `integrations/sysforge/services/client_query.py` (optional split) | Parser + phone normalize + FTS sanitize |
| `integrations/sysforge/routes.py` | Register client routes |
| `integrations/sysforge/static/js/clients.js` (new) | List/create/edit panel |
| `integrations/sysforge/static/js/clientSearch.js` (new) | Shared typeahead + debounce/abort |
| `integrations/sysforge/static/js/index.js` / router | Mount Clients view from dashboard card |
| `integrations/sysforge/README.md` | Document shipped surface |
| `tests/test_sysforge_clients.py` (new) | API + FTS + duplicates + soft-delete |
| `tests/test_sysforge_plugin.py` | Keep gate tests; optionally assert clients 404 when inactive |

**Do not modify** desktop Lucene code; web deliberately diverges to FTS5.

---

## API / UI contracts

### Client resource (JSON)

```json
{
  "id": 1,
  "first_name": "Jane",
  "last_name": "Doe",
  "nickname": null,
  "phone_number": "(555) 123-4567",
  "email": "jane@example.com",
  "address": null,
  "company": null,
  "associates": ["Spouse Name"],
  "referred_by": null,
  "notes": null,
  "is_incomplete": false,
  "date_added": "2026-07-17T12:00:00Z",
  "last_updated": "2026-07-17T12:00:00Z",
  "display_name": "Jane Doe"
}
```

- `associates`: array of strings in API; store as JSON text in SQLite like desktop.
- Soft-deleted clients: omitted from list/search/get (404 on get).
- Create may set `is_incomplete: true` when calculator does placeholder create (FirstName = typed query, empty LastName).

### Search

- `GET /api/sysforge/clients/search?q=chen&limit=20`
- Response: `{ "query": "chen", "results": [ /* Client */ ] }`
- Empty `q` -> `{ "results": [] }` (UI may show recent-6 later; **not** this workstream).
- Sanitize FTS input (reuse host idea: strip raw FTS operators; token/`"..."` only).
- Limit default 20; hard cap ≤50.

### Duplicates

- `POST /api/sysforge/clients/duplicates`  
  Body: `{ "phone": "...", "email": "...", "name": "...", "exclude_id": null }`  
  Response: `{ "duplicates": [ /* Client */ ] }`
- Server does **not** refuse `POST /clients` when duplicates exist; UI warns only.

### Errors

| Case | Status |
|------|--------|
| Plugin inactive | 404 (existing gate) |
| Validation failed | 400 + `{ "detail": "<desktop-style message>" }` |
| Not found / deleted | 404 |
| Invalid id | 422/400 |

---

## UX contracts

Copy these into QA; fail the workstream if broken.

- [ ] **Matches before Add New** — dropdown order fixed; Add New is last row when query non-empty.
- [ ] **Debounce** — no search fire on every key without delay; rapid typing aborts prior request (no stale overwrite).
- [ ] **Phone parity** — creating `(555) 123-4567` then searching `5551234567` / `555-123-4567` finds the client.
- [ ] **Email case** — `Billing@ACME.com` finds `billing@acme.com`.
- [ ] **Duplicate warn, don’t block** — shared phone shows banner; **Create new client anyway** succeeds; second client with same phone allowed.
- [ ] **Use this client** — selects existing row and clears warning.
- [ ] **Soft-delete** — disappears from search/list; historical invoice FKs remain valid later (no hard delete).
- [ ] **Incomplete create** — Add New with typed name creates incomplete client selectable for invoices (calculator will call same API).
- [ ] **Keyboard path (prep)** — typeahead helper supports Up/Down/Enter selection of matches and Add New (Classic overlay will reuse; implement basics now).

**Not required here:** Classic overlay empty->recent-6, clear-search≠deselect, four-column layout.

---

## Tests / verification

### Automated (`tests/test_sysforge_clients.py`)

Mirror desktop `ClientServiceTests` + `ClientDuplicateDetectionTests`:

1. Create -> get -> update -> soft-delete -> get returns 404; search excludes.
2. Validation: empty client -> 400; bad email -> 400; long first name -> 400.
3. Search by name token via FTS.
4. Search by normalized phone (formatted storage, digit query).
5. Search by email case-insensitive.
6. `FindPotentialDuplicates` merges phone+email; `exclude_id` works.
7. Shared phone returns multiple duplicates (legitimate shared contact).
8. Query parser unit tests: email / phone / name branches.
9. Plugin inactive -> clients routes 404.
10. After soft-delete, FTS search does not return id; after create, search finds within same connection (trigger sync).

### Manual smoke (MASTER §8.3 subset)

1. Install plugin -> open Business -> Clients.
2. Create “Maria Chen” with phone `(555) 123-4567`.
3. Typeahead: `chen`, `5551234567`, email — all hit.
4. Start create with same phone -> warning -> Use existing / Create anyway both work.
5. Soft-delete -> search empty for that client.

### Exit criteria (from gap-manifest / MASTER)

- Clients CRUD + FTS5 typeahead: matches before Add New; debounce + abort.
- Duplicate warnings on create: non-blocking DB-12.
- Calculator workstream can depend on stable search/duplicates APIs without redoing clients.

---

## Risks

| Risk | Mitigation |
|------|------------|
| FTS5 query syntax errors / injection-like operators | Sanitize like `session_search._sanitize_fts_query`; never pass raw user string to `MATCH` |
| Phone not in FTS the way Lucene skipped `phone_norm` | Explicit merge with `find_by_phone` / `phone_norm` column (desktop already merges DB phone hits) |
| Trigger drift on soft-delete | Soft-delete path must delete FTS row; test both UPDATE `IsDeleted=1` and search |
| Associates JSON invalid | Desktop returns null on bad JSON; API should not 500 — store raw, search with best-effort join |
| Dual search stacks (FTS + LIKE fallback) | Prefer FTS always when available; LIKE fallback only if FTS probe fails at startup (should be rare; treat as install failure for P1) |
| Scope creep into Classic / merge | Keep merge and four-column dashboard in their workstreams |
| Calculator lands before clients UI polish | Ship API + `clientSearch.js` first; minimal list UI second |

---

## Effort

**M** (medium)

- Schema/FTS + service + routes: ~1 focused PR
- Minimal UI + typeahead + duplicate banner: ~1 PR
- Tests + README: same or thin follow-up

Larger only if someone insists on PyLucene parity (rejected for web MVP) or folds Classic dashboard into this ticket (do not).

---

## Implementation checklist (ticket-ready)

1. [ ] New migration: `clients_fts` + triggers + soft-delete sync
2. [ ] `normalize_phone` / `parse_client_query` / `validate_client` / `display_name`
3. [ ] `ClientService` CRUD + search + duplicates + `rebuild_clients_fts`
4. [ ] REST routes under `/api/sysforge/clients*`
5. [ ] `clientSearch.js` (debounce, abort, matches-before-Add-New)
6. [ ] Clients list/create/edit panel + soft-delete confirm
7. [ ] Duplicate warning banner (Use / Create anyway)
8. [ ] `tests/test_sysforge_clients.py` green
9. [ ] README documents FTS5 decision and endpoints
)
