---
title: SysForge AI Phase 7 — detailed implementation plan
type: feat
date: 2026-07-19
topic: sysforge-ai-phase-7-detailed
parent: 2026-07-19-009-feat-sysforge-ai-phase-7-future-plan.md
architecture: 2026-07-19-010-feat-sysforge-ai-architecture-implementation-plan.md
phase: 7
optional: true
---

# Phase 7 — detailed implementation plan

## Dependencies

Phases 1–6 stable.

## Exact actions (MVP scope)

| Action | Implementation |
|--------|----------------|
| `health_digest` | Compose status, outstanding, drafts, placeholders, backup age, companion inbox — tool-only, no new API |
| `report_aging` | `GET /reports/aging` — buckets by days since `DateCreated` (no DueDate migration) |
| `invoice_batch_validate` | In-tool validation of N client × template lines |
| `invoice_batch_create` | `POST /invoices/batch` with T2 gate + idempotency key per client+period |
| `business_navigate` | Wrapper returning `ui_hint` + suggests `ui_control` |

**Deferred:** `payment_plan_*` (needs schema product approval).

## Files to create/modify

| Path | Change |
|------|--------|
| `integrations/sysforge/services/reports.py` | `aging_report()` |
| `integrations/sysforge/routes.py` | `GET /reports/aging`, `POST /invoices/batch` |
| `src/tools/sysforge_digest.py` | `compose_health_digest()` |
| `src/tools/sysforge.py` | Phase 7 action handlers |
| `tests/test_manage_sysforge_phase7.py` | Per sub-feature |

## No migration required

Aging uses `DateCreated` heuristic per master plan; no `DueDate` column unless product requests later (would be new migration `0035_*.sql`).

## Step order

1. `health_digest` composition
2. `report_aging` API + tool
3. Batch validate/create
4. `business_navigate` + agent_loop NL report examples (prompt-only for `report_sales` summarization)

## Definition of done

- Agent answers "60+ days overdue" via `report_aging`.
- `health_digest` one-call morning briefing.
- Batch 10 clients with dry_run + gated create.

## Remaining gaps (document if not shipped)

- Payment plan tables and actions
- `report_custom` DSL
- Desktop ZIP backup bridge
