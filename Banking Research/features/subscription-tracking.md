# Subscription tracking

## What it is / user value

Focused view on recurring subscription charges (streaming, SaaS, gym) with monthly/annual cost rollup and cancellation tracking.

**User value:** Answer "how much do I spend on subscriptions?" — Monarch and PocketGuard headline feature.

## Competitor examples

- **Monarch:** Auto-detect subscriptions; monthly total
- **PocketGuard:** Subscription list in premium
- **Copilot:** Recurring charge identification

## Odysseus-specific approach

Subset of [recurring-bills.md](recurring-bills.md) with `is_subscription=true`. UI emphasizes:

- Total monthly equivalent (annual ÷ 12)
- "Zombie" subscriptions (no recent charge but still active flag)
- Last charge date from imported transactions

No bank cancellation integration — user marks cancelled manually.

## Data model changes

Uses `finance_recurring` with `is_subscription` flag. Optional:

```sql
finance_subscription_meta (
  recurring_id TEXT PK FK,
  service_url TEXT,
  cancel_notes TEXT,
  last_charged_date DATE
)
```

## API / UI surfaces

- `GET /api/finance/subscriptions` — filtered recurring list + totals
- Subscription dashboard widget
- "Mark cancelled" action

## Implementation phases

### MVP

- Filter recurring to subscriptions
- Monthly total card
- List with last amount and date

### Polish

- Price change detection (amount increased)
- Export subscription list CSV
- Agent tool: "list my subscriptions"

## Dependencies

- [recurring-bills.md](recurring-bills.md)

## Security considerations

- Standard owner scope

## Open questions / risks

- Overlap with recurring bills UI — combine tabs or separate?

## Effort estimate

**S** (mostly UI on recurring infrastructure)
