# Search & filter transactions

## What it is / user value

Fast transaction register with search, filters, and sort. Users find specific purchases, review imports, and audit spending.

**User value:** Replace scrolling through bank websites; central searchable history across accounts.

## Competitor examples

- **Monarch:** Clean searchable transaction list; mark reviewed
- **YNAB:** Account register with search and flags
- **Copilot:** Filter by category, account, date
- **Actual Budget:** Register view with powerful filters

## Odysseus-specific approach

- Paginated transaction list (50 per page, cursor-based)
- Full-text search on payee (decrypt in app layer or search index — see security doc)
- Filters: account, category, date range, amount range, status, import batch, tag, uncategorized only
- Sort: date (default desc), amount, payee
- Inline edit: category, memo, tags

## Data model changes

- Indexes on `(owner, date)`, `(account_id, date)`, `(owner, category_id)`
- Optional `finance_transactions_fts` virtual table for payee search (encrypted payee complicates FTS — decrypt-on-read filter for MVP, FTS phase 2)

## API / UI surfaces

- `GET /api/finance/transactions?account=&category=&q=&from=&to=&status=&tag=&page=`
- `GET /api/finance/transactions/{id}`
- `PATCH /api/finance/transactions/{id}`
- Register UI: sticky filter bar, infinite scroll or pagination
- Mobile-responsive row layout

## Implementation phases

### MVP

- List + filter by account, date, category
- Payee substring search (SQL LIKE on decrypted payee in Python layer for moderate volumes)
- Sort by date

### Polish

- Saved filters ("Last month dining")
- Export filtered view to CSV
- FTS for 50k+ transactions
- Keyboard shortcuts (j/k navigate)

## Dependencies

- [transaction-import-parsing.md](transaction-import-parsing.md)
- [transaction-categorization.md](transaction-categorization.md)

## Security considerations

- Search results owner-scoped
- Export requires auth; rate-limited
- Do not expose payee in URL query params (POST search body optional)

## Open questions / risks

- Encrypted payee search performance — benchmark at 10k rows; may need client-side filter cache

## Effort estimate

**M**
