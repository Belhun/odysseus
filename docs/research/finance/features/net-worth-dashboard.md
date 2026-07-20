# Net worth dashboard

## What it is / user value

Snapshot of assets minus liabilities over time. Checking + savings + investments minus credit cards and loans.

**User value:** Holistic financial health; Monarch and Empower centerpiece feature.

## Competitor examples

- **Monarch:** Net worth tracker with historical chart
- **Empower (Personal Capital):** Free net worth + investments
- **YNAB:** Net worth report
- **Copilot:** Net worth in dashboard

## Odysseus-specific approach

Manual import constraints:

- **Liquid accounts:** Balance from transactions + opening balance
- **Credit cards:** Negative liability (balance owed)
- **Loans:** Manual balance updates or amortization from imported payments
- **Manual assets:** User-entered home value, car value (optional rows)

Net worth = sum(asset balances) − sum(liability balances) per date point.

Historical chart: store monthly snapshots on 1st of month or compute from transaction-running balances.

## Data model changes

```sql
finance_manual_assets (
  id TEXT PK,
  owner TEXT NOT NULL,
  name TEXT,
  asset_type TEXT,              -- real_estate|vehicle|other
  value_cents INTEGER,
  as_of_date DATE
)

finance_net_worth_snapshots (
  id TEXT PK,
  owner TEXT NOT NULL,
  snapshot_date DATE,
  total_assets_cents INTEGER,
  total_liabilities_cents INTEGER,
  net_worth_cents INTEGER,
  breakdown_json TEXT           -- encrypted optional detail
)
```

## API / UI surfaces

- `GET /api/finance/net-worth/current`
- `GET /api/finance/net-worth/history?months=24`
- `POST /api/finance/net-worth/snapshot` — manual refresh
- Dashboard card: big number + trend sparkline
- Breakdown by account type

## Implementation phases

### MVP

- Current net worth from account balances
- Simple line chart (6 months) from weekly snapshots

### Polish

- Manual assets (home, car)
- Investment account type (balance only, no lot detail)
- Export history CSV

## Dependencies

- [account-aggregation.md](account-aggregation.md)
- [transaction-import-parsing.md](transaction-import-parsing.md)

## Security considerations

- Net worth is sensitive aggregate — owner-scoped; no public sharing

## Open questions / risks

- Loan balance without full import history — manual adjustment UX critical
- Investment tracking depth — see separate investment doc if added

## Effort estimate

**M**
