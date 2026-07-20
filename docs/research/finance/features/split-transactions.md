# Split transactions

## What it is / user value

Divide one purchase across multiple categories (e.g., Costco: $80 groceries + $40 household). Parent transaction holds total; child splits hold category portions.

**User value:** Accurate category reports when stores sell mixed goods.

## Competitor examples

- **YNAB:** Split transaction UI in register
- **Monarch:** Split across categories
- **Quicken Simplifi:** Split lines
- **Actual Budget:** Split support

## Odysseus-specific approach

- Parent `finance_transactions` row keeps bank-imported amount intact
- Child rows in `finance_transaction_splits` with category + amount
- Sum of splits must equal parent amount (validation)
- Budget/spent calculations use splits, not parent category
- Import creates unsplit parent; user splits manually or via rule (advanced)

## Data model changes

```sql
finance_transaction_splits (
  id TEXT PK,
  transaction_id TEXT FK NOT NULL,
  category_id TEXT FK NOT NULL,
  amount_cents INTEGER NOT NULL,
  memo TEXT,
  UNIQUE(transaction_id, category_id)  -- or allow duplicate categories with merge
)

-- Parent: is_split_parent BOOLEAN, category_id null when split
```

## API / UI surfaces

- `POST /api/finance/transactions/{id}/split` — `{ splits: [{ category_id, amount_cents }] }`
- `DELETE /api/finance/transactions/{id}/split` — unsplit
- Split editor modal in register row

## Implementation phases

### MVP

- Manual split UI (2–5 lines)
- Validation sum = total
- Reports use splits

### Polish

- Split templates ("Costco default")
- Percentage-based split
- Split across tags

## Dependencies

- [transaction-categorization.md](transaction-categorization.md)
- [search-filter-transactions.md](search-filter-transactions.md)

## Security considerations

- Splits inherit parent's owner via transaction FK

## Open questions / risks

- Dedup hash on import — parent only; splits don't affect hash
- Refunds on split transactions — negative parent with splits

## Effort estimate

**M**
