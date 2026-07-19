# Migration gap-plans status

**Updated:** 2026-07-17  
**Plugin version:** `0.15.0` (`integrations/sysforge/manifest.json`)  
**Schema:** migrations `0002`–`0030` applied / latest `0030_client_merge`  
**Canonical order:** [`FILL-GAP-ROADMAP.md`](FILL-GAP-ROADMAP.md) · ids in [`gap-manifest.json`](gap-manifest.json)

This file is the **source of truth** for ship state. Per-issue plans stay historical; prefer this table when picking work.

---

## Workstream status (all 18)

| Id | Phase | Status | Plugin notes |
|----|-------|--------|--------------|
| `schema-money-utc-foundation` | P0 | **Done** | Migrations `0002`–`0015`; money/UTC helpers; install + lazy migrate |
| `business-shell-dashboard-router` | P0 | **Done** | Dashboard cards, inner router, history, LRU cache |
| `business-settings-mvp` | P1 | **Done** | `GET`/`PUT /settings`; tax/currency/autosave |
| `parts-placeholders-merge` | P1 | **Done** | Parts CRUD, placeholders, merge UI |
| `drafts-service-autosave` | P1 | **Done** | File drafts + calculator autosave |
| `clients-crud-fts-duplicates` | P1 | **Done** | CRUD + FTS5 + duplicate warn (merge → invoice-ops D) |
| `invoice-calculator-save-contracts` | P1 | **Done** | Calculator create/edit/save-as-new contracts |
| `nav-lifecycle-view-edit-routes` | P1 | **Done** | View/Edit routes; same-surface short-circuit |
| `classic-client-dashboard` | P2 | **Done** | Four-column Classic workspace |
| `invoice-viewer-return-context` | P2 | **Done** | Viewer + return context + price-compare |
| `projects-wo-four-column` | P2 | **Done** | WO/devices/projects; hub + four-column detail |
| `backup-restore-post-import-reindex` | P2 | **Done** | ZIP/JSON backup + BUG-018 reindex; JSON now includes payments/docs/merge |
| `diagnostics-readonly-panel` | P2 | **Done** | Read-only diagnostics panel |
| `draft-retention-draft-08` | P2 | **Done** | Opt-in retention; default off |
| `screw-maps-s0-s2` | P3 | **Done** | Schema `0020`–`0022` + annotate UI + lock; S3 lookup / library UI deferred |
| `parts-search-suppliers-depth` | P3 | **Done** | FTS + suppliers + price history + triage (A–D) |
| `future-ui-mru-shell-polish` | deferred | **Partial** | MRU + favorites + breadcrumb + `open_sysforge` shipped; nav persist / in-Business shortcuts / themes deferred |
| `invoice-ops-pdf-payments-merge` | deferred | **Done** | Slices A–E (PDF, email, payments, merge, sales CSV); roles/RBAC out |

---

## Migration ID map (desktop → plugin)

Desktop SysForge and the Odysseus plugin share content but **renumber** after clients FTS to avoid collisions.

| Content | Desktop SysForge | Plugin odysseus-sysforge |
|---------|------------------|--------------------------|
| Settings → invoices core | `0002`–`0015` | `0002`–`0015` (aligned) |
| Clients FTS | (Lucene; no SQL FTS file) | `0016_clients_fts.sql` |
| Work orders | `0016_work_orders.sql` | `0017_work_orders.sql` |
| Invoice devices | `0017_invoice_devices.sql` | `0018_invoice_devices.sql` |
| Projects | `0018_projects.sql` | `0019_projects.sql` |
| Screw maps | `0019`–`0021` | `0020`–`0022` |
| Parts FTS | — | `0023_parts_fts.sql` |
| Suppliers v2 | — | `0024_suppliers_v2.sql` |
| Preferred supplier | — | `0025_parts_preferred_supplier.sql` |
| Client MRU `LastInteractedAt` | Planned | `0026_clients_last_interacted.sql` |
| Payments | Planned (v3+) | `0027_payments.sql` |
| Invoice documents | Planned (v3+) | `0028_invoice_documents.sql` |
| Part price history | Planned | `0029_part_price_history.sql` |
| `MergedIntoClientId` | Planned (v2) | `0030_client_merge.sql` |

Never edit an applied migration. Append the next ID after `0030`.

---

## Remaining backlog (honest, short)

| Item | Notes |
|------|--------|
| Future UI leftovers | In-Business shortcut actions (`sysforge_home` / clients / calculator); nav history across reload; Avalonia themes/profiles visions |
| Screw-map depth | S3 “find by measurements”, library publish/clone UI, zoom/pan extras, S5 mobile |
| Projects polish | Rich notes (P4), inventory (P6), DisplayCode |
| Invoice-ops out of scope | Roles/RBAC, multi-jurisdiction tax, recurring invoices, QuickBooks sync |
| Host / integrations | Snipe-IT, Wazuh, NetBox, n8n (MASTER Phase 10) |
| PDF binary in JSON | JSON export stores `InvoiceDocuments` **metadata** only; ZIP backup carries `documents/` files + full DB |

Parity MVP shop loop (quote → Classic → viewer → backup) is **complete**. Remaining work is polish and later epics, not blockers for daily Business use.

---

## Suggested manual smoke test (whole Business plugin)

Run with plugin installed (`features.sysforge` on) and a fresh or known-good `data/plugins/sysforge/sysforge.db`.

1. **Shell** — Open Business; dashboard cards load; Back/Home work; breadcrumb shows `Business › …`.
2. **Settings** — Change tax %; save; reload panel; value sticks. Diagnostics shows schema `0030` and healthy DB.
3. **Clients** — Create client; FTS typeahead finds by name/phone; duplicate warn offers Use existing / Create anyway.
4. **Classic** — Open Clients card → Classic; select client; edit Address/Notes; empty search shows recent MRU.
5. **Calculator** — New invoice (≥1 line); Save → lands Classic with client; Edit same id; Save as new → viewer then Back to Classic.
6. **Viewer ops** — Download PDF; Email… (or confirm 502 if no SMTP); record partial payment → Outstanding list; pay remainder → Paid; void with reason.
7. **Merge** — Create duplicate (Create anyway) → Client merge → survivor keeps invoices; loser gone from search.
8. **Reports** — `#sysforge/reports/sales` → set today → Run → totals match; Download CSV opens with header + invoice row.
9. **Parts** — Catalog search (FTS); triage convert; placeholder merge confirm; optional supplier preferred.
10. **Projects** — Mark accepted → WO; create project from device (blank Device ID refused); four-column detail; Done editing autosaves device fields.
11. **Screw map** — From project Before/After → annotate HW map; place dots; leave and reopen (autosave).
12. **Drafts** — Autosave appears on Drafts list; retention stays **off** by default; pin optional.
13. **Backup** — Create ZIP; Export JSON (confirm `payments` / `invoiceDocuments` keys when present); Restore or import → search still finds clients (BUG-018).

---

## Phase history (condensed)

### P0 — Done
- Schema + money/UTC; Business shell dashboard/router.

### P1 — Done
- Settings, parts+placeholders, drafts, clients FTS, calculator, nav View/Edit.

### P2 — Done
- Classic, viewer return-context, projects/WO, backup+reindex, diagnostics, draft retention.

### P3 — Done
- Screw maps S0–S2 (+ lock); parts FTS / suppliers / price history / triage.

### Deferred — Done / Partial
- **invoice-ops** A–E Done at `0.15.0` (was Partial A–D at `0.14.0`).
- **future-ui-mru** Partial at `0.13.0`+ (MRU shipped; persist/shortcuts deferred).
