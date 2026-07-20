---
title: SysForge AI Phase 3 — detailed implementation plan
type: feat
date: 2026-07-19
topic: sysforge-ai-phase-3-detailed
parent: 2026-07-19-005-feat-sysforge-ai-phase-3-gates-plan.md
architecture: 2026-07-19-010-feat-sysforge-ai-architecture-implementation-plan.md
phase: 3
---

# Phase 3 — detailed implementation plan

## Dependencies

Phase 2.

## Exact actions

`client_merge_preview`, `client_merge`, `client_delete`, `invoice_delete`, `invoice_save_as_new`, `invoice_accept`, `invoice_email`, `invoice_update_prices_apply`, `payment_record`, `payment_void`, `part_delete`, `supplier_delete`, `placeholder_merge_preview`, `placeholder_merge`, `draft_delete`.

## Files to modify

| Path | Change |
|------|--------|
| `src/tools/sysforge.py` | Gated handlers + `_require_gate()` helper |
| `src/confirmation_gates/sysforge.py` | Validators per T2/T3 action |
| `integrations/sysforge/confirmation_gate.py` | Register all gated actions |
| `src/tool_security.py` | Block sysforge writes on `app_api` |
| `src/tools/system.py` | Sysforge write block message in `do_app_api` |
| `tests/test_manage_sysforge_gates.py` | Token required/accepted |
| `tests/test_app_api_sysforge_block.py` | POST blocked, GET allowed |

## Confirmation gates

Implement `require_confirmed_action` for each T2/T3 action. Gate payload includes ids, names, money totals.

## Step order

1. Gate validators + unit tests
2. payment_record, payment_void
3. client_merge, client_delete
4. invoice delete/email/accept/apply prices
5. part/supplier delete, placeholder merge, draft_delete
6. app_api write block

## Definition of done

No gated action succeeds without token; `app_api` POST `/api/sysforge/clients` blocked.
