# Nav lifecycle + View/Edit route contracts

| Field | Value |
|-------|-------|
| **Issue id** | `nav-lifecycle-view-edit-routes` |
| **Title** | Nav lifecycle + View/Edit route contracts |
| **Phase** | P1 |
| **Effort** | **M** |
| **Primary sources** | Chat [014ea2dd](../chat-reviews/014ea2dd-9086-4b38-a232-1af81abdd778.md) (CurrentView double-assign / CardClicked); SysForge `NavigationService` + `MainWindowViewModel.CurrentView`; `.cursor/rules/state-and-event-lifecycle.mdc`; research `06-frontend-routing.md` |
| **Manifest** | `gap-plans/gap-manifest.json` → this workstream |
| **Master plan** | `synthesis/MASTER-MIGRATION-PLAN.md` → Phase P1 navigation / invoice route contracts |

---

## Goal / success

Ship a SysForge web shell router where:

1. **View** always opens a **read-only invoice viewer**.
2. **Edit** always opens the **invoice calculator** loaded with that invoice (not a separate “edit form” for the Client Dashboard path).
3. Navigation **survives same-panel re-assign**: opening the same route/panel instance twice does not tear down live handlers (dashboard cards, View/Edit buttons, drafts → calculator wiring).
4. Outgoing panels get a clear **deactivate** hook; incoming panels get **activate** (refresh) without a full remount when the cached panel is reused.

**Done when:**

- Client Dashboard **View** → `#sysforge/invoice-view/:id` shows read-only data; no editable line grid.
- Client Dashboard **Edit** → `#sysforge/invoice-calculator?invoiceId=:id` (or equivalent) loads calculator in edit-existing mode.
- Viewer **Edit** CTA → same calculator edit route.
- Home dashboard card clicks still work after: open Client Dashboard → back → click another card (regression of BUG-001).
- Navigating Client Dashboard → View → Back → View again on the same invoice does not leave the shell with dead click handlers.
- Automated tests cover: route contracts, same-route re-enter, and handler survival after double apply.

---

## Current state

### SysForge desktop (source of truth)

**View / Edit contracts** (`ClientDashboardViewModel`):

| UI action | Navigation API | Target VM | Behavior |
|-----------|----------------|-----------|----------|
| **View** | `NavigateToInvoiceViewerAsync(invoiceId)` | `InvoiceViewerViewModel` | Read-only display; `EditInvoice` → calculator |
| **Edit** | `NavigateToInvoiceCalculatorEditAsync(invoiceId)` | `InvoiceCalculatorViewModel` | Calculator with existing invoice loaded |
| **New invoice** | `NavigateToInvoiceCalculatorWithClientAsync(clientId)` | `InvoiceCalculatorViewModel` | Calculator with client pre-selected |

Also: `InvoiceViewerViewModel.EditInvoice` → `NavigateToInvoiceCalculatorEditAsync`.  
`InvoiceEditViewModel` exists for a separate finalized-edit surface (`NavigateToInvoiceEditAsync`); **out of this workstream’s Client Dashboard View/Edit contract** (see Scope).

**Lifecycle bug that must not recur on web** (chat 014ea2dd / BUG-001 + BUG-002):

1. `NavigationService.NavigateToAsync` resolves a **cached** `Control` and raises `ViewChanged`.
2. `MainWindowViewModel.OnNavigationServiceViewChanged` → `ApplyNavigationResult` sets `CurrentView = view`.
3. Callers such as `NavigateToItemDirect` set `CurrentView = view` **again** with the **same** instance.
4. A setter that always unsubscribed *before* `SetProperty` removed `DashboardViewModel.CardClicked` on the no-op second assign, then skipped re-subscribe because `SetProperty` returned false.
5. Symptom: dashboard cards and Client Dashboard View/Edit appeared to “do nothing” after a navigation sync fix.

**Desktop fix (proven):**

- Unsubscribe only when `!ReferenceEquals(_currentView, value)`.
- Keep `ViewChanged` as the UI apply path; tolerate duplicate assigns of the same control.
- Rule: `.cursor/rules/state-and-event-lifecycle.mdc`.

**Desktop activation hooks** (`NavigationService`):

- Leaving a different VM type → `OnViewClosingAsync` (2s cap) then `OnViewDeactivated`.
- Entering a view → `OnViewActivated` (+ targeted refresh, e.g. `RefreshClientInvoices` on client dashboard).
- Invoice flow captures `InvoiceNavigationReturnContext` before first invoice-flow navigate; save/back can return to the origin screen.

### Odysseus web (target today)

- Plugin shell stub: `integrations/sysforge/static/js/index.js` — modal + status only; **no router, no View/Edit, no panel cache**.
- Research already maps destinations in `docs/research/sysforge/06-frontend-routing.md` (`invoice-view/:id`, calculator, client-dashboard, history stack, ViewCache LRU).
- Hash deep-link pattern proposed: `#sysforge/invoice-view/123`.
- No web equivalent yet of `ViewChanged` + same-instance re-apply safety.

### Gap

Web needs an explicit **route contract + panel lifecycle** layer before Client Dashboard and invoice UIs land. Without it, the first “wire both hashchange and openPanel” implementation will reintroduce silent dead handlers.

---

## Scope

### In scope

- `static/js/sysforge/router.js` (or plugin-local equivalent under `integrations/sysforge/static/js/`): navigate / back / apply / cache.
- Route table for P1 invoice + shell destinations used by View/Edit:
  - `dashboard`
  - `client-dashboard` (optional `?clientId=`)
  - `invoice-view/:id`
  - `invoice-calculator` with `invoiceId` and/or `clientId` query params
- Panel lifecycle API: `mount` / `activate` / `deactivate` / `unmount` with **same-panel re-assign** rules.
- Wiring Client Dashboard View/Edit buttons and Viewer Edit button to those routes (once those views exist, or via stub handlers + tests first).
- Hash sync (`#sysforge/...`) without fighting Odysseus chat session hashes.
- Unit/integration tests for router identity and handler survival.
- Short comment or ADR note in router pointing at the desktop `ReferenceEquals` lesson.

### Out of scope

- Full invoice calculator / viewer UI pixel port (separate feature plans; this workstream owns **routing contracts** and lifecycle).
- `InvoiceEditViewModel` / `invoice-edit/:id` finalized editor (can share lifecycle helpers later; not the Client Dashboard **Edit** target).
- PDF, email send, payments, client merge (deferred ops workstream).
- Projects / work orders / screw-map routes beyond registering placeholders if needed for history.
- Persisting navigation history across browser refresh (desktop also treats cross-restart history as non-bug / deferred).
- Changing Odysseus main-app section router (`sessions.js` hash for chats).

---

## Dependencies

| Depends on | Why |
|------------|-----|
| P0 plugin shell open/close (`integrations/sysforge`, feature flag, install gate) | Router lives inside the Business panel |
| Invoice GET API `GET /api/sysforge/invoices/{id}` | Viewer + calculator edit load |
| Client Dashboard panel (or minimal stub with View/Edit buttons) | End-to-end UX verification |
| Dashboard cards panel | Regression: card clicks after nested navigation |

| Soft / parallel | Why |
|-----------------|-----|
| Invoice return-context after save | Same history trim patterns; can follow in a thin follow-up if save flows are not ready |
| ViewCache LRU (max 5) | Performance; lifecycle rules must hold with or without cache |

**Blocks:** Client Dashboard View/Edit UX and any panel that subscribes shell-level events on “current panel” change.

---

## Concrete steps

### 1. Freeze the route contract (doc → code constants)

Define a single source of truth (e.g. `ROUTE` enum + `buildRoute` helpers):

| Intent | Route | Params | Notes |
|--------|-------|--------|-------|
| View invoice | `invoice-view` | `id` (path) | Read-only |
| Edit invoice (dashboard / viewer) | `invoice-calculator` | `invoiceId` | Loads existing invoice into calculator |
| New invoice for client | `invoice-calculator` | `clientId` | No `invoiceId` |
| Client hub | `client-dashboard` | optional `clientId` | |
| Home cards | `dashboard` | — | |

Reject ambiguous URLs in tests: `invoice-edit/:id` must **not** be what Client Dashboard Edit uses.

### 2. Implement `applyNavigation(next)` with identity checks

Pseudo-contract for the shell:

```text
applyNavigation(nextPanelKey, nextParams, nextElementOrController):
  prev = current
  sameSurface = prev != null
    && prev.panelKey == next.panelKey
    && shallowEqual(prev.params, next.params)
    && prev.controller === next.controller   // same cached instance

  if (!sameSurface):
    prev?.deactivate()
    unsubscribeShellHandlers(prev)          // only when surface changes
    current = next
    subscribeShellHandlers(current)         // dashboard cards, etc.
    current.activate({ reason: 'enter' })
    render(current)
  else:
    // SAME instance / same route re-apply (ViewChanged + openPanel duplicate)
    // DO NOT unsubscribe shell handlers
    current.activate({ reason: 'reapply' }) // optional refresh only
    // optional: update title / back affordance only
```

Map to desktop:

| Desktop | Web |
|---------|-----|
| `ReferenceEquals(_currentView, value)` | `controller ===` (or stable `panelId`) |
| Unsubscribe before swap | `unsubscribeShellHandlers` only on surface change |
| `SetProperty` true → subscribe | Subscribe only when surface changes |
| `OnViewActivated` | `activate({ reason })` |
| `OnViewDeactivated` | `deactivate()` when leaving a different surface |

### 3. Single writer for “current panel”

Prefer **one** apply path:

- Hashchange → `router.navigateFromHash`
- Sidebar / cards / View/Edit → `router.navigate(...)`
- Internal `navigate` always ends in `applyNavigation`

If a second caller must set the same panel (mirror of `NavigateToItemDirect` after `ViewChanged`), it must call `applyNavigation` again safely (no-op unsubscribe), not a raw `innerHTML = ''` remount.

### 4. History stack

- Push on `navigate` when the surface key or params change.
- Do **not** push on pure re-apply of the same surface.
- `back()` pops and `applyNavigation` without treating it as a fresh mount if cache hits.
- Cap stack (research: max 20) to match desktop `NavigationHistory` intent.

### 5. Wire View / Edit call sites

When Client Dashboard and Viewer land:

```text
View  → router.navigate('invoice-view', { id })
Edit  → router.navigate('invoice-calculator', { invoiceId })
Viewer Edit → router.navigate('invoice-calculator', { invoiceId })
```

Do not route Edit to `invoice-edit` for these buttons.

### 6. Hash protocol

- Format: `#sysforge/<route>[/id][?query]`
- On SysForge panel open: if hash is already `#sysforge/...`, apply it; else default `dashboard`.
- On navigate: update hash with `history.replaceState` / `pushState` carefully so Odysseus chat `hashchange` handlers ignore non-`sysforge` prefixes (guard at the top of the SysForge listener).
- Deep link: `/app#sysforge/invoice-view/123` opens plugin panel then applies route (install/feature gated).

### 7. Cache policy

- Cache controllers by `panelKey` (and for parameterized panels, by `panelKey + id` or reload params on activate).
- Reusing a cached calculator with a **different** `invoiceId` is a **param change** → treat as surface change for data load; still avoid tearing unrelated shell subscriptions.
- Leaving invoice-view for calculator: deactivate viewer (cancel in-flight fetch AbortController), activate calculator.

### 8. Document the invariant

Add a 5–10 line comment at `applyNavigation` (and optionally a one-pager under `docs/migration-audit/` only if the team wants it central). Point to BUG-001/002 and `state-and-event-lifecycle.mdc`. Do not edit `AI_LEARNINGS.md` unless asked.

---

## Files

| Path | Action |
|------|--------|
| `integrations/sysforge/static/js/router.js` | **Create** — navigate, back, apply, history, hash |
| `integrations/sysforge/static/js/panel-lifecycle.js` | **Create** (optional split) — subscribe helpers, identity compare |
| `integrations/sysforge/static/js/index.js` | **Update** — open panel → init router; close → deactivate current |
| `integrations/sysforge/static/js/views/dashboard.js` | **Create/Update** — card clicks → `navigate`; shell subscribes once per mount |
| `integrations/sysforge/static/js/views/client-dashboard.js` | **Update** — View/Edit buttons → route helpers |
| `integrations/sysforge/static/js/views/invoice-viewer.js` | **Update** — Edit CTA → calculator route; read-only UI |
| `integrations/sysforge/static/js/views/invoice-calculator.js` | **Update** — honor `invoiceId` / `clientId` on activate |
| `integrations/sysforge/manifest.json` | Ensure static assets listed if the plugin copies files on install |
| `tests/test_sysforge_router.js` or `tests/test_sysforge_nav_lifecycle.py` | **Create** — see Tests |
| `docs/research/sysforge/06-frontend-routing.md` | Optional: add “same-panel re-apply” subsection after implementation |

**Desktop references (read-only):**

- `SysForge/Services/NavigationService.cs` — `ViewChanged`, invoice navigate APIs, activate/deactivate
- `SysForge/ViewModels/MainWindowViewModel.cs` — `CurrentView` setter (~99–160), `ApplyNavigationResult`, `NavigateToItemDirect`
- `SysForge/ViewModels/ClientDashboardViewModel.cs` — `ViewInvoice` / `EditInvoice`
- `SysForge/ViewModels/InvoiceViewerViewModel.cs` — read-only + Edit → calculator
- `SysForge/.cursor/rules/state-and-event-lifecycle.mdc`
- `SysForge/Plans/Open-Bugs-And-Investigations.md` — BUG-001, BUG-002

---

## API / UI contracts

### REST (consumed, not invented here)

| Call | Used by |
|------|---------|
| `GET /api/sysforge/invoices/{id}` | Viewer activate; calculator edit activate |
| `GET /api/sysforge/clients/{id}` | Optional header on viewer / calculator |

No new REST endpoints required for this workstream.

### Router API (JS)

```javascript
// Public surface (names indicative)
navigate(routeKey, params = {}, { replace = false } = {})
back()
getCurrent() // { routeKey, params, panelKey }
applyFromHash(hash)
```

### UI events (shell)

| Event / hook | When |
|--------------|------|
| `activate({ reason: 'enter' \| 'reapply' \| 'back' })` | Panel becomes current |
| `deactivate()` | Panel no longer current (different surface) |
| Shell handler bind | Only on enter of a new controller instance |
| Shell handler unbind | Only when leaving that controller instance |

### Route ↔ desktop mapping

| Web route | Desktop API |
|-----------|-------------|
| `invoice-view/:id` | `NavigateToInvoiceViewerAsync` |
| `invoice-calculator?invoiceId=` | `NavigateToInvoiceCalculatorEditAsync` |
| `invoice-calculator?clientId=` | `NavigateToInvoiceCalculatorWithClientAsync` |
| `client-dashboard` | `NavigateToClientDashboardAsync` |
| `dashboard` | Dashboard `NavigateToAsync` / cards |

---

## UX contracts

| Action | User-visible result |
|--------|---------------------|
| **View** | Read-only invoice: line items, totals, client; **no** cell editing; primary secondary action **Edit** goes to calculator |
| **Edit** | Invoice calculator with that invoice loaded; editable lines/totals; save paths owned by calculator workstream |
| **Back** from viewer/calculator | Return toward Client Dashboard / prior stack entry; invoice list usable |
| **Dashboard card** after nested nav | Cards remain clickable (no silent no-op) |
| Same invoice **View** twice | Viewer shows data; no blank shell; no duplicate stacked handlers firing twice |

**Explicit non-goal for Edit:** opening a distinct “Invoice Edit” AXAML clone (`InvoiceEditView`) from Client Dashboard. Desktop production path uses the **calculator**.

---

## Tests / verification

### Automated

1. **Route builders** — View/Edit helpers emit the table above; Edit never emits `invoice-edit`.
2. **Same-instance re-apply** — Mount dashboard controller; `apply` twice with same controller; assert subscribe count === 1; simulate card click still invokes navigate.
3. **Surface change** — Dashboard → client-dashboard → dashboard; assert dashboard deactivate then re-subscribe; card click works.
4. **Param change** — `invoice-view/1` → `invoice-view/2`: deactivate/load new id; no duplicate global listeners.
5. **Hash round-trip** — `navigate` → hash string → `applyFromHash` → same current route.
6. **History** — A → B → back → A; re-apply of A does not push extra history entry.

Prefer a small pure JS test (Node or pytest + jsdom if the repo already uses that). If only Python exists today, test the route-table module extracted as pure functions first.

### Manual QA (mirror desktop BUG-001/002)

1. Open Business → Dashboard → Client Dashboard → **View** invoice → confirm read-only → Back.
2. **Edit** same invoice → confirm calculator → Back.
3. Return to Dashboard → click another card (e.g. Drafts or Calculator) → must open.
4. Repeat View on same invoice twice via list buttons.
5. Deep link `#sysforge/invoice-view/<id>` with plugin installed.

### Regression anchors

- Desktop BUG-001 / BUG-002 fixed behavior must hold on web.
- Chat 014ea2dd finding: double assign of active content must not unwire handlers.

---

## Risks

| Risk | Mitigation |
|------|------------|
| Remounting via `innerHTML` on every hashchange | Cache controllers; `activate` vs remount; never wipe shell listeners in re-apply |
| Two writers (hashchange + button) both “mount” | Funnel through `applyNavigation`; identity short-circuit |
| Confusing `invoice-edit` vs calculator Edit | Constants + tests; UI copy says Edit but route is calculator |
| Abort/fetch leaks on fast View→Edit | `deactivate` aborts pending GETs (AbortController per panel) |
| Odysseus global `hashchange` conflicts | Namespace `#sysforge/`; early-return in foreign handlers |
| Over-caching stale invoice data | On activate with `invoiceId`, always refetch or compare etag/updated_at |

---

## Effort

**M** (medium)

- Router + lifecycle + hash + tests: ~2–4 days.
- Wiring View/Edit once dashboard/viewer stubs exist: ~0.5–1 day.
- Full visual ports of viewer/calculator are **not** included in this estimate (separate L items).

---

## Implementation checklist

- [ ] Route constants + builders for View / Edit / New
- [ ] `applyNavigation` with same-surface short-circuit
- [ ] History push rules (no push on re-apply)
- [ ] Hash `#sysforge/...` sync + deep link open
- [ ] Dashboard shell handler subscribe/unsubscribe gated on identity
- [ ] Client Dashboard View → viewer; Edit → calculator
- [ ] Viewer Edit → calculator
- [ ] Tests for double-apply and route contracts
- [ ] Manual QA walkthrough (BUG-001/002 web equivalents)

---

## Source notes

- **gap-manifest / MASTER-MIGRATION-PLAN:** This issue is Phase **P1**; treat navigation lifecycle and View/Edit contracts as prerequisites for invoice UI fill-the-gap work that assumes working panel switches.
- **014ea2dd:** View/Edit navigation + dashboard card regression → `state-and-event-lifecycle` rule; desktop fix is `ReferenceEquals` gate on `CurrentView`.
- **NavigationService:** Invoice navigate methods and `ViewChanged` are the behavioral spec for web `navigate` + apply.
- **Research `06-frontend-routing.md`:** Target file layout and route keys; this plan adds the missing same-panel re-assign invariant those notes omit.
