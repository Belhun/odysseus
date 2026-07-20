---
title: SysForge AI Phase 2 — detailed implementation plan
type: feat
date: 2026-07-19
topic: sysforge-ai-phase-2-detailed
parent: 2026-07-19-004-feat-sysforge-ai-phase-2-shop-loop-plan.md
architecture: 2026-07-19-010-feat-sysforge-ai-architecture-implementation-plan.md
phase: 2
---

# Phase 2 — detailed implementation plan

## Dependencies

Phase 1.

## Exact actions

`invoice_validate`, `invoice_preview`, `invoice_create`, `invoice_update`, `invoice_devices_get`, `invoice_devices_set`, `invoice_update_prices_preview`, `draft_list`, `draft_get`, `draft_save`, `draft_autosave`, `draft_pin`, `draft_rename`, `part_stock_set`, `part_price_history_add`, `placeholder_convert`, `project_hub`, `project_list`, `project_get`, `project_update`, `project_status_set`, `project_notes_set`, `project_from_invoice_preflight`, `project_create_from_invoice`, `work_order_get`, `work_order_from_estimate`, `screw_map_get`.

## Files to modify

| Path | Change |
|------|--------|
| `src/tools/sysforge.py` | DraftDocument builder; validate imports `invoice_validation` |
| `src/tool_schemas.py` | `line_items`, `draft` object properties |
| `tests/test_manage_sysforge_phase2.py` | Shop loop script |
| `tests/test_manage_sysforge_invoices.py` | Validate/preview golden |

## API additions

None. `invoice_validate` calls `integrations.sysforge.services.invoice_validation` in-process.

## Confirmation gates

None (except `invoice_update_prices_apply` deferred to Phase 3).

## Tests

- validate missing client
- preview tax math
- create + get round trip
- draft_save → draft_get
- project_from_invoice_preflight errors
- project_create_from_invoice success

## Step order

1. DraftDocument builder + validate/preview
2. invoice_create/update
3. Draft CRUD
4. Devices, projects, work orders
5. Stock, placeholder convert
6. Integration tests

## Definition of done

Full shop loop test: search → draft → validate → create → outstanding shows balance.
