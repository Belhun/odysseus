# Fill-the-gap plans index

Per-issue implementation plans for SysForge → odysseus-sysforge Business plugin parity.

**Sources of truth**

- Machine-readable list: [`gap-manifest.json`](gap-manifest.json) (18 workstreams)
- Recommended order + deps: [`FILL-GAP-ROADMAP.md`](FILL-GAP-ROADMAP.md)
- Phase narrative: [`../synthesis/MASTER-MIGRATION-PLAN.md`](../synthesis/MASTER-MIGRATION-PLAN.md)

**Effort scale:** S (small) · M (medium) · L (large). Taken from each plan’s Effort section.

---

## P0 — Foundation

| Id | Title | Effort | Plan | Goal |
|----|-------|--------|------|------|
| `schema-money-utc-foundation` | Checksummed migrations + money/UTC helpers | **M** | [schema-money-utc-foundation.md](schema-money-utc-foundation.md) | Real checksummed SQLite schema plus cents/UTC helpers so every later API shares desktop money and time rules. |
| `business-shell-dashboard-router` | Business dashboard shell + inner router | **M** | [business-shell-dashboard-router.md](business-shell-dashboard-router.md) | Replace the status stub with a four-card dashboard and `router.js` multi-view shell. |

---

## P1 — Invoice MVP (shop loop)

| Id | Title | Effort | Plan | Goal |
|----|-------|--------|------|------|
| `clients-crud-fts-duplicates` | Clients CRUD, FTS5 search, duplicate warnings | **M** | [clients-crud-fts-duplicates.md](clients-crud-fts-duplicates.md) | Create/find/edit/soft-delete clients with FTS5 typeahead, matches-before-Add-New, and soft DB-12 duplicate warnings. |
| `parts-placeholders-merge` | Parts catalog + placeholder create/merge | **M** | [parts-placeholders-merge.md](parts-placeholders-merge.md) | Parts CRUD + LIKE search, placeholder create on invoice save, and irreversible merge with confirm. |
| `drafts-service-autosave` | File drafts service, list UI, calculator autosave | **M** | [drafts-service-autosave.md](drafts-service-autosave.md) | File-based drafts (atomic write, lock, leave flush), list UI, and calculator autosave; DRAFT-08 stays off. |
| `invoice-calculator-save-contracts` | Invoice calculator create/edit + save contracts | **L** | [invoice-calculator-save-contracts.md](invoice-calculator-save-contracts.md) | Keyboard-first calculator with same-id edit, save-as-new, busy flags, and placeholder orphan order. |
| `business-settings-mvp` | Business settings UI (tax / currency / autosave) | **S** | [business-settings-mvp.md](business-settings-mvp.md) | In-app Settings for tax, currency, and draft autosave so techs never hand-edit plugin JSON. |
| `nav-lifecycle-view-edit-routes` | Nav lifecycle + View/Edit route contracts | **M** | [nav-lifecycle-view-edit-routes.md](nav-lifecycle-view-edit-routes.md) | Same-surface nav does not kill handlers; View → read-only viewer; Edit → calculator route. |

---

## P2 — Client loop, projects, reliability

| Id | Title | Effort | Plan | Goal |
|----|-------|--------|------|------|
| `classic-client-dashboard` | Classic four-column Client Dashboard | **L** | [classic-client-dashboard.md](classic-client-dashboard.md) | Sole client hub: invoice rail \| preview \| projects \| client edit, with overlay search contracts. |
| `invoice-viewer-return-context` | Invoice viewer + save-as-new return context | **M** | [invoice-viewer-return-context.md](invoice-viewer-return-context.md) | Read-only viewer, price-compare flags, and save-as-new → viewer → Back to Classic with client selected. |
| `projects-wo-four-column` | Projects, work orders, create-from-invoice | **L** | [projects-wo-four-column.md](projects-wo-four-column.md) | Accept → WO → create project(s) from devices into the four-column project workspace. |
| `backup-restore-post-import-reindex` | Plugin backup/restore + BUG-018 reindex | **M** | [backup-restore-post-import-reindex.md](backup-restore-post-import-reindex.md) | Plugin-scoped backup/restore plus client search rebuild on every bulk import/restore path. |
| `diagnostics-readonly-panel` | Read-only Business diagnostics panel | **S** (MVP) | [diagnostics-readonly-panel.md](diagnostics-readonly-panel.md) | Schema version / DB health snapshot with no secret leakage; raw grids optional (M). |
| `draft-retention-draft-08` | Optional DRAFT-08 retention (safe defaults) | **M** | [draft-retention-draft-08.md](draft-retention-draft-08.md) | Opt-in old-draft cleanup only; never silent purge on install/load/boot. |

---

## P3 — Depth

| Id | Title | Effort | Plan | Goal |
|----|-------|--------|------|------|
| `screw-maps-s0-s2` | Screw maps S0–S2 annotate workspace | **L** | [screw-maps-s0-s2.md](screw-maps-s0-s2.md) | HW/Other screw-map schema + HTML canvas/SVG ScrewMapView (single-click, numbered dots, autosave+undo). |
| `parts-search-suppliers-depth` | Parts FTS, suppliers UX, price history, triage | **L** | [parts-search-suppliers-depth.md](parts-search-suppliers-depth.md) | FTS5 parts search, supplier preferred UX, price history + Update Prices preview, placeholder triage queue. |

---

## Deferred

| Id | Title | Effort | Plan | Goal |
|----|-------|--------|------|------|
| `future-ui-mru-shell-polish` | Client MRU, shortcuts, Future UI shell polish | **L** | [future-ui-mru-shell-polish.md](future-ui-mru-shell-polish.md) | Persistent client MRU, host shortcuts, and light shell polish after Classic; no dual theme/shortcut systems. |
| `invoice-ops-pdf-payments-merge` | Invoice v3+ PDF/email/payments + client merge | **L** (epic) | [invoice-ops-pdf-payments-merge.md](invoice-ops-pdf-payments-merge.md) | Paperwork and payments epic (PDF/email/ledger/reporting) plus DB-12 client merge after shop loop + backup. |

---

## Counts

| Phase | Plans |
|-------|------:|
| P0 | 2 |
| P1 | 6 |
| P2 | 6 |
| P3 | 2 |
| Deferred | 2 |
| **Total** | **18** |

Planning docs only in this folder. Product code lives under `integrations/sysforge/` and related host routes when implementation starts.
