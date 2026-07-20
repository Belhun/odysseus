# Debt payoff planner

## What it is / user value

Model debt repayment strategies (avalanche, snowball) across loan and credit card accounts. Show interest saved and payoff date when user adds extra payments.

**User value:** YNAB loan planner and PocketGuard debt tools; motivation for extra payments.

## Competitor examples

- **YNAB:** Loan calculator; interest and time saved per extra dollar
- **PocketGuard:** Debt payoff optimization
- **Monarch:** Loan tracking with balances
- **Undebt.it / similar:** Avalanche vs snowball (specialized)

## Odysseus-specific approach

- Loan accounts store: `principal_cents`, `apr_bps`, `minimum_payment_cents`
- Credit cards: balance from transactions; APR optional
- User sets monthly extra payment budget
- Simulator runs month-by-month without modifying real transactions

**Strategies:**

| Strategy | Order |
|----------|-------|
| Avalanche | Highest APR first |
| Snowball | Lowest balance first |

## Data model changes

```sql
-- Extend finance_accounts for loan type:
-- apr_bps INTEGER, minimum_payment_cents INTEGER, original_principal_cents

finance_debt_plans (
  id TEXT PK,
  owner TEXT NOT NULL,
  strategy TEXT,                -- avalanche|snowball
  extra_payment_cents INTEGER,
  created_at
)
```

Simulation is computed on read — no persistent amortization table unless user saves plan.

## API / UI surfaces

- `GET /api/finance/debt/summary` — all debts with APR, balance, min payment
- `POST /api/finance/debt/simulate` — `{ strategy, extra_cents }` → payoff dates, total interest
- Debt tab: comparison chart avalanche vs snowball
- Per-loan detail from imported payment history

## Implementation phases

### MVP

- Loan account fields
- Basic simulator (avalanche only)
- Payoff date + total interest

### Polish

- Snowball comparison side-by-side
- "What if $100 more?" slider
- Link goal to debt payoff
- Import loan payments from NFCU auto loan CSV

## Dependencies

- [account-aggregation.md](account-aggregation.md)
- [goals-sinking-funds.md](goals-sinking-funds.md) optional

## Security considerations

- Loan balances sensitive — account encryption covers

## Open questions / risks

- APR not in bank CSV — user must enter manually
- Variable rate loans — out of scope MVP

## Effort estimate

**M**
