---
title: SysForge AI tooling — Phase 2 shop loop writes
type: feat
date: 2026-07-19
topic: sysforge-ai-phase-2
parent: 2026-07-19-001-feat-sysforge-business-ai-tooling-master-plan.md
phase: 2
execution: code
---

# Phase 2 — shop loop writes

## Goals

Agents run the daily repair-shop loop: draft or edit invoices, manage devices, save drafts, spin up projects/work orders. Validation and preview precede every invoice commit.

## Dependencies

[Phase 1](2026-07-19-003-feat-sysforge-ai-phase-1-reads-plan.md).

## Estimated sequencing

8–12 days. Critical path for Business AI value.

## Action inventory

### Invoice calculator flow (T1, validate before commit)

| Action | REST | Notes |
|--------|------|-------|
| `invoice_validate` | Internal: `integrations/sysforge/services/invoice_validation.py` | Returns field errors |
| `invoice_preview` | Compute totals, tax, shipping from `DraftDocument` | No persist |
| `invoice_create` | `POST /invoices` | Body from validated draft |
| `invoice_update` | `PUT /invoices/{id}` | Finalized edit path |

Line items accept `part_id` or inline placeholder fields (`sku`, `description`, `unit_price_cents`).

### Invoice devices (T1)

| Action | REST |
|--------|------|
| `invoice_devices_get` | `GET /invoices/{id}/devices` |
| `invoice_devices_set` | `PUT /invoices/{id}/devices` |

### Price sync on finalized invoice (T2 preview in tool, apply gated Phase 3)

| Action | REST | Phase |
|--------|------|-------|
| `invoice_update_prices_preview` | `POST /invoices/{id}/update-prices/preview` | 2 (no gate) |
| `invoice_update_prices_apply` | `POST /invoices/{id}/update-prices/apply` | 3 (T2 gate) |

### Drafts (T1)

| Action | REST |
|--------|------|
| `draft_list` | `GET /drafts` |
| `draft_get` | `GET /drafts/{id}` |
| `draft_save` | `POST /drafts` or `PUT /drafts/{id}` |
| `draft_autosave` | `PUT /drafts/autosave` |
| `draft_pin` | `PATCH /drafts/{id}/pin` |
| `draft_rename` | `PATCH /drafts/{id}` |

### Parts stock & price history (T1)

| Action | REST |
|--------|------|
| `part_stock_set` | `PUT /parts/{id}/stock` |
| `part_price_history_add` | `POST /parts/{id}/price-history` |

### Placeholders (T2)

| Action | REST |
|--------|------|
| `placeholder_convert` | `POST /parts/placeholders/{id}/convert` |

### Projects & work orders (T1–T2)

| Action | REST |
|--------|------|
| `project_hub` | `GET /projects/hub` |
| `project_list` | `GET /projects` |
| `project_get` | `GET /projects/{id}` |
| `project_update` | `PATCH /projects/{id}` |
| `project_status_set` | `PATCH /projects/{id}/status` |
| `project_notes_set` | `PUT /projects/{id}/notes` |
| `project_from_invoice_preflight` | `GET /projects/from-invoice/preflight` |
| `project_create_from_invoice` | `POST /projects/from-invoice` |
| `work_order_get` | `GET /work-orders/{id}` |
| `work_order_from_estimate` | `POST /work-orders/from-accepted-estimate` |

### Screw maps (read prep for Phase 4)

| Action | REST |
|--------|------|
| `screw_map_get` | `GET /projects/{id}/screw-map` |

## API additions

None required. Ensure `invoice_validation` service is callable from tool layer without HTTP hop (import directly for speed).

## Confirmation rules

- Phase 2: **no gates** on `invoice_create` / `invoice_update` (shop speed).
- `placeholder_convert` is T2 but ships without gate in Phase 2; move behind gate if abuse appears (document in `action_help`).
- `invoice_update_prices_apply` deferred to Phase 3 with T2 gate.

## Files to touch

| File | Change |
|------|--------|
| `src/tools/sysforge.py` | Invoice/draft/project handlers |
| `src/tools/sysforge_invoices.py` | `DraftDocument` build, validate, preview |
| `integrations/sysforge/services/invoice_validation.py` | Export stable validate entry if needed |
| `src/tool_schemas.py` | `line_items` array schema, `DraftDocument` ref |
| `tests/test_manage_sysforge_phase2.py` | Full shop loop |
| `tests/test_manage_sysforge_invoices.py` | Validate/preview golden |

## Tests

- `invoice_validate` catches missing client and bad cents.
- `invoice_preview` tax math matches calculator UI fixture.
- `invoice_create` + `invoice_get` round trip with placeholder line.
- `draft_save` → `draft_get` preserves line items.
- `project_from_invoice_preflight` errors when devices missing.
- `project_create_from_invoice` success path.
- `invoice_update_prices_preview` shows delta per line.

## Acceptance criteria

1. Script: search client → build draft with 2 lines → `invoice_validate` → `invoice_create` → `outstanding_list` shows balance.
2. Script: save calculator draft → resume via `draft_get` → promote to invoice.
3. Script: accepted invoice → `project_create_from_invoice` → `project_get` has link.
4. Agent loop examples cover validate-before-create pattern.
5. No `app_api` needed for invoice create in tests.

## Sequencing within phase

1. `DraftDocument` builder + validate/preview
2. `invoice_create` / `invoice_update`
3. Draft CRUD + autosave
4. Devices + projects + work orders
5. Stock/placeholder convert
6. Integration tests

## Handoff

Phase 3 adds destructive ops and gates. Phase 4 adds photo/screw-map uploads. Do not implement merge/delete/email here.
