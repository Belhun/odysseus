---
title: SysForge AI tooling — Phase 7 and more (optional)
type: feat
date: 2026-07-19
topic: sysforge-ai-phase-7
parent: 2026-07-19-001-feat-sysforge-business-ai-tooling-master-plan.md
phase: 7
execution: code
optional: true
---

# Phase 7 — and more (optional)

## Goals

Stretch capabilities after core Phases 0–6 ship: collections workflow, payment plans, richer reporting, operational digests, batch invoicing. Each sub-feature can ship independently.

## Dependencies

[Phase 1](2026-07-19-003-feat-sysforge-ai-phase-1-reads-plan.md) reports/outstanding; [Phase 2](2026-07-19-004-feat-sysforge-ai-phase-2-shop-loop-plan.md) invoices; [Phase 6](2026-07-19-008-feat-sysforge-ai-phase-6-admin-plan.md) stable tooling base.

## Estimated sequencing

Backlog; 2–4 days per sub-feature.

## Action inventory

### Aging and collections

| Action | Purpose | API |
|--------|---------|-----|
| `report_aging` | Buckets: current, 30, 60, 90+ days | **NEW** `GET /reports/aging` |
| `collections_list` | Clients with overdue totals sorted | Compose from aging + `client_get` |
| `UI collections` | `open_panel business route=outstanding filter=overdue` | ui_control |

### Payment plans (if product approves)

| Action | Purpose | API |
|--------|---------|-----|
| `payment_plan_create` | Schedule installments for invoice | **NEW** schema + routes |
| `payment_plan_list` | Active plans | NEW |
| `payment_plan_record` | Apply scheduled payment | T2 gate |

Defer until desktop SysForge or plugin schema adds payment plan tables.

### Natural language reports

| Action | Purpose |
|--------|---------|
| `report_sales` | Existing; agent summarizes |
| `report_custom` | **NEW** parameterized report DSL (date range, group_by client/part) |

Start with agent-side summarization of `report_sales` + `outstanding_list` before building DSL.

### Health digest

| Action | Purpose |
|--------|---------|
| `health_digest` | One call: schema status, outstanding total, draft count, placeholder queue depth, last backup age, companion inbox |

Composes existing endpoints; no new API required for MVP.

### Batch invoices

| Action | Purpose | Gate |
|--------|---------|------|
| `invoice_batch_validate` | N clients × template lines | T0 |
| `invoice_batch_create` | Create N invoices | T2 |

Use case: monthly service contracts. Requires idempotency keys per client+period.

### Navigation enhancements

| Action | Purpose |
|--------|---------|
| `business_navigate` | Wrapper: `ui_hint` + `open_panel` for MRU clients, last invoice |

## API additions (prioritized)

1. `GET /reports/aging` — high value, low risk
2. `health_digest` — tool-only composition first
3. Payment plan tables — product gate
4. `POST /invoices/batch` — after single-invoice tooling proven

## Confirmation rules

- `invoice_batch_create`: T2 with client count and total revenue preview.
- `payment_plan_create`: T2.
- `payment_plan_record`: T2 per installment.

## Files to touch

| File | Change |
|------|--------|
| `integrations/sysforge/routes_reports.py` | Aging endpoint (new module) |
| `src/tools/sysforge.py` | Phase 7 actions |
| `src/tools/sysforge_digest.py` | `health_digest` composer |
| `src/tool_schemas.py` | Batch invoice params |
| `tests/test_manage_sysforge_phase7.py` | Per sub-feature |

## Tests

- `report_aging` buckets match fixture invoices with backdated `due_date`.
- `health_digest` returns all sections without N+1 HTTP (prefer single service call).
- `invoice_batch_validate` catches duplicate period per client.
- `invoice_batch_create` with token creates N invoices; idempotent retry safe.

## Acceptance criteria

Per sub-feature:

| Feature | Done when |
|---------|-----------|
| Aging | Agent answers "who is 60+ days overdue" |
| Health digest | Morning shop briefing in one tool call |
| NL reports | Agent summarizes sales report with citations to invoice ids |
| Batch invoices | 10-client batch with dry_run |
| Payment plans | Ship only if schema lands |

## Sequencing recommendation

1. `health_digest` (composition only)
2. `report_aging` API + tool
3. NL reports (prompt + examples only)
4. Batch invoices
5. Payment plans (blocked on product)

## Out of scope

- Desktop Avalonia parity for vision backlog items
- Wazuh/Snipe-IT integrations (product vision P3)
- Lucene migration beyond existing FTS5

## Parity note

Phase 7 rows in master checklist are explicitly **optional**. They do not block "full Business AI tooling" declaration for Phases 0–6.
