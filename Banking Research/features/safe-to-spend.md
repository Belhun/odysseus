# Safe-to-spend (In My Pocket)

## What it is / user value

Single number: how much is safe to spend today after bills, goals, and reserved funds. PocketGuard's signature feature.

**User value:** Low-effort budgeting for users who reject envelope complexity.

## Competitor examples

- **PocketGuard:** "In My Pocket" = income − bills − goals − necessities
- **Monarch:** Flexible spending bucket (related concept)
- **Copilot:** Adaptive daily spend guidance

## Odysseus-specific approach

```
Safe to spend = liquid_balance
              − sum(upcoming_bills before next_income)
              − sum(goal_contributions_due_this_period)
              − optional_category_reserves
```

Liquid balance = sum of checking/cash account balances from imports.

Requires: recurring bills, optional income schedule, category budget remaining (if user uses budgets).

## Data model changes

```sql
finance_safe_to_spend_settings (
  owner TEXT PK,
  include_goal_reserves BOOLEAN DEFAULT TRUE,
  include_discretionary_budget BOOLEAN DEFAULT FALSE,
  next_income_date DATE,
  next_income_cents INTEGER
)
```

Computed metric — no separate storage except cache with TTL.

## API / UI surfaces

- `GET /api/finance/safe-to-spend` — `{ amount_cents, breakdown: { balance, bills, goals, ... } }`
- Dashboard hero widget (large number)
- Tap to expand breakdown
- Optional daily ntfy digest

## Implementation phases

### MVP

- Balance minus upcoming bills (30 days)
- Simple breakdown

### Polish

- Goal reserves
- Per-day safe spend (divide by days to payday)
- Compare to PocketGuard formula docs for parity

## Dependencies

- [recurring-bills.md](recurring-bills.md)
- [account-aggregation.md](account-aggregation.md)
- [category-budgets.md](category-budgets.md) optional
- [goals-sinking-funds.md](goals-sinking-funds.md) optional

## Security considerations

- Aggregate endpoint only

## Open questions / risks

- Meaningless if user imports infrequently — show stale data warning
- Competes with envelope UX — market as "simple mode"

## Effort estimate

**S** (formula + UI on existing data)
