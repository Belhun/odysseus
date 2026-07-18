# Recurring bills & subscriptions

## What it is / user value

Detect and list recurring charges (rent, Netflix, gym) from transaction history. Show upcoming due dates and monthly total committed to bills.

**User value:** Spot forgotten subscriptions; plan cash needs for the month.

## Competitor examples

- **Monarch:** Automatic subscription detection
- **PocketGuard:** Bill tracking for In My Pocket calculation
- **Simplifi:** Bill reminders and scheduled bills
- **Mint (legacy):** Bill reminders

## Odysseus-specific approach

**Detection algorithm (post-import):**

1. Group transactions by normalized payee
2. Find patterns: same amount ±5%, interval 28–35 days (monthly) or 6–8 days (weekly)
3. Minimum 3 occurrences to suggest
4. User confirms → creates `finance_recurring` record

Manual bill creation also supported (user knows rent is 1st of month).

Optional: link to Odysseus calendar for reminder events (phase 2).

## Data model changes

```sql
finance_recurring (
  id TEXT PK,
  owner TEXT NOT NULL,
  account_id TEXT FK,
  payee TEXT,                   -- encrypted
  category_id TEXT FK,
  amount_cents INTEGER,
  frequency TEXT,               -- weekly|biweekly|monthly|quarterly|annual
  next_due_date DATE,
  is_subscription BOOLEAN DEFAULT FALSE,
  is_active BOOLEAN DEFAULT TRUE,
  auto_detected BOOLEAN DEFAULT FALSE,
  created_at
)
```

## API / UI surfaces

- `GET /api/finance/recurring`
- `POST /api/finance/recurring/detect` — scan and return suggestions
- `POST/PATCH/DELETE /api/finance/recurring`
- Bills tab: list with monthly total, calendar view
- Mark subscription cancelled

## Implementation phases

### MVP

- Manual recurring bill CRUD
- Simple monthly detection (3+ same payee/amount)
- Upcoming list (next 30 days)

### Polish

- Variable amount subscriptions (detect payee, amount range)
- Calendar sync for due dates
- ntfy notification before due
- Link to [subscription-tracking.md](subscription-tracking.md) view

## Dependencies

- [transaction-import-parsing.md](transaction-import-parsing.md)
- [transaction-categorization.md](transaction-categorization.md)

## Security considerations

- Encrypt payee on recurring records

## Open questions / risks

- False positives on coincidental same-amount charges
- Annual bills need longer history — require 2 years import for annual detect

## Effort estimate

**M**
