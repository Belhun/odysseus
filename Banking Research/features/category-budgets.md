# Category budgets (monthly limits)

## What it is / user value

Set a monthly spending limit per category and track spent vs remaining. Simpler than full envelope budgeting; matches Monarch category mode and Simplifi spending plans.

**User value:** "Am I on track for Groceries this month?" at a glance.

## Competitor examples

- **Monarch:** Category budgeting with monthly targets; historical suggestions
- **Simplifi:** Spending plan with watchlists
- **PocketGuard:** Category limits in premium tier
- **YNAB:** Category targets (more complex — see envelope doc)

## Odysseus-specific approach

- Budget month = calendar month (configurable to statement cycle later)
- Per category: `budgeted_cents` for selected month
- Spent = sum of outflow transactions in category for month (exclude transfers)
- Rollover optional per category (phase 2)
- No "assign every dollar" requirement — unfilled budget categories simply don't warn

## Data model changes

```sql
finance_budget_periods (
  id TEXT PK,
  owner TEXT NOT NULL,
  year_month TEXT NOT NULL,     -- '2025-06'
  UNIQUE(owner, year_month)
)

finance_budget_lines (
  id TEXT PK,
  period_id TEXT FK,
  category_id TEXT FK,
  budgeted_cents INTEGER NOT NULL DEFAULT 0,
  rollover_cents INTEGER DEFAULT 0,
  UNIQUE(period_id, category_id)
)
```

## API / UI surfaces

- `GET /api/finance/budget?month=2025-06` — lines with spent/remaining
- `PUT /api/finance/budget/lines` — bulk set amounts
- `POST /api/finance/budget/copy-previous` — copy last month
- Budget tab: horizontal bars per category, red when over
- Click category → drill to transactions

## Implementation phases

### MVP

- Monthly category limits
- Spent calculation from transactions
- Copy previous month
- Over-budget indicator

### Polish

- Rollover unused funds
- Suggested amounts from 3-month average
- Flex groups (fixed vs discretionary) — see envelope doc overlap

## Dependencies

- [transaction-categorization.md](transaction-categorization.md)
- [account-aggregation.md](account-aggregation.md)

## Security considerations

- Budget amounts not sensitive; owner-scoped

## Open questions / risks

- Credit card payments vs spending — exclude transfer/payment categories from budget

## Effort estimate

**M**
