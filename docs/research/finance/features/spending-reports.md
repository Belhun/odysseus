# Spending reports

## What it is / user value

Charts and tables showing where money went: category breakdown, trends over time, income vs expense. Core analytics after categorization.

**User value:** Visual answers for monthly review; YNAB/Monarch/Copilot all emphasize reports.

## Competitor examples

- **YNAB:** Spending breakdown, trends, income vs expense, age of money
- **Monarch:** Customizable charts, spending trends, income reports
- **Empower:** Spending by category
- **Tiller:** Spreadsheet charts (user-built)

## Odysseus-specific approach

- Prebuilt reports (no custom report builder in MVP):
  - Spending by category (pie + table)
  - Monthly trend (bar/line, 6–12 months)
  - Income vs expense
  - Top merchants by payee
- Date range picker; account filter
- Respect splits and exclude transfers
- Export CSV

## Data model changes

- No new tables; aggregate queries on `finance_transactions`
- Materialized summary optional for performance:

```sql
finance_monthly_summary (
  owner, year_month, category_id,
  total_cents INTEGER,
  PRIMARY KEY (owner, year_month, category_id)
)
```

Refresh on import commit or nightly task.

## API / UI surfaces

- `GET /api/finance/reports/spending-by-category?from=&to=`
- `GET /api/finance/reports/trends?months=12`
- `GET /api/finance/reports/income-vs-expense?from=&to=`
- `GET /api/finance/reports/top-payees?limit=20`
- Reports tab with chart library (reuse existing chart deps if any, or Chart.js)

## Implementation phases

### MVP

- Spending by category
- Monthly trend
- Date range filter

### Polish

- Income vs expense
- Top payees
- Compare months YoY
- PDF export
- Agent-generated narrative summary

## Dependencies

- [transaction-categorization.md](transaction-categorization.md)
- [split-transactions.md](split-transactions.md) — report logic must use splits

## Security considerations

- Aggregates only in API responses; no raw payee dump in report endpoints without auth
- Agent summaries: aggregates by default

## Open questions / risks

- Chart performance on large datasets — use summary table

## Effort estimate

**M**
