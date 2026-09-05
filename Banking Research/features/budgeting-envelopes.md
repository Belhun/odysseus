# Budgeting envelopes (zero-based)

## What it is / user value

YNAB-style zero-based budgeting: assign all available cash to category envelopes until "Ready to Assign" reaches zero. Digital cash envelope method.

**User value:** Forces intentional spending; breaks paycheck-to-paycheck cycle; savings by design.

## Competitor examples

- **YNAB:** Give every dollar a job; category targets; age of money
- **Goodbudget:** Digital envelopes; manual allocation
- **Actual Budget:** Envelope budgeting with rollover
- **EveryDollar:** Zero-based (Dave Ramsey)

## Odysseus-specific approach

Manual import means **no real-time bank balance sync**. Envelope funding uses:

- Sum of inflows in budget accounts (from imported transactions) minus assignments
- User can manually "Add funds" when physical cash or unimported income exists

**Core UI metric:** `Ready to Assign` = cash in budget accounts − sum(envelope assignments)

Envelope balance = assigned + rollover − activity in month

## Data model changes

Extends [category-budgets.md](category-budgets.md):

```sql
-- Add to finance_budget_lines or separate:
finance_envelope_assignments (
  period_id, category_id,
  assigned_cents INTEGER,       -- user assigned this month
  activity_cents INTEGER,       -- computed from transactions
  balance_cents INTEGER,          -- assigned + prior rollover - activity
  rollover_to_next INTEGER
)
```

`finance_accounts.is_budgeted` boolean — only budget accounts count toward Ready to Assign.

## API / UI surfaces

- `GET /api/finance/envelopes?month=` — all envelopes with balances
- `POST /api/finance/envelopes/assign` — `{ category_id, amount_cents }`
- `POST /api/finance/envelopes/move` — move between categories
- Envelope UI: left panel Ready to Assign, category list with available/balance
- Cover overspending flow (move from another envelope)

## Implementation phases

### MVP

- Assign dollars to categories
- Ready to Assign calculation
- Activity from imported transactions

### Polish

- Targets (monthly funding goals per category)
- Age of money metric
- Auto-assign rules ("fund Rent first")
- YNAB-style cover overspending wizard

## Dependencies

- [category-budgets.md](category-budgets.md)
- [account-aggregation.md](account-aggregation.md) — budget vs tracking accounts

## Security considerations

- Standard owner scope

## Open questions / risks

- Without live sync, cash account balance may drift — reconciliation feature critical
- Steeper learning curve — provide onboarding tour

## Effort estimate

**L**
