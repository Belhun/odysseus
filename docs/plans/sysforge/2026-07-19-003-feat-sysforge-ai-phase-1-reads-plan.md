---
title: SysForge AI tooling — Phase 1 core reads and safe writes
type: feat
date: 2026-07-19
topic: sysforge-ai-phase-1
parent: 2026-07-19-001-feat-sysforge-business-ai-tooling-master-plan.md
phase: 1
execution: code
---

# Phase 1 — core reads + safe writes

## Goals

Agents can look up shop state and create low-risk records without confirmation gates. Replace most read-only `app_api` SysForge traffic.

## Dependencies

[Phase 0 contracts](2026-07-19-002-feat-sysforge-ai-phase-0-contracts-plan.md).

## Estimated sequencing

5–8 days after Phase 0. Parallel track: dossier `sysforge_client_id` wiring can start day 1.

## Action inventory

### Plugin / diagnostics (T0)

| Action | REST mapping | Notes |
|--------|--------------|-------|
| `status` | `GET /status` | Schema version, feature flags |
| `diagnostics` | `GET /diagnostics` | No absolute paths in agent output |

### Clients (T0 read, T1 write)

| Action | REST | Tier |
|--------|------|------|
| `client_list` | `GET /clients` | T0 |
| `client_search` | `GET /clients/search?q=` | T0 |
| `client_recent` | `GET /clients/recent` | T0 |
| `client_get` | `GET /clients/{id}` | T0 |
| `client_duplicates` | `POST /clients/duplicates` | T0 |
| `client_list_invoices` | `GET /clients/{id}/invoices` | T0 |
| `client_create` | `POST /clients` | T1 |
| `client_update` | `PATCH /clients/{id}` | T1 |
| `client_touch` | `POST /clients/{id}/touch` | T1 |
| `client_link_dossier` | Local dossier API + `sysforge_client_id` on Person | T1 |
| `client_unlink_dossier` | Clear `sysforge_client_id` | T1 |

### Invoices (T0 read)

| Action | REST | Notes |
|--------|------|-------|
| `invoice_list` | `GET /invoices` | Filters: client_id, status, date range |
| `invoice_get` | `GET /invoices/{id}` | Full line items in `data` |
| `outstanding_list` | `GET /invoices/outstanding` | Include aging summary line |
| `invoice_price_compare` | `GET /invoices/{id}/price-compare` | Read-only drift flags |

### Payments (T0 read)

| Action | REST |
|--------|------|
| `payment_list` | `GET /invoices/{id}/payments` |

### Reports (T0)

| Action | REST |
|--------|------|
| `report_sales` | `GET /reports/sales` | Pass through date params |

### Parts (T0 read, T1 write)

| Action | REST | Tier |
|--------|------|------|
| `part_list` | `GET /parts` | T0 |
| `part_search` | `GET /parts/search?q=` | T0 |
| `part_get` | `GET /parts/{id}` | T0 |
| `part_usage` | `GET /parts/{id}/usage` | T0 |
| `part_stock_get` | `GET /parts/{id}/stock` | T0 |
| `part_price_history_list` | `GET /parts/{id}/price-history` | T0 |
| `part_create` | `POST /parts` | T1 |
| `part_update` | `PATCH /parts/{id}` | T1 |

### Suppliers (T0 read, T1 write)

| Action | REST | Tier |
|--------|------|------|
| `supplier_list` | `GET /suppliers` | T0 |
| `supplier_search` | `GET /suppliers/search` | T0 |
| `supplier_get` | `GET /suppliers/{id}` | T0 |
| `supplier_parts` | `GET /suppliers/{id}/parts` | T0 |
| `supplier_create` | `POST /suppliers` | T1 |
| `supplier_update` | `PUT /suppliers/{id}` | T1 |

### Placeholders (T0)

| Action | REST |
|--------|------|
| `placeholder_list` | `GET /placeholders` |
| `placeholder_groups` | `GET /placeholders/groups` |

## API additions

None. All endpoints exist in `integrations/sysforge/routes.py`.

## Confirmation rules

None in Phase 1. `client_create` / `part_create` are T1 and ship without gates; document in `action_help` that deletes merge later.

## Files to touch

| File | Change |
|------|--------|
| `src/tools/sysforge.py` | HTTP client wrapper to loopback `/api/sysforge/*` with owner context |
| `src/tools/sysforge_clients.py` | Optional split if file grows |
| `src/tools/dossier.py` | `client_link_dossier` / `unlink` helpers |
| `src/tool_schemas.py` | Phase 1 action params |
| `src/tool_index.py` | Keywords: client, invoice, outstanding, parts, supplier |
| `src/agent_loop.py` | Examples for common reads |
| `tests/test_manage_sysforge_phase1.py` | Integration tests against test DB |
| `tests/test_manage_sysforge_dossier_link.py` | Dossier bridge |

## Tests

- `client_search` returns ranked results for fixture data (`tests/test_sysforge_clients.py` vectors).
- `outstanding_list` sums match API JSON.
- `part_search` SKU-first behavior.
- `client_create` then `client_get` round trip.
- `client_link_dossier` sets `sysforge_client_id`; unlink clears.
- Plugin inactive → error.
- Response includes `*_formatted` money fields.

## Acceptance criteria

1. Agent answers "who owes money" via `outstanding_list` without `app_api`.
2. Agent finds client by phone fragment via `client_search`.
3. Agent creates a supplier and part in one turn.
4. Dossier person links to SysForge client id bidirectionally in tool output.
5. `tool_index` retrieval hits `manage_sysforge` for "invoice outstanding" queries.

## Sequencing within phase

1. HTTP wrapper + `status` / `diagnostics`
2. Client reads → client safe writes → dossier link
3. Invoice/outstanding/report reads
4. Parts/suppliers/placeholder reads + T1 creates
5. Tests + agent_loop examples

## Handoff

Phase 2 adds invoice/draft/project writes. Phase 3 adds `client_delete` and merges. Do not implement delete/merge/email in Phase 1.
