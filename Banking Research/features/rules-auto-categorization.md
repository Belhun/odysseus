# Rules & auto-categorization

## What it is / user value

Merchant/payee rules that automatically assign categories when transactions import or when user creates a rule from an existing transaction ("always categorize STARBUCKS as Coffee").

**User value:** After setup, most imports need zero manual categorization.

## Competitor examples

- **YNAB:** Payee rules; auto-categorize recurring transactions
- **Actual Budget:** Rule conditions (payee contains, amount, account) → set category
- **Monarch:** AI-assisted category suggestions; manual rules
- **Tiller:** AutoCat sheet formulas (spreadsheet rules)

## Odysseus-specific approach

Rules run **on import commit** and **on transaction create**. No cloud ML required for MVP.

**Rule types:**

| Type | Example |
|------|---------|
| Payee contains | `AMAZON` → Shopping |
| Payee exact | `NETFLIX.COM` → Subscriptions |
| Amount range | `$9.99–$15.99` on payee `*` → Streaming |
| Account + payee | NFCU CC + `SHELL` → Gas |

Priority: lower number = higher priority. First match wins.

## Data model changes

```sql
finance_rules (
  id TEXT PK,
  owner TEXT NOT NULL,
  name TEXT,
  priority INTEGER DEFAULT 100,
  match_payee_contains TEXT,
  match_payee_exact TEXT,
  match_amount_min_cents INTEGER,
  match_amount_max_cents INTEGER,
  match_account_id TEXT FK,
  action_category_id TEXT FK NOT NULL,
  action_tags TEXT,             -- JSON array of tag ids
  is_active BOOLEAN DEFAULT TRUE,
  created_at
)
```

## API / UI surfaces

- `GET/POST/PATCH/DELETE /api/finance/rules`
- `POST /api/finance/rules/test` — dry-run against sample payee
- `POST /api/finance/rules/from-transaction/{id}` — create rule from txn
- `POST /api/finance/rules/apply-all` — re-run on uncategorized
- Settings → Rules list with drag-reorder priority
- Transaction row: "Create rule" action

## Implementation phases

### MVP

- Payee contains + exact rules
- Run on import
- Create rule from transaction

### Polish

- Amount range + account conditions
- Apply rules retroactively
- Rule import/export JSON
- Regex payee (power users, off by default)

## Dependencies

- [transaction-categorization.md](transaction-categorization.md)
- [transaction-import-parsing.md](transaction-import-parsing.md)

## Security considerations

- Rules are owner-scoped
- Regex rules: timeout guard against ReDoS

## Open questions / risks

- Rule conflicts — document first-match-wins clearly in UI
- Payee normalization must match between rules and import parser

## Effort estimate

**M**
