# Priority matrix

Every steal candidate. Detail lives in the source-app files. Implement in Odysseus style; GPL/MIT clones are evidence, not a vendor tree.

**v1** = next web-modal slice after books. **Later** = after v1. **Phone-only** = no web UI. **Reject** = do not build.

| ID | Feature | Source | Priority | API for phone? | Odysseus hook |
|----|---------|--------|----------|----------------|---------------|
| C1 | Associated titles / payee autocomplete | Cashew `AssociatedTitles` | must-have v1 | suggest later | `finance_categorization_rules` |
| C2 | Named date-range spending caps | Cashew `Budgets` custom period | later | yes if shipped | new table; not envelopes |
| C3 | Upcoming + subscription filter | Cashew subscriptions/upcoming | must-have v1 | `GET /recurring` | `finance_recurring_series` |
| C4 | Lent/borrowed queue labels | Cashew credit/debt types | later | filter | `movement_class=reimbursement` |
| C5 | Goals / loan-goals | Cashew `Objectives` | later | yes | research goals; posted of an account |
| C6 | Heatmap | Cashew `homePageHeatmap.dart` | later | `GET /reports/heatmap` | true spend by day |
| C7 | Net-worth card | Cashew `homePageNetWorth.dart` | must-have v1 (layout) | existing GET | `/reports/net-worth` |
| C8 | Net-worth history | Cashew widget + MyFin patrimony | later | series GET | derive posted |
| C9 | Modal density / sticky tables | Cashew Material | must-have v1 | n/a | CSS in plugin JS |
| C10 | Sheet URL → CSV | Cashew `importCSV.dart` | later | server fetch | existing preview |
| C11 | Live FX | Cashew `exchangeRatesPage.dart` | later | `GET /fx` | account `currency` |
| C12 | Biometric lock | Cashew `initializeBiometrics.dart` | phone-only | n/a | companion + local_auth |
| C13 | Bulk bar polish | Cashew multi-select | must-have v1 | bulk exists | `POST /transactions/bulk` |
| C14 | Firebase / Drive / IAP / email scrape / shared budgets | Cashew | reject | — | [06-rejected.md](06-rejected.md) |
| M1 | Clipboard paste import | MyFin import Step0–3 | must-have v1 | preview text | `/import/preview` + commit |
| M2 | Operator rules (payee/memo/amount) | MyFin `ruleServices.tsx` | must-have v1 | apply on server | extend `finance_categorization_rules` |
| M3 | Rules tab + dry-run | MyFin `Rules.tsx` + July 17 plan | must-have v1 | `POST /rules/test` | overflow tab |
| M4 | Entities / payees | MyFin `/entities` | later | yes | payee registry plan |
| M5 | `is_essential` | MyFin txn flag | later | column | spend label only |
| M6 | Trailing-average budget suggestions | MyFin `avg_12_months_*` | must-have v1 | field on GET budgets | true spend |
| M7 | Month-close lock limits | MyFin `is_open` | later | flag | freeze limits, not txs |
| M8 | Goals + funding accounts | MyFin `goalServices.ts` | later | yes | account posted; no unallocated |
| M9 | Patrimony over time | MyFin patrimony stats | later | history GET | = C8 |
| M10 | Projections | MyFin projections | later | overlay-like | hypothetical; withhold if unclassified |
| M11 | Investing | MyFin `features/invest/` | later | — | not v1 |
| M12 | Split editor UI | MyFin split dialog | must-have v1 | PUT exists | `finance_transaction_splits` |
| M13 | Tags | MyFin tags | later | July 17 plan | no table yet |
| M14 | Dashboard pies / Nivo | MyFin Dashboard | later | spending JSON | CSS bars ok in v1 |
| O1 | Sankey | Ocular echarts sankey | later | optional | spending JSON |
| O2 | Privacy blur | Ocular privacy mode | must-have v1 | optional setting | client |
| O3 | FY month offset | Ocular `monthOffset` | later | setting | display only |
| O4 | Carry-over assigned cash | Ocular `carryOver` | reject | — | leftover info only later |
| O5 | Inline math | Ocular `evalMathExpression.ts` | must-have v1 | n/a | client; POST cents |
| O6 | Finance-only PWA | Ocular vite-plugin-pwa | later / not finance | — | Odysseus-wide if ever |
| O7 | Keyboard polish | Ocular keyboard nav | later | n/a | forms |
| O8 | Google annual budget sheet as ledger | Ocular parser | reject | — | not a bank import |
| D1 | DumbBudget as host | DumbBudget | reject | — | — |
| D2 | English RRULE-ish strings that auto-post | DumbBudget `server.js` | reject | — | no auto-post |
| D3 | Due-on-the-15th display for planned | DumbBudget patterns | later | maybe | planned `due_rule`; never post |
| T1 | `ody_` finance scope | Odysseus companion | must-have before phone | yes | [07-tokens-companion.md](07-tokens-companion.md) |

## Suggested v1 slice (web)

Order is dependency, not weeks:

1. Privacy blur + inline math (no schema).
2. Clipboard paste into existing import preview/commit.
3. Split editor on existing PUT.
4. Associated-title autocomplete + Rules tab (operators on payee/memo/amount).
5. Upcoming / subscription section on Recurring.
6. Average suggestions on Copy month.
7. Net-worth + cashflow cards on Reports; table density.

Then stop. Goals, heatmap, FX, payees, essential, Sankey, FY offset wait.

## Suggested v1 tests (when implementing)

Not this spec’s job to write them. When a later plan implements v1:

- Paste TSV from a NFCU-like table → same dedup as file import.
- Rule CONTAINS memo + amount max → dry-run count; regex invalid → 400.
- Split cents must sum to parent.
- Upcoming list uses `next_due_date`; marking automatic still cannot insert txs.
- Copy month suggestions use true spend, not signed dump.
- Privacy toggle hides cents in the DOM without changing API payloads.
- Amount `10+2.5` POSTs 1250 cents.
- `ody_` without finance scope still 403 on `/api/finance`.
