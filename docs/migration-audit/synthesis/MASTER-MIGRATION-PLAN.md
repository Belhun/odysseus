# Master migration plan — SysForge → odysseus-sysforge

**Audit date:** 2026-07-17  
**Audience:** Product owner + implementers  
**Constraint:** Documentation only (no product code in this audit).  
**Companion docs:** [feature-gap-matrix.md](feature-gap-matrix.md) · [feature-gap-summary.md](feature-gap-summary.md) · [future-plans-roadmap.md](future-plans-roadmap.md) · [CHAT-FINDINGS-INDEX.md](CHAT-FINDINGS-INDEX.md)

---

## 1. Parity verdict (current truth)

| Layer | Status |
|-------|--------|
| **odysseus-sysforge plugin shell** | **Done** — optional install/uninstall, `features.sysforge` flag, nav/rail gate, stub modal, gated `/api/sysforge/status`, plugin tests |
| **SysForge desktop product** | **Shipped** Phases 1–9 (clients, invoices/calculator, drafts, parts/placeholders, dashboard, settings/backup, diagnostics). Projects/WO + screw maps **in progress** |
| **Domain parity on web** | **Near zero** — empty `sysforge.db` touch, empty `drafts/` / `backups/` dirs, stub panel. No migrations, no domain APIs, no Business UI |
| **Research / planning** | **Strong** — `Sysforge research/` Phase A–D + feature cards; this audit bridges research to runtime |

**One-line verdict:** Install works; the shop product does not. Desktop ease-of-use lives entirely in Avalonia; the web plugin is a gated empty shell.

---

## 2. What SysForge has shipped (by domain)

### 2.1 Plugin / shell (desktop always-on; web optional)

| Capability | Desktop | Notes |
|------------|---------|-------|
| Startup, DI, checksummed migrations | Done | `MigrationRunner`, `0002`–`0021` |
| Sidebar + dashboard cards + view cache + back stack | Done | `NavigationService`, `ViewCache`, `DashboardViewModel` |
| Toasts, settings window, diagnostics | Done | Business settings + backup UI |

### 2.2 Clients

| Capability | Status |
|------------|--------|
| CRUD, Lucene search, duplicate detection | Done |
| Client Dashboard **Classic** four-column workspace | Done (production default) |
| Inline edit (incl. Address/Notes), acceptance dialog | Done |
| MRU / recent-6 persistent | Deferred (session MRU in search only) |
| Client merge tool | Deferred (detect only) |

### 2.3 Invoices / calculator

| Capability | Status |
|------------|--------|
| Invoice calculator (keyboard-first) | Done |
| Client search: **matches before “Add New”** | Done |
| Save + name prompt; edit same row (no forced rename) | Done |
| **Save as new** + viewer nav / back-stack | Done |
| Draft autosave; placeholder create on save | Done |
| Invoice edit + price compare; viewer | Done |
| Invoice devices; per-invoice JSON backup (no restore UI) | Devices Done; backup Partial |
| PDF / payments / reporting | Planned (v3+) |

### 2.4 Drafts

| Capability | Status |
|------------|--------|
| File JSON drafts + triple-buffer autosave | Done |
| Drafts list + name dialog | Done |
| **DRAFT-08** retention auto-delete on startup | Partial — method exists; **intentionally unwired** (silent delete risk) |

### 2.5 Parts / suppliers / placeholders

| Capability | Status |
|------------|--------|
| Parts CRUD, SQL LIKE search, placeholder create + merge UI | Done |
| Suppliers schema (no dedicated UI) | Schema Done |
| Lucene parts search; placeholder triage queue | Planned / stub doc |

### 2.6 Dashboard / navigation polish

| Capability | Status |
|------------|--------|
| Home dashboard cards | Done |
| Nav history persist across restart | Deferred (in-session only) |
| Future UI Phase 2–3 (shortcuts, favorites, themes) | Planned |

### 2.7 Projects / work orders

| Capability | Status |
|------------|--------|
| Schema `0016`–`0018`, services, hub, create-from-invoice | In progress / largely built |
| **Four-column project detail** as production target | Promoted (retire scroll detail) |
| Client acceptance → WO; devices on estimates | In progress / Done on branch |
| Rich notes, inventory light, DisplayCode | Planned |

### 2.8 Screw maps / repair docs

| Capability | Status |
|------------|--------|
| Schema `0019`–`0021`, service, ScrewMapView workspace | In progress |
| Autosave + undo; four-column entry; HW/Other only | In progress |
| S2 measurements UI, zoom/pan, S5 mobile, timeline | Planned / Draft |

### 2.9 Backup / search / settings

| Capability | Status |
|------------|--------|
| Settings backup/restore MVP; scheduled backups | Done (some Q-05 UX deferred) |
| Lucene client index; **BUG-018** post-import reindex | Done (reindex must run even on skip-all import) |
| Money INTEGER cents; UTC timestamps | Done |

---

## 3. Transfer quality into odysseus-sysforge

Legend: **Ported** = runtime · **Research-only** = documented in `Sysforge research/` · **Missing** = neither runtime nor enough port acceptance criteria

| Domain | Ported | Research-only | Missing (runtime) |
|--------|--------|---------------|-------------------|
| Plugin install / feature gate / nav stub | Yes | — | Domain APIs/UI |
| SQL migrations + money/UTC | — | `04-data-model-migration.md` | Schema + runner |
| Business shell (dashboard + router) | Stub modal | `shell-navigation-dashboard.md`, `06-frontend-routing.md` | Full shell |
| Clients + FTS | — | `clients-management.md`, `client-search-lucene.md` | All |
| Classic Client Dashboard | — | Inventory + chat `e24feae4` | All |
| Invoice calculator / edit / viewer | — | `invoice-*.md` | All |
| Drafts | Dir mkdir | `draft-management.md` | Service + UI |
| Parts / placeholders | — | `parts-catalog.md`, `placeholder-parts-merge.md` | All |
| Projects / WO / create-from-invoice | — | `projects-work-orders.md`, `invoice-devices.md` | All |
| Screw maps | — | `screw-maps.md` | All |
| Settings / plugin backup | Minimal `config.json` | `settings-backup.md` | Settings UI + scoped backup |
| Diagnostics | — | Diagnostics card (light) | Panel |
| Future UI / vision integrations | — | `future-ui-backlog.md`, `product-vision-integrations.md` | Defer |
| Host ROADMAP milestones for Business | — | — | Not listed in `ROADMAP.md` |

**Research path drift:** docs still mention `addons/sysforge/` and `E:\odysseus`; runtime is `integrations/sysforge/`. Refresh when coding starts.

---

## 4. High-signal findings from chat reviews (deduped)

Cite UUIDs briefly. Full index: [CHAT-FINDINGS-INDEX.md](CHAT-FINDINGS-INDEX.md).

### Must not lose (UX / correctness contracts)

| Contract | Why | Primary chats |
|----------|-----|---------------|
| **Nav / active-panel lifecycle** | Duplicate same-panel assign must not unsubscribe handlers (`CardClicked` death) | `014ea2dd`, `61c9c30b`, `97aa3734` |
| **View + Edit navigate visibly** | Filling calculator state without route change is a failure | `014ea2dd`, `21972123` |
| **Classic Client Dashboard** | Four columns: invoice rail \| preview \| projects \| client edit; one default, not A/B grid | `e24feae4`, `6bba6919` |
| **Search overlay + selection** | Compact overlay; empty → recent 6; clear search ≠ clear client; no auto-open when query == selected name; matches before Add New | `e24feae4`, `6bba6919`, `920df407`, `61c9c30b` |
| **Edit save vs save-as-new** | Edit updates same id/name; Save as new clones + name prompt; then viewer + back to client dashboard | `21e672a5`, `21972123`, `67a4ed8b`, `97aa3734` |
| **Placeholder orphan order** | Delete items → placeholders → insert items → **then** orphan cleanup | `21e672a5`, `8eceb374` |
| **Return context after save** | Back stack remembers origin (viewer ↔ calculator ↔ dashboard) | `67a4ed8b`, `21972123` |
| **Create-from-invoice** | Shared path: invoice picker + device picker + category; blank device ID refused | `5d77cdc9`, `c7be02df`, `02890eb3`, `c6ee4808` |
| **Four-column project detail** | Canonical project UX; do not ship scroll detail as second page | `38ff5cc4`, `363ca32e`, `039b6dc2`, `c6ee4808` |
| **DRAFT-08** | Retention method exists; default **off**; never silent startup delete without pin/warn | `bfe03bf6`, `97aa3734`, `a162de19` |
| **Post-import reindex (BUG-018)** | Bulk import must rebuild search even if every row skipped; Diagnostics ≠ search | `c2396042`, `55127af8`, `11201750` |
| **Duplicate warnings (DB-12)** | Warn, don’t hard-block; Use existing / Create anyway; merge later | `55127af8`, `784da76d` |
| **Money / enums / JSON helpers** | Cents + milliunits + tax bps; enum strings for CHECK; bad JSON → null | `0aea6b1e`, `f4de4b62` |
| **Async from day one** | Don’t port sync→async twice; cancel on leave; autosave lock; busy buttons | `693ac8c9`, `12512fc6` |
| **ScrewMapView contract** | Single-click place; number on dots; autosave+undo; HW/Other; 1:1 map/project | `7e801bff`, `ca042680`, `150e09d0` |
| **Migrations immutable** | Never edit applied SQL; new numbered files only | `693ac8c9` + SysForge `AI_LEARNINGS.md` |

### Product decisions already made (don’t re-litigate)

- Classic wins; retire Onboard/Preview+/Unified/Stacked/Timeline (`e24feae4`).
- Projects column on Classic is real list, not “Coming later” (`c6ee4808`).
- Screw map preview above Before/After when eligible (`f9ec8da7`).
- Empty line items allowed on **edit** save; calculator create still requires ≥1 item (`f4de4b62`).
- Fresh plugin DB; **no** desktop SysForge import in MVP (research `04-data-model-migration.md`).

### Meta / skip for product port

Cursor rule frontmatter (`53297bdf`, `587ae068`), empty chat (`7a8c3399`), MCP/Docker troubleshooting (`f75b5117`, mostly `11201750`), Critiques provenance hunt (`77531ed3`), directory-tree / audit-kickoff meta (`887181f4`, `4a705565`).

---

## 5. Phased work (same ease-of-use as desktop)

Ease-of-use order: **quote fast → client loop → shop flow → bench docs → polish → integrations**.

### Phase 0 — Foundation (P0)

**Goal:** Install opens a real Business shell with a real schema.

| Work | Exit criteria |
|------|---------------|
| Port migrations `0002`–`0015` (core shop) + checksum runner | DB not empty; schema version queryable |
| Money cents + UTC helpers in Python | Round-trip tests match desktop vectors |
| Replace stub modal with dashboard + `router.js` | Cards for Calculator / Clients / Drafts / Parts |
| Keep feature flag + install UX | Lean Odysseus when uninstalled |

**Chats / research:** matrix P0; shell cards; `693ac8c9` (async + migrations).

### Phase 1 — Invoice MVP (P1)

**Goal:** Solo tech quotes and saves in browser as fast as desktop keyboard flow.

| Work | Exit criteria |
|------|---------------|
| Clients CRUD + FTS5 typeahead | Matches before Add New; debounce + abort |
| Parts + placeholder create/merge | Line items resolve; merge irreversible confirm |
| Drafts file service + list + calculator autosave | Debounce, lock, atomic write, leave-page flush |
| Invoice calculator create/edit + save/name | Same-id edit; save-as-new; busy flags |
| Duplicate warnings on create | Non-blocking DB-12 |
| Minimal Business settings (tax/currency/autosave) | No hand-editing JSON for daily use |

**Defer:** Lucene parts, MRU persist, projects UI, screw maps, PDF.

**Chats:** `21e672a5`, `21972123`, `61c9c30b`, `8eceb374`, `f4de4b62`, `55127af8`.

### Phase 2 — Client workspace polish (P1→P2)

**Goal:** Classic dashboard daily loop.

| Work | Exit criteria |
|------|---------------|
| Classic four-column Client Dashboard | Preview Edit/View; search overlay; Notes/Address |
| Nav lifecycle + View/Edit routes | Smoke: card → dashboard → view → edit → home → card |
| Invoice viewer + return context | Save-as-new → viewer → back to client |
| Optional session/persistent MRU | Recent 6; clear search keeps client |
| Diagnostics read-only | Migration version / DB health (no secrets) |

**Chats:** `e24feae4`, `014ea2dd`, `6bba6919`, `67a4ed8b`.

### Phase 3 — Projects & work orders (P2)

**Goal:** Estimate → accept → WO → project(s).

| Work | Exit criteria |
|------|---------------|
| Migrations `0016`–`0018` + services | Schema + API parity |
| Invoice devices; acceptance dialog | Option C acceptance ≠ finalized alone |
| Create-from-invoice wizard | Shared picker path |
| Projects hub + **four-column detail** | One detail route; Classic projects column live |
| Settings: include archived in search | Hub respects setting |

**Chats:** `c6ee4808`, `5d77cdc9`, `c7be02df`, `38ff5cc4`, `003cf12a`, `f83f955a`.

### Phase 4 — Screw maps S0–S2 (P3)

**Goal:** HW/Other projects document screws in browser.

| Work | Exit criteria |
|------|---------------|
| Migrations `0019`–`0021` + image store under plugin data | 1:1 map/project; lock |
| ScrewMapView (HTML canvas/SVG) | Single-click place; autosave+undo; numbered dots |
| Entry from four-column preview | Above Before/After when eligible |

**Defer:** S5 mobile companion (tablet browser may substitute); annotation-only features as later.

**Chats:** `7e801bff`, `ca042680`, `150e09d0`, `f9ec8da7`.

### Phase 5 — Reliability & backup (P2)

| Work | Exit criteria |
|------|---------------|
| Plugin-scoped backup/restore (ZIP/JSON decision vs host) | Shop can restore Business data |
| Per-invoice backup restore UI | Match Partial desktop → Done |
| **BUG-018** on every bulk import path | Search finds imported clients after skip-all |
| Q-05 leftovers (conflict UI, SQL import button) as needed | Document intentional deferrals |

**Chats:** `55127af8`, `c2396042`, `f4de4b62`.

### Phase 6+ — Depth (P3)

| Phase | Focus |
|-------|--------|
| 6 | Parts FTS, supplier UX, price history, placeholder triage |
| 7 | Future UI (reuse Odysseus shortcuts/themes; no dual systems) |
| 8 | Projects P4/P6, repair timeline, release gate |
| 9 | Invoice v3+ PDF/email/payments/reporting; client merge |
| 10 | Managed-IT integrations as separate MCP/micro-add-ons |

Detail: [future-plans-roadmap.md](future-plans-roadmap.md) §3.

### Suggested 90-day stack

1. Phase 0–1 (foundation + invoice MVP)  
2. Phase 2 (Classic client loop)  
3. Phase 3 (projects/WO)  
4. Phase 4–5 as capacity allows  

---

## 6. UX contracts checklist (do not lose)

Copy into implementation tickets. Fail CI / QA if broken.

- [ ] **Single writer** for active Business panel, or detach handlers only on reference change (`014ea2dd`)
- [ ] Dashboard card → Client Dashboard still works after navigate-back / cache re-select
- [ ] Client Dashboard **View** opens read-only viewer route; **Edit** loads **and** navigates to calculator
- [ ] Classic four-column layout is the only Client Dashboard default
- [ ] Search: overlay, recent-6 when empty, clear ≠ deselect, no auto-open on edit load, matches before Add New, keyboard Up/Down/Enter
- [ ] Edit save: same invoice id/name; preserve status/finalized/sent_at
- [ ] Save as new: name dialog → new id → viewer → Back to Client Dashboard with client selected + list refresh
- [ ] Placeholder orphan cleanup **after** re-insert on update
- [ ] Calculator create requires ≥1 line; edit may save empty header
- [ ] Create-from-invoice: shared service; device ID required; HW/SW/Other
- [ ] Project detail = four-column only; screw map above photos when eligible
- [ ] DRAFT-08: retention default off; no silent purge
- [ ] Post-import / restore: reindex clients before claiming search works
- [ ] Money in integer cents end-to-end; UTC timestamps
- [ ] Autosave: debounce + concurrency lock + flush/timeout on leave
- [ ] Migrations: append-only; checksum policy mirrored from desktop

---

## 7. Deferred / future plans (priority)

| Priority | Item | Source |
|----------|------|--------|
| **P2 soon** | Client MRU persist (`LastInteractedAt`) | Future-UI; `a162de19`, `e24feae4` |
| **P2** | Wire optional draft retention (safe defaults) | DRAFT-08 / `bfe03bf6` |
| **P2** | Per-invoice backup restore UI; Q-05 Settings leftovers | `55127af8`, roadmap §3 Phase 5 |
| **P2** | Diagnostics “don’t ask again”; archive search setting | Projects plan |
| **P3** | Lucene/FTS parts; supplier preferred UX; price history | Invoice-Roadmap v2 |
| **P3** | Client merge tool | DB-12 |
| **P3** | Screw map S2–S5 extras; repair timeline; zoom/pan | Repair docs / `ca042680` |
| **P3** | Projects P4 rich notes; P6 inventory; DisplayCode | Projects plan |
| **P3** | Future UI Phase 2–3; nav history across restart | Future-UI |
| **Later** | PDF/email/payments/reporting/roles | Invoice-Roadmap v3+ |
| **Later** | Wazuh / Snipe-IT / NetBox / n8n | Product-vision; separate track |
| **Out of MVP** | Desktop DB import; Avalonia-faithful plugins; dual shortcut systems | Research |

---

## 8. Verification checklist

### 8.1 Plugin shell (already expected green)

- [ ] Install from Settings → Integrations enables Business nav
- [ ] Uninstall hides nav; `/api/sysforge/*` → 404
- [ ] `tests/test_sysforge_plugin.py` passes

### 8.2 After Phase 0

- [ ] Fresh install applies migrations; SchemaVersion populated
- [ ] Money/UTC helper unit tests pass
- [ ] Business opens dashboard (not status stub)

### 8.3 After Phase 1 (invoice MVP)

- [ ] Create client → search finds by name/phone/email (FTS)
- [ ] Calculator: typeahead, matches before Add New, save with name
- [ ] Placeholder line → merge into catalog part
- [ ] Draft autosave survives refresh; list opens draft
- [ ] Duplicate phone/email warns; Create anyway works
- [ ] Edit existing invoice: same name; placeholders survive update
- [ ] Save as new → new id; FK/orphan regression test green

### 8.4 After Phase 2 (Classic)

- [ ] Full smoke: Dashboard card → Classic → View → Edit → Save → Back → Dashboard card
- [ ] Search clear keeps selected client
- [ ] Save-as-new → viewer → Back lands on same client with new invoice visible

### 8.5 After Phase 3–4

- [ ] Accept estimate → work order → create project(s) from devices
- [ ] Four-column project detail CRUD; create-from-invoice from header + Classic
- [ ] Screw map: place/move/autosave/lock; SW projects blocked with clear message

### 8.6 Backup / search

- [ ] Plugin backup ZIP/JSON restore round-trip
- [ ] Import fixture with shared phones: after import (including skip-all), search finds clients
- [ ] Diagnostics list ≠ treated as search proof

### 8.7 Docs hygiene (do with first coding PR)

- [ ] Fix research paths `addons/` → `integrations/sysforge/`
- [ ] Expand `integrations/sysforge/README.md` with “what works today”
- [ ] Add Business port milestones to host `ROADMAP.md` or link this plan
- [ ] Mirror migration checksum policy for Python plugin migrations

---

## 9. Where to work next

| If you want… | Open |
|--------------|------|
| This plan (canonical) | **This file** |
| Cell-level gap evidence | [feature-gap-matrix.md](feature-gap-matrix.md) |
| Short verdict | [feature-gap-summary.md](feature-gap-summary.md) |
| Long future backlog | [future-plans-roadmap.md](future-plans-roadmap.md) |
| Per-chat checklist | [CHAT-FINDINGS-INDEX.md](CHAT-FINDINGS-INDEX.md) → `../chat-reviews/<uuid>.md` |
| Desktop status source of truth | SysForge `Plans/README.md` |
| Port approach cards | `Sysforge research/00-overview.md` + `features/*.md` |

**Recommended first engineering epic:** Phase 0 (migrations + Business dashboard shell), then Phase 1 clients → drafts → parts → calculator as one shop loop.
