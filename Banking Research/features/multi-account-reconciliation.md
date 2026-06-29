# Multi-account reconciliation

## What it is / user value

Mark transactions cleared/reconciled against a bank statement. Close statement periods so the register matches the user's known bank balance.

**User value:** Trust in data accuracy without live sync; essential for envelope budgeting when cash balance must match reality.

## Competitor examples

- **YNAB:** Reconcile account to statement balance
- **Actual Budget:** Reconciliation workflow
- **Quicken:** Classic reconcile mode
- **Tiller:** Balance History sheet vs transactions

## Odysseus-specific approach

1. User enters statement ending date and balance (from bank website or PDF)
2. System shows uncleared transactions in period
3. User checks off transactions that appear on statement
4. Difference must reach zero (or user posts adjustment transaction)
5. Period marked `reconciled`; cleared transactions locked from edit (unlock optional)

Manual import: new imports after reconcile may add uncleared rows — expected workflow.

## Data model changes

```sql
finance_reconcile_sessions (
  id TEXT PK,
  owner TEXT NOT NULL,
  account_id TEXT FK,
  statement_end_date DATE,
  statement_balance_cents INTEGER,
  computed_balance_cents INTEGER,
  difference_cents INTEGER,
  status TEXT,                  -- in_progress|completed
  completed_at
)

-- transaction.status: pending_review | cleared | reconciled
-- reconciled_at, reconcile_session_id on transaction optional
```

## API / UI surfaces

- `POST /api/finance/accounts/{id}/reconcile/start`
- `GET /api/finance/accounts/{id}/reconcile/{session_id}`
- `POST /api/finance/reconcile/{session_id}/toggle/{txn_id}`
- `POST /api/finance/reconcile/{session_id}/finish`
- `POST /api/finance/reconcile/{session_id}/adjustment` — create balancing txn
- Reconcile wizard UI

## Implementation phases

### MVP

- Mark transactions cleared (checkbox)
- Statement balance entry; show difference
- Finish when difference = 0

### Polish

- Full reconcile session history
- Lock reconciled transactions
- Auto-match by import batch date range
- Print reconcile report

## Dependencies

- [account-aggregation.md](account-aggregation.md)
- [transaction-import-parsing.md](transaction-import-parsing.md)

## Security considerations

- Adjustment transactions audited in import log

## Open questions / risks

- Credit card vs checking reconcile semantics differ — UI copy per account type

## Effort estimate

**M**
