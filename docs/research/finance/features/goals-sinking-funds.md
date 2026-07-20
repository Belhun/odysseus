# Goals & sinking funds

## What it is / user value

Save toward specific targets (emergency fund, vacation, down payment). Track progress as balance allocated to goal categories or linked accounts.

**User value:** Motivation and clarity on progress; YNAB and Monarch core feature.

## Competitor examples

- **YNAB:** Category targets by date or monthly contribution
- **Monarch:** Custom goals with account assignment and recommendations
- **PocketGuard:** Savings goals affect In My Pocket
- **Goodbudget:** Envelope per goal

## Odysseus-specific approach

**Goal types:**

| Type | Mechanism |
|------|-----------|
| Category goal | Dedicated category envelope; balance = assigned − spent |
| Account goal | Link savings account; progress = account balance − baseline |
| Target by date | Compute required monthly contribution |

Manual import: progress updates when savings account transactions import.

## Data model changes

```sql
finance_goals (
  id TEXT PK,
  owner TEXT NOT NULL,
  name TEXT NOT NULL,
  target_cents INTEGER NOT NULL,
  current_cents INTEGER DEFAULT 0,  -- computed or manual
  target_date DATE,
  category_id TEXT FK,              -- optional linked category
  account_id TEXT FK,               -- optional linked account
  icon TEXT,
  is_completed BOOLEAN DEFAULT FALSE,
  created_at
)
```

## API / UI surfaces

- `GET/POST/PATCH/DELETE /api/finance/goals`
- `GET /api/finance/goals/{id}/progress` — history series
- Goals dashboard: progress rings
- Suggested monthly contribution = (target − current) / months remaining

## Implementation phases

### MVP

- Create goal with target amount and optional date
- Manual current amount or link to category balance
- Progress bar

### Polish

- Goal history chart
- Multiple goals per category (sub-goals)
- Celebrate completion animation
- Agent: "Am I on track for vacation goal?"

## Dependencies

- [category-budgets.md](category-budgets.md) or [budgeting-envelopes.md](budgeting-envelopes.md)
- [account-aggregation.md](account-aggregation.md)

## Security considerations

- Goal names may be sensitive — encrypt optional

## Open questions / risks

- Account-linked goals need accurate balance from imports only

## Effort estimate

**M**
