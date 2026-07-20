# Tags & labels

## What it is / user value

Freeform labels on transactions (vacation-2025, tax-deductible, reimbursable) independent of category. Filter and report by tag.

**User value:** Cross-cutting views Monarch and Tiller users expect; business expense tracking.

## Competitor examples

- **Monarch:** Tags on transactions
- **Tiller:** Tags column in Transactions sheet
- **Copilot:** Custom labels
- **Actual Budget:** No native tags — Odysseus opportunity

## Odysseus-specific approach

- Many-to-many: transaction ↔ tags
- Tags created on the fly when typing
- Color per tag optional
- Rules can apply tags (see rules doc)
- Reports: filter spending by tag

## Data model changes

```sql
finance_tags (
  id TEXT PK,
  owner TEXT NOT NULL,
  name TEXT NOT NULL,
  color TEXT,
  UNIQUE(owner, name)
)

finance_transaction_tags (
  transaction_id TEXT FK,
  tag_id TEXT FK,
  PRIMARY KEY (transaction_id, tag_id)
)
```

## API / UI surfaces

- `GET/POST /api/finance/tags`
- `PATCH /api/finance/transactions/{id}/tags`
- Tag chips on transaction row; autocomplete input
- Filter bar: tag multi-select

## Implementation phases

### MVP

- Create tags, assign to transactions
- Filter by tag

### Polish

- Tag spending report
- Bulk tag from search results
- Tag groups / namespaces (work:)

## Dependencies

- [search-filter-transactions.md](search-filter-transactions.md)
- [rules-auto-categorization.md](rules-auto-categorization.md)

## Security considerations

- Tag names may reveal intent ("medical") — low sensitivity; plaintext OK

## Open questions / risks

- None significant

## Effort estimate

**S**
