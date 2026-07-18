# future-ui-mru-shell-polish — Client MRU, shortcuts, Future UI shell polish

| Field | Value |
|-------|-------|
| **Issue id** | `future-ui-mru-shell-polish` |
| **Title** | Client MRU, shortcuts, Future UI shell polish |
| **Phase** | deferred (MASTER §7 / roadmap Phase 7; MRU also listed as P2-soon once Classic exists) |
| **Priority** | low (do not block invoice/client MVP) |
| **Domain** | ux |
| **Depends on** | `classic-client-dashboard`, `business-shell-dashboard-router` |
| **Unlocks** | Faster daily client loop; host-aligned Business shortcuts; optional card favorites / chrome polish |
| **Sources** | gap-manifest entry; MASTER §2.2 / §2.6 / §5 Phase 2 optional MRU / §6 Phase 7 / §7 Deferred; future-plans-roadmap §1.5 / §3 Phase 7 / §4.1; feature-gap-matrix §2 / §10; chat [a162de19](a162de19-d9e4-4026-9c02-09d8fdad5c5b) (MRU audit); chat e24feae4 (session MRU shipped, persist deferred); SysForge `Plans/UI-Plans/Future-UI-Features.md`; `Sysforge research/features/future-ui-backlog.md` |

---

## Goal / success

**Goal:** After Classic Client Dashboard and the Business shell ship, add post-core polish that matches SysForge's deferred Future UI / MRU intent **without** building a second shortcut system, theme engine, or Avalonia-style plugin marketplace inside Odysseus.

**Success (exit criteria):**

1. **Persistent client MRU** — Empty client search shows up to **6** clients ordered by last interaction across browser restarts (not session-only). Opening Client Dashboard can optionally pre-select the top MRU client (product toggle; default **on** once Classic exists, or match questionnaire VI1 once answered).
2. **Touch points** — Invoice save, client view, client edit, and calculator client pre-select all bump MRU for that client id.
3. **Host shortcuts** — Business opens (and optional in-Business actions) register through Odysseus `keyboard-shortcuts.js` + Settings → Shortcuts. No plugin-local keybind store. Unbound-by-default matches other open-tool shortcuts.
4. **Shell polish slice** — At least one of: user-togglable Business dashboard card favorites (replace hardcoded `IsFavorite` metaphor), or light breadcrumbs / route title in Business chrome. Themes stay Odysseus global (`--section-accent` / theme modal); no dual theme UI.
5. **Nav history across restart** — Explicit product decision recorded (yes = persist last N Business routes in plugin `config.json` or host storage; no = keep in-session only from `business-shell-dashboard-router`). If yes, restore works after full page reload with plugin active.
6. Manual + automated checks in § Tests/verification pass.

**Non-goals for "done":** Client merge tool, Lucene parts, projects P4/P6, PDF/email/payments, Avalonia plugin marketplace, user profiles, performance-monitoring UI, desktop DB import, dual shortcut systems.

---

## Current state

### Desktop (SysForge) — reference behavior

| Piece | Location | Behavior |
|-------|----------|----------|
| Session MRU (shipped) | `ViewModels/Sandbox/ClientDashboardWireframeViewModel.cs` | Empty search → up to 6 in-memory `_recentClients`; seed first open from `GetAllClientsAsync().Take(6)` (not true interaction order); `TrackRecentClient` on search select. **No DB column.** |
| Persistent MRU (deferred) | `Plans/UI-Plans/Future-UI-Features.md` § Client Dashboard | Spec: `LastInteractedAt` **or** `RecentClientIds` in AppConfig (~20); `ClientService.GetRecentClients(limit=6)`; on dashboard construct populate search + select top. Touch: invoice save, view, edit, calculator pre-select. |
| Explicit deferral | Plans README; chat 6bba6919 → Future-UI; chat a162de19 audit | User chose Edit Client over building MRU; still missing in code. |
| Open decision | `Product-Decisions-Questionnaire.md` VI1 / VI2 | Storage: column vs AppConfig; nav history persist yes/no — unanswered. |
| Future UI Phase 1 | Main menu / shell | In-session nav history, toasts, window size, progress — **Done**. Persist history across restart — **Deferred** (BUG-016 not a bug). |
| Future UI Phase 2–3 | Future-UI-Features.md | Shortcuts, user favorites, themes, breadcrumbs, sidebar↔dashboard sync, plugins, profiles — **Planned / not started**. |
| Hardcoded favorites | `DashboardViewModel.InitializeCards` | `IsFavorite = true` on first card only; not user-configurable. |
| Clients schema | `Database/Migrations/0005_clients.sql` | No `LastInteractedAt`. |

### Odysseus (odysseus-sysforge) — what exists

| Piece | Location | State |
|-------|----------|--------|
| Host shortcuts | `static/js/keyboard-shortcuts.js`, Settings panel in `static/index.html` / `static/js/settings.js` | Full rebind UI; open-tool actions (`open_calendar`, …) click tool buttons; empty combo = unbound. **No `open_sysforge` / Business actions yet.** |
| Themes | Host theme modal + CSS vars | Reuse for Business chrome (`future-ui-backlog.md`). |
| Business plugin | `integrations/sysforge/*` | Install gate + stub UI today; shell/router and Classic dashboard are **upstream workstreams** (see Depends on). |
| Client MRU API/UI | — | **Missing** (also deferred on desktop for persist). |
| Research | `Sysforge research/features/future-ui-backlog.md` | Port approach: defer until core flows; avoid duplicate shortcuts; Effort **M** per feature area. |

### Gap (what this workstream fills)

1. Session MRU on Classic (when Classic lands) → **DB/config-backed** recent-6 + optional last-used default.
2. Business keyboard access → **host** shortcut registry, not a plugin Settings clone.
3. Future UI Phase 2–3 → **thin web slice** aligned with Odysseus chrome; defer Avalonia plugin/themes/profiles visions.

---

## Scope

### In scope

**A. Client MRU (primary ease-of-use win)**

- Choose and document storage (prefer **`LastInteractedAt` column** via new plugin migration; AppConfig list is acceptable fallback if questionnaire picks it).
- Service/API: list recent (limit 6), touch client id, clear optional.
- Wire touches from invoice save, client view/edit routes, calculator client select.
- Classic search empty state uses persistent list; replace "first 6 from GetAll" seed.
- Optional: on Client Dashboard open, set selected client to MRU[0] when no deep-link client id.

**B. Shortcuts (reuse Odysseus)**

- Add `open_sysforge` (label "Open Business") to `_defaultKeybinds` + Settings "Open Tools" category; map to `tool-sysforge-btn` click (same pattern as `open_tasks`).
- Default combo: **empty** (unbound), matching most open-tool shortcuts.
- Optional in-Business actions only if shell routes exist: e.g. `sysforge_home`, `sysforge_clients`, `sysforge_calculator` — still stored in host `keybinds`, handlers no-op unless Business modal open / plugin active.
- Do **not** add a second Shortcuts page inside Business Settings.

**C. Future UI shell polish (pick a thin vertical)**

Ship in priority order; stop when effort budget hits **L** or checklist below is green:

1. User favorites for Business dashboard cards (persist in plugin `config.json`: ordered card ids; pin favorites to top).
2. Breadcrumb or subtitle in Business header: `Business › Clients › Edit` from router route stack (in-session first; persist only if VI2 = yes).
3. Sidebar/rail ↔ dashboard sync: highlight Business nav while modal open; optional highlight matching card when on dashboard route.
4. Nav history across restart: persist last ≤20 Business route entries when product says yes.

**Themes:** document "use Odysseus Theme tool"; optionally set `--section-accent` for Business modal only. No custom theme editor in plugin.

### Out of scope

- Dual shortcut systems / plugin-local keybind JSON.
- Avalonia-faithful plugin marketplace, user-created views, extension API (roadmap: prefer MCP/skills).
- Custom theme authoring UI, user profiles, memory/performance monitors (Future UI Phase 3 heavy items).
- Client merge tool, parts Lucene, projects depth, invoice PDF/email/payments.
- Changing Classic four-column layout itself (owned by `classic-client-dashboard`).
- Desktop SysForge DB import.
- Editing existing applied migrations; MRU column = **new** migration only (`AI_LEARNINGS.md`).

---

## Dependencies

| Dependency | Why |
|------------|-----|
| `business-shell-dashboard-router` | Dashboard cards, router, Back/Home, in-session history — polish and favorites hang off this. |
| `classic-client-dashboard` | Empty-search MRU UX and selected-client behavior live on Classic. |
| `clients-crud-fts-duplicates` (indirect) | Touch/list APIs need real clients table + search. |
| `invoice-calculator-save-contracts` (indirect) | Invoice-save touch point. |
| `nav-lifecycle-view-edit-routes` (indirect) | Client view/edit routes as MRU touch points. |
| `schema-money-utc-foundation` (indirect) | Migration runner for `LastInteractedAt` column. |

**Gate:** Do not start product coding until Classic empty-search contract and Business `router.js` exist (even if session MRU only). Planning and API sketch can happen earlier.

**Product decisions to lock before coding MRU/nav-persist:**

| ID | Question | Recommended default if still unanswered |
|----|----------|------------------------------------------|
| VI1 | `LastInteractedAt` column vs AppConfig MRU list | **Column** + index; simpler `ORDER BY`; survives config resets |
| VI1 | Still want last-used auto-select on open? | **Yes** when search empty and no `?clientId=` / hash deep link |
| VI2 | Persist Business nav history across restart? | **No** for first slice; in-session only unless shop workflow needs reload recover |

---

## Concrete steps

### 0. Preconditions / decisions (½ day)

- Confirm Classic search empty → session MRU exists (or stub the API behind feature flag).
- Answer VI1/VI2 in a short note at top of this file or ticket (recommended defaults above).
- Inventory host shortcut actions; reserve names: `open_sysforge`, optionally `sysforge_home`, `sysforge_clients`, `sysforge_calculator`.

### 1. MRU persistence — schema + service (1–2 days)

1. Add new migration (next free id after plugin set), e.g. `00xx_clients_last_interacted.sql`:
   - `ALTER TABLE Clients ADD COLUMN LastInteractedAt TEXT NULL;`
   - Index: `ix_Clients_LastInteractedAt` on `(LastInteractedAt DESC)` where not deleted (or plain index if SQLite partial unsupported in runner).
2. Python helpers under `integrations/sysforge/`:
   - `touch_client_interaction(client_id)` → set `LastInteractedAt` to UTC now.
   - `get_recent_clients(limit=6)` → non-deleted, `LastInteractedAt IS NOT NULL`, order DESC, limit 6; if fewer than 6, **do not** silently pad with arbitrary `GetAll` unless product asks (document choice; desktop wireframe padded — prefer **no pad** for honest MRU).
3. Call `touch` from:
   - Invoice finalize/save success (client id on invoice).
   - Client GET detail / edit save.
   - Calculator "client selected" endpoint or client-side hook that already hits an API.

### 2. MRU API + Classic UI wire (1 day)

- `GET /api/sysforge/clients/recent?limit=6` → list DTOs same shape as search hits.
- `POST /api/sysforge/clients/{id}/touch` (optional if all touches are server-side on existing mutations).
- Classic client search JS: on empty query, fetch `/clients/recent` instead of session-only array; keep session overlay as write-through cache for snappy UI, hydrate from API on activate.
- On dashboard open: if auto-select enabled and no deep-linked client, select recent[0] and load columns (mirror Future-UI construct behavior).
- Clearing search must **not** clear selected client (Classic contract from e24feae4 / matrix).

### 3. Host shortcuts (½–1 day)

1. `static/js/keyboard-shortcuts.js`: add `open_sysforge: ''` to `_defaultKeybinds`; add `open_sysforge: 'tool-sysforge-btn'` to `_toolBtns`.
2. `static/js/settings.js`: defaults, icon, label "Open Business", include in Open Tools category keys array.
3. Feature-flag: if `features.sysforge` false, either hide the row or leave it (click no-ops because button hidden). Prefer **hide** when plugin inactive to reduce clutter.
4. Optional Business-scoped actions: handlers check `isSysforgeOpen()` from plugin `index.js`; if closed, `open_sysforge` first or ignore.

### 4. Favorites + light chrome (1–2 days)

1. Plugin `config.json` key e.g. `dashboard_favorites: ["calculator", "clients", ...]`.
2. Dashboard render: favorites first, then rest; star/toggle control on card.
3. Header breadcrumb from router: join route titles; update on navigate/back/home.
4. Skip custom themes; verify Business modal readable under host light/dark.

### 5. Nav history persist (optional, ½–1 day)

Only if VI2 = yes:

- On each Business navigate, write stack snapshot to `config.json` (`nav_history: [{route, params, ts}, …]` cap 20) or `localStorage` keyed by user.
- On `openSysforge`, restore last route if still valid; else dashboard.
- If VI2 = no: document "in-session only" and close BUG-016-equivalent for web.

### 6. Tests + docs (½–1 day)

- API tests for recent/touch ordering and deleted-client exclusion.
- Shortcut registry test or smoke note (host test harness may be light; at least assert defaults include `open_sysforge` if unit-tested).
- Update `integrations/sysforge/README.md` and research `future-ui-backlog.md` status row when shipping.
- Mark MASTER / roadmap Phase 7 checklist items done for the slice you shipped.

### Suggested ship order

1. MRU schema + API + Classic empty-search (highest shop value).  
2. `open_sysforge` host shortcut.  
3. Favorites + breadcrumb.  
4. Nav persist only if requested.

---

## Files

### Create (expected)

| Path | Role |
|------|------|
| `integrations/sysforge/migrations/00xx_clients_last_interacted.sql` | New column + index |
| `integrations/sysforge/services/client_mru.py` (or under existing clients service) | `touch` / `get_recent` |
| `tests/test_sysforge_client_mru.py` | Ordering, touches, deleted filter |
| Optional: `integrations/sysforge/static/js/mru.js` | Client-side cache hydrate |

### Modify

| Path | Role |
|------|------|
| `integrations/sysforge/routes.py` | Recent (+ optional touch) routes |
| Classic client dashboard JS (from `classic-client-dashboard` workstream) | Empty search → recent API; open default select |
| Invoice/client/calculator save paths | Call `touch` |
| `integrations/sysforge/static/js/index.js` / dashboard module | Favorites order; breadcrumb |
| `static/js/keyboard-shortcuts.js` | `open_sysforge` |
| `static/js/settings.js` | Shortcut catalog entry; hide if inactive |
| `integrations/sysforge/README.md` | MRU + shortcuts notes |
| `Sysforge research/features/future-ui-backlog.md` | Status → Partial/Done for shipped slice |

### Read-only references

| Path | Why |
|------|-----|
| `SysForge/Plans/UI-Plans/Future-UI-Features.md` | Canonical MRU + Phase 2–3 spec |
| `SysForge/ViewModels/Sandbox/ClientDashboardWireframeViewModel.cs` | Session MRU UX to upgrade |
| `SysForge/ViewModels/DashboardViewModel.cs` | Hardcoded `IsFavorite` metaphor |
| `Sysforge research/features/future-ui-backlog.md` | Port constraints |
| `static/js/keyboard-shortcuts.js` | Open-tool pattern to copy |

### Avoid

- New Settings → Shortcuts UI inside Business.
- Porting Avalonia `SettingsService` window-state history blindly.
- Editing `0005_clients.sql` in place.

---

## API / UI contracts

### HTTP

All under `/api/sysforge/`, same auth/owner gate as other Business routes; **404 when plugin inactive**.

```
GET /api/sysforge/clients/recent?limit=6
→ 200 { "clients": [ { "id", "first_name", "last_name", "nickname", "phone", "email", "last_interacted_at", … } ] }
→ empty list if none touched yet (not an error)

POST /api/sysforge/clients/{id}/touch
→ 204 or 200 { "id", "last_interacted_at" }
→ 404 if missing/deleted

# Prefer implicit touch on existing mutations when possible:
POST /api/sysforge/invoices (save)        → touches invoice.client_id
PUT  /api/sysforge/clients/{id}         → touches id
GET  /api/sysforge/clients/{id}         → optional touch on view (document; may be noisy — prefer explicit view-open from UI)
```

**Config (plugin `config.json` additions):**

```json
{
  "dashboard_favorites": ["calculator", "clients"],
  "client_mru_autoselect": true,
  "nav_history": []
}
```

### Host shortcut contract

| Action id | Default combo | Effect |
|-----------|---------------|--------|
| `open_sysforge` | `''` (unset) | Click `#tool-sysforge-btn` / open Business |
| `sysforge_home` (optional) | `''` | `router.goHome()` if open |
| `sysforge_clients` (optional) | `''` | `navigate('clients')` if open |
| `sysforge_calculator` (optional) | `''` | `navigate('calculator')` if open |

Storage: existing host settings `keybinds` merge (same as calendar/tasks). Conflict detection uses existing Settings UI.

### JS module hooks

- Classic search: `loadRecentClients()` on activate + when query becomes empty.
- Router: `getBreadcrumb(): string[]` for header.
- Favorites: `toggleFavorite(cardId)`, `orderedCards()`.

---

## UX contracts

1. **Empty search** shows up to 6 recent clients; typing switches to live search results (Classic overlay behavior unchanged).
2. **Clear search** keeps the selected client; does not wipe MRU.
3. **First-ever use** (no touches): empty recent list + placeholder copy ("Interact with a client to see them here") — better than fake MRU from `GetAll`.
4. **Auto-select last-used** only when opening Clients with no deep-link client id; do not steal selection while user is mid-search.
5. **Shortcuts:** rebind only via Odysseus Settings → Shortcuts; Esc cancel listening unchanged.
6. **Favorites:** pin cards to top; do not hide non-favorites.
7. **Breadcrumb:** informational; clicking a segment may navigate if route registered (optional enhancement).
8. **Themes:** Business follows host theme; no separate Business dark-mode toggle.
9. **Reload:** with nav persist off, reopen Business → dashboard or last in-session route per shell workstream; with persist on, restore saved stack.

---

## Tests / verification

### Automated

- [ ] `get_recent_clients` orders by `LastInteractedAt` DESC; respects limit; excludes `IsDeleted`.
- [ ] Two touches flip order; third client pushes 7th out of the visible 6.
- [ ] Invoice save / client update integration tests assert `LastInteractedAt` set (UTC).
- [ ] Recent endpoint gated: inactive plugin → 404.
- [ ] Migration applies on fresh install and on existing DB upgrade path (checksum immutable for old files).

### Manual smoke

- [ ] Touch client A via edit, B via invoice save → empty search shows B then A (or A then B per last touch).
- [ ] Restart browser / reload → same recent order.
- [ ] Settings → Shortcuts shows Open Business; bind e.g. Ctrl+Alt+B (if free); opens Business when plugin on.
- [ ] With plugin off, shortcut hidden or no-ops; no dual shortcut page in Business.
- [ ] Favorite a card → reorder persists after close/reopen Business.
- [ ] Breadcrumb updates on Clients → Edit → Back.
- [ ] Host theme change still readable in Business modal.

### Regression watch

- [ ] Classic: clear search ≠ deselect; query == selected name does not auto-reopen wrongly (Classic contracts).
- [ ] Shell: same-route re-activate does not kill card click handlers (`state-and-event-lifecycle` / ReferenceEquals lesson).
- [ ] Host Esc / modal close / other open-tool shortcuts still work.

---

## Risks

| Risk | Impact | Mitigation |
|------|--------|------------|
| Building dual shortcut/theme systems | User confusion; MASTER "Out of MVP" | Host registry only; themes via Odysseus |
| Starting before Classic/shell exist | Rework | Hard depends_on; session MRU first in Classic |
| Padding recent with `GetAll` | Fake "MRU" misleads | Prefer empty state until real touches |
| Touch on every GET detail | Noise / wrong order | Touch on intentional UI events + saves |
| Nav persist of stale routes | Open errors after schema/UI rename | Validate route ids on restore; fall back to dashboard |
| Scope creep into Phase 3 (plugins/profiles) | Deferred workstream becomes epic | Cap checklist; ship MRU + open_sysforge as MVP of this issue |
| Editing old migrations for column | Checksum crash | New migration file only |
| Questionnaire VI1 unanswered | Wrong storage choice | Use recommended column default; note in ticket |

---

## Effort

**L (large)** for the full package (MRU + host shortcuts + favorites/breadcrumb + optional nav persist): roughly **5–8 engineering days** after Classic and shell exist.

| Chunk | Size |
|-------|------|
| Decisions + contracts | S |
| MRU migration + service + API + Classic wire | M |
| Host `open_sysforge` (+ optional in-Business actions) | S |
| Favorites + breadcrumb chrome | M |
| Nav history persist (optional) | S |
| Tests + README / backlog status | S |

**M** if you ship **only** persistent MRU + `open_sysforge` and defer favorites/breadcrumb/nav-persist to a follow-up ticket.

**S** is wrong for the titled workstream; research's "M per feature area" still sums to **L** when MRU and shell polish ship together.

---

## Implementation checklist (copy into ticket)

- [ ] Lock VI1/VI2 (or accept recommended defaults)
- [ ] New `LastInteractedAt` migration + `get_recent` / `touch`
- [ ] Wire touches: invoice save, client edit/view, calculator select
- [ ] `GET /clients/recent`; Classic empty search uses it
- [ ] Optional autoselect last-used on Clients open
- [ ] Host `open_sysforge` in keyboard-shortcuts + Settings catalog
- [ ] Dashboard favorites in `config.json` (or defer)
- [ ] Business header breadcrumb from router (or defer)
- [ ] Nav persist across restart only if VI2 = yes
- [ ] Tests + manual smoke above
- [ ] Update future-ui-backlog / README status

---

## Source notes

- **a162de19:** Audit of deferred work; Client dashboard MRU called out as explicitly deferred in chat (via 6bba6919 → Future-UI-Features); no `LastInteractedAt` / `GetRecentClients` in desktop code.
- **e24feae4:** Classic ships **session** MRU; persist listed as P2+ follow-up.
- **future-plans-roadmap §3 Phase 7:** Reuse Odysseus shortcuts/themes; no dual systems.
- **future-plans-roadmap §4.1:** Client MRU called high-value ease-of-use gap with no dedicated port card until this plan.
- **MASTER §7:** MRU persist = P2 soon; Future UI Phase 2–3 + nav history across restart = P3; dual shortcuts = out of MVP.
- **future-ui-backlog.md:** Defer until core Business flows; Effort M per area; shortcut duplication is the main risk.
)
