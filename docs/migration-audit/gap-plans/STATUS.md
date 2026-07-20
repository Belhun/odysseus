# Migration gap-plans status

**Updated:** 2026-07-19  
**Plugin version:** `0.18.0` (`integrations/sysforge/manifest.json`)  
**Schema:** migrations `0002`–`0034` / latest `0034_companion` (`0031` screw-map unique; `0032` DisplayCode index; `0033` PartStock; `0034` companion)  
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
| `projects-wo-four-column` | P2 | **Done** | WO/devices/projects; hub + four-column detail; polish in `0.17.0` (DisplayCode, markdown notes, PartStock) |
| `backup-restore-post-import-reindex` | P2 | **Done** | ZIP/JSON backup + BUG-018 reindex; JSON includes payments/docs/`contentBase64`/merge |
| `diagnostics-readonly-panel` | P2 | **Done** | Read-only diagnostics panel |
| `draft-retention-draft-08` | P2 | **Done** | Opt-in retention; default off |
| `screw-maps-s0-s2` | P3 | **Done** | Schema `0020`–`0022` + annotate UI + lock; library publish/clone + S3; `0031` UNIQUE; zoom/pan + note markers; **S5 companion `0.18.0`** (`0034`) |
| `parts-search-suppliers-depth` | P3 | **Done** | FTS + suppliers + price history + triage (A–D); stock badges via `0033` |
| `future-ui-mru-shell-polish` | deferred | **Done** | MRU + favorites + breadcrumb + `open_sysforge` + in-Business shortcuts; VI2 nav persist = no; Avalonia themes/profiles out |
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
| ScrewMapSets source UNIQUE | — | `0031_screw_map_sets_source_unique.sql` |
| Projects DisplayCode unique index | Column since `0019` | `0032_projects_display_code_index.sql` |
| PartStock (inventory light) | Invoice-Roadmap v2 | `0033_part_stock.sql` |
| Mobile companion (pair/session/context/inbox) | S5 plan | `0034_companion.sql` |

Never edit an applied migration. Append the next ID after `0034`.

---

## Remaining backlog (honest, short)

| Item | Notes |
|------|--------|
| Screw-map depth | Image delete/reorder **skipped** (not on desktop); custom VPS relay out (Tailscale/HTTPS hooks + docs shipped) |
| Projects polish leftovers | Full Obsidian/WYSIWYG notes; PDF/screenshot embed in notes; invoice-line stock reserve; purchase orders; DisplayCode manual override / reprint labels |
| Invoice-ops out of scope | Roles/RBAC, multi-jurisdiction tax, recurring invoices, QuickBooks sync |
| Future UI out of scope | Nav history across reload (VI2 = no); Avalonia themes/profiles / marketplace visions |
| Host / integrations | Snipe-IT, Wazuh, NetBox, n8n (MASTER Phase 10) |

**No shippable leftover slices** in [`remaining-areas.json`](remaining-areas.json). Parity MVP shop loop is **complete**. Remaining work is deeper polish and later epics, not blockers for daily Business use.

### Fleet shipped through `0.18.0`

| Slice | Version | Shipped | Deferred / skipped |
|-------|---------|---------|-------------------|
| Screw-map REVIEW tighten | `0.16.1` | `0031` UNIQUE; block zero-photo publish; DeviceModel sync on project update; `max_results` cap | — |
| In-Business shortcuts | `0.17.0` | Host `sysforge_home` / `clients` / `calculator` | Nav persist; dual Shortcuts UI |
| Screw-map canvas depth | `0.17.0` | Zoom/pan; note-marker place/edit | Image delete/reorder (not on desktop) |
| JSON doc binaries | `0.17.0` | `invoiceDocuments[].contentBase64` export/import | — |
| Projects DisplayCode | `0.17.0` | Auto `YYMMDD-ABBR-CAT-SEQ`; unique index; hub/detail/search | Manual override; reprint labels |
| Rich notes (P4 light) | `0.17.0` | Markdown toolbar + live preview | Obsidian/WYSIWYG; PDF/inline photo embed |
| Inventory light (P6) | `0.17.0` | `PartStock`; catalog on-hand; project badges; soft reserve/release | Draft-invoice reserve; PO; Snipe-IT |
| Screw-map S5 companion | `0.18.0` | Pair+QR+upload (A); context SSE/poll (B); inbox import (C); Tailscale/`public_base_url` docs (D) | Custom VPS relay |

---

## Suggested manual smoke test (whole Business plugin)

Run with plugin installed (`features.sysforge` on) and a fresh or known-good `data/plugins/sysforge/sysforge.db`.

1. **Shell** — Open Business; dashboard cards load; Back/Home work; breadcrumb shows `Business › …`. Optional: bind `sysforge_home` / `clients` / `calculator` in Settings → Shortcuts.
2. **Settings** — Change tax %; save; reload panel; value sticks. Diagnostics shows schema `0034` and healthy DB. Companion panel: enable, inbox path, public URL optional.
3. **Clients** — Create client; FTS typeahead finds by name/phone; duplicate warn offers Use existing / Create anyway.
4. **Classic** — Open Clients card → Classic; select client; edit Address/Notes; empty search shows recent MRU.
5. **Calculator** — New invoice (≥1 line); Save → lands Classic with client; Edit same id; Save as new → viewer then Back to Classic.
6. **Viewer ops** — Download PDF; Email… (or confirm 502 if no SMTP); record partial payment → Outstanding list; pay remainder → Paid; void with reason.
7. **Merge** — Create duplicate (Create anyway) → Client merge → survivor keeps invoices; loser gone from search.
8. **Reports** — `#sysforge/reports/sales` → set today → Run → totals match; Download CSV opens with header + invoice row.
9. **Parts** — Catalog search (FTS); set On hand stock; triage convert; placeholder merge confirm; optional supplier preferred.
10. **Projects** — Mark accepted → WO; create project from device (blank Device ID refused); DisplayCode appears in hub/header; markdown notes save + preview; parts show stock badge; four-column detail; Done editing autosaves device fields.
11. **Screw map** — From project Before/After → annotate HW map; zoom/pan; place screw + note markers; leave and reopen (autosave). Lock → Publish to library (title + tags; refuse with no photos). On a second empty HW project with same device model → Browse library → Reuse. In ScrewMapView → Find by measurements → top 3 → click selects (no auto-assign).
12. **Phone companion (S5)** — Odysseus bound for LAN (`APP_BIND=0.0.0.0`). Project detail → Show QR → phone scans → enter 6-digit code → Take photo → desktop image count rises within seconds. Switch project on laptop → phone context updates. Lock map → phone upload returns conflict. Optional: drop PNG in Inbox → Scan → Import.
13. **Drafts** — Autosave appears on Drafts list; retention stays **off** by default; pin optional.
14. **Backup** — Create ZIP; Export JSON (confirm `payments` / `invoiceDocuments` / `contentBase64` when PDFs exist); Restore or import → search still finds clients (BUG-018).

---

## Phase history (condensed)

### P0 — Done
- Schema + money/UTC; Business shell dashboard/router.

### P1 — Done
- Settings, parts+placeholders, drafts, clients FTS, calculator, nav View/Edit.

### P2 — Done
- Classic, viewer return-context, projects/WO, backup+reindex, diagnostics, draft retention.

### P3 — Done
- Screw maps S0–S2 (+ lock); library publish/clone + S3 measurement lookup; `0031` source UNIQUE; zoom/pan + note markers; parts FTS / suppliers / price history / triage.

### Projects polish — `0.17.0`
- DisplayCode generator + unique index (`0032`).
- Markdown notes toolbar + preview (P4 light).
- PartStock inventory light (`0033`) + project reserve/release.

### Screw-map S5 — `0.18.0`
- Method A LAN pair + QR + phone upload; Method B inbox; Method C Tailscale/HTTPS docs + `public_base_url`; migration `0034`.

### Deferred workstreams — Done
- **invoice-ops** A–E Done at `0.15.0` (was Partial A–D at `0.14.0`).
- **future-ui-mru** Done at `0.17.0` (MRU/favorites/breadcrumb/`open_sysforge` earlier; in-Business shortcuts closed the last shippable slice).
