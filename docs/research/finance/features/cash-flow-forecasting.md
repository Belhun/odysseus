# Cash-flow forecasting

## What it is / user value

Project future account balances based on recurring bills, known income, and average discretionary spend. Answer "will I overdraft before payday?"

**User value:** Monarch and Simplifi differentiator; forward-looking vs backward-looking reports.

## Competitor examples

- **Monarch:** Cash-flow projections
- **Simplifi:** Spending plan with projected balances
- **Tiller:** Cash flow forecast templates
- **Copilot:** Predictive spending

## Odysseus-specific approach

Without live sync, forecast uses:

- Current account balance (from imports + reconcile)
- Confirmed [recurring bills](recurring-bills.md) as scheduled outflows
- Optional expected income (recurring or manual paycheck date)
- Historical average daily spend as discretionary burn rate (optional)

Project daily balance for next 30–90 days.

## Data model changes

```sql
finance_forecast_settings (
  owner TEXT PK,
  horizon_days INTEGER DEFAULT 30,
  include_discretionary_burn BOOLEAN DEFAULT TRUE,
  discretionary_daily_cents INTEGER  -- computed or override
)

finance_scheduled_items (
  id TEXT PK,
  owner TEXT NOT NULL,
  account_id TEXT FK,
  name TEXT,
  amount_cents INTEGER,
  due_date DATE,
  is_income BOOLEAN,
  source TEXT                   -- recurring_id | manual
)
```

## API / UI surfaces

- `GET /api/finance/forecast?account_id=&days=30` — series of `{ date, balance_cents }`
- `GET /api/finance/forecast/events` — list scheduled items in horizon
- Forecast chart overlaying balance line + bill markers
- "Low balance" warning threshold

## Implementation phases

### MVP

- Project from recurring bills only
- Single account forecast
- 30-day horizon

### Polish

- Multi-account combined forecast
- Income scheduling
- Discretionary burn from 90-day average
- What-if: add hypothetical expense

## Dependencies

- [recurring-bills.md](recurring-bills.md)
- [account-aggregation.md](account-aggregation.md)
- [multi-account-reconciliation.md](multi-account-reconciliation.md) — accurate starting balance

## Security considerations

- Forecast data derived; no new PII

## Open questions / risks

- Forecast accuracy low without regular imports — show "last import date" disclaimer
- Variable bills (utilities) — use average of last 3

## Effort estimate

**L**
