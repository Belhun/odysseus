# Parts catalog + placeholder create/merge

| Field | Value |
|-------|-------|
| **Issue id** | `parts-placeholders-merge` |
| **Title** | Parts catalog + placeholder create/merge |
| **Phase** | P1 |
| **Priority** | high |
| **Effort** | **M** |
| **Primary sources** | `Sysforge research/features/parts-catalog.md`, `placeholder-parts-merge.md`; SysForge `PartService.cs`, `PlaceholderMergeViewModel.cs`, `PlaceholderWorkflowTests.cs`; chats `21e672a5`, `8eceb374` (orphan order / BUG-006) |
| **Manifest** | `gap-plans/gap-manifest.json` → `parts-placeholders-merge` |
| **Master plan** | `synthesis/MASTER-MIGRATION-PLAN.md` → Phase 1 (Invoice MVP); feature-gap-matrix §5 |

---

## Goal / success

Ship a SysForge web parts layer where:

1. Users can **list, search, create, update, and delete** catalog parts (SQL `LIKE` search; money in integer cents).
2. Invoice save can **create placeholder parts** for line items with no `PartId`, inside the same DB transaction as the invoice write.
3. Edit-invoice save runs **orphan placeholder cleanup only after** new line items are inserted (desktop BUG-006 order).
4. Users can open a **Placeholder Merge** panel, see name-grouped duplicates, **confirm**, then merge; invoice line `UnitPriceCents` never changes.
5. Calculator typeahead can call a parts search API that prefers real parts and only falls back to placeholders when there is no strong non-placeholder match.

**Done when:**

- `GET/POST/PUT/DELETE /api/sysforge/parts...` round-trips against migrated `Parts` (and optional `SupplierId`).
- Search endpoint matches desktop ranking rules for MVP (`SearchParts` / autocomplete).
- Saving an invoice with a free-text part line creates `IsPlaceholder = 1` and backfills `PartId` on the item.
- Updating an invoice that still references the same placeholders does **not** delete those placeholders mid-save.
- Merge UI: load groups (≥2 placeholders with same normalized name) → confirm → merge → sources gone, target kept, lines reassigned.
- Automated tests port the critical vectors from `PartServiceTests` + `PlaceholderWorkflowTests`.
- Lucene/FTS parts upgrade and dedicated supplier UX remain **out** (tracked as `parts-search-suppliers-depth`).

---

## Current state

### SysForge desktop (source of truth)

| Capability | Status | Anchor |
|------------|--------|--------|
| Parts CRUD + SKU uniqueness | Done | `PartService` (`Add`/`Update`/`Delete`/`Get*`) |
| SQL `LIKE` search | Done | `SearchPartsAsync`, `SearchPartsForAutocompleteAsync` |
| Suppliers schema + FK on parts | Done (no dedicated UI) | `0003_suppliers.sql`, `Part.SupplierId` |
| Money as cents | Done | `0012_money_to_cents.sql` → `BasePriceCents` |
| Placeholder create on save | Done | `CreatePlaceholderPartsFromItemsAsync` inside `InvoiceService.SaveInvoiceAsync` |
| Orphan cleanup after re-insert | Done (BUG-006 fix) | Delete items → create placeholders → insert items → **then** `DeleteOrphanedPlaceholdersAsync` |
| Placeholder merge UI | Done | Sidebar “Placeholder Merge” → `PlaceholderMergeView` / `PlaceholderMergeViewModel` |
| Lucene parts / triage queue | Planned | Defer to P3 workstream |
| Dedicated Parts catalog window | **Absent** | CRUD is service-level; calculator search + merge tool are the main UIs |

**Schema (final shape after money migration):** `Parts` with `BasePriceCents`, `SKU` unique index (NULLs allowed), `IsPlaceholder`, optional `SupplierId` → `Suppliers`. Invoice items may carry `SupplierId` (`0013`) so placeholders inherit supplier when known.

**Merge algorithm (port verbatim):**

1. `GetPlaceholderGroupsAsync`: load `IsPlaceholder = 1`, group by `Name.Trim().ToLowerInvariant()`, drop groups with `< 2` parts.
2. Suggested name = most common name; suggested SKU = first non-empty SKU; most recent price from latest invoice line (else part `BasePriceCents`).
3. `MergePlaceholdersAsync(sourceIds, targetId)` in one transaction:
   - Enrich target: most recent line price → `BasePriceCents`; fill empty SKU / Description / SupplierId from group.
   - `UPDATE InvoiceItems SET PartId = target WHERE PartId IN sources` (**do not** touch `UnitPriceCents`).
   - `DELETE` source parts.
4. UI today: target = `SelectedGroup.Parts[0]`, sources = rest. Desktop has **no confirm dialog**; MASTER / research require **confirm on web** because merge is irreversible.

**SKU conflicts:** `NormalizeSku` (trim; empty → `NULL`). Conflict throws `SkuConflictException` with conflicting part; save rolls back. Critiques floated a name-choice dialog; **shipped code is exception-based** — web should map to HTTP 409 + structured body for P1 (dialog polish can follow).

### Odysseus web (target today)

- Plugin routes: `GET /api/sysforge/status` only (`integrations/sysforge/routes.py`).
- UI: status stub modal (`integrations/sysforge/static/js/index.js`); no parts panel, no merge panel.
- Install: empty `sysforge.db` touch; **no** `Parts` / `Suppliers` schema until `schema-money-utc-foundation` lands.
- Tests: plugin install/catalog only (`tests/test_sysforge_plugin.py`); no domain part/placeholder tests.

### Gap

Web has zero parts surface. Invoice calculator cannot resolve or create catalog rows. Placeholder merge (desktop cleanup path) does not exist. This workstream fills the parts domain so `invoice-calculator-save-contracts` can call into it.

---

## Scope

### In scope

- Consume migrated `Suppliers` + `Parts` (+ invoice-item `SupplierId` column) from P0 foundation; do not invent a parallel schema.
- Python port of `PartService` behaviors (CRUD, search, placeholders, groups, merge, convert, orphan delete, usage count).
- REST API under `/api/sysforge/parts` and `/api/sysforge/placeholders/...`.
- **Parts catalog UI** (list + search + create/edit form) — web needs this even though desktop has no dedicated catalog window; dashboard “Parts” card opens it.
- **Placeholder Merge UI** with irreversible confirm, refresh, delete-unused-placeholder (usage count = 0 only).
- Service methods callable from invoice save (same connection/transaction), including the **post-insert orphan cleanup** contract.
- `ConvertPlaceholderToFullPart` endpoint + “promote” action from catalog/merge (enrich fields, clear `IsPlaceholder`).
- Minimal supplier id pass-through on part create/update (no supplier management screens).
- Tests ported from C# vectors; pytest against file-backed SQLite.

### Out of scope

- Lucene / FTS5 parts search upgrade → `parts-search-suppliers-depth` (P3).
- Dedicated suppliers CRUD UI, preferred-supplier UX, price history, placeholder triage queue.
- Full invoice calculator UI / save orchestration UX (owns wiring; this workstream only supplies APIs + hooks).
- Client merge tool, PDF, payments.
- Changing desktop C# or editing applied SysForge migration files.
- Auto-merge on SKU conflict during save (keep fail-closed 409 for P1).

---

## Dependencies

| Depends on | Why |
|------------|-----|
| `schema-money-utc-foundation` | `Parts` / `Suppliers` / cents / UTC / checksummed migrations; async DB access pattern |
| `business-shell-dashboard-router` | Dashboard Parts card + inner route for catalog + merge panels |

| Soft / parallel | Why |
|-----------------|-----|
| `clients-crud-fts-duplicates` | Not required for parts alone; needed before end-to-end invoice save QA |
| `drafts-service-autosave` | Calculator autosave is separate; parts APIs stay independent |

**Blocks:** `invoice-calculator-save-contracts` (manifest `depends_on` includes this id). Calculator save must call placeholder create + orphan cleanup in the documented order.

---

## Concrete steps

### 1. Freeze domain contracts from desktop SQL

Copy query semantics (not ORM fluff) from `PartService.cs`:

| Operation | Rules |
|-----------|--------|
| Normalize SKU | Trim; whitespace-only → `NULL` |
| Unique SKU | App check + DB unique index; exclude self on update |
| Validate part | Name required (no length cap); `BasePriceCents >= 0`; `SupplierId` if set must be valid id |
| `SearchParts` | Non-placeholder `LIKE` on Name/SKU/Description first (SKU rank 1, Name 2); if empty and `include_placeholders=true`, search placeholders |
| Autocomplete | Name `LIKE` or exact SKU; order exact name → starts-with → SKU → else; `limit` default 10 |
| Create placeholder | `ItemType == Part` AND `PartId is null` AND non-empty `PartName`; set `IsPlaceholder=1`, `BasePriceCents` from line, `SupplierId` from line, backfill `item.PartId` |
| Orphan delete | Placeholders with zero `InvoiceItems.PartId` refs; **only after** new items inserted |
| Merge | See algorithm above; preserve line prices |

Document the save-order contract for the invoice workstream:

```text
UPDATE invoice header (or INSERT)
DELETE FROM InvoiceItems WHERE InvoiceId = ?
CreatePlaceholderPartsFromItems(items, tx)   # backfills PartId
INSERT InvoiceItems ...
DeleteOrphanedPlaceholders(tx)               # AFTER inserts
COMMIT
```

Never delete orphans between `DELETE` items and `INSERT` items.

### 2. Implement `parts` service module

Suggested layout under the plugin:

- `integrations/sysforge/services/parts.py` — all SQL
- `integrations/sysforge/services/sku.py` — normalize + conflict error type
- Reuse money/UTC helpers from foundation (`cents` integers in API bodies)

Keep methods that accept an open connection + transaction for invoice save reuse.

### 3. Expose REST API

Mount on the gated `/api/sysforge` router (404 when plugin inactive).

Wire OpenAPI-ish request models: cents fields as `int`, ISO UTC timestamps as strings, `is_placeholder` as bool.

### 4. Parts catalog UI

Route: `#sysforge/parts` (or `parts-catalog`).

- Table/list: Name, SKU, price (format from cents), placeholder badge, usage count optional.
- Search box → `GET /parts/search?q=` with debounce (~200–300ms) + AbortController.
- Add / Edit form: name, SKU, base price, description, tags/devices as plain text or JSON strings matching desktop storage, warranty checkbox, optional supplier id.
- Delete: confirm; if FK nulls line `PartId`, surface toast (“removed from catalog; invoice lines unlinked”) — match desktop delete behavior.
- Entry: dashboard **Parts** card → this route.

### 5. Placeholder Merge UI

Route: `#sysforge/placeholder-merge` (sidebar/nav twin of desktop Order=3 item).

- On activate: `GET /placeholders/groups` (auto-load like desktop `CurrentView` hook).
- List groups: suggested name, suggested SKU, most recent price, invoice count, member parts + per-part usage.
- Select group → **Merge** → confirm dialog: “Merge N placeholders into «name»? This cannot be undone.” → `POST /placeholders/merge`.
- Delete unused member: refuse when usage > 0 (toast); else `DELETE /parts/{id}`.
- Busy flag disables Merge/Refresh/Delete while in flight (mirror `IsLoading` / `CanWork`).

### 6. Hooks for invoice save (no full calculator here)

Export Python helpers:

- `create_placeholder_parts_from_items(conn, items)`
- `delete_orphaned_placeholders(conn)`

Invoice workstream imports these; do **not** duplicate SQL. Add a thin internal-only test that runs the four-step order against a fake invoice to prove the contract before calculator UI exists.

### 7. Convert / promote placeholders

From catalog row or merge panel: edit fields → `POST /parts/{id}/convert` sets `is_placeholder=false` after SKU uniqueness check. Use for “this placeholder is now a real catalog part” without merging duplicates.

### 8. Dashboard / shell wiring

- Parts card → catalog route.
- Optional second card or sidebar link → Placeholder Merge (desktop exposes merge in sidebar, not only dashboard).
- Respect panel lifecycle from `nav-lifecycle-view-edit-routes` when that lands; until then, simple show/hide is OK if handlers are not double-bound.

---

## Files

| Path | Action |
|------|--------|
| `integrations/sysforge/services/parts.py` | **Create** — CRUD, search, placeholders, groups, merge, convert, orphans |
| `integrations/sysforge/services/sku.py` | **Create** — normalize + `SkuConflictError` |
| `integrations/sysforge/routes.py` | **Update** — register parts/placeholder routes |
| `integrations/sysforge/static/js/views/parts-catalog.js` | **Create** — list/search/form |
| `integrations/sysforge/static/js/views/placeholder-merge.js` | **Create** — groups, confirm merge, delete unused |
| `integrations/sysforge/static/js/index.js` (or router) | **Update** — mount routes / cards |
| `integrations/sysforge/manifest.json` | Ensure new static assets are packaged |
| `tests/test_sysforge_parts.py` | **Create** — CRUD, search, SKU conflict |
| `tests/test_sysforge_placeholders.py` | **Create** — create, orphan order, merge, usage delete |
| `Sysforge research/features/parts-catalog.md` | Optional status note after ship (not required for close) |

**Desktop references (read-only):**

- `SysForge/Database/PartService.cs` — full behavior
- `SysForge/Database/SkuConflictException.cs`
- `SysForge/Helpers/PartValidationHelpers.cs`
- `SysForge/Models/Part.cs`, `PlaceholderGroup.cs`, `PartSearchResult.cs`
- `SysForge/ViewModels/PlaceholderMergeViewModel.cs`, `Views/PlaceholderMergeView.axaml`
- `SysForge/Database/InvoiceService.cs` — save order (~170–221)
- `SysForge/Database/Migrations/0003_suppliers.sql`, `0004_parts.sql`, `0012_money_to_cents.sql`, `0013_invoice_items_supplier.sql`
- `SysForge.Tests/Database/PartServiceTests.cs`, `PlaceholderWorkflowTests.cs`

---

## API / UI contracts

### REST

| Method | Path | Body / query | Response / errors |
|--------|------|--------------|-------------------|
| `GET` | `/api/sysforge/parts` | optional `?placeholders=0\|1\|all` | `{ items: Part[] }` |
| `GET` | `/api/sysforge/parts/{id}` | — | `Part` or 404 |
| `GET` | `/api/sysforge/parts/search` | `q`, `include_placeholders` (default true), `mode=full\|autocomplete`, `limit` | `{ items: Part[] }` |
| `POST` | `/api/sysforge/parts` | Part fields (cents) | `{ id }` or **409** sku conflict |
| `PUT` | `/api/sysforge/parts/{id}` | Part fields | 204 / 404 / **409** |
| `DELETE` | `/api/sysforge/parts/{id}` | — | 204 / 404 |
| `POST` | `/api/sysforge/parts/{id}/convert` | Updated part fields | 204 / 404 / **409** |
| `GET` | `/api/sysforge/placeholders` | — | `{ items: Part[] }` placeholders only |
| `GET` | `/api/sysforge/placeholders/groups` | — | `{ groups: PlaceholderGroup[] }` |
| `POST` | `/api/sysforge/placeholders/merge` | `{ target_part_id, source_part_ids: int[] }` | `{ merged: n }` / 400 if `<1` source / 404 target |
| `GET` | `/api/sysforge/parts/{id}/usage` | — | `{ count: int }` |

**Part JSON (indicative):**

```json
{
  "id": 12,
  "name": "iPhone 14 screen",
  "base_price_cents": 8900,
  "description": null,
  "sku": "IP14-SCR",
  "compatible_devices": "[\"iPhone 14\"]",
  "tags": null,
  "has_warranty": false,
  "supplier_id": null,
  "date_added": "2026-07-17T20:00:00+00:00",
  "last_updated": "2026-07-17T20:00:00+00:00",
  "is_placeholder": false
}
```

**409 Sku conflict body:**

```json
{
  "detail": "SKU already exists",
  "code": "sku_conflict",
  "sku": "IP14-SCR",
  "conflicting_part": { "id": 3, "name": "…", "is_placeholder": false }
}
```

**PlaceholderGroup JSON:** `parts`, `part_usage_counts` (map id→count), `suggested_name`, `suggested_sku`, `most_recent_price_cents`, `invoice_count`.

### Invoice-save hook (Python, not a public route)

```python
# Called inside invoice transaction — same connection
created = parts_service.create_placeholders_from_items(conn, items)
# ... insert invoice items ...
orphans = parts_service.delete_orphaned_placeholders(conn)
```

### UI entry points

| Surface | Opens |
|---------|--------|
| Dashboard Parts card | Parts catalog |
| Nav / secondary link | Placeholder Merge |
| Calculator (later) | `GET .../parts/search?mode=autocomplete` |

---

## UX contracts

| Action | User-visible result |
|--------|---------------------|
| Search catalog | Results update as you type; empty query clears or shows none (match desktop: blank query → empty list for search APIs) |
| Create part | Persists; duplicate SKU → inline error naming the conflicting part (no silent overwrite) |
| Placeholder badge | Clear visual on list rows where `is_placeholder` |
| Merge without confirm | **Blocked** — confirm dialog required (web stronger than current desktop VM) |
| Merge confirm OK | Toast success; group list refreshes; sources disappear; invoice history prices unchanged |
| Delete placeholder in use | Warning toast with usage count; no delete |
| Delete unused placeholder | Removed; list refreshes |
| Long part names | Do not truncate in forms (UX-03); allow wrap/stretch |

**Copy for merge confirm:** state irreversibility and count of sources being removed.

---

## Tests / verification

### Automated (port these C# intents)

From `PartServiceTests`:

1. Add part → cents persisted (`120.00` → `12000`).
2. Update name/price → reload matches.
3. Delete unused → row gone.
4. Delete referenced → part gone; line `PartId` null (FK / app behavior).
5. `usage` count matches invoice refs.
6. `GetPlaceholderParts` returns only placeholders.

From `PlaceholderWorkflowTests`:

1. Save path with missing `PartId` → placeholder created, item linked, SKU/name/cents set.
2. **Edit update does not delete still-referenced placeholders** (orphan order regression).
3. SKU conflict on placeholder create → `SkuConflict` / 409; **no** invoice row; **no** placeholder row (atomicity).
4. Merge: two placeholders same name → one remains; both lines point at target; `UnitPriceCents` unchanged on lines.
5. Grouping: single placeholder → not listed; two “Screen” + one “Battery” → one group of two.

Add web-only:

6. Merge API rejects empty `source_part_ids`.
7. Search: real part match suppresses placeholders; no real match returns placeholders when flag true.
8. Plugin inactive → all routes 404.

Use file-backed SQLite (not `:memory:`) so transaction visibility matches desktop tests.

### Manual QA

1. Install plugin → open Business → Parts card → create `OLED Panel` / SKU `OLED-100` / price.
2. Search `OLED` → find it; mark a second create with same SKU → conflict message.
3. (With calculator stub or SQL fixture) insert invoice line without `part_id` → save → placeholder appears in catalog with badge.
4. Create two placeholders named `Digitizer` on different invoices → Merge panel shows one group → confirm merge → one part left; both invoices still show original line prices.
5. Try delete merged target while still used → blocked; delete a true orphan → succeeds.
6. Refresh merge panel → empty or reduced groups.

### Regression anchors

- MASTER §4 / chats `21e672a5`, `8eceb374`: placeholder orphan cleanup **after** re-insert.
- MASTER Phase 1 checklist: “Placeholder line → merge into catalog part”; “Edit existing invoice: placeholders survive update”.
- Research: merge irreversible + confirm; Lucene deferred.

---

## Risks

| Risk | Mitigation |
|------|------------|
| Invoice workstream reimplements placeholder SQL and gets orphan order wrong | Single shared service; document order in this plan; shared test |
| Unique SKU index vs multiple `NULL` SKUs | SQLite allows multiple NULLs; keep normalize-to-NULL; never store `""` |
| Desktop merge lacks confirm; users expect undo | Web confirm mandatory; no undo API in P1 |
| `SkuConflictException` vs rejected “name choice dialog” critique | Ship 409 for P1; note dialog as optional follow-up under search-depth workstream |
| Empty `Placeholder-Parts-Workflow-Plan.md` on desktop | Treat **code + tests** as spec; do not invent triage queue UX |
| Catalog UI scope creep (suppliers, price history) | Stick to CRUD + badge + convert; defer rest |
| Deleting parts nulls invoice FKs unexpectedly | Confirm dialog + toast; usage endpoint before delete in UI |
| Money displayed as floats | API and DB stay cents; format only in UI |

---

## Effort

**M** (medium)

| Slice | Estimate |
|-------|----------|
| Parts service + REST + SKU/money wiring | ~1.5–2.5 days |
| Catalog UI (list/search/form) | ~1–1.5 days |
| Placeholder merge UI + confirm | ~1 day |
| Invoice-hook helpers + orphan-order tests | ~0.5–1 day |
| Port C# test vectors to pytest | ~1 day |

**Total ~5–7 days** for one engineer familiar with the plugin. Calculator UI integration time belongs to `invoice-calculator-save-contracts`, not this estimate.

---

## Implementation checklist

- [ ] Parts service: CRUD, normalize SKU, uniqueness, validation
- [ ] Search + autocomplete endpoints matching desktop ranking
- [ ] Placeholder create + orphan delete (transaction-aware)
- [ ] Groups + merge (preserve `UnitPriceCents`)
- [ ] Convert placeholder → full part
- [ ] REST routes gated by plugin active
- [ ] Parts catalog UI + dashboard card
- [ ] Placeholder Merge UI + irreversible confirm
- [ ] Pytest: CRUD, conflict atomicity, orphan order, merge price preservation
- [ ] Manual QA walkthrough above
- [ ] Hand off hook signatures to invoice calculator workstream

---

## Source notes

- **gap-manifest:** P1 high; depends on schema + shell; summary says port API/UI + create on save + merge with confirm; Lucene/supplier detail later.
- **MASTER Phase 1:** “Parts + placeholder create/merge | Line items resolve; merge irreversible confirm.”
- **feature-gap-matrix §5:** CRUD, SQL LIKE, placeholder create, merge UI all **Missing** on Odysseus; Lucene Planned both sides.
- **parts-catalog.md:** Port SQL verbatim; REST search for typeahead; Lucene optional later; watch `IsPlaceholder` + SKU UX.
- **placeholder-parts-merge.md:** Dedicated route + panel; port merge transaction + tests; creation stays in calculator API; empty workflow plan → code/tests only.
- **Chats `21e672a5` / `8eceb374`:** Orphan cleanup order is a hard contract for edit-save.
)
