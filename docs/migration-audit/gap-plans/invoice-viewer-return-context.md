# Invoice viewer + save-as-new return context

| Field | Value |
|-------|-------|
| **Issue id** | `invoice-viewer-return-context` |
| **Title** | Invoice viewer + save-as-new return context |
| **Phase** | **P2** |
| **Priority** | high |
| **Domain** | invoices |
| **Effort** | **M** |
| **Primary sources** | Chat [21972123](../chat-reviews/21972123-780e-4496-99cd-5be905556a3b.md) (save-as-new → viewer → Back); chat [67a4ed8b](../chat-reviews/67a4ed8b-7a7b-4bd0-8933-3d4e33a185f6.md) (return context + viewer Edit); chat [21e672a5](../chat-reviews/21e672a5-191b-42d1-a2ae-4a5527cb8784.md) (save-as-new clone contracts); research `Sysforge research/features/invoice-viewer.md` |
| **Manifest** | `gap-plans/gap-manifest.json` → `invoice-viewer-return-context` |
| **Master plan** | `synthesis/MASTER-MIGRATION-PLAN.md` → Phase 2 exit: *Save-as-new → viewer → back to client*; §4 / §6 return-context + save-as-new UX contracts |
| **Depends on** | `classic-client-dashboard`, `invoice-calculator-save-contracts` (also assumes `nav-lifecycle-view-edit-routes`) |

---

## Goal / success

Close the Odysseus gap for the **post-save invoice review loop** that SysForge desktop already ships:

1. **Read-only invoice viewer** at `#sysforge/invoice-view/:id` (header + line list; no cell editing).
2. **Save as new** ends on that viewer for the **new** invoice id (after name dialog + clone save).
3. **Back** from that viewer lands on the **origin screen** (Classic Client Dashboard with the same client selected and invoice rail refreshed), not the calculator.
4. **Viewer Edit** opens the calculator for that invoice **without** wiping the captured origin, so a later edit-save still returns to the origin.
5. **Price compare** (desktop Done on finalized edit): for finalized invoices, flag line items whose `UnitPriceCents` differ from current catalog `BasePriceCents`.

**Done when:**

- Client Dashboard **View** and post–save-as-new both open the same viewer route with loaded header + items.
- Save-as-new stack is: name dialog → new id → viewer → Back → Classic with client selected and **new invoice visible** in the rail.
- Viewer **Edit** → calculator edit; shell Back / post-save return still honors origin.
- Automated tests cover history trim, return-context capture rules, and save-as-new navigation.
- Manual smoke matches MASTER §8.4: *Save-as-new → viewer → Back lands on same client with new invoice visible*.

---

## Current state

### SysForge desktop (source of truth)

| Piece | Location | Behavior |
|-------|----------|----------|
| Viewer VM | `InvoiceViewerViewModel.cs` | Load invoice + client + items; cancel CTS on deactivate; **Edit** → `NavigateToInvoiceCalculatorEditAsync` |
| Viewer UI | `InvoiceViewerView.axaml` | Title + "Read-only view"; top-right **Edit**; client / date / status / total; line list |
| Return context model | `InvoiceNavigationReturnContext.cs` | `ViewModelType` + optional `ClientId` / `ProjectId` / `WorkOrderId` |
| Capture | `NavigationService.CaptureInvoiceReturnContextIfStartingFlow` | Only when **leaving a non-invoice screen** into viewer/calculator/edit; viewer → Edit does **not** overwrite |
| History trim | `TrimInvoiceFlowFromHistory` + `NavigationHistory.RemoveCurrentEntry` | Pops consecutive calculator / viewer / edit entries |
| Save-as-new nav | `NavigateToInvoiceViewerAfterSaveAsNewAsync` | Trim invoice flow → load viewer → navigate (does **not** force dashboard first) |
| Normal edit save nav | `NavigateAfterInvoiceSaveAsync` | Trim → restore return context (or fallback Classic with `savedClientId`) |
| Save-as-new action | `InvoiceCalculatorViewModel.SaveAsNewInvoice` | Name prompt → new estimate row → clear calculator → viewer nav |
| Price compare | `InvoiceEditViewModel.ComparePricesToDatabaseAsync` | Finalized only; sets `HasPriceMismatch` / `CurrentDatabasePriceCents` |

**Proven save-as-new back stack (BUG-008 / chat 21972123 + 67a4ed8b):**

```text
[Client Dashboard | client C selected]
        │  Edit / New invoice  (capture return context = Classic + ClientId=C)
        ▼
[Invoice Calculator]
        │  Save as new → name dialog → INSERT new id N
        │  Clear calculator edit state
        │  TrimInvoiceFlowFromHistory()   // calculator off stack
        ▼
[Invoice Viewer | id=N]                 // pushed after trim
        │  Back
        ▼
[Client Dashboard | client C + refreshed invoice list including N]
```

**Viewer Edit must preserve origin (chat 67a4ed8b):**

```text
… → Viewer (return context still Classic+C)
        │  Edit  (Capture sees invoice-flow current → no overwrite)
        ▼
[Calculator | edit N]
        │  Save Invoice (same id)
        │  NavigateAfterInvoiceSaveAsync
        ▼
[Client Dashboard | C]   // not Projects Hub, not blank home
```

### Odysseus web (target today)

- Plugin shell exists; Business domain UI is still largely missing or stubbed.
- Research already names route `invoice-view/:id` and module `invoice-viewer.js` (`06-frontend-routing.md`, `features/invoice-viewer.md`).
- No runtime viewer, no `InvoiceNavigationReturnContext` equivalent, no history trim after save-as-new.
- Calculator save-as-new (when ported in P1) must not stop at "stay on calculator with new id" (early 21e672a5 behavior); desktop **superseded** that with viewer nav (21972123).

### Gap

Web needs the **viewer panel**, **return-context module**, and **save-as-new → viewer → Back** wiring on top of P1 calculator + P2 Classic dashboard + P1 nav lifecycle. Without history trim, Back from the viewer returns to the calculator and breaks the shop loop.

---

## Scope

### In scope

- Read-only **invoice viewer** panel/route (`invoice-view/:id`).
- Shared read-only **render** of header + line items (reuse calculator display components where practical; no editable grid).
- **Viewer Edit** CTA → calculator edit route (`invoice-calculator?invoiceId=`).
- **Return-context** store + capture-on-first-invoice-entry + clear-on-successful-return.
- **History trim** of invoice-flow routes before save-as-new viewer push and before post-save return.
- Wire calculator **Save as new** success → `navigateToViewerAfterSaveAsNew(newId, clientId)`.
- Wire calculator **Save** (edit existing) success → `navigateAfterInvoiceSave(savedClientId)` (origin restore).
- On return to Classic: **reselect client** + **refresh invoice rail** so the new/updated invoice appears.
- **Price compare (MVP):** on viewer activate for `is_finalized` invoices, mark mismatched lines vs catalog; show a clear visual cue (no PDF). Optional "use catalog price" can ship if cheap; otherwise defer mutation to a thin follow-up and keep flags read-only.
- Tests for trim / capture / save-as-new stack (see Tests).

### Out of scope

- PDF / print / email / payments (Invoice-Roadmap v3+; research risk note).
- Full `InvoiceEditView` finalized editor UI as a separate page (Client Dashboard Edit stays on **calculator**; price-compare flags can live on viewer).
- Building Classic Client Dashboard, calculator create/edit, or router lifecycle from scratch (owned by dependency workstreams).
- Persisting return context / nav history across browser refresh (desktop in-session only; MASTER defers cross-restart history).
- Projects / WO / projects-hub origin restore **beyond** storing `projectId` / `workOrderId` in the context object and calling into those navigators **when those routes exist**. Until `projects-wo-four-column` lands, implement Classic + fallback; leave typed hooks for project/WO/hub.
- Client search overlay guard / LastEdited column (chat 21972123 extras; belong with Classic / calculator workstreams unless already present).

---

## Dependencies

| Depends on | Why |
|------------|-----|
| `invoice-calculator-save-contracts` | Save / Save-as-new APIs, name dialog, clone row, clear-edit-state |
| `classic-client-dashboard` | Back target with client selected + invoice list refresh |
| `nav-lifecycle-view-edit-routes` | `invoice-view` / calculator routes, history stack, same-panel re-apply safety |
| `GET /api/sysforge/invoices/{id}` (+ items) | Viewer load |
| `GET /api/sysforge/parts/{id}` (or batch) | Price compare cents |
| Feature flag / plugin shell | Panel hosts the viewer |

| Soft / parallel | Why |
|-----------------|-----|
| `projects-wo-four-column` | Extends return-context origins; do not block Classic loop |
| Shared invoice line render component | Less duplication with calculator read mode |

**Blocks:** `projects-wo-four-column` (manifest), any flow that assumes save-as-new lands on a review screen, and MASTER Phase 2 Classic smoke.

---

## Concrete steps

### 1. Freeze contracts (constants before UI)

Document in code (comments + route helpers):

| Intent | Web API | Desktop mirror |
|--------|---------|----------------|
| Open viewer | `navigate('invoice-view', { id })` | `NavigateToInvoiceViewerAsync` |
| Save-as-new → viewer | `navigateToViewerAfterSaveAsNew(id, clientId)` | `NavigateToInvoiceViewerAfterSaveAsNewAsync` |
| Edit from viewer | `navigate('invoice-calculator', { invoiceId })` | `NavigateToInvoiceCalculatorEditAsync` |
| After edit save | `navigateAfterInvoiceSave(savedClientId)` | `NavigateAfterInvoiceSaveAsync` |
| Back button | `back()` after trim rules | `NavigationHistory` + toolbar Back |

Reject: save-as-new staying on calculator; Back from post-save viewer returning to calculator.

### 2. Add return-context module

Create a small module (e.g. `integrations/sysforge/static/js/invoice-return-context.js`):

```text
shape:
  { originRoute, clientId?, projectId?, workOrderId? }

captureIfStartingInvoiceFlow(currentRoute):
  if currentRoute is invoice-view | invoice-calculator | invoice-edit:
    return  // do not overwrite (viewer Edit case)
  store snapshot of current route + ids from active panel

clear():
  store = null

consume() -> context | null:
  take and clear
```

Populate `clientId` from Classic selection; later `projectId` / `workOrderId` from project/WO panels.

### 3. History trim helper

```text
trimInvoiceFlowFromHistory(stack):
  while top is invoice-view | invoice-calculator | invoice-edit:
    pop / RemoveCurrentEntry equivalent
```

Call sites:

1. Immediately **before** pushing viewer in `navigateToViewerAfterSaveAsNew`.
2. Immediately **before** restoring origin in `navigateAfterInvoiceSave`.

Do **not** trim when merely opening viewer from Classic View (user should Back to Classic via normal stack).

### 4. Implement viewer panel

`integrations/sysforge/static/js/views/invoice-viewer.js` (+ HTML partial or template):

- `activate({ id })`: `GET` invoice + items (+ client); AbortController on deactivate.
- Render: title (`DisplayName`), subtitle "Read-only view", client, date, status, total, line table.
- Header **Edit** disabled until load succeeds; then `navigate('invoice-calculator', { invoiceId })`.
- No inputs on lines; no Save.

Optional: share a `renderInvoiceReadonly(model)` helper with calculator preview.

### 5. Wire save-as-new (calculator)

On successful Save as new (after toast / clear edit state):

```text
1. Capture already happened when calculator opened from Classic.
2. clearCalculatorEditState()
3. navigateToViewerAfterSaveAsNew(newId, savedClientId):
     trimInvoiceFlowFromHistory()
     navigate('invoice-view', { id: newId })   // push viewer
```

Cancel of name dialog: no nav, stay on calculator.

### 6. Wire edit save return

On successful **Save Invoice** while editing existing:

```text
navigateAfterInvoiceSave(savedClientId):
  trimInvoiceFlowFromHistory()
  ctx = consume()
  if ctx.origin is classic / client-dashboard:
    navigate('client-dashboard', { clientId: ctx.clientId ?? savedClientId })
    activate → loadClient + refresh invoices
  else if project / WO / hub when those routes exist:
    navigate to that origin with stored id
  else:
    navigate Classic with savedClientId
```

### 7. Classic activate refresh

When Classic becomes current with a `clientId` (enter or return):

- Load/select that client.
- Refresh invoice rail (desktop `LoadClientAsync` / `RefreshClientInvoices` / `OnViewActivated`).

This is what makes the new invoice appear after save-as-new → Back.

### 8. Price compare (viewer MVP)

On viewer load when `invoice.is_finalized`:

- For each line with `part_id`, fetch part (or one batch endpoint).
- If `part.base_price_cents != item.unit_price_cents`, set mismatch flag + catalog cents.
- UI: badge / row highlight + show catalog price; keep read-only unless "apply catalog" is already cheap.

Skip compare for estimates (match desktop optimization).

### 9. Capture call sites

Call `captureIfStartingInvoiceFlow` from every navigator that **enters** invoice flow from outside:

- Classic View → viewer
- Classic Edit / New → calculator
- (Later) project / WO invoice actions

Do **not** call capture when Viewer Edit → calculator.

### 10. Deep link

`#sysforge/invoice-view/123` opens Business panel (install gated) then viewer. No return context → Back falls through to dashboard or prior hash history.

---

## Files

| Path | Action |
|------|--------|
| `integrations/sysforge/static/js/views/invoice-viewer.js` | **Create** - load, render, Edit CTA, deactivate abort |
| `integrations/sysforge/static/js/invoice-return-context.js` | **Create** - capture / consume / clear |
| `integrations/sysforge/static/js/router.js` (or equivalent) | **Update** - `navigateToViewerAfterSaveAsNew`, `navigateAfterInvoiceSave`, `trimInvoiceFlowFromHistory`; register `invoice-view` |
| `integrations/sysforge/static/js/views/invoice-calculator.js` | **Update** - save-as-new → viewer; edit save → after-save return; clear edit state before leave |
| `integrations/sysforge/static/js/views/client-dashboard.js` | **Update** - on activate with `clientId`, select + refresh invoices; View button → viewer |
| `integrations/sysforge/static/js/views/render-invoice-readonly.js` | **Create** (optional) - shared header/lines markup |
| `integrations/sysforge/routes.py` (or invoice routes) | Ensure `GET /invoices/{id}` returns items + finalized + money fields; optional `GET /invoices/{id}/price-compare` |
| `tests/test_sysforge_invoice_viewer_nav.py` (and/or JS unit tests) | **Create** - see Tests |
| `Sysforge research/features/invoice-viewer.md` | Optional post-ship note: return-context + save-as-new stack |

**Desktop references (read-only):**

- `SysForge/Models/InvoiceNavigationReturnContext.cs`
- `SysForge/Services/NavigationService.cs` (`Capture*`, `Trim*`, `NavigateToInvoiceViewer*`, `NavigateAfterInvoiceSaveAsync`)
- `SysForge/Services/NavigationHistory.cs` (`RemoveCurrentEntry`)
- `SysForge/ViewModels/InvoiceViewerViewModel.cs` / `InvoiceViewerView.axaml`
- `SysForge/ViewModels/InvoiceCalculatorViewModel.cs` (`SaveAsNewInvoice`)
- `SysForge/ViewModels/InvoiceEditViewModel.cs` (`ComparePricesToDatabaseAsync`)
- `Plans/Open-Bugs-And-Investigations.md` BUG-008

---

## API / UI contracts

### REST

| Call | Role |
|------|------|
| `GET /api/sysforge/invoices/{id}` | Viewer header: id, name/display, client_id, dates, status, finalized, totals (integer cents) |
| `GET /api/sysforge/invoices/{id}/items` **or** items embedded | Line rows for readonly table |
| `GET /api/sysforge/clients/{id}` | Client display name if not embedded |
| `GET /api/sysforge/parts/{id}` or batch compare | Price compare |

**Suggested optional endpoint** (keeps UI dumb):

`GET /api/sysforge/invoices/{id}/price-compare` →  
`[{ item_id, part_id, unit_price_cents, catalog_price_cents, has_mismatch }]`  
Only meaningful when finalized; otherwise `[]` / 204.

No new write APIs required for viewer/return-context. Save-as-new remains calculator POST/clone from the P1 workstream.

### Router / JS contracts

```javascript
// Indicative public surface
captureInvoiceReturnContextIfStartingFlow()
trimInvoiceFlowFromHistory()
navigateToInvoiceViewer(invoiceId)                 // normal View
navigateToViewerAfterSaveAsNew(invoiceId, clientId)
navigateAfterInvoiceSave(savedClientId)
// Viewer Edit uses existing:
navigate('invoice-calculator', { invoiceId })
```

### Route ↔ desktop map

| Web | Desktop |
|-----|---------|
| `invoice-view/:id` | `NavigateToInvoiceViewerAsync` |
| save-as-new helper | `NavigateToInvoiceViewerAfterSaveAsNewAsync` |
| edit-save helper | `NavigateAfterInvoiceSaveAsync` |
| `invoice-calculator?invoiceId=` | `NavigateToInvoiceCalculatorEditAsync` |
| `client-dashboard?clientId=` | Classic `LoadClientAsync` / direct nav |

---

## UX contracts (save-as-new → viewer → back stack)

### Happy path (must pass QA)

| Step | User sees |
|------|-----------|
| Classic, client C, Edit invoice | Calculator with that invoice; client search **not** forced open |
| **Save as new Invoice** | Name dialog; cancel leaves calculator unchanged |
| Confirm name | Toast success; land on **read-only viewer** for **new** id; calculator edit state cleared |
| Viewer chrome | Title = new name; subtitle "Read-only view"; **Edit** enabled after load |
| **Back** | Classic Client Dashboard; **client C still selected**; invoice rail includes the **new** invoice |
| Viewer **Edit** then **Save Invoice** | Return to Classic (same client), not calculator, not a random hub |

### Stack rules (implementer checklist)

1. Opening calculator/viewer from Classic **captures** `{ origin: client-dashboard, clientId }`.
2. Viewer → Edit **does not** recapture.
3. Save-as-new **trims** calculator (and any invoice-flow tops) **before** pushing viewer.
4. After trim + viewer push, history top-under-viewer is Classic (or other origin), so Back skips calculator.
5. Normal edit save **trims** then **consumes** return context to restore origin + refresh.
6. Missing context → Classic with `savedClientId` (desktop fallback).

### Explicit failures (treat as bugs)

- Back from post-save-as-new viewer returns to calculator.
- Save-as-new leaves user editing the old invoice id.
- Viewer Edit clears origin so edit-save jumps to home dashboard with no client.
- New invoice missing from Classic list until full page reload.
- Viewer allows editing line cells.

### Price-compare UX

- Finalized invoice in viewer: mismatched lines visually flagged; show invoice cents vs catalog cents.
- Estimates: no compare noise.

---

## Tests / verification

### Automated

1. **Capture gate** - From `client-dashboard`, enter calculator → context set. From `invoice-view`, enter calculator → context unchanged.
2. **Trim** - Stack `[classic, calculator]` → trim → `[classic]`. Stack `[classic, calculator, viewer]` → trim → `[classic]`.
3. **Save-as-new nav** - After helper: current = `invoice-view` with new id; stack under it is classic (no calculator).
4. **After-save return** - With context Classic+C: lands on `client-dashboard` with `clientId=C` and refresh called.
5. **Fallback** - No context → Classic with `savedClientId`.
6. **Viewer Edit route** - Emits calculator `invoiceId`, never `invoice-edit` for this CTA.
7. **Price compare pure fn** - Same cents → no flag; different cents → flag (unit test without UI).

Prefer pure JS tests for context/trim/route helpers; Python API tests for GET invoice + optional compare endpoint.

### Manual QA (MASTER §8.4 + BUG-008)

1. Classic → Edit → **Save as new** → confirm name → viewer shows new invoice.
2. Back → same client selected; new invoice in rail.
3. View that invoice → Edit → Save → back to Classic with client selected.
4. View → Back (without save-as-new) still returns to Classic.
5. Finalized invoice with drifted catalog price shows mismatch in viewer.
6. Deep link `#sysforge/invoice-view/<id>` opens read-only viewer when plugin enabled.

### Regression anchors

- Desktop BUG-008 confirmed behavior.
- MASTER §6 checkbox: *Save as new: name dialog → new id → viewer → Back to Client Dashboard with client selected + list refresh*.
- MASTER §4: *Return context after save* (`67a4ed8b`, `21972123`).
- Do not regress P1 edit-save same-id/name contracts from `21e672a5` (owned by calculator workstream; smoke here after wiring return).

---

## Risks

| Risk | Mitigation |
|------|------------|
| History trim wrong → Back skips Classic or double-pops | Unit-test trim; only trim **invoice-flow** route keys; never trim classic/dashboard |
| Capturing on every calculator activate overwrites project origin | Capture **only** when current route is non-invoice (mirror desktop `IsInvoiceFlowViewModel`) |
| Save-as-new navigates before clear-edit → stale calculator on later cache hit | Clear `_editingInvoice` / equivalent **before** viewer navigate (chat 21972123) |
| Classic cached panel does not refresh list | `activate({ reason })` must reload invoices when `clientId` present |
| Price-compare N+1 part fetches | Batch endpoint or single compare API |
| Implementing project/WO return before those routes exist | Ship Classic + fallback now; keep context fields; wire origins when P2 projects land |
| Confusing early 21e672a5 "stay on new invoice in calculator" notes | Treat 21972123 viewer nav as superseding; checklist in calculator workstream must call viewer helper |
| Hash history vs in-memory stack diverge | Single writer: all save/back paths go through router helpers, not raw `history.back()` |

---

## Effort

**M** (medium)

| Slice | Estimate |
|-------|----------|
| Viewer panel + route + Edit CTA | ~1-1.5 days |
| Return context + history trim + save-as-new / after-save wiring | ~1-1.5 days |
| Classic refresh on return + QA fixes | ~0.5 day |
| Price-compare flags (viewer, finalized) | ~0.5-1 day |
| Automated tests | ~0.5 day |

**Total ~3-5 days** once calculator save-as-new, Classic dashboard, and nav lifecycle exist.  
If those dependencies are incomplete, this workstream blocks on them (do not invent a second router).

Larger if project/WO origin restore and "apply catalog price" mutations are required in the same PR; keep those as follow-ups to stay **M**.

---

## Implementation checklist

- [x] Route `invoice-view/:id` + viewer panel (read-only header + lines)
- [x] Viewer **Edit** → calculator `invoiceId` (disabled until loaded)
- [x] `invoice-return-context` capture / consume / clear with invoice-flow gate
- [x] `trimInvoiceFlowFromHistory` helper
- [x] Save-as-new → trim → viewer (clear calculator edit state first)
- [x] Edit save → trim → restore origin (Classic+client refresh; fallback `savedClientId`)
- [x] Classic activate refreshes invoice rail for selected client
- [x] Finalized price-compare flags on viewer
- [x] Tests: capture gate, trim, save-as-new stack, after-save return
- [ ] Manual QA: MASTER §8.4 save-as-new → viewer → Back

---

## Source notes

- **gap-manifest:** P2 high; depends on Classic + calculator save contracts; ships viewer, price-compare, return-context / history trim so post-save matches desktop.
- **MASTER Phase 2 / §6 / §8.4:** Exit criteria and checklist language for save-as-new → viewer → Back with client + list refresh.
- **21972123:** BUG-008 path; `NavigateToInvoiceViewerAfterSaveAsNewAsync` + history entry removal; calculator clears edit state before leave.
- **67a4ed8b:** `InvoiceNavigationReturnContext`; capture-on-flow-start; viewer Edit must not reset origin; `NavigateAfterInvoiceSaveAsync`; save-as-new trim without forcing dashboard before viewer.
- **21e672a5:** Save-as-new button + name dialog + clone semantics (P1 calculator). Post-save **stay on calculator** was later replaced by viewer navigation; port the button/contracts from this chat and the **nav target** from 21972123/67a4ed8b.
- **Research `invoice-viewer.md`:** Route `invoice-view/:id`; share render with edit; effort **M**; PDF out of MVP.
- **Desktop code:** Prefer current `NavigationService` / `InvoiceViewerViewModel` over older chat prose when they disagree (67a4ed8b trim-only save-as-new path is what the tree does today).
