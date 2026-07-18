# Classic four-column Client Dashboard

| Field | Value |
|-------|-------|
| **Issue id** | `classic-client-dashboard` |
| **Title** | Classic four-column Client Dashboard |
| **Phase** | P2 |
| **Effort** | **L** |
| **Priority** | high |
| **Domain** | clients |
| **Primary sources** | Chat [e24feae4](../chat-reviews/e24feae4-31c7-4770-a8cd-3180e82f0415.md) (Classic wins); [6bba6919](../chat-reviews/6bba6919-90f5-4c2c-959c-b6fb279f5abd.md) (SearchListSelection / invoice rail); [920df407](../chat-reviews/920df407-41fd-4f6d-a38d-dc5c4065a110.md) (query == DisplayName → no auto-open); SysForge Classic AXAML/VM; research `Sysforge research/features/client-dashboard.md`; `Plans/UI-Plans/Client-Dashboard-Prototypes.md` |
| **Manifest** | `gap-plans/gap-manifest.json` → `classic-client-dashboard` |
| **Master plan** | `synthesis/MASTER-MIGRATION-PLAN.md` → Phase 2 *Classic dashboard daily loop* |
| **Depends on** | `clients-crud-fts-duplicates`, `invoice-calculator-save-contracts`, `nav-lifecycle-view-edit-routes` |

---

## Goal / success

Ship the **only** Client Dashboard product surface in Odysseus: the Classic **four-column workspace** (invoice rail | center preview | projects | client info/edit), with compact **overlay search** and inline **Address/Notes** edit.

This is the daily hub after calculator save: pick a client → see invoices → preview without leaving → View/Edit → edit client in place.

**Done when:**

1. Business **Clients** card (and any deep link) opens **Classic only**; no A/B layout picker, no DataGrid hub as default.
2. Layout is four columns at desktop width: **Invoices | Preview | Projects | Client info**.
3. Search is a **thin bar**; results/recent list is an **overlay** (does not push layout height).
4. Empty search shows up to **6 session-recent clients**; typing runs FTS typeahead (name/phone/email).
5. Clearing the search box **keeps** the selected client and invoice rail (`SearchListSelection` contract).
6. Programmatic fill of the search field with the selected client's `display_name` (deep link / pick) **does not** open the overlay.
7. Invoice rail shows **cards** (name, status, total); click loads **in-page preview** (header meta + line items).
8. Preview **Edit** navigates to calculator edit route; preview **View / Full screen** navigates to read-only viewer route (routes from `nav-lifecycle-view-edit-routes`).
9. Client column supports read mode + inline edit with **Address** and multi-line **Notes** (plus name/phone/email).
10. On panel **activate** (return from calculator/viewer), invoice list **refreshes** so new/updated invoices appear.
11. Smoke: Dashboard card → Classic → select client → preview → View → Back → Edit → Save → Back → Classic still live; cards still clickable.

---

## Current state

### SysForge desktop (source of truth)

**Product decision (e24feae4, May 2026):** Classic is the production Client Dashboard. Onboard / Preview+ / Unified / Stacked / Timeline (and earlier Cards/Hub/Split) were **retired**. Do not port them.

| Piece | Path |
|-------|------|
| Classic view | `SysForge/Views/Sandbox/ClientDashboardWireframeClassicView.axaml` |
| Classic VM | `SysForge/ViewModels/Sandbox/ClientDashboardWireframeClassicViewModel.cs` (thin subclass) |
| Shared Classic logic | `SysForge/ViewModels/Sandbox/ClientDashboardWireframeViewModel.cs` |
| Base CRUD/search/edit | `SysForge/ViewModels/ClientDashboardViewModel.cs` |
| Search overlay | `Views/Sandbox/ClientSearchOverlayBar.axaml` (+ `SearchOverlayPopupSizing`) |
| Invoice preview | `Views/Sandbox/InvoicePreviewPanel.axaml` |
| Keyboard helper | `Views/Sandbox/ClientDashboardSearchHelper.cs` |
| Doc | `Plans/UI-Plans/Client-Dashboard-Prototypes.md` |
| Nav target | `NavigationService.NavigateToClientDashboardAsync` → `ClientDashboardWireframeClassicViewModel` |

**Column map (Classic AXAML `ColumnDefinitions="220,*,200,280"`):**

| Col | Content |
|-----|---------|
| 0 | Invoice cards for `SelectedClient` (`ClientInvoices` / `HasInvoices`) |
| 1 | `InvoicePreviewPanel` (Edit / Full screen / Create project CTA) |
| 2 | Projects list (`ClientProjects`); empty → "No projects for this client." |
| 3 | Client summary + inline edit (Address, Notes, …) |

**Older `ClientDashboardView` (DataGrid hub):** still in repo for reference; **not** on home card / deep links. Web must not revive it as the default.

**Session MRU:** in-memory recent-6 in wireframe VM (`MaxRecentClients = 6`). Persistent `LastInteractedAt` / `GetRecentClients` is **deferred** (`future-ui-mru-shell-polish`).

**Projects column:** later chat `c6ee4808` bound a **real** list (not "Coming later"). Full project detail + create-from-invoice depth is owned by `projects-wo-four-column`; Classic must host the column and list API when available.

### Odysseus web (target today)

| Area | Status |
|------|--------|
| Plugin shell | Stub modal / status (`integrations/sysforge/static/js/index.js`) |
| Clients API/UI | Missing until `clients-crud-fts-duplicates` |
| Invoice APIs/calculator | Missing until `invoice-calculator-save-contracts` |
| Router + View/Edit routes | Missing until `business-shell-dashboard-router` + `nav-lifecycle-view-edit-routes` |
| Client Dashboard view | **Missing** (research proposes `client-dashboard.js`) |

**Gap:** no client workspace at all. P1 clients list/edit is a thin CRUD surface; Classic is the real shop hub.

---

## Scope

### In scope

- Route `client-dashboard` (optional `?clientId=` / hash `#sysforge/client-dashboard?clientId=`).
- Classic four-column HTML/CSS layout + view module.
- Compact search overlay: recent-6 (session), FTS results, keyboard Up/Down/Enter, focus/blur/outside dismiss.
- Selection model: `selectedClient` vs `searchListSelection` (clear query ≠ deselect).
- Overlay suppress when `query.trim()` equals selected `display_name` (case-insensitive).
- Invoice rail cards + center preview panel (meta + line-item table).
- Preview actions wired to existing View/Edit routes.
- Inline client edit including **Address** + **Notes**; Save/Cancel via clients API.
- Panel `activate` → refresh invoices (and projects list if API exists).
- Home **Clients** card → Classic (replace any P1 placeholder clients list as the primary entry, or keep a thin "All clients" secondary if already shipped—Classic remains the card target).
- Empty states: no client selected; no invoices; no projects.
- CSS for overlay width = search bar width on first open (avoid narrow-then-wide bug class).

### Out of scope

- **Retired prototype layouts:** Onboard, Preview+, Unified, Stacked, Timeline, Cards, Hub, Split, Unified client+invoice search.
- Old DataGrid-only hub as product default.
- Persistent MRU / default-open last client (`future-ui-mru-shell-polish`).
- Full invoice **viewer** UI and save-as-new return-context trim (`invoice-viewer-return-context`); Classic only **calls** View route.
- Calculator create/edit/save contracts (`invoice-calculator-save-contracts`); Classic only navigates with `invoiceId` / `clientId`.
- Projects schema, create-from-invoice dialog, four-column project detail (`projects-wo-four-column`). Host a list + navigate when that stream lands; until then empty-state copy is fine (no permanent "Coming later" marketing stub).
- Client acceptance dialog, client merge tool, PDF/email/payments.
- Phase 9 `InvoiceEditView` / price-compare as Classic **Edit** target (desktop Edit → calculator; keep that).
- Avalonia ViewLocator / XAML loader bugs (desktop-only); do treat "nav looks dead" as web QA.

---

## Dependencies

| Depends on | Why |
|------------|-----|
| `clients-crud-fts-duplicates` | `GET/PUT` client, `GET .../clients/search`, display fields including address/notes |
| `invoice-calculator-save-contracts` | `GET /invoices?client_id=`, `GET /invoices/{id}` (+ items) for rail + preview; Edit opens calculator |
| `nav-lifecycle-view-edit-routes` | `client-dashboard`, `invoice-view/:id`, `invoice-calculator?invoiceId=` routes; activate/deactivate; same-panel re-enter |
| Soft: `business-shell-dashboard-router` | Clients card + modal host (usually already done before P2) |

| Soft / parallel | Why |
|-----------------|-----|
| `invoice-viewer-return-context` | Full viewer + Back stack; Classic View button can land on stub viewer first |
| `projects-wo-four-column` | Fills Projects column + preview "Create project" CTA; Classic ships column host first |

**Blocks:** `invoice-viewer-return-context`, `projects-wo-four-column`, `future-ui-mru-shell-polish` (manifest).

---

## Concrete steps

### 1. Confirm desktop contracts (0.5 day)

1. Re-read Classic AXAML + `ClientDashboardWireframeViewModel` + `ClientDashboardViewModel` (`SearchListSelection`, `LoadClientAsync`, `HasInvoices`, preview commands).
2. Re-read chats e24feae4 / 6bba6919 / 920df407 checklists; treat **code + 6bba** as truth for clear-search (**keep** client), not any mangled "clear → deselect" wording in older matrix snippets.
3. Skip all retired prototype files; if found in git history, do not revive.

### 2. Register route + Clients card target (0.5 day)

1. In plugin `router.js`, register `client-dashboard` with `mount` / `activate` / `deactivate`.
2. Point Business dashboard **Clients** card at `navigate('client-dashboard')`.
3. Support `params.clientId` / hash query: on mount/activate, `GET /clients/{id}`, set selection, fill search text with `display_name`, **suppress overlay**.
4. On activate: refresh `GET /invoices?client_id=` (mirror `RefreshClientInvoices` / `NotifyViewActivated`).

### 3. Build Classic layout shell (1–2 days)

1. Add `integrations/sysforge/static/js/views/client-dashboard.js` (or `static/js/sysforge/views/client-dashboard.js` if host path already chosen—stay consistent with shell plan).
2. CSS grid: four columns ≈ `220px | 1fr | 200px | 280px`; stack to 2×2 or vertical on narrow widths without inventing a second product layout.
3. Top row: search overlay control only (thin bar).
4. Wire empty-state copy from Classic AXAML.

### 4. Search overlay + selection model (1–2 days)

1. Reuse or wrap `clientSearch.js` from clients-crud (debounce ~200–300 ms, abort).
2. State:
   - `selectedClient` — drives columns; survives query clear.
   - `searchListSelection` — only non-null picks update `selectedClient`.
   - `searchQuery`, `overlayOpen`, `sessionRecent[]` (max 6).
3. Empty query + overlay open → show session recent (seed from first N active clients once if recent empty—desktop seeds from DB take(6); acceptable).
4. Non-empty query → FTS results; **no Add New row on Classic** (Add New stays on calculator).
5. Guards:
   - Clear query → clear results/recent mode; **do not** null `selectedClient`.
   - If `selectedClient` and query equals `display_name` (trim, case-insensitive) → `overlayOpen = false` and skip opening on programmatic set.
6. Open overlay on focus / user typing (when guard allows); close on pick, Escape, light-dismiss outside.
7. Keyboard: Down/Up move highlight; Enter selects highlighted (or first); match `ClientDashboardSearchHelper`.
8. Overlay panel width = search input width on first open (ResizeObserver / measure).

### 5. Invoice rail + preview panel (1–2 days)

1. List: `GET /api/sysforge/invoices?client_id={id}` (include incomplete/estimates per desktop `includeIncomplete: true`).
2. Card fields: `display_name` (or name fallback), `display_status` / status, `final_total` (cents → currency helper), optional date.
3. Explicit `hasInvoices` boolean for empty vs list (do not rely on fragile length-only CSS).
4. Click card → `selectedInvoiceId` → `GET /invoices/{id}` → fill preview (client name, total, status, date, line items: part name, qty, unit, line total).
5. Preview CTAs:
   - **Edit** → `navigate('invoice-calculator', { invoiceId })` (must change route, not only preload—nav lifecycle contract).
   - **Full screen / View** → `navigate('invoice-view', { id })`.
   - **Create project from invoice** → hide or disable until `projects-wo-four-column`; do not ship fake success.
6. Highlight selected card; clear preview when client changes.

### 6. Client info + inline edit (1 day)

1. Read: display name, phone, email, address, notes.
2. Edit: first/last (or nickname if API has it), phone, email, address, notes (`textarea`).
3. Save → `PUT/PATCH /clients/{id}`; refresh selected client from response; exit edit mode.
4. Cancel → discard draft fields.
5. Changing `selectedClient` while editing cancels edit (desktop behavior).

### 7. Projects column host (0.5 day)

1. Render list from `GET /api/sysforge/projects?client_id=` when endpoint exists; else empty state "No projects for this client."
2. Click → `navigate('project-detail', { id })` only if route registered; otherwise no-op toast "Projects coming in next phase."
3. Do not hardcode "Coming later" as permanent chrome once projects ship.

### 8. New invoice affordance (0.5 day)

1. Mirror desktop: with client selected, **Create invoice** → calculator with `clientId` preselected (`NavigateToInvoiceCalculatorWithClientAsync`).
2. Optional Refresh control for invoice rail (desktop has it; activate refresh may be enough).

### 9. Tests + smoke (1 day)

1. Unit tests for selection/overlay guards (pure JS).
2. API integration: invoices by client + client get used by the view.
3. Manual smoke checklist below.

---

## Files

### Create (Odysseus)

| Path | Role |
|------|------|
| `integrations/sysforge/static/js/views/client-dashboard.js` | Classic mount/activate; selection; preview |
| `integrations/sysforge/static/js/components/client-search-overlay.js` | Overlay bar + keyboard + width sync (or fold into view if tiny) |
| `integrations/sysforge/static/css/client-dashboard.css` | Four-column grid + overlay stacking |
| `tests/test_sysforge_client_dashboard.py` and/or `tests/js/` overlay unit tests | Contracts |

### Touch

| Path | Role |
|------|------|
| `integrations/sysforge/static/js/router.js` | Register `client-dashboard` |
| `integrations/sysforge/static/js/index.js` / dashboard cards | Clients card → Classic |
| `integrations/sysforge/static/js/clientSearch.js` | Shared search fetch (from clients-crud) |
| `integrations/sysforge/routes.py` | Only if list-by-client invoice route missing from calculator stream |
| `integrations/sysforge/README.md` | One-line: Classic Client Dashboard |

### Desktop reference only (do not port blindly)

| Path | Role |
|------|------|
| `ClientDashboardWireframeClassicView.axaml` | Layout proportions + empty copy |
| `ClientDashboardWireframeViewModel.cs` | MRU, preview load, overlay open flags |
| `ClientDashboardViewModel.cs` | `SearchListSelection`, edit fields, invoice load |
| `ClientSearchOverlayBar.*`, `InvoicePreviewPanel.*` | Overlay + preview UX |
| `ClientDashboardView.*` | **Reference / retired default** |

---

## API / UI contracts

Assume plugin prefix `/api/sysforge` and inactive → 404.

### Required (from dependency streams)

| Method | Path | Use |
|--------|------|-----|
| `GET` | `/clients/search?q=&limit=` | Overlay typeahead |
| `GET` | `/clients/{id}` | Deep link / refresh after save |
| `PUT`/`PATCH` | `/clients/{id}` | Inline edit (body includes `address`, `notes`, …) |
| `GET` | `/invoices?client_id=` | Invoice rail (`include_incomplete=1` if needed) |
| `GET` | `/invoices/{id}` | Preview header + items |

### Optional this stream / next stream

| Method | Path | Use |
|--------|------|-----|
| `GET` | `/projects?client_id=` | Projects column (`projects-wo-four-column`) |
| `POST` | `/projects/from-invoice` | Preview CTA (later) |

### Router / UI

| Action | Route / behavior |
|--------|------------------|
| Open Classic | `client-dashboard` ; optional `clientId` |
| Preview Edit | `invoice-calculator` + `invoiceId` (**navigate**) |
| Preview View | `invoice-view/:id` (**navigate**) |
| Create invoice | `invoice-calculator` + `clientId` |
| Activate Classic | Refresh invoices for current `selectedClient` |

### Client JSON fields used by Classic

At minimum: `id`, `display_name` (or first/last), `phone`, `email`, `address`, `notes`. Money on invoices: integer cents via shared money helpers.

---

## UX contracts

### Overlay search

| Rule | Detail | Source |
|------|--------|--------|
| Compact bar | Results in overlay/popup over workspace; not a permanent tall list | e24feae4 |
| Empty → recent 6 | Session MRU; cap 6; label "Recent clients" | Classic wireframe |
| Clear keeps client | `searchListSelection` null on clear; `selectedClient` unchanged | 6bba6919 |
| No auto-open on name fill | If query == selected `display_name` (ignore case), keep overlay closed | 920df407 + MASTER overlay contract |
| Open on user intent | Focus / typing (when guard allows); close on pick / outside / blur | `ClientSearchOverlayBar` |
| Keyboard | Up / Down / Enter | SearchHelper / 6bba6919 |
| Width | First open matches search field width | `SearchOverlayPopupSizing` |
| Matches only | Classic overlay: **no** Add New sentinel (calculator owns Add New) | Classic AXAML |

### Invoice cards + preview

| Rule | Detail | Source |
|------|--------|--------|
| Cards not DataGrid | Name, status, total (date optional) | e24feae4 Classic |
| Select → in-page preview | Do not leave Classic to see line items | `InvoicePreviewPanel` |
| Empty rail | "Select a client first." / no-invoices empty when selected | Classic AXAML + 6bba |
| `hasInvoices` | Explicit flag for list vs empty | 6bba6919 |
| Edit | Calculator edit route (visible navigation) | 6bba / nav-lifecycle |
| View / Full screen | Read-only viewer route | same |
| Stale list | Refresh on activate after save/return | 6bba `NotifyViewActivated` |

### Client column

| Rule | Detail |
|------|--------|
| Inline edit | Address + multi-line Notes required |
| Save/Cancel | Save persists; Cancel discards |
| No client | "Pick a client to see details." |

### Projects column

| Rule | Detail |
|------|--------|
| Real list when API exists | Not a permanent "Coming later" stub | MASTER / c6ee4808 |
| Empty | "No projects for this client." |

---

## Tests / verification

### Automated

1. **Selection:** set `selectedClient`, clear `searchQuery` → selected still set; invoice fetch not cleared by query alone.
2. **Overlay guard:** `selectedClient` + query = display name → `overlayOpen === false`; change one character → guard lifts.
3. **MRU:** pick clients A,B,… → recent list order updates, length ≤ 6.
4. **API:** `GET /invoices?client_id=` returns only that client's rows; preview `GET /invoices/{id}` includes items.
5. **Router:** navigate Classic → View → Back → activate called / invoices refreshed (hook into nav-lifecycle tests).
6. **Plugin gate:** inactive plugin → routes 404; no Classic mount.

### Manual smoke (MASTER §8.4 + Phase 2)

- [ ] Clients card opens Classic four-column only (no prototype chooser).
- [ ] Search empty → recent; type → matches; Enter selects; overlay closes.
- [ ] Clear search → client + invoices remain.
- [ ] Deep link / return with clientId → name in box, overlay closed.
- [ ] Invoice card → preview meta + lines; Edit → calculator; View → viewer.
- [ ] Edit client Address/Notes → Save → read mode shows new values.
- [ ] Save invoice from calculator → Back/activate → new row visible on Classic.
- [ ] After Classic → View → Back → Dashboard card still works (lifecycle).
- [ ] Narrow viewport: usable stacked layout; overlay still dismissible.

---

## Risks

| Risk | Mitigation |
|------|------------|
| Rebuilding retired A/B layouts | Explicit out-of-scope list; Classic AXAML only |
| Clear-search deselects client | Enforce `searchListSelection` split; unit test |
| Overlay opens on edit/deep link | DisplayName equality guard on Classic + calculator |
| Stale invoice rail after save | `activate` refresh mandatory |
| View/Edit "does nothing" | Depend on nav-lifecycle; never mutate calculator state without `navigate` |
| Projects CTA half-wired | Disable until projects stream; empty list OK |
| Confusing P1 clients list vs Classic | Clients **card** → Classic; optional secondary "manage all" only if needed |
| Money/format drift | Use shared cents → display helpers from schema/money stream |
| Large single JS file | Prefer overlay + preview helpers; keep under one view module |

---

## Effort

**L** (about 6–9 focused days after dependencies land).

| Slice | Size |
|-------|------|
| Route + layout shell | M |
| Overlay + selection guards | M |
| Invoice cards + preview | M |
| Client inline edit | S |
| Projects column host | S |
| Tests + smoke polish | S |

Research `client-dashboard.md` also rates port effort **L**; this plan matches that once P1 clients + invoices + router exist. Without those dependencies, do not start Classic UI beyond a non-interactive layout sketch.
)
