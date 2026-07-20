# Parts FTS, suppliers UX, price history, triage

| Field | Value |
|-------|-------|
| **Issue id** | `parts-search-suppliers-depth` |
| **Title** | Parts FTS, suppliers UX, price history, triage |
| **Phase** | P3 |
| **Priority** | low (manifest); high ease-of-use once P1 parts MVP ships |
| **Effort** | **L** |
| **Primary sources** | `Plans/Product-Vision/Invoice-Roadmap.md` v2; `Plans/README.md` (Lucene parts Not started); `docs/research/sysforge/features/parts-catalog.md`, `suppliers.md`, `placeholder-parts-merge.md`, `client-search-lucene.md`; desktop `PartService.SearchPartsAsync` / merge |
| **Manifest** | `gap-plans/gap-manifest.json` → `parts-search-suppliers-depth` |
| **Master plan** | `synthesis/MASTER-MIGRATION-PLAN.md` → Phase 6+ Depth (P3) |
| **Roadmap** | `synthesis/future-plans-roadmap.md` → §3 Phase 6, §4.1 Lucene parts / triage / price history / supplier UX |
| **Gap matrix** | `synthesis/feature-gap-matrix.md` → §5 Lucene parts search (P3) |

---

## Goal / success

After P1 parts + placeholder merge exists, deepen the catalog loop so parts entry feels as fast as client FTS entry, and so suppliers / prices / placeholders stop being “schema only.”

Ship four related capabilities on the Odysseus SysForge plugin:

1. **Parts full-text search (FTS5)** — replace or sit under SQL `LIKE` for catalog + calculator typeahead; match Invoice-Roadmap search intent (SKU-first for numeric queries; placeholders only when no strong catalog hit).
2. **Supplier UX** — autocomplete, preferred supplier on parts, supplier detail with linked parts (schema fields from Invoice-Roadmap v2).
3. **Price history + Update Prices preview** — append-only history; calculator “Update Prices” offers BasePrice or a history entry with a delta preview before apply; never rewrite `InvoiceItems.UnitPriceCents` on merge.
4. **Placeholder triage queue** — dedicated queue beyond merge: convert one placeholder into a full part (fields, SKU, supplier, tags) with SKU-conflict handling.

**Done when:**

- Calculator / Parts views typeahead use FTS (or documented FTS-backed API) with debounce + abort; ranking matches the contracts below.
- Preferred supplier can be set on a part; supplier autocomplete works on part edit and triage convert.
- `GET` price history returns recent entries; Update Prices shows old → new cents and requires confirm before write.
- Placeholder Queue lists open placeholders; convert clears `IsPlaceholder` without deleting invoice line history prices.
- Post-import / restore rebuilds **parts** FTS the same way clients FTS is rebuilt (BUG-018 class for parts).
- Automated tests cover FTS ranking, preferred supplier FK, history append, update preview gate, triage convert + SKU conflict, merge “never touch UnitPriceCents.”

**Exit criterion (roadmap):** “Parts entry as fast as client entry.”

---

## Current state

### SysForge desktop (source of truth)

| Capability | Status | Evidence |
|------------|--------|----------|
| Parts CRUD + SQL `LIKE` search | **Done** | `PartService.SearchPartsAsync`, `SearchPartsForAutocompleteAsync` |
| Lucene / FTS parts search | **Not started** | `Plans/README.md`; research `parts-catalog.md` |
| Suppliers table | **Schema Done** | `0003_suppliers.sql`; `Models/Supplier.cs` (Name, ContactInfo JSON, ShippingInfo JSON, Notes, DateAdded) |
| Dedicated supplier UI / preferred | **Planned (v2)** | Invoice-Roadmap v2; research `suppliers.md` = embed in parts for MVP |
| Placeholder create + merge UI | **Done** | `PlaceholderMergeViewModel`; `MergePlaceholdersAsync` |
| Placeholder triage queue | **Planned** | Invoice-Roadmap v2; `Placeholder-Parts-Workflow-Plan.md` empty stub |
| Price history table / Update Prices from history | **Planned (v2)** | Invoice-Roadmap v2; not in code |
| Preserve line `UnitPriceCents` on merge | **Done** | `MergePlaceholdersAsync` reassigns `PartId` only |

**Desktop search behavior today** (`PartService.SearchPartsAsync`):

1. Empty query → `[]`.
2. `LIKE %query%` on Name / SKU / Description where `IsPlaceholder = 0`, ordered SKU match → Name match → else, then Name.
3. If zero catalog hits and `includePlaceholdersWhenNoStrongMatch` → same `LIKE` on placeholders.
4. Autocomplete variant: Name `LIKE` or exact SKU; rank exact Name → starts-with Name → exact SKU; `LIMIT` (default 10).

**Invoice-Roadmap intended parts search (not built):**

- Numbers/dashes → SKU first → Name → Description → Tags/CompatibleDevices.
- Text → Name → Description → Tags/Devices.
- Include placeholders only when no strong non-placeholder match.
- v2: fuzzy Names, synonyms, boost preferred suppliers; incremental index + rebuild tool.

**Invoice-Roadmap v2 schema additions (not migrated on desktop yet):**

- Suppliers: `Website`, `PrimaryPhone`, `PrimaryEmail`, `DefaultShippingRate`, `Rating`, `IsPreferred`.
- Parts: `PreferredSupplierId` FK nullable; `PartPriceHistory(Id, PartId, Price, Source, EffectiveAt)` **or** PriceHistory JSON.
- DAL: `AddPartPriceHistory`, `GetPartPriceHistory`, `SetPreferredSupplier`; Suppliers `GetSupplierById`, `GetPartsBySupplier`, `SearchSuppliers`.

**Price / merge invariants already shipped:**

- Merge never changes `InvoiceItems.UnitPriceCents` (true “invoice price history”).
- Catalog `BasePriceCents` may be updated from recent line prices during merge; that is **catalog** price, not line rewrite.
- v1 Update Prices: refresh line `UnitPrice` from parts DB only when invoice not invoiced/finalized (desktop calculator / edit surfaces).

### Odysseus web (target today)

- Plugin stub only: `integrations/sysforge` status modal; **no** parts API, FTS, suppliers, price history, or triage UI.
- Research recommends **SQLite FTS5** for client search MVP (`client-search-lucene.md`); same choice applies to parts (avoid PyLucene).
- P1 workstream `parts-placeholders-merge` owns SQL `LIKE` search + merge; this P3 workstream **upgrades** that surface.

### Gap

Desktop still plans Lucene parts; Odysseus should not wait for Lucene.NET. Port the **behavioral** Invoice-Roadmap v2 depth on top of P1 parts using FTS5 + new migrations + REST/UI. Treat empty `Placeholder-Parts-Workflow-Plan.md` as a risk: behavior for triage must be specified here and locked with tests.

---

## Scope

### In scope

1. **Migration(s)** (append-only, after P1 parts schema is present):
   - `Parts_fts` FTS5 virtual table + triggers (or content-sync equivalent) on Name, SKU, Description, Tags, CompatibleDevices.
   - Supplier enrichment columns from Invoice-Roadmap v2 (subset OK if phased; prefer full column set in one migration).
   - `Parts.PreferredSupplierId` FK → `Suppliers(Id)` ON DELETE SET NULL.
   - `PartPriceHistory` table (prefer normalized table over JSON for query/preview).
2. **Parts search service upgrade** — FTS query API preserving placeholder gate + SKU-first ranking for digit/dash queries; fallback `LIKE` only if FTS unavailable (document; prefer fail closed with rebuild).
3. **Supplier APIs + UI** — list/search/autocomplete; part field + preferred flag; supplier detail panel (contacts, notes, related parts). No purchase-order / inventory light.
4. **Price history APIs + Update Prices UX** — append on catalog BasePrice change and optional “record from invoice line”; preview deltas; apply only to eligible invoices (not finalized / not Invoiced per v1 gate).
5. **Placeholder triage queue UI** — list placeholders (usage counts); convert-to-full form (reuse `ConvertPlaceholderToFullPart` semantics); link supplier; SKU conflict dialog. Merge UI remains available (P1); triage does not replace merge.
6. **Reindex hooks** — rebuild parts FTS on part CRUD, placeholder convert/merge, backup restore, bulk import (mirror clients BUG-018).
7. **Tests** — see Tests section.

### Out of scope

- Inventory light (`PartStock`, reservations) — Phase 8 / Projects P6 / separate backlog.
- Client merge tool, invoice-level discount, LockedFields — other deferred items.
- Lucene.NET / PyLucene on web.
- Fuzzy synonyms / analyzer tuning beyond FTS5 tokenizers + simple prefix queries (can follow up).
- PDF/email/payments (v3+).
- Changing merge’s “never touch UnitPriceCents” contract.
- Rewriting P1 placeholder **create-on-save** rules.
- Dedicated multi-window Avalonia Supplier window chrome; web = panel/route inside Business shell.

### Phasing inside this workstream (recommended ship order)

| Slice | Deliverable | Can ship alone? |
|-------|-------------|-----------------|
| A | FTS5 + search API swap + reindex | Yes (largest UX win) |
| B | Supplier columns + autocomplete + preferred + detail | Yes |
| C | `PartPriceHistory` + Update Prices preview | After calculator Update Prices exists |
| D | Placeholder triage queue | After P1 merge + convert API |

Do A first. B/C/D can parallelize after A if staffing allows; D depends on convert API from P1.

---

## Dependencies

| Depends on | Why |
|------------|-----|
| `parts-placeholders-merge` (P1) | Parts table, `LIKE` search baseline, placeholder create/merge, SKU conflict |
| `invoice-calculator-save-contracts` (P1) | Typeahead consumer; Update Prices button surface; money in cents |
| `schema-money-utc-foundation` (P0) | Append-only migrations, cents, UTC helpers |
| `business-shell-dashboard-router` (P0) | Parts / triage / supplier routes inside Business panel |
| Clients FTS pattern (from `clients-crud-fts-duplicates`) | Copy FTS5 + rebuild conventions; shared diagnostics messaging |

| Soft / parallel | Why |
|-----------------|-----|
| `backup-restore-post-import-reindex` | Must call parts FTS rebuild on restore/import once both land |
| `nav-lifecycle-view-edit-routes` | Panel activate/deactivate for Parts / Triage / Supplier detail |
| `diagnostics-readonly-panel` | Show parts FTS row count ≠ list count mismatch |

**Blocks:** Fast catalog entry parity; v2 supplier/price workflows; clearing placeholder backlog without only using merge.

---

## Concrete steps

### 1. Freeze search ranking contract

Document and test these rules (port Invoice-Roadmap + current desktop gate):

| Input | Behavior |
|-------|----------|
| Empty / whitespace | `[]` |
| Query matches catalog (`IsPlaceholder=0`) | Return catalog hits only |
| No catalog hits + `include_placeholders=true` (default) | Return placeholder hits |
| Query looks numeric / SKU-like (`^[0-9A-Za-z][0-9A-Za-z\-_/]*$` or contains digit) | Boost SKU matches above Name |
| Text-heavy query | Name → Description → Tags/CompatibleDevices |
| Autocomplete | Cap `limit` (default 10); debounce 150–250ms; AbortController on new keystroke |

Web default engine: **FTS5**. Do not claim “Lucene parity” in UI copy; say “Full-text parts search.”

### 2. Add append-only migration(s)

Propose next free migration id after P1 parts migrations (example names; renumber to fit runner):

**`00xx_parts_fts.sql`**

```sql
-- Parts_fts content=Parts or external content table
CREATE VIRTUAL TABLE IF NOT EXISTS Parts_fts USING fts5(
  Name, SKU, Description, Tags, CompatibleDevices,
  content='Parts', content_rowid='Id'
);
-- AFTER INSERT/UPDATE/DELETE triggers to sync Parts_fts
-- Rebuild helper: INSERT INTO Parts_fts(Parts_fts) VALUES('rebuild');
```

**`00xx_suppliers_v2.sql`**

- `ALTER TABLE Suppliers ADD COLUMN Website TEXT;`
- `PrimaryPhone`, `PrimaryEmail`, `DefaultShippingRate` (integer cents or bps — match money helper; prefer cents), `Rating` INTEGER, `IsPreferred` INTEGER NOT NULL DEFAULT 0.
- Keep unique `Name`.

**`00xx_parts_preferred_and_price_history.sql`**

```sql
ALTER TABLE Parts ADD COLUMN PreferredSupplierId INTEGER
  REFERENCES Suppliers(Id) ON DELETE SET NULL;
-- SQLite: FK may be app-enforced if ALTER limits apply; mirror 0013 pattern.

CREATE TABLE IF NOT EXISTS PartPriceHistory (
  Id INTEGER PRIMARY KEY,
  PartId INTEGER NOT NULL REFERENCES Parts(Id) ON DELETE CASCADE,
  PriceCents INTEGER NOT NULL,
  Source TEXT NOT NULL,           -- 'manual' | 'catalog_edit' | 'invoice_line' | 'merge'
  EffectiveAt TEXT NOT NULL,      -- UTC ISO
  Note TEXT
);
CREATE INDEX IF NOT EXISTS ix_PartPriceHistory_PartId_EffectiveAt
  ON PartPriceHistory(PartId, EffectiveAt DESC);
```

Never edit applied migrations; checksum policy from P0.

### 3. Upgrade parts search service

- Replace `LIKE`-only implementation behind `GET /api/sysforge/parts/search`.
- Keep query params: `q`, `limit`, `include_placeholders` (bool, default true).
- Map FTS `MATCH` with column weights if available (`SKU`, `Name`, …); else post-sort in Python using same CASE order as desktop.
- On write paths (`POST/PATCH/DELETE` parts, convert, merge): sync FTS (triggers preferred) + assert row visible in search within same request in tests.
- Expose `POST /api/sysforge/parts/search/rebuild` (admin/diagnostics) for BUG-018-class recovery.

### 4. Supplier service + autocomplete

- CRUD minimal: create/update/list/get; soft uniqueness on Name (409 on conflict).
- `GET /api/sysforge/suppliers/search?q=&limit=` for autocomplete (Name prefix / FTS optional; `LIKE` OK at small N).
- `PATCH /api/sysforge/parts/{id}` accepts `supplier_id` and `preferred_supplier_id` (may equal; preferred is the “default buy from” hint).
- `GET /api/sysforge/suppliers/{id}/parts` for detail panel.
- UI: part editor supplier typeahead; star/preferred toggle; route `#sysforge/suppliers/:id`.

### 5. Price history + Update Prices preview

**Write rules**

- On catalog `BasePriceCents` change via part edit → append history (`Source=catalog_edit`).
- Optional: when saving invoice lines, offer “record line price to history” (can be slice C follow-up); at minimum support explicit `POST .../price-history`.
- Merge may update catalog BasePrice from recent lines (desktop today) → append history (`Source=merge`) **without** changing line UnitPriceCents.

**Update Prices flow (calculator)**

1. User clicks Update Prices (disabled if finalized or Status=Invoiced — match v1).
2. API returns proposed rows: `{ item_id, part_id, current_unit_cents, proposed_cents, source: 'base'|'history', history_id? }`.
3. UI shows table with deltas (`+120` / `-50` cents formatted as currency).
4. User confirms → `POST` apply; recalculate line totals + invoice totals.
5. Choosing a history entry sets proposed from that `PriceCents`, not silent BasePrice overwrite.

### 6. Placeholder triage queue

Beyond P1 merge (many placeholders → one catalog part):

| Action | Behavior |
|--------|----------|
| Open Queue | List `IsPlaceholder=1` with invoice usage count, name, rough price, supplier if any |
| Convert | Form: Name, SKU, BasePriceCents, Description, Tags, Supplier/Preferred; calls convert API; clears placeholder flag |
| SKU conflict | Return 409 with conflicting part id/name; UI: “Use existing” (merge into that part) or change SKU |
| Jump to merge | Link/button into existing merge UI for duplicate groups |

Route: `#sysforge/parts/triage` (or `placeholders`).

Do **not** auto-delete placeholders without confirm. Convert is reversible only via careful re-flag (prefer irreversible convert + merge for cleanup — document).

### 7. Wire reindex on bulk paths

Any path that bulk-loads parts (restore ZIP, SQL import, seed) must:

1. Write rows.
2. `rebuild` parts FTS.
3. Only then claim search works in UI/diagnostics.

Diagnostics: “Parts in table: N; FTS rows: M” with rebuild button.

### 8. Update research / plan stubs (docs only)

After implementation (or as tickets land):

- Fill behavior notes into research cards or a short `docs/plans/parts-fts-suppliers.md` if the team wants a living note.
- Do **not** pretend desktop Lucene parts is Done; keep Plans README honest for Avalonia.

---

## Files

| Path | Action |
|------|--------|
| `integrations/sysforge` migrations folder (or shared `src/plugins/sysforge/db/migrations/`) | **Create** `00xx_parts_fts.sql`, `00xx_suppliers_v2.sql`, `00xx_parts_preferred_and_price_history.sql` |
| `integrations/sysforge/routes.py` or `routes/sysforge_parts.py` | **Create/Update** — parts search, suppliers, price history, triage, rebuild |
| `integrations/sysforge/` services: `parts_search.py`, `suppliers.py`, `price_history.py` | **Create** |
| `integrations/sysforge/static/js/views/parts.js` | **Update** — FTS typeahead; preferred supplier field |
| `integrations/sysforge/static/js/views/parts-triage.js` | **Create** — queue + convert form |
| `integrations/sysforge/static/js/views/supplier-detail.js` | **Create** |
| `integrations/sysforge/static/js/views/invoice-calculator.js` | **Update** — Update Prices preview modal |
| `integrations/sysforge/static/js/router.js` | **Update** — routes `parts`, `parts/triage`, `suppliers/:id` |
| `tests/test_sysforge_parts_fts.py` | **Create** |
| `tests/test_sysforge_suppliers.py` | **Create** |
| `tests/test_sysforge_price_history.py` | **Create** |
| `tests/test_sysforge_parts_triage.py` | **Create** |
| Backup/restore module | **Update** — call parts FTS rebuild |
| `docs/research/sysforge/features/parts-catalog.md` | Optional post-ship note: FTS5 done on web |
| `docs/research/sysforge/features/suppliers.md` | Optional post-ship note: v2 UX |

**Desktop references (read-only):**

- `SysForge/Database/PartService.cs` — `SearchPartsAsync`, autocomplete, `GetPlaceholderPartsAsync`, `ConvertPlaceholderToFullPartAsync`, `MergePlaceholdersAsync`
- `SysForge/Database/Migrations/0003_suppliers.sql`, `0004_parts.sql`, `0012_money_to_cents.sql`, `0013_invoice_items_supplier.sql`
- `SysForge/Models/Supplier.cs`, `Part.cs`
- `SysForge/ViewModels/PlaceholderMergeViewModel.cs`
- `SysForge/Plans/Product-Vision/Invoice-Roadmap.md` §v2
- `SysForge/Plans/README.md` — Lucene parts Not started
- `docs/research/sysforge/features/client-search-lucene.md` — FTS5 recommendation

---

## API / UI contracts

### REST

| Method | Path | Contract |
|--------|------|----------|
| `GET` | `/api/sysforge/parts/search?q=&limit=10&include_placeholders=true` | Ranked hits; empty q → `[]`; money fields in integer cents |
| `POST` | `/api/sysforge/parts/search/rebuild` | Full FTS rebuild; returns `{ parts_count, fts_count }` |
| `GET` | `/api/sysforge/suppliers?q=` | List / filter |
| `GET` | `/api/sysforge/suppliers/search?q=&limit=` | Autocomplete |
| `GET` | `/api/sysforge/suppliers/{id}` | Detail + optional embedded summary |
| `GET` | `/api/sysforge/suppliers/{id}/parts` | Related parts |
| `POST` | `/api/sysforge/suppliers` | Create; 409 on duplicate Name |
| `PATCH` | `/api/sysforge/suppliers/{id}` | Update v2 fields + `is_preferred` |
| `PATCH` | `/api/sysforge/parts/{id}` | Includes `supplier_id`, `preferred_supplier_id`; BasePrice change appends history |
| `GET` | `/api/sysforge/parts/{id}/price-history` | Newest first |
| `POST` | `/api/sysforge/parts/{id}/price-history` | `{ price_cents, source, note? }` |
| `POST` | `/api/sysforge/invoices/{id}/update-prices/preview` | Proposed deltas; 400 if finalized/Invoiced |
| `POST` | `/api/sysforge/invoices/{id}/update-prices/apply` | Body: chosen proposals; transactional |
| `GET` | `/api/sysforge/parts/placeholders` | Triage list + usage counts |
| `POST` | `/api/sysforge/parts/placeholders/{id}/convert` | Body: full part fields; 409 SKU conflict |

**Money:** all prices `*_cents` integers. **Time:** UTC ISO-8601.

**Search hit payload (indicative):**

```json
{
  "id": 12,
  "name": "iPhone 14 Pro Screen Assembly",
  "sku": "IP14P-SCR-001",
  "base_price_cents": 8999,
  "is_placeholder": false,
  "supplier_id": 1,
  "preferred_supplier_id": 1,
  "match_rank": 1
}
```

### UI routes

| Route | Panel |
|-------|-------|
| `#sysforge/parts` | Catalog list + search |
| `#sysforge/parts/triage` | Placeholder queue |
| `#sysforge/suppliers/:id` | Supplier detail |
| Calculator (existing) | Typeahead + Update Prices modal |

---

## UX contracts

| Action | User-visible result |
|--------|---------------------|
| Type in part search | Debounced results; SKU-looking queries surface SKU hits first; placeholders appear only if no catalog hit |
| Clear search | Empty dropdown / list; no phantom selection |
| Set preferred supplier on part | Persists; search/detail shows preferred name; autocomplete can badge preferred |
| Open supplier name on part | Supplier detail with contacts/notes + parts list |
| Update Prices | Preview table with per-line old/new/delta; Cancel leaves invoice unchanged; Confirm writes only eligible lines |
| Choose history price in preview | Proposed column uses history cents; BasePrice unchanged until separate catalog edit |
| Open triage queue | All placeholders with usage; Convert opens form; success removes from queue |
| SKU conflict on convert | Blocking dialog; no silent overwrite |
| Merge (P1) | Still available; still does not change historical line unit prices |
| After restore | Parts search finds restored catalog without manual SQL |

**Copy:** avoid “Lucene” in product UI. Prefer “Search parts” / “Rebuild search index.”

---

## Tests / verification

### Automated

1. **FTS ranking** — Seed catalog + placeholders; query SKU fragment → catalog SKU first; query unique placeholder-only name → placeholder; query with catalog hit → no placeholders in list.
2. **Autocomplete limit** — 15 matching names → max `limit` results.
3. **Debounce/abort** — JS unit or route test: superseded request ignored (status abort / ignore stale).
4. **Rebuild** — Delete FTS rows artificially (or corrupt); rebuild restores search hits; counts match.
5. **Supplier preferred** — Set preferred; GET part returns id; delete supplier → preferred null (SET NULL).
6. **Supplier name conflict** — Second create same Name → 409.
7. **Price history append** — PATCH BasePrice → history length +1; `Source=catalog_edit`; EffectiveAt UTC.
8. **Update Prices preview/apply** — Finalized invoice → 400; open estimate → preview deltas → apply changes UnitPriceCents + totals; Cancel path leaves DB unchanged.
9. **Merge invariant** — Two placeholders on invoices with different UnitPriceCents; merge → lines keep original cents; PartIds retargeted.
10. **Triage convert** — Placeholder → full part; `IsPlaceholder=0`; search finds as catalog; SKU clash → 409.
11. **Money** — No float dollars in JSON bodies for these endpoints.

### Manual QA

- Calculator: type `IP14`, pick part, save; change BasePrice; Update Prices shows delta; confirm.
- Triage: create placeholder via save; convert with supplier; verify invoice still shows old line price.
- Restore backup → search part by SKU without rebuild button (auto path) or with one click if diagnostics warns.

### Regression

- P1 merge confirm + irreversible delete of source placeholders.
- Clients FTS still works; shared migration runner order intact.

---

## Risks

| Risk | Mitigation |
|------|------------|
| Empty desktop `Placeholder-Parts-Workflow-Plan.md` | This plan + tests are the spec; do not invent silent auto-convert |
| Desktop Lucene never ships; web FTS diverges | Document intentional FTS5; keep ranking tests as shared contract |
| FTS drift after restore/import | Mandatory rebuild hook; diagnostics mismatch banner |
| SQLite ALTER FK limits | Follow `0013` pattern: app-enforced FK + indexes |
| Update Prices vs “invoice price history” confusion | UI copy: “Update line prices from catalog/history”; merge docs stress lines never rewritten by merge |
| Scope creep into inventory / PO | Explicit out of scope; refuse PartStock in this issue |
| Large catalog FTS rebuild time | Async rebuild + progress later; sync OK for shop-scale MVP |
| Dual `SupplierId` vs `PreferredSupplierId` | Define: `SupplierId` = primary link (existing); Preferred = buy-from hint (may match); both optional |

---

## Effort

**L** (large)

| Slice | Effort |
|-------|--------|
| A FTS5 + search + rebuild | **M** |
| B Suppliers UX | **M** |
| C Price history + Update Prices preview | **M** |
| D Triage queue | **S–M** |

Total **L** because four product surfaces, new migrations, and calculator coupling. Do not schedule before P1 parts + calculator save contracts are green.

---

## Implementation checklist

- [ ] Ranking + placeholder-gate contract written into tests first
- [ ] Append-only migrations: FTS, suppliers v2 columns, PreferredSupplierId, PartPriceHistory
- [ ] Parts search API switched to FTS5; autocomplete + debounce/abort
- [ ] Rebuild endpoint + restore/import hooks
- [ ] Supplier search/CRUD + detail + preferred on parts
- [ ] Price history append + Update Prices preview/apply
- [ ] Placeholder triage queue + convert + SKU 409 UX
- [ ] Router entries + Business nav links (Parts, Triage)
- [ ] Automated tests (list above)
- [ ] Manual QA walkthrough
- [ ] Optional research card notes after ship

---

## Source notes

- **gap-manifest:** After MVP parts+merge, deepen search (FTS5), supplier autocomplete/preferred, price history + update preview, triage beyond merge. Depends on `parts-placeholders-merge`, `invoice-calculator-save-contracts`.
- **MASTER §5 Phase 6+:** “Parts FTS, supplier UX, price history, placeholder triage.”
- **MASTER §7 / P3:** Lucene/FTS parts; supplier preferred UX; price history ← Invoice-Roadmap v2.
- **future-plans-roadmap §3 Phase 6:** FTS5 or Lucene-equivalent; triage UX from empty Placeholder plan; supplier UX; price history + update preview. Exit: parts entry as fast as client entry.
- **future-plans-roadmap §4.1:** Lucene/FTS parts; placeholder triage queue; price history + delta preview; supplier detail / preferred — all called out as missing Odysseus planning (this document closes that gap for one workstream).
- **feature-gap-matrix §5:** SQL LIKE Done on desktop / Missing on web (P1); Lucene parts Planned both sides → defer to P3; suppliers schema Done / no dedicated UI.
- **parts-catalog.md:** Port SQL verbatim for MVP; Lucene optional later → this workstream is that “later,” via FTS5.
- **suppliers.md:** Embed in parts/invoice for MVP; richer UX here.
- **placeholder-parts-merge.md:** Merge Done on desktop; triage queue is the Invoice-Roadmap extension beyond merge.
- **client-search-lucene.md:** Prefer FTS5 over PyLucene for web — same decision for parts.
- **Invoice-Roadmap v2:** Schema, DAL, Update Prices history selection, Placeholder Queue, supplier autocomplete/detail — behavioral blueprint for slices B–D.
- **PartService.MergePlaceholdersAsync:** Never update `InvoiceItems.UnitPriceCents`; preserve true invoice price history while catalog BasePrice may move.
