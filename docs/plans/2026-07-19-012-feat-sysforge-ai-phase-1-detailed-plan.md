---
title: SysForge AI Phase 1 — detailed implementation plan
type: feat
date: 2026-07-19
topic: sysforge-ai-phase-1-detailed
parent: 2026-07-19-003-feat-sysforge-ai-phase-1-reads-plan.md
architecture: 2026-07-19-010-feat-sysforge-ai-architecture-implementation-plan.md
phase: 1
---

# Phase 1 — detailed implementation plan

## Dependencies

Phase 0 complete.

## Exact actions to implement

**T0 reads:** `diagnostics`, `client_list`, `client_search`, `client_recent`, `client_get`, `client_duplicates`, `client_list_invoices`, `invoice_list`, `invoice_get`, `outstanding_list`, `invoice_price_compare`, `payment_list`, `report_sales`, `part_list`, `part_search`, `part_get`, `part_usage`, `part_stock_get`, `part_price_history_list`, `supplier_list`, `supplier_search`, `supplier_get`, `supplier_parts`, `placeholder_list`, `placeholder_groups`.

**T1 writes:** `client_create`, `client_update`, `client_touch`, `client_link_dossier`, `client_unlink_dossier`, `part_create`, `part_update`, `supplier_create`, `supplier_update`.

## Files to modify

| Path | Change |
|------|--------|
| `src/tools/sysforge.py` | Handler functions per action; `_format_money_fields` on responses |
| `src/tools/dossier.py` | (optional) shared link helpers — or inline in sysforge |
| `src/tool_index.py` | Expand keywords: outstanding, invoice, supplier |
| `src/agent_loop.py` | Examples: outstanding_list, client_search |
| `tests/test_manage_sysforge_phase1.py` | Integration tests |
| `tests/test_manage_sysforge_dossier_link.py` | Dossier bridge |

## API additions

None (all routes exist).

## Confirmation gates

None in Phase 1.

## Tests

- `client_search` ranked results
- `outstanding_list` totals
- `client_create` → `client_get` round trip
- `client_link_dossier` sets `sysforge_client_id`
- Money `*_formatted` in response `data`

## Step order

1. HTTP helper hardening (query params, error mapping)
2. Client reads → writes → dossier link
3. Invoice/outstanding/report reads
4. Parts/suppliers/placeholder reads + T1 creates
5. Integration tests

## Acceptance criteria

1. "Who owes money" via `outstanding_list` without `app_api`.
2. Phone fragment search via `client_search`.
3. Create supplier + part in one session.
4. Dossier link bidirectional in tool output.

## Definition of done

`pytest tests/test_manage_sysforge_phase1.py tests/test_manage_sysforge_dossier_link.py` pass.
