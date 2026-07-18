# business-shell-dashboard-router — Business dashboard shell + inner router

| Field | Value |
|-------|-------|
| **Issue id** | `business-shell-dashboard-router` |
| **Title** | Business dashboard shell + inner router |
| **Phase** | P0 |
| **Priority** | critical |
| **Domain** | shell |
| **Depends on** | `schema-money-utc-foundation` |
| **Unlocks** | `clients-crud-fts-duplicates`, `parts-placeholders-merge`, `drafts-service-autosave`, `business-settings-mvp`, `nav-lifecycle-view-edit-routes`, `diagnostics-readonly-panel`, `future-ui-mru-shell-polish` |
| **Sources** | gap-manifest entry; MASTER §5 Phase 0 / §8.2; feature-gap-matrix §1; SysForge `DashboardViewModel` / `NavigationService` / `MainWindowViewModel`; odysseus `integrations/sysforge/static/js/index.js` |

---

## Goal / success

**Goal:** After install, opening Business Management shows a real shop home (card dashboard) and a multi-view inner router, not a status stub. Feature-flag install/uninstall stays intact. Domain modules (clients, calculator, drafts, parts) plug into named routes later without rewriting the shell.

**Success (exit criteria):**

1. With `features.sysforge === true`, rail/sidebar open Business into a **dashboard** with four cards: Calculator, Clients, Drafts, Parts.
2. Clicking a card navigates inside the Business modal to that view via a shared `router.js` (view cache + in-session back stack).
3. Back returns to the previous Business view; Home/Dashboard control returns to the card grid.
4. Closing and reopening Business restores the last route **or** lands on dashboard (pick one; document it; prefer restore-last for session parity with desktop cache).
5. When plugin is inactive: nav hidden, `/api/sysforge/*` still 404, no Business shell scripts required for host boot.
6. Placeholder module views render titled “coming in P1” panels (no domain APIs required for this workstream).
7. Manual + automated checks in § Tests/verification pass.

**Non-goals for “done”:** Real CRUD, Classic Client Dashboard, invoice save contracts, settings UI, diagnostics panel, persistent nav history across browser restart.

---

## Current state

### Desktop (SysForge) — reference behavior

| Piece | Location | Behavior to mirror (web-adapted) |
|-------|----------|----------------------------------|
| Home cards | `SysForge/ViewModels/DashboardViewModel.cs`, `Views/DashboardView.axaml` | WrapPanel of cards; click raises `CardClicked` → navigate to target VM |
| Sidebar + chrome | `MainWindowViewModel.cs` | Sidebar items; title; back; `CurrentView` is single writer for visible content |
| Router | `Services/NavigationService.cs` | `NavigateToAsync` / `NavigateBackAsync`; caches views; history stack |
| View cache | `Services/ViewCache.cs` | Max 5 views; LRU eviction; keyed by view type |
| Lifecycle pitfall | `MainWindowViewModel.CurrentView` setter | Detach event handlers **only** when control reference changes (`!ReferenceEquals`); duplicate same-instance assign must not kill `CardClicked` |

Desktop cards today: Quick Invoice Calculator, Client Dashboard, Projects.  
**P0 web cards follow MASTER Phase 0**, not Projects: Calculator / Clients / Drafts / Parts.

Desktop sidebar also lists Invoice Calculator, Placeholder Merge, Diagnostics. Web P0 can use a thin **inner nav** (Dashboard + Back + optional module links) inside the existing Odysseus modal; do not rebuild Avalonia chrome.

### Odysseus (odysseus-sysforge) — what exists

| Piece | Location | State |
|-------|----------|--------|
| Install gate | `integrations/sysforge/install.py`, `uninstall.py`, `manifest.json`, `src/settings.py` (`sysforge: false`) | Done |
| Host nav | `static/index.html` (`tool-sysforge-btn`, `rail-sysforge`); `static/app.js` `PLUGIN_NAV` + deep link `/business` | Done; gated by feature flag |
| Stub UI | `integrations/sysforge/static/js/index.js` | Modal + status copy + `GET /api/sysforge/status` only |
| API | `integrations/sysforge/routes.py` | `/status` only; 404 when inactive |
| Static mount | `app.py` → `/static/plugins/sysforge` | Done |
| Tests | `tests/test_sysforge_plugin.py` | Install/catalog/gate only |

**Gap:** No dashboard, no inner sidebar/tabs, no `router.js`, no view cache, no back stack. Opening Business feels like an empty product (MASTER §1 / matrix §1 “Install succeeds → empty product”).

### Research targets (paths may drift)

- `Sysforge research/features/shell-navigation-dashboard.md`
- `Sysforge research/06-frontend-routing.md`
- Target module path in research: `static/js/sysforge/router.js` — **prefer** plugin-scoped path under `integrations/sysforge/static/js/` served as `/static/plugins/sysforge/js/` so uninstall does not leave host orphans.

---

## Scope

### In scope

- Replace stub panel body with Business shell chrome: header title, Back, Home/Dashboard, optional compact inner nav.
- Dashboard view with four MVP cards (labels, short preview text, navigate-on-click).
- `router.js`: register routes, `navigate(name, opts?)`, `back()`, `canGoBack`, current route, simple view cache (DOM nodes keyed by route id).
- Placeholder views for `calculator`, `clients`, `drafts`, `parts` (static copy + route title only).
- Wire card clicks and inner-nav to router; keep `openSysforge` / `closeSysforge` / `isSysforgeOpen` exports stable for `static/app.js`.
- Preserve modal drag, modalManager register (`sysforge-modal`, rail/sidebar ids), feature-flag gate.
- Lightweight CSS for shell layout (plugin CSS file or scoped styles).
- Extend plugin tests / add a focused JS-contract note or smoke checklist (see Tests).
- Document route name map for P1 modules.

### Out of scope

- SQL migrations, money/UTC helpers (`schema-money-utc-foundation`).
- Real clients/parts/drafts/calculator APIs or UI (`clients-crud-fts-duplicates`, etc.).
- Classic four-column Client Dashboard (`classic-client-dashboard`).
- View/Edit invoice route contracts (`nav-lifecycle-view-edit-routes`) beyond leaving hooks for later.
- Business settings UI, diagnostics, backup, Projects, screw maps.
- Replacing Odysseus host rail with a full-window Business app (stay in modal for P0; size may increase).
- Favorites, themes, keyboard shortcut system, nav history persist across restart (`future-ui-mru-shell-polish`).
- Fixing unrelated host merge conflicts in `static/app.js` unless they block Business open (note in Risks).

---

## Dependencies

| Dependency | Why | If missing |
|------------|-----|------------|
| **`schema-money-utc-foundation`** (soft for pure UI) | Manifest lists it; Phase 0 ships schema + shell together so install opens a “real” product. Status/health can show schema version later. | Shell can land on placeholder views without DB, but do **not** claim Phase 0 complete until schema workstream is green. Prefer sequencing: schema first or same PR train. |
| Existing plugin install / `PLUGIN_NAV` | Entry points already open the modal | Keep; do not reinvent |
| `modalManager.js`, `windowDrag.js` | Host chrome patterns | Reuse |

**Downstream consumers (design for):** P1 modules register real mount functions into the same route table instead of placeholders. `nav-lifecycle-view-edit-routes` will harden activate/deactivate and View/Edit navigation on top of this router.

---

## Concrete steps

### 1. Lock the shell architecture (½ day)

Decide and write into this plan’s contracts (already proposed below):

1. **Container:** Keep `#sysforge-modal` (draggable Odysseus modal). Widen default size (e.g. `min(1100px, 96vw)` × `min(720px, 90vh)`) so cards and later calculator fit.
2. **Layout:** Header row (title + Back + Home) → optional left rail (Dashboard + 4 modules) → `#sysforge-view-host` main pane.
3. **Router ownership:** Single module owns `currentRoute`, history stack, and which DOM node is shown. `index.js` only opens/closes modal and calls `router.mount(hostEl)`.
4. **Lifecycle rule:** One writer for “active view element.” If re-entering the same route, do **not** tear down and rebind card listeners (mirror `CurrentView` / `CardClicked` fix).

### 2. Add `router.js` (1 day)

Create `integrations/sysforge/static/js/router.js` with:

- `register(routeId, { title, render(container) | mount(container), activate?, deactivate? })`
- `navigate(routeId, { replace?: boolean, params?: object })`
- `back()`, `goHome()` → `dashboard`
- In-session history array; ignore duplicate consecutive navigations to same route
- View cache: Map routeId → `{ el, mounted }`; max **5** entries; LRU drop calls `deactivate` then removes node
- `getState()` for tests / status strip: `{ routeId, canGoBack, cacheSize }`

No hash/URL routing required in P0 (host already owns `/business` → open modal). Optional later: `?sf=clients` query for deep module open.

### 3. Build dashboard view (½–1 day)

Create `integrations/sysforge/static/js/views/dashboard.js` (or inline factory in `shell.js`):

- Cards array (order 1–4):

  | id | title | preview | route |
  |----|-------|---------|-------|
  | calc | Quick Invoice Calculator | Calculate invoices quickly | `calculator` |
  | clients | Clients | Search and manage clients | `clients` |
  | drafts | Drafts | Resume unsaved invoice drafts | `drafts` |
  | parts | Parts | Catalog and placeholders | `parts` |

- Render as a wrap grid similar to `DashboardView.axaml` (icon, title, preview). Prefer text/SVG icons over emoji if host design already avoids emoji; match existing Odysseus modal typography.
- Bind click → `router.navigate(card.route)` once per mount; on cache re-show, `activate` only refreshes title — **do not** double-bind.

### 4. Placeholder module views (½ day)

Four thin views sharing one helper `mountPlaceholder(title, body)`:

- Title matches route
- Body: one sentence that the module lands in P1; no fake forms
- Optional: show `GET /api/sysforge/status` version in footer of shell (not as the main content)

### 5. Rebuild `index.js` shell entry (½–1 day)

Replace status-only `#sysforge-panel` content with shell markup:

1. Build modal once (as today).
2. On first open: `router.mount(#sysforge-view-host)`, register all routes, `navigate('dashboard', { replace: true })`.
3. On subsequent open: show modal; optionally `router.activateCurrent()` without resetting stack.
4. Keep exports: `openSysforge`, `closeSysforge`, `isSysforgeOpen`.
5. Keep modalManager registration and backdrop click close.
6. Header Back button: `disabled` when `!canGoBack`; Home always → dashboard (clear or push per UX contracts).

### 6. Host touchpoints (small)

- Confirm `static/app.js` still toggles `sysforge-modal` via `_loadSysforgeModule()`; no API change needed if exports stay stable.
- Confirm `/business` deep link still clicks `#tool-sysforge-btn`.
- If modal HTML grows, ensure Appearance UI-vis key `tool-sysforge` still only gates host buttons, not inner routes.

### 7. CSS / a11y polish (½ day)

- Plugin CSS under `integrations/sysforge/static/css/shell.css` (link from modal or import side-effect).
- Focus management: on navigate, move focus to view heading; Back button has `aria-label`.
- Respect reduced-motion if host has a pattern; avoid decorative animation tax.

### 8. Tests + verification (½ day)

- Keep install/gate tests green.
- Add router unit tests if the repo has a JS test runner; otherwise add a Python test that static files exist + a short manual checklist in this doc (already below).
- Smoke: install → open → four cards → each placeholder → Back → Home → uninstall → 404.

### 9. Handoff notes for P1

In `integrations/sysforge/README.md` (short paragraph only):

- Route ids: `dashboard`, `calculator`, `clients`, `drafts`, `parts`
- How to replace a placeholder: `router.register('clients', { mount })` from module file
- Lifecycle: deactivate on leave for abort/autosave later

---

## Files

### Create

| Path | Role |
|------|------|
| `integrations/sysforge/static/js/router.js` | Inner navigation, history, view cache |
| `integrations/sysforge/static/js/views/dashboard.js` | Card home |
| `integrations/sysforge/static/js/views/placeholders.js` | Shared P1 stub panels (or one file per route) |
| `integrations/sysforge/static/css/shell.css` | Shell layout |

### Modify

| Path | Change |
|------|--------|
| `integrations/sysforge/static/js/index.js` | Replace stub body with shell + router mount; keep open/close API |
| `integrations/sysforge/README.md` | Document routes + extension point |
| `tests/test_sysforge_plugin.py` | Assert shell static assets exist; optional status still gated |
| `docs/migration-audit/gap-plans/gap-manifest.json` | No change required unless status field added later |

### Read-only references (do not port Avalonia)

| Path | Why |
|------|-----|
| `SysForge/.../DashboardViewModel.cs` | Card model + click event |
| `SysForge/.../DashboardView.axaml` | Layout density |
| `SysForge/.../NavigationService.cs` | Navigate / back / cache / activate hooks |
| `SysForge/.../ViewCache.cs` | LRU size 5 |
| `SysForge/.../MainWindowViewModel.cs` | ReferenceEquals lifecycle rule |
| `static/app.js`, `static/index.html` | Host open path + `/business` |

### Avoid for this workstream

- New FastAPI domain routes (except optional tiny `/status` enrichment from schema workstream)
- Host theme redesign
- Parallel Finance plugin patterns unless copying modal open/toggle only

---

## API / UI contracts

### HTTP (unchanged for shell)

| Method | Path | When inactive | When active |
|--------|------|---------------|-------------|
| GET | `/api/sysforge/status` | 404 | `{ ok, plugin_id, installed, version, installed_at }` |

Optional later (owned by schema workstream, consumed by shell footer): `schema_version` field on status. **Do not block shell on it.**

### JS module contract (`index.js`)

```js
export async function openSysforge(): Promise<void>
export function closeSysforge(): void
export function isSysforgeOpen(): boolean
export default { openSysforge, closeSysforge, isSysforgeOpen }
```

Host continues:

- Feature off → early return in click handler
- `Modals.toggle('sysforge-modal')` then open/close
- Dynamic import `/static/plugins/sysforge/js/index.js`

### Router contract

```js
// Route ids (stable strings for P1+)
'dashboard' | 'calculator' | 'clients' | 'drafts' | 'parts'

router.register(id, definition)
router.navigate(id, { replace?, params? })
router.back()          // no-op if stack empty
router.goHome()        // navigate dashboard
router.getState()      // { routeId, canGoBack, title, cacheSize }
router.mount(hostEl)   // once
```

**Params:** opaque object for future (`{ clientId }`, `{ invoiceId }`). P0 placeholders ignore params.

### DOM ids (stable)

| Id | Purpose |
|----|---------|
| `sysforge-modal` | Modal root (host modalManager) |
| `sysforge-close-btn` | Close |
| `sysforge-back-btn` | Inner back |
| `sysforge-home-btn` | Dashboard |
| `sysforge-view-host` | Active view mount point |
| `sysforge-view-title` | Chrome title |
| `sysforge-card-<route>` | Dashboard cards (for tests / a11y) |

---

## UX contracts

Carry these from MASTER §6 / desktop lessons into the shell **now** so P1 does not re-break them.

1. **Single writer for active view.** Only `router.navigate` swaps `#sysforge-view-host` children visibility (or replaces the visible pane). Do not have `index.js` and a module both set “current panel.”
2. **Same-route re-entry.** Opening dashboard twice (Home while already on dashboard, or cache hit) must **not** unsubscribe/rebind card clicks in a way that leaves zero handlers. Pattern: bind once on first `mount`; `activate` is idempotent.
3. **Card → module → Back.** From dashboard, open Clients placeholder, Back returns to dashboard with cards still clickable.
4. **Home vs Back.** Back = history pop. Home = go to `dashboard` (may push or replace; prefer **replace** when jumping home so stack does not grow unbounded).
5. **Close modal ≠ destroy cache (P0 choice).** Prefer keep cache/stack while plugin session lives; clear on uninstall or full page reload. Document the choice in README.
6. **Feature gate.** Uninstalled: no visible Business entry; opening via stale JS must no-op or show nothing useful; APIs 404.
7. **Do not fake domain success.** Placeholders must not look like empty data tables that imply the DB is wired.
8. **Defer:** persistent history across restart, favorites stars on cards, Projects card, Classic dashboard layout.

---

## Tests / verification

### Automated

- Existing `tests/test_sysforge_plugin.py`: install marker, feature flag, catalog, API 404 when inactive — must stay green.
- Add assertions (Python is enough):
  - `integrations/sysforge/static/js/router.js` exists
  - `index.js` contains route id strings `dashboard`, `calculator`, `clients`, `drafts`, `parts` (or import paths to view modules)
- If a frontend test harness exists later: unit-test history (navigate A→B→back→A) and LRU eviction at size 5.

### Manual smoke (Phase 0 §8.2)

1. Fresh profile / features off → Business hidden.
2. Settings → Integrations → Install Business Management → rail + sidebar appear.
3. Open Business → **dashboard cards**, not “Loading status…” as primary UI.
4. Click each card → titled placeholder; header title updates.
5. Back from a module → previous view; cards work again.
6. Home → dashboard.
7. Close modal, reopen → shell still works (cache/stack per documented policy).
8. Uninstall → nav hidden; `GET /api/sysforge/status` → 404.
9. Deep link `/business` with plugin installed opens the shell.

### Regression watch

- Host modalManager minimize/restore still finds `sysforge-modal`.
- `PLUGIN_NAV` visibility sync after install without hard refresh (if current install toast requires reload, keep that behavior; do not invent a second nav sync).

---

## Risks

| Risk | Impact | Mitigation |
|------|--------|------------|
| Modal too small for future calculator | P1 UX pain | Enlarge modal now; allow maximize/tile via existing host tileManager |
| Over-building Avalonia sidebar parity | Schedule slip | Inner nav + cards only; no collapse persistence |
| Double-binding card clicks after cache | “Cards dead” bug from desktop | ReferenceEquals-style activate; one bind site |
| Router in host `static/js/` instead of plugin | Orphans after uninstall | Keep under `integrations/sysforge/static/` |
| Coupling shell to unfinished schema | Blocked P0 | Shell runs with placeholders; Phase 0 complete only when both workstreams done |
| `static/app.js` merge conflict markers near Finance/Sysforge handlers | Broken open path | Resolve conflict before claiming shell verified (docs-only now; fix in product PR) |
| Treating matrix “nav history = P1” as skip | Incomplete P0 | This workstream **includes** in-session router/history; persist-across-restart stays deferred |

---

## Effort

**M (medium)** — roughly **3–5 engineering days**.

| Chunk | Size |
|-------|------|
| Architecture + contracts | S |
| `router.js` + cache/history | M |
| Dashboard + placeholders + `index.js` rewrite | M |
| CSS/a11y + tests + README | S |

Smaller if you ship a minimal router without LRU first; still count as M if you include cache + Back + four cards to MASTER exit criteria.

**L** only if you expand into full-page Business host chrome, URL deep-linking per module, or real module UIs in the same ticket.

---

## Implementation checklist (copy into ticket)

- [ ] `router.js` with register / navigate / back / goHome / cache(5)
- [ ] Dashboard with Calculator / Clients / Drafts / Parts cards
- [ ] Four placeholder views
- [ ] `index.js` shell chrome; stub status copy removed from primary pane
- [ ] Lifecycle: same-route activate does not kill card handlers
- [ ] Feature flag + modalManager + `/business` still work
- [ ] Tests + manual smoke above
- [ ] README route map for P1 handoff
)
