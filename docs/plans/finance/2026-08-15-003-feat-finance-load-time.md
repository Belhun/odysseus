# Finance load time after large imports

**Branch:** `feat/finance-trustworthy-books`  
**Date:** 2026-08-15

## Problem

After importing ~3300 Wells rows, opening Finance takes 20–40 seconds. `GET /api/finance/accounts` and `GET /api/finance/categories` both log as slow. The transaction list (50 rows) is fine once those return.

Measured cause: both list endpoints call `ensure_default_categories`, which always calls `maybe_backfill_movements`. That helper runs `detect_movements` whenever **any** row still has `movement_class IS NULL`. Imported spend/income rows are supposed to stay null (sign infers class). About 2651 rows stay null, so every Finance open re-runs pairing over the whole ledger. Pairing is O(n²) over unmatched rows. The two GETs run in parallel and fight the SQLite write lock, which is why categories can sit at ~40s.

Preloading all 3300 rows into the browser would make this worse. The machine already has the SQLite file. What we need is: do not redo ledger-wide detect on every paint, warm the one-shot backfill in the background, and make detect itself scale.

## In scope

- Stop movement backfill on the accounts/categories GET path.
- Run movement backfill at most once per owner (`movement_backfill_v1_owners` stamp). Import commit already calls `detect_movements`.
- Warm that one-shot backfill in a daemon thread after app startup so the first Finance open is not the bill.
- Pair detect by opposite `amount_cents` instead of scanning every unmatched row.
- Add `(account_id, date)` index for posted SUM.

## Out of scope

- Redis, a second database, or loading the full ledger into the SPA.
- Changing spend/income inference for null `movement_class`.
- Navy Fed debit-sign / generic-CSV import (separate issue).
- Rewriting reports or the transaction grid beyond the hot path.

## Approach

1. `ensure_default_categories` seeds categories only. No `maybe_backfill_movements`.
2. `maybe_backfill_movements` stamps the owner in `config.json` after one run, even if null classes remain.
3. `app.py` startup schedules `schedule_movement_warmup()` (daemon). Tests that mount only the finance router do not start the full app lifespan, so they stay isolated.
4. `detect_movements` indexes unmatched rows by amount and looks up `-amount`.
5. Schema migrate adds `ix_finance_tx_account_date`.

## Files

- `integrations/finance/services/categories.py`
- `integrations/finance/services/movements.py`
- `integrations/finance/database.py`
- `integrations/finance/models.py`
- `app.py`
- `tests/test_finance_movements.py`
- `tests/test_finance_transactions.py`

## Tests

- Listing accounts with many unclassified rows does not call `detect_movements`.
- `maybe_backfill_movements` runs detect once per owner, then no-ops.
- Existing unique same-day auto-link and ambiguous-peer tests still pass.
- Detect on two accounts with hundreds of non-matching rows still auto-links the unique pair.
