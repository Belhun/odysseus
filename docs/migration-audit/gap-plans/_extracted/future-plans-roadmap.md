# SysForge → odysseus-sysforge: future plans migration roadmap

**Created:** 2026-07-17  
**Purpose:** Consolidate unfinished / future work from SysForge into a migration-ready roadmap for the Odysseus Business Management (SysForge) plugin.  
**Constraint:** Documentation only; no product code changes in this audit.

### Source roots scanned

| Root | Role |
|------|------|
| `F:\Codeing Project\SysForge\Plans\` | Master index, Implementation-Plan phases, Feature-Plans, UI-Plans, Product-Vision, TODO, bugs, post-impl |
| `F:\Codeing Project\SysForge\.cursor\plans\` | Cursor agent plans (email search, invoice calculator sketch, Phase 1 config) |
| `F:\Codeing Project\SysForge\SysForge\Future-UI-Features.md` | Redirect stub → `Plans/UI-Plans/Future-UI-Features.md` |
| `F:\Codeing Project\SysForge\Critiques\` | Tracker (empty open list) + Solved-Critiques deferred/accepted archives |
| `F:\Codeing Project\SysForge\commands for future.md` | Ops note only (`rm` local `sysforge.db`); not a feature backlog |
| `F:\Codeing Project\odysseus-sysforge\ROADMAP.md` | Host-app (Odysseus) help-wanted; **not** SysForge-specific |
| `F:\Codeing Project\odysseus-sysforge\docs/research/sysforge\` | Port research (feature cards, inventory, phases A–D) |
| `F:\Codeing Project\odysseus-sysforge\docs\plans\` | Email local-sync plans (host app; not SysForge domain) |

### Ease-of-use goals (carry into Odysseus)

Preserve these SysForge product goals when sequencing ports:

1. **Keyboard-first estimates** — type client/part → pick first match → save fast.
2. **One place per device** — project workspace holds intake, plan, parts, photos, screw map.
3. **Clear shop flow** — estimate → client accepts → work order → project(s) → finish/pickup/payment.
4. **Opt-in complexity** — advanced UI (favorites, plugins, themes) after core bench flows work.
5. **Fresh start** — plugin DB is empty on install; no desktop SysForge import in MVP (`docs/research/sysforge/00-overview.md`, `04-data-model-migration.md`).

---

## 1. Catalog of planned features (SysForge status)

Status keys: **Done**, **Partial**, **In progress**, **Planned**, **Deferred**, **Stub**, **Draft**.

### 1.1 Core implementation plan (Phases 1–9)

Source: `Plans/README.md`, `Plans/Implementation-Plan/`, `.cursor/plans/phase_1_implementation_plan_63f57f78.plan.md`

| Feature | Status | Primary SysForge sources |
|---------|--------|--------------------------|
| Config.json / busy timeout / migration hardening | Done | `Plans/Implementation-Plan/Phase-1/`, `.cursor/plans/phase_1_implementation_plan_63f57f78.plan.md` |
| Dependency injection | Done | `Plans/Implementation-Plan/Phase-2/` |
| Money in INTEGER cents | Done | `Plans/Implementation-Plan/Phase-3/` |
| UTC timestamps | Done | `Plans/Implementation-Plan/Phase-4/` |
| Draft system + autosave | Done | `Plans/Feature-Plans/Draft-Management-System-Plan.md`, Phase 5 |
| Draft auto-delete on startup (DRAFT-08) | Partial | Method exists; not wired on startup (`Plans/README.md`, BUG-017 = by design) |
| Placeholder creation on save | Done | `Plans/Feature-Plans/Phase-1-Updated-Plan.md`, Phase 6 |
| JSON field validation | Done | Phase 7 |
| Part search + placeholder merge UI | Done | Phase 8; plan doc empty (`Placeholder-Parts-Workflow-Plan.md` = Stub) |
| Client dashboard, invoice edit/viewer, price compare | Done | Phase 9 |
| Main menu shell (sidebar, cache, toasts, window persist) | Done | `Plans/UI-Plans/Main-Menu-UI-Plan.md` |
| Nav history persist across restarts | Deferred | In-session only; `SettingsService.UpdateWindowState` skips history |

### 1.2 Clients, invoices, parts (shipped + leftovers)

| Feature | Status | Primary SysForge sources |
|---------|--------|--------------------------|
| Client CRUD + Lucene client search | Done | `Plans/README.md`, research `features/client-search-lucene.md` |
| Client duplicate detection | Done | Post-impl DB-12; **merge tool Deferred** |
| Client dashboard Classic layout | Done | `Plans/UI-Plans/Client-Dashboard-Prototypes.md` |
| MRU / last-used client + recent 6 in search | Deferred | `Plans/UI-Plans/Future-UI-Features.md` § Client Dashboard |
| Invoice calculator + save/name flow | Done | Phase 9; early sketch `.cursor/plans/invoice-calculator-system-508c2075.plan.md` (superseded) |
| Calculator client search: matches before “Add New” | Done | `Plans/TODO.md` |
| Drafts list UI | Done | Draft plan |
| Per-invoice JSON backup | Partial | Backup on update; **no restore UI** |
| Lucene parts search | Planned | Still SQL `LIKE` (`Plans/README.md`) |
| Suppliers table (reference) | Done (schema) | Invoice roadmap v1; richer UX = v2 Planned |
| Email `:` contains fallback in Lucene QueryBuilder | Planned (Cursor plan) | `.cursor/plans/email-68ea9ae6.plan.md` (todos unchecked) |

### 1.3 Post-implementation deferred scope

Source: `Plans/Post-Implementation-Improvements.md`, `Plans/Archive/Post-Implementation-Improvements.md`

| Feature | Status | Notes |
|---------|--------|-------|
| APP-07 async DB | Done | Commit `a01c3e3` |
| DOC-01/02 root README | Done | |
| DB-10 finalized edit + price compare | Done | Phase 9 |
| DB-12 client merge tool | Deferred | Detection shipped |
| Q-05 import conflict UI | Deferred | Skip-only today |
| Q-05 SQL import button in Settings | Deferred | API exists |
| Q-05 auto-restart after restore | Deferred | Manual restart toast |
| Q-05 custom backup folder picker | Deferred | API only |

### 1.4 Projects, work orders, screw maps

Source: `Plans/Feature-Plans/Projects-and-Work-Orders-Plan.md`, `Plans/Product-Vision/Repair-Documentation-System.md`, `Plans/Feature-Plans/Screw-Map-S5-Mobile-Companion-Plan.md`

| Feature | Status | Notes / sources |
|---------|--------|-----------------|
| P1 Work orders + invoice devices | Done / In progress | Migrations `0016`–`0017`; hub flows |
| P2 Project shell | Done / In progress | Migration `0018`; detail still Partial (sandbox wireframe) |
| P3 Projects hub + search | In progress | Hub VMs exist; archive search setting etc. |
| P4 Rich notes (Obsidian-style) | Planned | Editor spike TBD |
| P5 S0+S1 screw map annotate | In progress | Migrations `0019`–`0020`; annotation UI |
| P5 S2 measurements + reverse lookup | Planned | Columns exist; UI deferred |
| P5 S3 library / clone / provenance UI | Partial / In progress | Library migration noted; cross-model search deferred |
| P5 S4–S5 mobile companion | Draft / Planned | `Screw-Map-S5-Mobile-Companion-Plan.md` (LAN / inbox / relay) |
| P6 Inventory light on projects | Planned | Invoice-Roadmap v2 inventory |
| P7 Release package (docs + screenshots) | Planned | Official ship gate |
| Repair timeline (separate from screw maps) | Planned | Repair-Documentation-System.md |
| Zoom/pan, image reorder/delete | Planned | Deferred in repair doc status table |
| Google Calendar scheduling | Deferred | Out of projects plan scope |
| Carrier tracking APIs | Deferred | Manual `TrackingStatus` only |

### 1.5 Future UI backlog

Source: `Plans/UI-Plans/Future-UI-Features.md` (canonical); `SysForge/Future-UI-Features.md` = redirect

| Area | Status | Items |
|------|--------|-------|
| Future UI Phase 1 | Done | Nav history (in-session), toasts, window size, progress, settings access |
| Future UI Phase 2 | Planned | Keyboard shortcuts, **user** favorites (not hardcoded), advanced cache, preloading |
| Future UI Phase 3 | Planned | Plugin system, custom themes, advanced dashboard, performance monitoring, user profiles |
| Sidebar ↔ dashboard sync | Planned | |
| Breadcrumbs / status bar | Planned | |
| Client MRU (recent 6) | Deferred | Explicit chat deferral |
| Nav history across restart | Deferred | |

### 1.6 Invoice / product vision roadmap (v2 / v3+)

Source: `Plans/Product-Vision/Invoice-Roadmap.md`, `Plans/Product-Vision/Roadmap.md`, `Plans/Product-Vision/Features-and-Scope.md`

| Version theme | Status | Highlights |
|---------------|--------|------------|
| v1 core invoicing | Done (desktop) | Calculator, placeholders, client search, price update |
| v2 workspace / suppliers / inventory light / price history / dedupe merge | Mostly Planned; WO/projects **In progress** | See Invoice-Roadmap v2 sections |
| v2 repair documentation MVP | Partial | Screw maps S0+S1; timeline/mobile Planned |
| v3+ reporting, PDF/email, payments, Snipe-IT, roles, audit, automations | Planned | Product-Vision only |
| Managed IT (Wazuh/NetBox/Snipe-IT/n8n) | Planned | `Integrations.md`, Features-and-Scope milestones v0.1–v0.5 |
| Multi-instance DB coordination (Q-04) | Planned (policy only) | `Database-Design-Document.md` |

### 1.7 Bugs / cleanup / open decisions

| Item | Status | Source |
|------|--------|--------|
| BUG-010 debug `AppendAllText` | Partial cleanup | `Plans/Open-Bugs-And-Investigations.md` |
| BUG-016 nav history persist | Not a bug / Deferred | |
| BUG-017 DRAFT-08 startup delete | Not a bug / Deferred | |
| Product decisions questionnaire | Open (mostly unanswered) | `Plans/Feature-Plans/Product-Decisions-Questionnaire.md` |
| Critique tracker open items | Empty | `Critiques/CRITIQUE_REVIEW_TRACKER.md` |
| Critique deferred files | Empty (shipped to Archive) | `Critiques/Solved-Critiques/*/deferred.md` |
| `commands for future.md` | N/A | Wipe local DB only |

### 1.8 Status rollup counts (unique feature themes)

Approximate unique themes from the catalog above (excluding superseded Cursor invoice sketch and empty placeholder plan stub):

| Status | Approx. count | Examples |
|--------|---------------|----------|
| Done | ~35 | Phases 1–9 core, shell, drafts, calculator, duplicate detect, backup MVP |
| Partial / In progress | ~15 | Projects hub, screw maps S0–S1/library, DRAFT-08, invoice JSON backup, Future UI Phase 1 vs 2–3 |
| Planned / Deferred / Draft | ~40+ | MRU clients, Lucene parts, P4–P7, S2–S5, v2/v3 invoice ops, integrations, Future UI Phase 2–3 |

---

## 2. What already appears in odysseus-sysforge docs

### 2.1 Covered in `docs/research/sysforge/` (port planning)

These SysForge futures are **already named** in Odysseus research (status + port approach), even if not coded yet:

| Theme | Odysseus research path | Alignment with SysForge |
|-------|------------------------|-------------------------|
| Feature inventory + status | `docs/research/sysforge/01-feature-inventory.md` | Mirrors `Plans/README.md` Done/Partial/Planned |
| Port phases A–D (plugin skeleton → backend → frontend → fresh DB) | `00-overview.md` | Host migration strategy |
| Future UI Phase 2–3 | `features/future-ui-backlog.md` | Explicit: defer until Business flows ship |
| Projects / work orders | `features/projects-work-orders.md` | Schema first, UI after invoice MVP |
| Screw maps + mobile defer | `features/screw-maps.md` | HTML canvas; defer mobile companion |
| Product-vision integrations | `features/product-vision-integrations.md` | Separate micro-add-ons / MCP; not MVP |
| Invoice calculator / edit / viewer / devices | `features/invoice-*.md` | Core port targets |
| Drafts, placeholders, clients, Lucene→FTS5 | matching `features/*.md` | MVP search recommendation: FTS5 |
| Suppliers, diagnostics, toast, shell | matching cards | |
| Data model / no desktop import | `04-data-model-migration.md` | Matches ease-of-use fresh start |
| Addon architecture / packaging | `02-addon-architecture.md`, `07-deployment-packaging.md` | One-click install |

### 2.2 Host `ROADMAP.md` (Odysseus platform)

`ROADMAP.md` is **platform-wide** (Cookbook, agents, email performance, CSS, tours). It does **not** list SysForge Business Management features. Relevant only where host capabilities help SysForge later:

| Host ROADMAP item | Possible SysForge reuse |
|-------------------|-------------------------|
| Backup/restore guide for `data/` | Plugin backups under `data/plugins/sysforge/` |
| Email performance / local sync | Shop notifications later; **not** invoice PDF email yet |
| Accessibility / keyboard nav | Aligns with Future UI shortcuts |
| Task scheduler visibility | Could drive DRAFT-08 cleanup / scheduled backups |
| Plugin/MCP patterns | Vision integrations as MCP tools |

### 2.3 `docs/plans/` (email local sync)

All files under `docs/plans/email/email-local-sync-*` and follow-ups are **Odysseus mail**, not SysForge invoicing. Do not treat as SysForge migration scope.  
SysForge Cursor plan `.cursor/plans/email-68ea9ae6.plan.md` is **Lucene client `email:` query**, unrelated to Odysseus IMAP sync.

### 2.4 Gap: no dedicated SysForge future-roadmap file (until this doc)

Before this synthesis, Odysseus had research cards and inventory but **no single phased “remaining plans → port order”** document under `docs/`. This file fills that gap.

---

## 3. Recommended phased port plan (remaining work)

Order follows ease-of-use: ship the bench path first, then repair documentation depth, then polish and integrations.

### Phase 0 — Plugin foundation (Odysseus research Phase A)

**Goal:** Install Business Management without breaking lean Odysseus.

| Work | Sources | Ease-of-use note |
|------|---------|------------------|
| Feature flag + one-click install/uninstall | `docs/research/sysforge/00-overview.md`, `02-addon-architecture.md` | Zero terminal / zip steps |
| Fresh `sysforge.db` + migration runner | `04-data-model-migration.md` | No desktop import |
| Stub nav entry gated on install | `06-frontend-routing.md` | |

**Exit:** Plugin installs, empty DB, no Business routes until installed.

### Phase 1 — Invoice MVP (daily money path)

**Goal:** Create estimate → save → view/edit → client search as fast as desktop.

| Work | SysForge sources | Odysseus research |
|------|------------------|-------------------|
| Clients + FTS5/typeahead search | Phases 2/9, Lucene client design | `features/clients-management.md`, `client-search-lucene.md` |
| Invoice calculator + drafts autosave | Draft plan, Phase 5/9 | `invoice-calculator.md`, `draft-management.md` |
| Invoice viewer + edit + price compare | Phase 9, DB-10 | `invoice-viewer.md`, `invoice-edit.md` |
| Placeholder create + merge | Phase 6/8 | `placeholder-parts-merge.md` |
| Parts catalog + SQL search (MVP) | Phase 8 | `parts-catalog.md` |
| Settings: tax/shipping + backup MVP | Q-05 shipped subset | `settings-backup.md` |
| Shell dashboard cards for Business | Main-Menu-UI-Plan | `shell-navigation-dashboard.md`, `03-ui-design-port.md` |

**Defer in this phase:** Lucene parts, MRU clients, Future UI Phase 2–3, projects.

**Exit:** Solo tech can quote and save invoices in browser with keyboard-friendly search.

### Phase 2 — Client workspace polish (ease-of-use wins)

| Work | SysForge sources | Why now |
|------|------------------|---------|
| Client dashboard (Classic metaphor) | `Client-Dashboard-Prototypes.md`, Phase 9 | Primary post-save navigation |
| Client MRU / recent 6 | `Future-UI-Features.md` § Client Dashboard | Faster than retyping |
| Duplicate warnings (detect); merge later | Post-impl DB-12 | Prevent bad data without blocking save |
| Diagnostics read-only panel | Diagnostics views | Trust / debug without CLI |
| Optional: wire draft retention job | DRAFT-08 / Product questionnaire VII3 | Use Odysseus scheduler |

**Exit:** Client-centric daily loop matches desktop Classic dashboard intent.

### Phase 3 — Projects & work orders (shop flow)

| Work | SysForge sources | Odysseus research |
|------|------------------|-------------------|
| Schema migrations 0016–0018 | Projects plan P1–P2 | `projects-work-orders.md`, `invoice-devices.md` |
| Client accepted → work order | Projects plan lifecycle Q&A | |
| Manual create project per device | P2 | |
| Projects hub (active / gaps) | P3 | |
| Vendor/tracking fields (manual) | Projects plan | |
| Archive + IncludeArchivedInSearch | Projects plan Settings | |

**Still later:** P4 rich notes, P6 inventory, DisplayCode generator, Google Calendar.

**Exit:** Estimate → accept → work order → project list works end-to-end on web.

### Phase 4 — Screw maps S0–S2 (bench documentation)

| Work | SysForge sources | Odysseus research |
|------|------------------|-------------------|
| Schema 0019–0021 + image storage under plugin data | Repair-Documentation-System.md | `screw-maps.md` |
| Annotate (View/Edit, markers, numbering) | S0+S1 | HTML canvas/SVG rewrite |
| Lock on complete / manual lock | Repair status table | |
| S2 measurement UI + reverse lookup | S2 deferred table | |
| Library browse/reuse (same model string) | S3/S4 library notes | |

**Defer:** S5 mobile companion (Odysseus tablet browser may substitute; see S5 plan Method A as design input).

**Exit:** HW/Other projects can document screw positions and measurements on desktop/laptop browser.

### Phase 5 — Reliability & backup completeness

| Work | SysForge sources |
|------|------------------|
| Import conflict UI | Q-05 deferred |
| SQL import button / custom backup folder | Q-05 deferred |
| Per-invoice backup restore UI | Partial invoice JSON backup |
| Backup includes screw map image folders | Questionnaire VII2 |
| BUG-010-class cleanup (no debug file spam) | Open-Bugs BUG-010 |

**Exit:** Shop can back up/restore plugin data confidently.

### Phase 6 — Search & parts depth

| Work | SysForge sources |
|------|------------------|
| Richer parts search (FTS5 or Lucene-equivalent) | Lucene parts Planned |
| Placeholder workflow doc → real triage UX | Empty `Placeholder-Parts-Workflow-Plan.md`; Invoice-Roadmap placeholder queue |
| Supplier UX (autocomplete, preferred supplier) | Invoice-Roadmap v2 |
| Price history + update preview | Invoice-Roadmap v2 |
| Email `:` contains fallback (if Lucene/FTS email field kept) | `.cursor/plans/email-68ea9ae6.plan.md` |

**Exit:** Parts entry as fast as client entry.

### Phase 7 — Future UI / Odysseus alignment

| Work | SysForge sources | Odysseus note |
|------|------------------|---------------|
| Keyboard shortcuts (Business section) | Future-UI Phase 2 | Reuse Odysseus shortcut settings; avoid second system (`future-ui-backlog.md`) |
| User favorites for dashboard cards | Future-UI | Replace hardcoded favorites |
| Sidebar ↔ card sync, breadcrumbs | Future-UI | |
| Themes / profiles / plugins | Future-UI Phase 3 | Prefer Odysseus themes + MCP/skills over Avalonia plugin vision |

**Exit:** Shell polish without blocking bench work.

### Phase 8 — Projects depth & release gate

| Work | SysForge sources |
|------|------------------|
| P4 rich notes + PDF/screenshot in notes | Projects plan P4 |
| P6 inventory light + reservations | Invoice-Roadmap inventory |
| Repair timeline | Repair-Documentation-System.md |
| Zoom/pan, reorder/delete images | Repair deferred table |
| S5 mobile companion (if tablet browser insufficient) | `Screw-Map-S5-Mobile-Companion-Plan.md` |
| Install docs + screenshots | Projects P7 release gate |

**Exit:** Matches SysForge “official public release” gate for projects feature set.

### Phase 9 — Invoice ops v3+ (documents & money)

| Work | SysForge sources |
|------|------------------|
| PDF generation + email send | Invoice-Roadmap v3+, Features-and-Scope |
| Payments / partial payments | Invoice-Roadmap v3+ |
| Reporting (sales, unpaid, tax) | Invoice-Roadmap v3+ |
| Invoice-level discounts / locked snapshot fields | Invoice-Roadmap v2 leftovers |
| Client merge tool | DB-12 deferred |
| Roles / audit log | Invoice-Roadmap v3+ |

**Exit:** Professional shop paperwork without leaving Odysseus.

### Phase 10 — Integrations track (separate product)

| Work | SysForge sources | Odysseus approach |
|------|------------------|-------------------|
| Snipe-IT asset link | Integrations.md, Features-and-Scope | Micro-add-on / MCP (`product-vision-integrations.md`) |
| Wazuh / NetBox / n8n | same | Do not block repair shop MVP |
| Label PDF/ZPL, portable collector | Features-and-Scope v0.4 | Later |
| Multi-instance coordination | Q-04 / Database-Design-Document | Document limits first |

**Exit:** Managed-IT vision remains optional; repair shop stays usable alone.

### Suggested priority stack (next 90 days of port work)

1. Phase 0–1 (plugin + invoice MVP)  
2. Phase 2 (client MRU + dashboard)  
3. Phase 3 (work orders / projects hub)  
4. Phase 4 (screw map annotate + S2)  
5. Phase 5 (backup completeness)  
6. Then Phase 6–10 as capacity allows  

---

## 4. Explicit “not yet planned in odysseus” list

Items that appear in SysForge plans but are **missing or only vaguely implied** in Odysseus `docs/research/sysforge/` / `ROADMAP.md` / `docs/plans/` (no dedicated port card, phase, or acceptance criteria).

### 4.1 High value for ease-of-use (should add to Odysseus planning)

| Item | SysForge source | Why it matters |
|------|-----------------|----------------|
| Client MRU / recent 6 + last-used default | `Plans/UI-Plans/Future-UI-Features.md` | Research inventory lists it Planned but **no port approach card** beyond inventory row |
| DRAFT-08 optional startup/scheduled auto-delete | Draft plan, BUG-017, questionnaire VII3 | Inventory notes Partial; no scheduler wiring plan |
| Per-invoice JSON backup **restore UI** | `Plans/README.md` Partial | Invoice-edit card mentions backup format; restore UX unspecified |
| Q-05 deferred Settings UX (conflict UI, SQL import button, custom folder, auto-restart) | Archive Post-Implementation Improvement 5 | Backup card covers MVP only |
| Client **merge** tool (post-detect) | DB-12 deferred, Invoice-Roadmap v2 | Detection ported in spirit; merge not planned |
| Lucene/FTS **parts** search upgrade | `Plans/README.md` | Clients search planned; parts still “SQL LIKE” without upgrade phase |
| Placeholder **triage queue** UX beyond merge | Invoice-Roadmap v2; empty Placeholder plan | Merge exists; queue UX not in research cards |
| Projects P4 **rich notes** editor spike | Projects-and-Work-Orders-Plan P4 | Mentioned in plan; no Odysseus editor choice |
| Screw map **S2** measurement + reverse lookup | Repair-Documentation-System deferred table | Screw-maps card defers mobile; under-specifies S2 |
| Screw map **zoom/pan / reorder / delete** | Repair status table | Not in research card |
| Repair **timeline** (non-screw journal) | Repair-Documentation-System.md | Inventory lists Planned; no feature card |
| Human-readable `DisplayCode` | Projects plan ID strategy | Open question; not in research |
| Work order **aggregate status enum** finalization | Projects open questions | Schema exists; product enum TBD |
| Archive + hard-delete Diagnostics rules (“don’t ask again today”) | Projects plan Diagnostics | Diagnostics card is light |
| `IncludeArchivedInSearch` setting | Projects plan | Not listed in settings-backup card |
| Price **history** + delta preview on Update Prices | Invoice-Roadmap v2 | Not in invoice-edit research |
| Invoice-level discount + LockedFields | Invoice-Roadmap v2 | Not in research |
| Inventory light (`PartStock`, reservations) | Invoice-Roadmap v2, Projects P6 | Not a dedicated research card |
| Supplier detail UX / preferred supplier | Invoice-Roadmap v2 | `suppliers.md` is minimal CRUD only |
| Nav history **persist across restart** | Future-UI / Main-Menu / BUG-016 | Explicitly deferred; no Odysseus decision |
| Sidebar ↔ dashboard sync, breadcrumbs, status bar | Future-UI-Features.md | future-ui-backlog mentions some; breadcrumbs/status bar thin |
| User-configurable favorites (vs hardcoded) | Future-UI + inventory | future-ui-backlog mentions; no acceptance criteria |
| Email `:` contains wildcard fallback | `.cursor/plans/email-68ea9ae6.plan.md` | Not in research (desktop Lucene-specific) |
| Product-Decisions questionnaire as living Odysseus decision log | `Product-Decisions-Questionnaire.md` | Open answers block S2/S5/P4; not mirrored |

### 4.2 Medium / later (document as backlog, don’t block MVP)

| Item | SysForge source |
|------|-----------------|
| S5 mobile companion (LAN / inbox / relay) | `Screw-Map-S5-Mobile-Companion-Plan.md` (research says defer; no method pick) |
| Google Calendar scheduling | Projects out-of-scope; Features-and-Scope v0.3 |
| Carrier tracking API | Projects plan |
| PDF / email invoices | Invoice-Roadmap v3+ |
| Payments + outstanding balances | Invoice-Roadmap v3+ |
| Reporting / KPIs / saved searches | Invoice-Roadmap v3+ |
| Roles, RBAC, audit log | Invoice-Roadmap v3+; Features-and-Scope later |
| Multi-rate tax jurisdictions | Invoice-Roadmap v3+ |
| Label generation PDF/ZPL | Features-and-Scope |
| Portable collector CLI | Features-and-Scope |
| Accounts tracking (MFA notes) | Features-and-Scope catalog |
| Remediations / conflict review from Wazuh | Features-and-Scope v0.5 |
| Multi-tenant UX | Features-and-Scope later |
| Application-level multi-instance | Q-04 / Database-Design-Document |
| Plugin marketplace / user-created views | Future-UI Phase 3 |
| Performance metrics / memory monitoring UI | Future-UI |
| Managed IT “engagements” separate from Projects | Projects plan appendix / questionnaire IX4 |

### 4.3 Explicitly out of Odysseus SysForge MVP (by existing research)

These are **intentionally not** MVP; keep them on the “not planned for MVP” list:

- Desktop SysForge DB import (`04-data-model-migration.md`)
- Avalonia-faithful plugin architecture inside Odysseus (use MCP/skills instead)
- Dual shortcut systems (reuse Odysseus shortcuts)
- Wazuh / Snipe-IT / NetBox / n8n **bundled** in first Business install

### 4.4 Host-only / non-SysForge (do not migrate as SysForge features)

| Item | Location |
|------|----------|
| Cookbook / SGLang / Deep Research | `ROADMAP.md` |
| Agent prompt bloat / skill injection | `ROADMAP.md` |
| Email IMAP local sync phases | `docs/plans/email/email-local-sync-*` |
| Wipe local Avalonia DB command | `SysForge/commands for future.md` |

---

## 5. Critiques → future work mapping

| Critique outcome | Migration note |
|------------------|----------------|
| Tracker open sections empty | No new open critiques to port (`CRITIQUE_REVIEW_TRACKER.md`) |
| Deferred folders empty; APP-07 / Q-05 archived as done | Carry only **remaining deferred scope** (merge tool, Q-05 UI leftovers) |
| DRAFT-08 accepted as deferred auto-delete | Optional Odysseus scheduled job; default off |
| Q-04 multi-instance policy documented | Port as ops doc, not feature |
| DB-12 merge documented as future | Phase 9 above |

---

## 6. Source index (cite paths)

### SysForge — plans

- `Plans/README.md` — master status table  
- `Plans/TODO.md` — calculator search order (Done)  
- `Plans/Open-Bugs-And-Investigations.md`  
- `Plans/Post-Implementation-Improvements.md` + `Plans/Archive/Post-Implementation-Improvements.md`  
- `Plans/Implementation-Plan/` (Phases 1–9)  
- `Plans/Feature-Plans/Draft-Management-System-Plan.md`  
- `Plans/Feature-Plans/Phase-1-Updated-Plan.md`  
- `Plans/Feature-Plans/Placeholder-Parts-Workflow-Plan.md` (empty stub)  
- `Plans/Feature-Plans/Projects-and-Work-Orders-Plan.md`  
- `Plans/Feature-Plans/Screw-Map-S5-Mobile-Companion-Plan.md`  
- `Plans/Feature-Plans/Screw-Map-Decisions-Questionnaire.md` (redirect)  
- `Plans/Feature-Plans/Product-Decisions-Questionnaire.md`  
- `Plans/UI-Plans/Future-UI-Features.md`  
- `Plans/UI-Plans/Main-Menu-UI-Plan.md`  
- `Plans/UI-Plans/Client-Dashboard-Prototypes.md`  
- `Plans/Product-Vision/Roadmap.md`  
- `Plans/Product-Vision/Invoice-Roadmap.md`  
- `Plans/Product-Vision/Repair-Documentation-System.md`  
- `Plans/Product-Vision/Features-and-Scope.md`  
- `Plans/Product-Vision/Integrations.md`  
- `Plans/Product-Vision/Open-Questions.md`  
- `Plans/Database-Design-Document.md`  

### SysForge — other

- `SysForge/Future-UI-Features.md` (redirect)  
- `.cursor/plans/email-68ea9ae6.plan.md`  
- `.cursor/plans/invoice-calculator-system-508c2075.plan.md` (historical sketch)  
- `.cursor/plans/phase_1_implementation_plan_63f57f78.plan.md` (Done)  
- `Critiques/CRITIQUE_REVIEW_TRACKER.md`  
- `Critiques/Solved-Critiques/` (+ Archive)  
- `commands for future.md`  

### odysseus-sysforge

- `ROADMAP.md`  
- `docs/research/sysforge/00-overview.md` … `07-deployment-packaging.md`  
- `docs/research/sysforge/01-feature-inventory.md`  
- `docs/research/sysforge/features/*.md` (including `future-ui-backlog.md`, `projects-work-orders.md`, `screw-maps.md`, `product-vision-integrations.md`)  
- `docs/plans/*` (email host plans; non-SysForge)  

---

## 7. Maintenance

When a SysForge plan ships in odysseus-sysforge:

1. Update the matching row in §1 and the phase checklist in §3.  
2. Move the item out of §4 (“not yet planned”) into the research feature card or a follow-up plan under `docs/plans/`.  
3. Keep ease-of-use order: **invoice → client loop → projects → screw maps → polish → integrations**.
