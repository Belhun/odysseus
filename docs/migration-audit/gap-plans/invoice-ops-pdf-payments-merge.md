# Gap plan: Invoice v3+ PDF/email/payments + client merge

| Field | Value |
|-------|--------|
| **Issue id** | `invoice-ops-pdf-payments-merge` |
| **Title** | Invoice v3+ PDF/email/payments + client merge |
| **Phase** | **deferred** (MASTER §5 Phase 9 / §7 Later; future-plans-roadmap §3 Phase 9) |
| **Priority** | low |
| **Domain** | invoices |
| **Effort** | **L** (epic; ship as ordered slices A–E, each ~M) |
| **Depends on** | `invoice-viewer-return-context`, `backup-restore-post-import-reindex` |
| **Sources** | gap-manifest · MASTER §5 Phase 9 / §7 Later · future-plans-roadmap §3 Phase 9 / §4.2 · feature-gap-matrix §3 Invoice v2/v3 · `Plans/Product-Vision/Invoice-Roadmap.md` v3+ · DB-12 merge notes in `Plans/Archive/Post-Implementation-Improvements.md` · Product-Decisions-Questionnaire III8 / V1 · chats [55127af8](../chat-reviews/55127af8-5c1c-45ed-8f64-b1558712f3cf.md), [784da76d](../chat-reviews/784da76d-e4c8-44bb-9eca-59d99e1b0980.md) · research `invoice-viewer.md`, `05-backend-services.md` |

**Constraint for this doc:** planning only. No product code changes in this workstream write-up.

**When to start:** After shop loop (calculator → viewer → Classic client) and plugin backup/reindex are solid. Do not pull this into P0–P2 parity MVP.

---

## Goal / success

Give a repair shop **professional paperwork and money tracking inside Odysseus Business** without leaving the host app: printable/emailable invoices, recorded payments (including partial), unpaid/outstanding views, and a **client merge** tool that cleans accidental duplicates after DB-12 detection-only.

### Success criteria (exit)

1. From invoice viewer (and optionally Classic dashboard), user can **Download PDF** for an invoice; bytes match header + line items + tax/shipping snapshots; money renders from integer cents.
2. User can **Email invoice** to the client’s email (or an override address) with the PDF attached, using Odysseus host mail (`POST /api/email/send`), not a second SMTP stack inside the plugin.
3. User can **record payments** (full or partial) against an invoice; outstanding balance updates; status can move to `Paid` only when balance ≤ 0 (or via explicit mark-paid with audit note).
4. **Outstanding / unpaid list** (minimal reporting slice) shows invoices with balance > 0; sales/tax CSV export is available for a date range.
5. **Client merge:** pick survivor + loser → reassign invoices (and work orders/projects if present) → set `MergedIntoClientId` on loser → soft-delete loser → rebuild client search. Irreversible confirm required.
6. Duplicate **detection** (DB-12) remains warn-only; merge is a separate intentional tool (never auto-merge).
7. Plugin backup/JSON export (from dependency workstream) includes new tables (`Payments`, merge columns, generated PDF attachments if stored).
8. Roles/RBAC and Snipe-IT stay **out** of this exit (tracked separately); audit of merge + payment writes is in scope as a thin append-only log or reuse host logging.

**Exit phrase (roadmap):** “Professional shop paperwork without leaving Odysseus.”

---

## Current state

### SysForge desktop (source of truth)

| Piece | Status | Notes |
|-------|--------|--------|
| Invoice statuses `Estimate` / `Invoiced` / `Paid` | Done | CHECK on `Invoices`; `UpdateInvoiceStatusAsync`, `FinalizeInvoiceAsync` + `SentAt` |
| Invoice viewer / calculator / edit | Done | PDF/print **not** built (`invoice-viewer` research: future) |
| PDF generation | Planned (v3+) | Invoice-Roadmap: `GenerateInvoicePdf(invoiceId)`; service abstraction |
| Email send / templates | Planned (v3+) | Product vision; desktop has no Odysseus mail bridge |
| `Payments` table | Planned (v3+) | Schema only in roadmap: Amount, Method, Reference, ReceivedAt, Notes |
| Partial payments / outstanding | Planned (v3+) | DAL: `AddPayment`, `GetPaymentsByInvoice`, `GetOutstandingInvoices` |
| Reporting (sales, tax, unpaid, LTV) | Planned (v3+) | No desktop UI |
| Invoice-level discount / locked snapshot fields | Planned (v2 leftovers) | Phase 9 table lists with ops; not in migrations yet |
| DB-12 duplicate **detection** | Done (2026-05-18) | Warn + Use existing / Create anyway; no uniqueness on phone/email |
| Client **merge** tool | Deferred | Spec in Post-Implementation Improvements “Future Enhancement: Merge Tool”; checklist open |
| `MergedIntoClientId` | Planned (v2) | In Invoice-Roadmap only; **not** in migrations `0005`–`0021` |
| `Attachments` generic table | Planned (v3+) | Not in migrations; projects use separate attachment tables |
| Roles / Users / AuditLog | Planned (v3+) | MASTER §7 Later; Phase 9 lists roles/audit with ops |
| Placeholder merge | Done | Parts only — **not** a template for client merge UX beyond “confirm irreversible” |

Documented merge approach (desktop, deferred):

- New `ClientMergeView` + VM
- Find candidates (phone/email + similar name); include soft-deleted in search when cleaning
- Side-by-side compare; user picks **master** (survivor)
- Transfer invoices (and jobs/projects per questionnaire III8 — decide before implement)
- Soft-delete loser; update references
- No DB uniqueness constraints (legitimate shared contact stays allowed)

### odysseus-sysforge today

| Piece | Status |
|-------|--------|
| Business plugin shell | Stub install/status; domain CRUD missing until P0/P1 streams |
| Invoice viewer / PDF | Missing; research marks PDF out of MVP |
| Host PDF tooling | Present for **documents** (`src/pdf_form_doc.py`, render/export routes) — reusable patterns, not invoice layout |
| Host email | `POST /api/email/send` (owner-gated); Outlook OAuth still limited (`docs/email-outlook.md`) |
| Payments / merge / reporting | Missing |
| Research note | `05-backend-services.md`: “Potential future: invoice emailed via Odysseus `routes/email_routes.py`” — **not** invoice PDF email yet (future-plans §2.2) |

**Verdict:** Desktop and Odysseus are aligned on **deferral**. This epic is greenfield schema + services on both sides for PDF/payments/merge; Odysseus has a head start on **transport** (email + PDF libs) once invoice data exists.

---

## Scope

### In scope (ordered slices)

Ship in this order unless product reprioritizes. Each slice should be mergeable alone.

| Slice | Name | Effort | Delivers |
|-------|------|--------|----------|
| **A** | Invoice PDF | M | Generate + download PDF; store optional attachment blob under plugin data; viewer CTA |
| **B** | Email send | M | Attach PDF; call host `/api/email/send`; set `SentAt` / status rules; simple template (subject/body) |
| **C** | Payments + outstanding | M | `Payments` table; record/list/void; balance; unpaid list; status sync |
| **D** | Client merge | M | `MergedIntoClientId`; merge API + UI; reassign FKs; search rebuild |
| **E** | Thin reporting | S–M | Date-range sales + unpaid + tax CSV; no full BI dashboard |

**Also in scope (supporting):**

1. New **append-only migrations** after the highest applied shop migration at start time (never edit old files). Likely: `Payments`, `Clients.MergedIntoClientId`, optional `InvoiceDocuments` or reuse roadmap `Attachments` with `EntityType='invoice'`.
2. Money as **integer cents** end-to-end (same as P0 helpers).
3. UTC for `ReceivedAt`, `SentAt`, merge timestamps.
4. Extend plugin backup/JSON export entities once tables exist (coordinate with `backup-restore-post-import-reindex`).
5. Product decision capture for questionnaire gaps before Slice C/D: payment methods list; merge reassigns WO/projects yes/no; PDF layout fields (shop name/logo from Business settings).

### Out of scope

| Item | Why |
|------|-----|
| Parity MVP / P0–P2 shop loop | Already covered by other workstreams; this epic waits |
| Full roles/RBAC / multi-user permissions | MASTER §7 Later; separate track |
| Snipe-IT / Wazuh / NetBox / n8n | Phase 10 integrations |
| Label PDF/ZPL, portable collector | Features-and-Scope; later |
| Multi-jurisdiction tax engines | Invoice-Roadmap v3+ tax regions — after single-rate shop works |
| Recurring invoices / automation reminders | v3+ automations |
| QuickBooks / external accounting sync | Questionnaire V1 “external tool” option — export CSV first |
| Auto-merge on duplicate detect | Explicitly rejected; detection stays advisory |
| Second SMTP stack inside plugin | Reuse host email |
| Avalonia `ClientMergeView` pixel parity | Web Business UI patterns |
| Desktop live `.db` import as onboarding | MASTER out of MVP |
| Finance plugin ledger | Different product (`odysseus-finance`) |

### Explicit product decisions to lock before coding

Record answers in the PR or a short ADR:

1. **Merge cascade (III8):** reassign work orders + projects to survivor, or invoices only?
2. **Paid status:** auto when `sum(payments) >= FinalTotal`, or only manual “Mark paid”?
3. **Email without client email:** allow override To: always, or block with validation?
4. **PDF storage:** regenerate on demand only, or persist file + hash under `data/plugins/sysforge/documents/`?
5. **Void payment:** soft-void with reason vs hard delete?

Defaults if unanswered: (1) invoices + WO + projects; (2) auto when balance ≤ 0 and at least one payment; (3) allow override; (4) persist on generate/email; (5) soft-void.

---

## Dependencies

| Dependency | Why blocked without it |
|------------|------------------------|
| `invoice-viewer-return-context` | PDF/email CTAs live on read-only viewer; return context must exist for post-send navigation |
| `backup-restore-post-import-reindex` | New tables must round-trip; merge/import must rebuild client search (BUG-018 class) |
| `schema-money-utc-foundation` (transitive) | Cents + UTC + append-only migrations |
| `invoice-calculator-save-contracts` (transitive) | Real invoices with items/totals to render and pay |
| `clients-crud-fts-duplicates` (transitive) | Duplicate detection UX; merge search rebuild target |
| `classic-client-dashboard` (soft) | Entry points: unpaid list, merge from client hub |
| `business-settings-mvp` (soft) | Shop name, tax defaults, logo/path for PDF letterhead |
| Host email configured | Slice B needs a working send account (non-Outlook-basic if OAuth still blocked) |

**Soft / parallel:** `projects-wo-four-column` before merge cascade includes WO/projects.

**Do not wait on:** Future UI MRU, screw maps, parts Lucene depth, managed-IT integrations.

---

## Concrete steps

### Step 0 — Prerequisites gate (½ day)

1. Confirm green: create/edit invoice → viewer → back to Classic; plugin backup JSON includes clients/invoices.
2. Open questionnaire answers (III8, V1) or adopt defaults above.
3. Pick next migration IDs (e.g. `00NN_payments.sql`, `00NN_client_merge.sql`, `00NN_invoice_documents.sql`) after `Check-MigrationStatus` equivalent for plugin DB.

### Step 1 — Schema (Slice A–D foundation)

**Payments** (Invoice-Roadmap v3+):

```sql
-- conceptual; finalize types to match money-cents migrations
CREATE TABLE Payments (
  Id INTEGER PRIMARY KEY,
  InvoiceId INTEGER NOT NULL REFERENCES Invoices(Id),
  AmountCents INTEGER NOT NULL,
  Method TEXT NOT NULL,          -- Cash, Card, Check, Transfer, Other
  Reference TEXT,
  ReceivedAt TEXT NOT NULL,     -- UTC ISO
  Notes TEXT,
  IsVoided INTEGER NOT NULL DEFAULT 0,
  VoidedAt TEXT,
  VoidReason TEXT
);
CREATE INDEX IX_Payments_InvoiceId ON Payments(InvoiceId);
```

**Client merge column:**

```sql
ALTER TABLE Clients ADD COLUMN MergedIntoClientId INTEGER NULL
  REFERENCES Clients(Id);
```

**Optional invoice documents** (if persisting PDFs):

```sql
CREATE TABLE InvoiceDocuments (
  Id INTEGER PRIMARY KEY,
  InvoiceId INTEGER NOT NULL REFERENCES Invoices(Id),
  Kind TEXT NOT NULL,           -- 'pdf'
  FileName TEXT NOT NULL,
  MimeType TEXT NOT NULL,
  SizeBytes INTEGER NOT NULL,
  StoredRelPath TEXT NOT NULL,  -- under plugin data dir
  Sha256 TEXT,
  CreatedAt TEXT NOT NULL
);
```

Wire MigrationRunner checksums; never edit prior files.

### Step 2 — Slice A: PDF service + API + viewer button

1. Add `integrations/sysforge/pdf_invoice.py` (or `src/sysforge/…`) with `generate_invoice_pdf(invoice_id) -> bytes`.
2. Layout: shop header (settings) → client block → line table → totals (tax/shipping snapshots) → status/footer. Prefer a small HTML→PDF or reportlab/weasy path already acceptable in Odysseus deps; avoid pulling a second heavy stack if PyMuPDF/HTML path exists.
3. `GET /api/sysforge/invoices/{id}/pdf` → `application/pdf` download.
4. Optional: persist via `InvoiceDocuments` and return `document_id`.
5. Viewer UI: **Download PDF** next to Edit.

### Step 3 — Slice B: Email via host

1. Plugin endpoint `POST /api/sysforge/invoices/{id}/email` body: `{ "to"?, "subject"?, "body_html"?, "account_id"? }`.
2. Server: generate PDF → call existing email send helper (same code path as `POST /api/email/send`) with attachment; do **not** duplicate SMTP auth in plugin.
3. On success: set `SentAt` (UTC); optionally bump status `Estimate` → `Invoiced` if product wants “sent = invoiced.”
4. UI: Viewer **Email…** dialog (To prefilled from client email; editable).
5. Document Outlook/OAuth limitation: same as host (`docs/email-outlook.md`).

### Step 4 — Slice C: Payments

1. Service: `add_payment`, `list_payments`, `void_payment`, `invoice_balance_cents`, `list_outstanding`.
2. Balance = `FinalTotalCents - sum(non-voided payment AmountCents)` (clamp display at 0).
3. Status sync rule (locked in Step 0): auto `Paid` when balance ≤ 0; clearing payments can reopen to `Invoiced` only with explicit confirm.
4. UI: Viewer (or Edit) **Payments** panel: list, add form (amount, method, reference, date), void with reason.
5. Classic / dashboard: **Unpaid** filter or card linking to outstanding list route `#sysforge/invoices/outstanding`.

### Step 5 — Slice D: Client merge

1. `POST /api/sysforge/clients/merge` `{ "survivor_id", "loser_id" }` — reject if equal, missing, or loser already merged.
2. Single transaction:
   - Reassign `Invoices.ClientId` (and WO/Projects if decided)
   - Merge notes/associates JSON carefully (append, don’t clobber)
   - `UPDATE Clients SET MergedIntoClientId=survivor, IsDeleted=1 WHERE Id=loser`
   - Commit → **rebuild client search** (BUG-018 discipline)
3. UI `#sysforge/clients/merge`: candidate finder (reuse `FindPotentialDuplicates` signals) → side-by-side → confirm “Merge is permanent.”
4. After merge: navigating loser id redirects to survivor with banner “Merged into …”.

### Step 6 — Slice E: Thin reporting

1. `GET /api/sysforge/reports/sales?from=&to=` → JSON + `Accept: text/csv`.
2. Metrics: invoice count, parts subtotal, labor, tax, collected payments, outstanding.
3. Settings or dashboard **Reports** panel with date range + download CSV. No chart library required.

### Step 7 — Backup / export parity

1. Extend `SysForgeExportData` (or v1.1 bump) with `payments`, `mergedIntoClientId`, optional documents metadata.
2. Import: restore payments; preserve merge links; rebuild search when clients imported.
3. Update sample fixture with one partial-payment invoice and one merge candidate pair (Walsh/Jenkins style already in sample — add payment rows).

### Step 8 — Docs + freeze

1. Update `integrations/sysforge/README.md`: PDF/email/payments/merge user notes.
2. Mark gap-manifest item complete only when slices A–D exit; E can trail by one PR.
3. Leave roles/Snipe-IT on Phase 10 list.

---

## Files

### Create (Odysseus)

| Path | Role |
|------|------|
| `integrations/sysforge/migrations/00NN_payments.sql` | Payments table |
| `integrations/sysforge/migrations/00NN_client_merge.sql` | `MergedIntoClientId` |
| `integrations/sysforge/migrations/00NN_invoice_documents.sql` | Optional PDF store |
| `integrations/sysforge/payments.py` | Payment domain service |
| `integrations/sysforge/pdf_invoice.py` | PDF generator |
| `integrations/sysforge/client_merge.py` | Merge transaction |
| `integrations/sysforge/reports.py` | Sales/outstanding queries |
| `integrations/sysforge/routes_invoice_ops.py` (or extend `routes.py`) | PDF/email/payments/merge/report endpoints |
| `integrations/sysforge/static/js/invoice_payments.js` | Payments panel |
| `integrations/sysforge/static/js/client_merge.js` | Merge UI |
| `integrations/sysforge/static/js/invoice_pdf_email.js` | Viewer CTAs + email dialog |
| `tests/test_sysforge_invoice_ops.py` | PDF/payments/merge/report tests |
| `tests/fixtures/sysforge/invoice-ops-sample.json` | Extended fixture |
| `docs/migration-audit/gap-plans/invoice-ops-pdf-payments-merge.md` | This plan |

### Modify

| Path | Role |
|------|------|
| Invoice viewer JS (from `invoice-viewer-return-context`) | Download / Email / Payments entry |
| Client dashboard / settings nav | Merge tool + Outstanding + Reports links |
| Backup service (from backup workstream) | Export/import new entities |
| Client search rebuild helper | Called after merge |
| `integrations/sysforge/README.md` | Operator docs |
| Business settings | Shop letterhead fields if missing |

### Desktop reference (read-only)

| Path | Use |
|------|-----|
| `Plans/Product-Vision/Invoice-Roadmap.md` § v3+ | Schema + DAL names |
| `Plans/Archive/Post-Implementation-Improvements.md` § Future Enhancement: Merge Tool | Merge UX/steps |
| `Plans/Feature-Plans/Product-Decisions-Questionnaire.md` III8, V1 | Open decisions |
| `SysForge/Database/ClientService.cs` | `FindPotentialDuplicatesAsync` (detect only) |
| `SysForge/Database/InvoiceService.cs` | Status / finalize / money patterns |
| `SysForge/ViewModels/PlaceholderMergeViewModel.cs` | Irreversible confirm pattern (parts) |

### Do not copy

| Path / behavior | Reason |
|-----------------|--------|
| Desktop Lucene index files | Web uses FTS/rebuild helper |
| New SMTP client in plugin | Host email only |
| Hard UNIQUE on phone/email | Breaks legitimate shared contacts |

---

## API / UI contracts

Prefix: `/api/sysforge`. All require active plugin. Prefer owner/admin for mutate (match other Business writes).

### Endpoints

| Method | Path | Contract |
|--------|------|----------|
| GET | `/invoices/{id}/pdf` | `200 application/pdf`; `404` unknown invoice |
| POST | `/invoices/{id}/email` | Body `{ to?, subject?, body_html?, account_id? }` → `{ ok, message_id?, sent_at }`; `400` if no To; `502/503` if host mail fails |
| GET | `/invoices/{id}/payments` | `{ payments: [...], balance_cents, final_total_cents }` |
| POST | `/invoices/{id}/payments` | Body `{ amount_cents, method, reference?, received_at?, notes? }` → payment row + updated balance/status |
| POST | `/payments/{id}/void` | Body `{ reason }` → voided payment + balance |
| GET | `/invoices/outstanding` | List `{ invoice_id, client_id, name, balance_cents, status }[]` |
| POST | `/clients/merge` | Body `{ survivor_id, loser_id }` → `{ survivor_id, loser_id, invoices_moved, projects_moved, … }`; `409` if invalid pair |
| GET | `/clients/merge/candidates` | Query `phone` / `email` / `client_id` → candidate list (detect-only helper) |
| GET | `/reports/sales` | Query `from`, `to`; JSON default; `?format=csv` or `Accept: text/csv` |

### Status / money rules

- All money fields: **integer cents** in API JSON (`amount_cents`, `balance_cents`).
- Timestamps: UTC ISO-8601 strings.
- `Paid` implies balance ≤ 0; API returns both `status` and `balance_cents` so UI never infers alone.
- Email success updates `SentAt`; does not delete drafts.

### UI routes (hash)

| Route | Purpose |
|-------|---------|
| `#sysforge/invoice-view/:id` | Existing viewer + PDF / Email / Payments actions |
| `#sysforge/invoices/outstanding` | Unpaid list |
| `#sysforge/clients/merge` | Merge tool |
| `#sysforge/reports/sales` | Thin reporting |

---

## UX contracts

Copy into implementation tickets. Fail QA if broken.

- [ ] Viewer **Download PDF** works offline relative to mail (no email account required).
- [ ] **Email** dialog prefills client email; user can override To; empty To blocked with inline error.
- [ ] Email failure shows host error text; invoice data unchanged except no false `SentAt`.
- [ ] Payments: amount > 0 required; overpay allowed but show warning (“balance will be credit”).
- [ ] Void payment requires reason; voided rows stay visible (struck through).
- [ ] Outstanding list empty-state copy when all paid.
- [ ] Merge: side-by-side survivor/loser; primary action disabled until both selected and confirm checked.
- [ ] Merge confirm copy states **permanent** and lists counts (invoices, projects) that will move.
- [ ] After merge, loser disappears from default client search; survivor shows combined invoices.
- [ ] Duplicate **warning** on create still offers Use existing / Create anyway — never forces merge.
- [ ] Money display uses same currency formatting as calculator (settings).
- [ ] Single-writer / activate-deactivate rules from `nav-lifecycle-view-edit-routes` still hold when opening merge/outstanding panels.

---

## Tests / verification

### Automated (pytest)

| Case | Assert |
|------|--------|
| PDF bytes | Non-empty PDF magic `%PDF`; contains invoice name / client display string |
| PDF cents | Totals match DB cents (no float drift) |
| Email happy path | Mock host send; `SentAt` set; attachment present in call args |
| Email failure | Mock 503; no `SentAt`; 502/503 propagated |
| Payment partial | Two payments; balance = total − sum; status not Paid until covered |
| Payment void | Balance restores; `IsVoided=1` |
| Outstanding | Only balance > 0 rows |
| Merge moves invoices | All `ClientId` → survivor; loser `IsDeleted` + `MergedIntoClientId` |
| Merge rebuilds search | Search finds survivor by loser’s old phone after merge (BUG-018 class) |
| Merge rejects | Same id; missing id; chain-merge already merged loser → 409 |
| Report CSV | Header row + one data row for fixture range |
| Backup round-trip | Export/import payments + merge column (once backup extended) |

### Manual walkthrough

1. Create client + invoice with tax/shipping → Viewer → Download PDF → open in OS viewer.
2. Email to yourself via configured account → confirm attachment and `SentAt`.
3. Record partial payment → Outstanding shows remainder → second payment → status Paid.
4. Void first payment → balance/status update.
5. Create duplicate client (Create anyway) → Merge tool → survivor keeps both invoices → search.
6. Plugin backup → restore on clean plugin DB → payments and merge links survive; search works.

---

## Risks

| Risk | Mitigation |
|------|------------|
| Epic scope creep (roles, Snipe-IT, full BI) | Hard out-of-scope list; exit = A–D (+ E optional) |
| Float money regressions | Cents-only API; reuse P0 helpers; golden PDF total tests |
| Email provider auth (Outlook basic auth) | Document host limitation; support app-password providers first |
| Merge data loss | Single transaction; safety backup tip in UI; no hard-delete of loser |
| FK misses (WO/projects/devices) | Checklist of tables with `ClientId` before merge PR; extend transaction |
| PDF layout thrash | Ship plain letterhead v1; no designer chrome in first PR |
| Backup schema drift | Bump export version when adding payments/merge; import rejects unknown critically |
| Status vs payments fights finalized edit rules | Document interaction with Phase 9 desktop “all invoices editable”; payments don’t lock lines |
| Starting too early | Gate on viewer + backup dependencies; keep phase **deferred** in manifest |

---

## Effort

| | |
|--|--|
| **Epic** | **L** |
| Slice A PDF | M |
| Slice B Email | M (smaller if host send helper is clean) |
| Slice C Payments | M |
| Slice D Client merge | M |
| Slice E Reporting | S–M |
| Calendar hint | After P2 backup; not in 90-day MVP stack (MASTER suggested stack stops at Phase 5) |

**Sizing rationale:** Four greenfield subsystems (documents, mail bridge, money ledger, destructive merge) plus schema/backup/test surface. No desktop code to port for PDF/payments; merge has a written spec but zero implementation.

---

## Source index

- `docs/migration-audit/gap-plans/gap-manifest.json` → `invoice-ops-pdf-payments-merge`
- `docs/migration-audit/synthesis/MASTER-MIGRATION-PLAN.md` §5 Phase 9, §7 Later
- `docs/migration-audit/synthesis/future-plans-roadmap.md` §3 Phase 9, §4.2, §5 DB-12 mapping
- `docs/migration-audit/synthesis/feature-gap-matrix.md` §3 Invoice v2/v3
- `SysForge/Plans/Product-Vision/Invoice-Roadmap.md` v2 merge column + v3+ documents/payments
- `SysForge/Plans/Archive/Post-Implementation-Improvements.md` Improvement 4 / Future merge tool
- `SysForge/Plans/Feature-Plans/Product-Decisions-Questionnaire.md` III8, V1
- `odysseus-sysforge/Sysforge research/features/invoice-viewer.md`
- `odysseus-sysforge/Sysforge research/05-backend-services.md` (email via host)
- `odysseus-sysforge/docs/email-outlook.md`
