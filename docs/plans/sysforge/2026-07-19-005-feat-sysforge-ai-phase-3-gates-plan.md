---
title: SysForge AI tooling — Phase 3 gates and destructive actions
type: feat
date: 2026-07-19
topic: sysforge-ai-phase-3
parent: 2026-07-19-001-feat-sysforge-business-ai-tooling-master-plan.md
phase: 3
execution: code
---

# Phase 3 — gates + destructive

## Goals

Irreversible and financial actions require `ask_user` confirmation with preview payloads. Begin blocking SysForge **writes** via `app_api` so agents cannot bypass gates.

## Dependencies

[Phase 2](2026-07-19-004-feat-sysforge-ai-phase-2-shop-loop-plan.md).

## Estimated sequencing

5–8 days.

## Action inventory

### Client merge & delete (T3)

| Action | REST | Gate |
|--------|------|------|
| `client_merge_preview` | `GET /clients/merge/candidates` + local diff summary | T0 |
| `client_merge` | `POST /clients/merge` | T3 |
| `client_delete` | `DELETE /clients/{id}` | T3 |

Gate payload: survivor id, merged id(s), invoice count reassigned, name/phone snapshot.

### Invoice destructive & comms (T2–T3)

| Action | REST | Gate |
|--------|------|------|
| `invoice_delete` | `DELETE /invoices/{id}` | T3 |
| `invoice_save_as_new` | `POST /invoices/{id}/save-as-new` | T2 |
| `invoice_accept` | Business accept flow (status transition) | T2 |
| `invoice_email` | `POST /invoices/{id}/email` | T3 |
| `invoice_update_prices_apply` | `POST /invoices/{id}/update-prices/apply` | T2 |

`invoice_accept` maps to finalized/accepted status per plugin contract; include total cents in gate.

### Payments (T2–T3)

| Action | REST | Gate |
|--------|------|------|
| `payment_record` | `POST /invoices/{id}/payments` | T2 |
| `payment_void` | `POST /payments/{id}/void` | T3 |

### Parts & suppliers delete (T3)

| Action | REST | Gate |
|--------|------|------|
| `part_delete` | `DELETE /parts/{id}` | T3 |
| `supplier_delete` | `DELETE /suppliers/{id}` | T3 |

### Placeholder merge (T3)

| Action | REST | Gate |
|--------|------|------|
| `placeholder_merge_preview` | Build from `GET /placeholders/groups` + selection | T0 |
| `placeholder_merge` | `POST /placeholders/merge` | T3 |

Preview must state: target part id, placeholder ids, **invoice line prices unchanged**.

### Drafts delete (T2)

| Action | REST | Gate |
|--------|------|------|
| `draft_delete` | `DELETE /drafts/{id}` or `POST /drafts/delete` | T2 |

## API additions

None. Optional: `POST /clients/merge/preview` if GET candidates insufficient for agent summary (prefer tool-layer diff).

## Confirmation rules

Implement in `src/confirmation_gates/sysforge.py`:

1. Agent calls preview action first when available.
2. Agent calls `ask_user` with `confirmation` block: `tool=manage_sysforge`, `action=<action>`, `payload=<preview data>`.
3. User approves → `confirmation_token` passed to gated action.
4. Token single-use per action batch; reuse pattern matches `manage_finance` `create_category`.

**app_api block (partial):** In `src/tool_security.py`, reject `app_api` `POST`/`PUT`/`PATCH`/`DELETE` to `/api/sysforge/*` with message: "Use manage_sysforge."

Reads via `app_api` still allowed until Phase 6.

## Files to touch

| File | Change |
|------|--------|
| `src/tools/sysforge.py` | Gated action handlers |
| `src/confirmation_gates/sysforge.py` | Register T2/T3 actions |
| `src/tool_security.py` | Block SysForge writes on `app_api` |
| `src/tools/system.py` | Update `app_api` hint text |
| `src/agent_loop.py` | Gate workflow examples |
| `tests/test_manage_sysforge_gates.py` | Token required / rejected |
| `tests/test_app_api_sysforge_block.py` | Write block |
| Reuse | `tests/test_sysforge_client_merge.py`, `test_sysforge_invoice_ops.py` vectors |

## Tests

- `client_merge` without token → gate error with instructions.
- Valid token → merge succeeds; token reuse fails.
- `payment_record` gate shows amount cents and invoice id.
- `invoice_email` gate shows recipient and invoice number.
- `placeholder_merge` gate text mentions line prices preserved.
- `app_api` POST `/api/sysforge/clients` → blocked.
- `app_api` GET `/api/sysforge/clients/search` → still allowed.

## Acceptance criteria

1. No gated action succeeds without token in automated tests.
2. Preview → ask_user → commit flow documented in `action_help` for merge and delete.
3. `app_api` cannot merge clients or delete invoices.
4. Gate payloads include money and entity names human-readable.
5. Parity checklist T3 rows satisfied.

## Sequencing within phase

1. Gate registry + unit tests
2. Payment record + void
3. Client merge + delete
4. Invoice delete/email/accept/apply prices
5. Part/supplier delete + placeholder merge
6. `app_api` write block + docs

## Handoff

Phase 4 handles binary uploads. Phase 5 bulk parts. Phase 6 completes `app_api` read block and admin T4 gates.
