# Invoice calculator create/edit + save contracts

| Field | Value |
|-------|-------|
| **Issue id** | `invoice-calculator-save-contracts` |
| **Title** | Invoice calculator create/edit + save contracts |
| **Phase** | **P1** |
| **Effort** | **L** |
| **Priority** | critical |
| **Domain** | invoices |
| **Primary sources** | SysForge `InvoiceCalculatorViewModel.cs`, `InvoiceCalculatorView.axaml`(+`.cs`), `InvoiceService.cs`, `PartService.CreatePlaceholderPartsFromItemsAsync` / `DeleteOrphanedPlaceholdersAsync`, `InvoiceValidationHelpers.cs`, `InvoiceEditViewModel.cs` (empty-item + Save as new parity); chats [21e672a5](../chat-reviews/21e672a5-191b-42d1-a2ae-4a5527cb8784.md), [920df407](../chat-reviews/920df407-41fd-4f6d-a38d-dc5c4065a110.md), [21972123](../chat-reviews/21972123-780e-4496-99cd-5be905556a3b.md), [f4de4b62](../chat-reviews/f4de4b62-87a3-4f5f-b09f-09cc62baa5c8.md), [8eceb374](../chat-reviews/8eceb374-24a7-4fc9-88c2-0b796a7b4528.md); research `docs/research/sysforge/features/invoice-calculator.md`, `invoice-edit.md` |
| **Manifest** | `gap-plans/gap-manifest.json` → `invoice-calculator-save-contracts` |
| **Master plan** | `synthesis/MASTER-MIGRATION-PLAN.md` → Phase 1 (Invoice MVP) + §6 UX contracts |

---

## Goal / success

Port the desktop keyboard-first invoice calculator into the Odysseus Business plugin so a solo tech can quote, edit, and save invoices in the browser with the same save identity, placeholder, and search contracts as SysForge.

**Done when:**

1. **Create loop** — pick client (typeahead), add line items (parts/labor/misc + placeholders), tax/shipping toggles, name prompt, save → new invoice row as `Estimate` / not finalized / `sent_at` null.
2. **Edit same id** — load existing invoice into calculator; **Save** updates the same row and keeps stored **name**; does **not** force a rename dialog; does **not** reset `status` / `is_finalized` / `sent_at`.
3. **Save as new** — while editing, clone lines into a **new** estimate; name dialog; new id returned. Viewer return-nav is a follow-on (`invoice-viewer-return-context`); this workstream may toast + stay on calculator cleared, or soft-navigate to a stub viewer route if one exists—do not block on Classic back-stack.
4. **Placeholder orphan order** — on update: `DELETE` items → create placeholders → `INSERT` items → **then** orphan cleanup. Placeholders still referenced by the new lines must survive (BUG-006).
5. **Empty-item policy** — create (and drafts) require ≥1 line; **edit/update** of an existing invoice may save with zero lines (header preserved; service-layer allow). Accidental wipe recovery relies on per-invoice backup (desktop) / equivalent later—do not hard-block edit-empty.
6. **Client search UX** — matches (cap ~5) **before** a single **Add New** row; Up/Down/Enter; dropdown **stays closed** when query equals selected client `display_name` (edit-load guard).
7. **Busy / async** — `is_saving` / `is_loading` disable Save / Save as new; cancel in-flight loads on leave; money in integer cents end-to-end; status/discount/item_type as strings.
8. **Tests green** — API + orphan regression + edit-identity + empty-edit + search-order; plugin gate still 404 when inactive.

---

## Current state

### SysForge desktop (source of truth)

| Area | Behavior | Anchor |
|------|----------|--------|
| Calculator VM | Create + edit (`_editingInvoice`), totals, client/part search, drafts hooks, Save / Save as new, busy flags | `InvoiceCalculatorViewModel.cs` (~2k lines) |
| Calculator view | Keyboard Enter navigation, client/part overlays, Quick Add, focus targets | `InvoiceCalculatorView.axaml`(+`.cs`) |
| Save (create) | Require client + ≥1 item; name dialog; set `Status=Estimate`, `IsFinalized=false`, `SentAt=null` | `SaveInvoice` |
| Save (edit, calculator) | Same client/≥1 item guard in VM today; **no** name dialog; keep `Name`; reuse `_editingInvoice` (preserve status/finalized/sent) | `SaveInvoice` + chat `21e672a5` |
| Save (edit, dedicated) | **Zero items allowed**; comment: auto-backup covers accidental wipe | `InvoiceEditViewModel.SaveInvoice` |
| Service empty policy | `ValidateInvoiceItems` allows empty list; create UI may still require items | `InvoiceValidationHelpers.cs` remarks + `f4de4b62` |
| Save as new | New `Invoice` row; name dialog; defaults to estimate; calculator shows button only when `IsEditingExistingInvoice` | `SaveAsNewInvoice` |
| Persist transaction | Validate → optional backup if `Id!=0` → totals → INSERT or UPDATE header → (update: DELETE items) → placeholders → INSERT items → orphan cleanup → commit | `InvoiceService.SaveInvoiceAsync` |
| Orphan order (BUG-006) | Cleanup **after** re-insert so in-memory `PartId`s still resolve | chat `21e672a5`; test `SaveInvoice_OnUpdate_DoesNotDeletePlaceholdersBeforeReinsertingItems` |
| Client dropdown guard | If `SelectedClient` set and query == `DisplayName` (ordinal ignore-case) → `ShowClientDropdown=false` | chat `920df407` / `21972123`; `UpdateClientSearchResultsAsync` |
| Matches before Add New | `Take(5)` then `ClientSearchResult.CreateAddNew(query)` | calculator ~1231–1236 |
| Money / enums | Cents + milliunits + tax bps; `Status`/`ItemType`/`DiscountType` as strings for CHECK | `MoneyHelpers`, `InvoiceService` |
| FK toast | SQLite extended **787** → re-pick part / fix supplier (not “already exists”) | calculator + edit VMs |
| Do not port | `AppendAllText` debug.log instrumentation in view code-behind | research `invoice-calculator.md` |

**Product decision to prefer over VM lag:** MASTER §4 / `f4de4b62` — empty lines OK on **edit** save; calculator **create** still requires ≥1 item. Port the service + edit policy; on calculator edit path, **allow** empty save (align with dedicated edit + MASTER), even though current desktop calculator VM still blocks empty.

### Odysseus web (target today)

| Area | State |
|------|--------|
| Plugin shell | Install/uninstall, feature gate, stub Business UI only |
| Invoices API / UI | **Missing** — no calculator route, no `/api/sysforge/invoices*` |
| DB | Empty until `schema-money-utc-foundation` ports invoice/parts/clients migrations |
| Upstream deps | Clients / parts-placeholders / drafts workstreams not shipped yet (this plan assumes they land first) |

### Gap (one sentence)

Desktop ships a full keyboard calculator with hard save/orphan/search contracts; Odysseus has zero invoice runtime, so this workstream is the shop-loop MVP after clients, parts, and drafts exist.

---

## Scope

### In scope

- Python `InvoiceService` (save create/update, get by id, get items, list by client, delete if desktop has it) + totals calculation matching cents vectors.
- Placeholder create-on-save + orphan cleanup with **correct order** (owned jointly with `parts-placeholders-merge`; this workstream owns the invoice save orchestration and regression test).
- REST: create, get, update (same id), save-as-new (or create with clone body), list-by-client.
- Calculator UI in Business shell: create + load-for-edit, line grid, tax/shipping, name dialog, Save / Save as new, busy flags.
- Client typeahead integration (consume `clients-crud-fts-duplicates` APIs): matches before Add New; edit-load dropdown guard; keyboard Up/Down/Enter.
- Part typeahead + “create placeholder” path on save (consume parts API).
- Wire drafts autosave hooks from `drafts-service-autosave` (debounce/lock/flush on leave)—do not reimplement DraftService here.
- Money/enum/JSON helpers usage for invoice payloads.
- Per-invoice JSON backup-on-update **parity with desktop** (file under plugin data) if cheap after parts land; else stub + ticket note—do not block empty-edit policy on backup UI.
- Tests: orphan order, same-id update, status preservation, empty edit, create requires items, FK messaging mapping.
- README: “Calculator create/edit + save contracts” once shipped.

### Out of scope

- **Invoice viewer + save-as-new return context** (`invoice-viewer-return-context`) — full viewer, history trim, Back → Classic with client selected.
- **Nav lifecycle / View vs Edit route polish** (`nav-lifecycle-view-edit-routes`) — beyond “Edit loads calculator and navigates.”
- **Classic Client Dashboard** (`classic-client-dashboard`).
- **Price compare** dedicated UI (desktop `ComparePricesToDatabase`; P2).
- **Invoice devices / projects / WO** (later phases).
- **PDF / email / payments** (`invoice-ops-pdf-payments-merge`).
- **Dedicated `InvoiceEditView` polish** as a second page — prefer one calculator surface for P1; dedicated edit can reuse the same API later.
- Desktop DB import; Avalonia debug.log; Lucene parts search.

---

## Dependencies

| Depends on | Why |
|------------|-----|
| `schema-money-utc-foundation` | `Invoices` / `InvoiceItems` / `Parts` schema, cents columns, UTC helpers, checksum migrations |
| `business-shell-dashboard-router` | Calculator card + `#sysforge/invoice-calculator` (and edit-with-id) route |
| `clients-crud-fts-duplicates` | Client search, Add New / incomplete create, duplicate banner hooks |
| `parts-placeholders-merge` | Part search, placeholder create, orphan delete SQL, merge UI elsewhere |
| `drafts-service-autosave` | Autosave during calculator session; clear autosaves after successful invoice save |

| Soft / parallel | Why |
|-----------------|-----|
| `business-settings-mvp` | Tax/currency defaults for calculator; hard-code config.json defaults until settings UI ships |
| `nav-lifecycle-view-edit-routes` | **Downstream** — hardens Edit/View navigation after calculator exists |
| `invoice-viewer-return-context` | **Downstream** — completes save-as-new → viewer → Classic back |
| `classic-client-dashboard` | Primary entry for Edit from invoice rail |

**Blocked if:** no schema, no clients search, no parts/placeholder helpers, or Business still status stub with no router.

---

## Concrete steps

### 1. Service layer — save orchestration (do first)

1. Port `InvoiceValidationHelpers` to Python:
   - Header: non-negative money, tax 0–100 (or bps equivalent), valid client id when set.
   - Items: allow **empty list**; when present, require non-empty `part_name`, positive qty, non-negative prices; discount percent/amount rules.
2. Port `CalculateInvoiceTotals` using money helpers (parts/labor/misc split; tax on taxable or Part; shipping from rate when included).
3. Implement `save_invoice(invoice, items)` in one SQLite transaction:
   - Validate header + items.
   - If `invoice.id` set: optional `backup_existing_invoice` JSON to plugin data (mirror desktop; outside or before txn so file I/O failure does not abort—match desktop comment).
   - Normalize UTC on `date_created` / `sent_at` / `last_edited_at` (insert: `last_edited_at = date_created`; update: `UtcNow`).
   - **Insert** (`id == 0`): INSERT header with caller-supplied status fields (create path sets Estimate / not finalized / sent null).
   - **Update** (`id != 0`): UPDATE header **without** forcing status/finalized/sent unless caller sends them; then `DELETE FROM InvoiceItems WHERE InvoiceId = ?`.
   - Call `create_placeholder_parts_from_items` (parts service) — backfill `part_id` on lines needing placeholders.
   - `INSERT` all line items (enum fields as **strings**).
   - Call `delete_orphaned_placeholders` **only after** inserts.
   - Commit; return invoice id.
4. Add `get_invoice`, `get_invoice_items`, `get_invoices_by_client`, `delete_invoice` (header+items + orphan cleanup if desktop does) as needed by UI.
5. Map SQLite FK failures (extended 787 / constraint) to a distinct error type for API toast copy.

**Orphan order (non-negotiable):**

```text
UPDATE header
DELETE InvoiceItems for id          # update only
create_placeholder_parts_from_items # may INSERT Parts, set item.part_id
INSERT InvoiceItems
delete_orphaned_placeholders        # ONLY now
COMMIT
```

Wrong order (delete items → orphan cleanup → insert) is BUG-006 and must fail CI.

### 2. API routes

1. Gate all routes behind existing plugin active check (404 when inactive).
2. Endpoints (names illustrative; keep `/api/sysforge/` prefix):

| Method | Path | Role |
|--------|------|------|
| `POST` | `/invoices` | Create (name required; ≥1 item enforced here **or** in UI+create flag—see empty policy) |
| `GET` | `/invoices/{id}` | Header + items |
| `PUT` | `/invoices/{id}` | Same-id update; empty items allowed; preserve status fields unless body includes them |
| `POST` | `/invoices/{id}/save-as-new` | Clone body → new estimate id + name |
| `GET` | `/invoices?client_id=` | List for dashboard later |
| `DELETE` | `/invoices/{id}` | Optional P1 if desktop delete is needed for tests |

3. Request/response use **integer cents** (and milliunits for qty); accept/return ISO UTC timestamps; status as string enum (`Estimate`, etc.).
4. Create path: if items empty → `400` with clear message. Update path: empty items → `200` with zero lines.
5. Busy-safe: endpoints are async; no sync SQLite on event loop if host pattern uses `to_thread` / aiosqlite—follow whatever P0 foundation chose.

### 3. Calculator UI (JS)

1. Route: `invoice-calculator` (create) and `invoice-calculator/:id` (edit load). Dashboard **Calculator** card → create; later Classic **Edit** → edit route (nav workstream hardens this).
2. Layout: client search field + overlay; line grid (name / qty / price / type); Quick Add; tax/shipping toggles + totals; Save; **Save as new** visible only when `editingInvoiceId != null`.
3. Load edit: `GET /invoices/{id}` → fill client, lines, toggles; set search query to `display_name`; **do not open** client dropdown (guard).
4. Name dialog: modal for **create** and **save-as-new** only; default `"{Client} - MM/dd/yyyy"` (UTC date or local—match desktop `GenerateDefaultInvoiceName` using client display + date). Edit save skips dialog.
5. After successful create/edit save: clear form, clear edit id, clear draft autosaves (API), toast success; navigate per shell (dashboard or stay—viewer deferred).
6. After save-as-new: clear edit state; toast; optionally `router` to future viewer; do not leave stale `_editingInvoice`.
7. Wire `IsSaving` / `IsLoading`: disable Save buttons; prevent double-submit.
8. Autosave: call drafts service on change (debounce); skip when empty create; flush on leave (drafts workstream contract).

### 4. UX contracts wiring (must not regress)

Implement these as explicit code comments + QA checklist (see UX section):

1. **Keyboard-first** — client: Up/Down/Enter; lines: Enter advances focus (Quick Add → name → price → qty pattern from `HandleEnterKey` / view code-behind—port the focus state machine, not Avalonia specifics).
2. **Matches before Add New** — append Add New **after** matches; never first when hits exist.
3. **Dropdown guard** — `selectedClient && query.trim().toLowerCase() === displayName.trim().toLowerCase()` → hide overlay (no search fetch needed).
4. **Empty-item policy** — create blocked; update allowed.
5. **Status preservation** — edit PUT must not send Estimate/finalized reset unless user changed status (P1 calculator may omit status fields on edit body so server keeps DB values).

### 5. Tests then README

1. Port critical vectors from `InvoiceServiceTests` + `PlaceholderWorkflowTests` (especially update-with-placeholder survival and orphan-when-line-removed).
2. API tests for create/edit/save-as-new/empty-edit/create-empty-400.
3. Front-end unit or Playwright smoke if host already has pattern; otherwise manual checklist is required exit for keyboard + dropdown guard.
4. Update `integrations/sysforge/README.md` with endpoints + contracts.

---

## Files

### SysForge (read / port from)

| Path | Why |
|------|-----|
| `SysForge/ViewModels/InvoiceCalculatorViewModel.cs` | Save / Save as new / load / client search / focus / busy |
| `SysForge/Views/InvoiceCalculatorView.axaml`(+`.cs`) | Keyboard, overlays, Quick Add (strip debug.log) |
| `SysForge/ViewModels/InvoiceEditViewModel.cs` | Empty-item edit + Save as new naming (`(copy)`) |
| `SysForge/Database/InvoiceService.cs` | Transaction order, totals, backup-on-update |
| `SysForge/Database/PartService.cs` | `CreatePlaceholderPartsFromItemsAsync`, `DeleteOrphanedPlaceholdersAsync` |
| `SysForge/Helpers/InvoiceValidationHelpers.cs` | Empty-list policy + item rules |
| `SysForge/Helpers/MoneyHelpers.cs`, `DateTimeHelpers.cs` | Cents / UTC (via P0) |
| `SysForge.Tests/Database/InvoiceServiceTests.cs` | Same-id update, replace items, status text |
| `SysForge.Tests/Database/PlaceholderWorkflowTests.cs` | Orphan order regression |
| `SysForge/Views/InvoiceNameDialog.axaml` | Name prompt UX |

### Odysseus (expected touch set)

| Path | Role |
|------|------|
| `integrations/sysforge/services/invoices.py` (new) | Save orchestration + totals |
| `integrations/sysforge/services/parts.py` (or extend) | Placeholder create + orphan delete (if not already from parts workstream) |
| `integrations/sysforge/helpers/invoice_validation.py` (new) | Validation |
| `integrations/sysforge/routes.py` | Mount invoice routes |
| `integrations/sysforge/static/js/invoice-calculator.js` (new) | UI + keyboard + guards |
| `integrations/sysforge/static/js/client-search.js` | Reuse from clients workstream |
| `integrations/sysforge/static/js/router.js` | Register calculator routes |
| `tests/test_sysforge_invoices.py` (new) | API + orphan + identity |
| `integrations/sysforge/README.md` | Document shipped surface |

Exact filenames may follow whatever P0/P1 layout the shell already uses; keep invoice logic out of host `app.py` beyond mount.

---

## API / UI contracts

### Invoice header (JSON)

```json
{
  "id": 12,
  "client_id": 3,
  "client_info": "Alex Rivera - (555) 0100",
  "name": "Alex Rivera - 07/17/2026",
  "date_created": "2026-07-17T20:00:00Z",
  "last_edited_at": "2026-07-17T21:15:00Z",
  "parts_subtotal_cents": 5000,
  "labor_cost_cents": 7500,
  "shipping_cost_cents": 0,
  "tax_amount_cents": 906,
  "final_total_cents": 13406,
  "include_tax": true,
  "include_shipping": false,
  "tax_rate_bps": 725,
  "shipping_rate_cents": 0,
  "status": "Estimate",
  "is_finalized": false,
  "sent_at": null,
  "items": []
}
```

### Invoice item (JSON)

```json
{
  "part_id": 44,
  "part_name": "Screen assembly",
  "sku": null,
  "quantity_milliunits": 1000,
  "unit_price_cents": 5000,
  "discount_type": "None",
  "discount_value": 0,
  "is_taxable": true,
  "line_total_cents": 5000,
  "sort_order": 0,
  "item_type": "Part",
  "supplier_id": null
}
```

- Money: **cents only** on the wire (no float dollars in persistence).
- Enums: strings matching desktop CHECK (`Part`/`Labor`/`Misc`, `Estimate`, discount types).
- `part_id` null on Part lines → placeholder creation on save.

### Create vs update vs save-as-new

| Action | Name dialog | Identity | Status defaults | Items empty |
|--------|-------------|----------|-----------------|-------------|
| Create `POST /invoices` | Yes | New id | Estimate / not finalized / sent null | **400** |
| Update `PUT /invoices/{id}` | No | Same id + same name unless body renames | Preserve DB unless body sets | **Allowed** |
| Save as new `POST .../save-as-new` | Yes | New id | Always new Estimate | **400** (same as create) |

### Errors

| Case | Status / behavior |
|------|-------------------|
| Plugin inactive | 404 |
| Validation | 400 + `{ "detail": "..." }` |
| Not found | 404 |
| SKU conflict on placeholder | 409 (or 400) with conflict detail |
| FK / missing part (787) | 409/400 with **re-pick part / fix supplier** copy—not “already exists” |
| Busy double-submit | Client disables; server remains idempotent where practical |

---

## UX contracts

Copy into QA; fail the workstream if broken.

### Keyboard-first

- [ ] Client field: **Down/Up** moves highlight in overlay; **Enter** selects highlight (or first row if none); selecting a match commits client and closes overlay.
- [ ] **Enter** in Quick Add adds/focuses line flow; Enter in name/price/qty advances per desktop focus targets (Quick Add → FirstItemName → Price → Quantity → next).
- [ ] Invalid price on Enter restores model or clears; does not advance.
- [ ] Quantity empty/invalid displays as **1** (desktop safe-parse).
- [ ] Save buttons disabled while `is_saving` or `is_loading`.

### Matches before Add New

- [ ] Non-empty client query: API matches listed first (cap 5 in UI), then **one** Add New row with the typed query.
- [ ] Add New never sorts above real matches.
- [ ] Empty query: overlay closed (recent-6 is Classic overlay territory—not required here).

### Client dropdown guard (edit load)

- [ ] After `LoadWithInvoice` / `LoadWithClient` / pick-from-list, search text shows `display_name` and **overlay stays closed**.
- [ ] Changing the query so it no longer equals selected display name reopens search.
- [ ] Guard is case-insensitive trim equality (desktop ordinal ignore-case).

### Empty-item policy

- [ ] **Create**: Save with 0 lines → blocked (toast/400); draft save also requires items (desktop).
- [ ] **Edit/update** existing id: Save with 0 lines → succeeds; header remains; orphan cleanup may remove unused placeholders.
- [ ] Accidental empty edit is recoverable via backup-on-update when that file path ships; do not invent soft-delete items in P1.

### Save identity

- [ ] Edit Save: same invoice id; name unchanged without dialog.
- [ ] Edit Save: finalized/sent/status not wiped by create defaults.
- [ ] Save as new: new id; name from dialog; button only in edit mode on calculator.
- [ ] Clear form exits edit mode (`editingInvoiceId = null`).

### Placeholders

- [ ] Unknown part name on save creates placeholder and links `part_id`.
- [ ] Update that keeps the same placeholder lines does **not** delete those Parts mid-save.
- [ ] Removing a placeholder-only line and saving deletes the orphan Part after re-insert.

---

## Tests / verification

### Automated (`tests/test_sysforge_invoices.py`)

Mirror / adapt:

1. `SaveInvoice_NewInvoice_PersistsHeaderAndItems`
2. `SaveInvoice_UpdateSameId_DoesNotCreateSecondInvoice` (BUG-006/007 identity)
3. `SaveInvoice_UpdateReplacesItems`
4. `SaveInvoice_OnUpdate_DoesNotDeletePlaceholdersBeforeReinsertingItems` (**orphan order**)
5. Update remove-all-placeholder-lines → placeholders deleted after save
6. Create with empty items → 400; update with empty items → 200 + zero lines
7. Create sets Estimate / not finalized; update preserves finalized + sent_at
8. Save-as-new returns new id; original unchanged
9. Status stored as text string
10. Money totals vector (fixed cents fixture)
11. Plugin inactive → invoice routes 404
12. FK / missing part surfaces distinct error payload

Optional JS: unit test for dropdown guard pure function + matches-before-Add-New list builder.

### Manual smoke (MASTER §8.3 subset)

1. Install plugin → Business → Calculator.
2. Search client: matches above Add New; Enter selects.
3. Add part line (catalog) + unknown name line → Save with name → invoice exists; unknown is placeholder.
4. Re-open edit: client name filled, **dropdown closed**; change a price → Save → same id/name.
5. Edit: remove all lines → Save succeeds (empty header).
6. Edit: Save as new → new id; original intact.
7. Keyboard: quote a full invoice without mouse except optional Save click.
8. Rapid Save double-click does not create two invoices.

### Exit criteria (manifest / MASTER)

- Calculator create/edit + save/name: same-id edit; save-as-new; busy flags.
- Placeholder orphan cleanup after re-insert.
- Create ≥1 line; edit may save empty header.
- Client typeahead: matches before Add New; edit-load guard.
- FK/orphan regression tests green.

---

## Risks

| Risk | Mitigation |
|------|------------|
| Wrong orphan cleanup order (BUG-006) | Codify order in service docstring; first regression test in CI; code review checklist item |
| Porting calculator VM “as-is” keeps empty-item block on edit | Follow MASTER/`f4de4b62` policy explicitly in API + calculator edit path |
| Save as new blocked waiting on viewer/Classic | Ship clone + clear + toast; hand off nav to `invoice-viewer-return-context` |
| Float money drift | Cents-only API; shared test vectors from desktop |
| Enum CHECK failures | Always bind status/item_type/discount as strings |
| Client dropdown auto-open on edit (easy miss) | Guard function + manual smoke from day one (`920df407`) |
| Network autosave vs desktop file speed | Rely on drafts workstream debounce/lock; never block Save on autosave |
| Scope creep into devices/PDF/viewer | Keep out-of-scope list firm; separate tickets |
| Parts workstream incomplete | Do not invent a second placeholder implementation; block or thin-slice shared `PartService` helpers first |
| Debug.log / Avalonia focus quirks | Do not port `AppendAllText` debug; reimplement Enter focus in JS simply |

---

## Effort

**L** (large)

- Service + orphan-safe transaction + API: ~1–2 PRs
- Calculator UI (keyboard, overlays, save dialogs, edit load): ~1–2 PRs
- Tests + README + smoke: thin follow-up or same final PR

Not **XL** if clients/parts/drafts already landed and the UI stays one calculator surface (no second InvoiceEdit page, no viewer). Becomes **XL** if this ticket absorbs Classic dashboard entry, viewer back-stack, devices, or price-compare.

---

## Implementation checklist (ticket-ready)

1. [ ] `InvoiceValidationHelpers` + totals in Python (empty list allowed)
2. [ ] `save_invoice` transaction with **post-insert** orphan cleanup
3. [ ] REST create / get / update / save-as-new (+ list-by-client)
4. [ ] Create rejects empty items; update allows empty items
5. [ ] Edit preserves status / finalized / sent_at; no rename dialog
6. [ ] Calculator JS: grid, tax/shipping, name dialog, busy flags
7. [ ] Client search: matches before Add New; Up/Down/Enter; edit-load guard
8. [ ] Save as new button only while editing; clears edit state after success
9. [ ] Drafts autosave hooks + clear on successful invoice save
10. [ ] Placeholder create-on-save wired through parts service
11. [ ] FK error mapping (787-style) to user-facing copy
12. [ ] `tests/test_sysforge_invoices.py` incl. orphan-order regression
13. [ ] Manual keyboard + edit-load dropdown smoke
14. [ ] README documents contracts; defer viewer return to its workstream
)
