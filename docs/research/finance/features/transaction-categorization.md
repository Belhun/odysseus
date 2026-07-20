# Transaction categorization

## What it is / user value

Assign every transaction to a spending/income category (Groceries, Rent, Salary) so budgets and reports work. Users edit categories inline; system suggests on import.

**User value:** Answer "where did my money go?" without manual spreadsheet work.

## Competitor examples

- **YNAB:** Customizable category groups and categories; targets per category
- **Monarch:** Default categories + custom; AI suggestions
- **Copilot:** AI auto-categorization (~94% accuracy claimed)
- **PocketGuard:** Auto-categorization with manual override

## Odysseus-specific approach

- Ship default category tree (Bills, Everyday, Fun, Income, Transfers)
- User can add/rename/hide categories (not delete if transactions exist — merge instead)
- Category assignment happens at import (rules) and manual edit
- Optional: local LLM batch categorization for uncategorized rows (phase 2, privacy-preserving)

## Data model changes

```sql
finance_categories (
  id TEXT PK,
  owner TEXT NOT NULL,
  parent_id TEXT FK,            -- null = top-level group
  name TEXT NOT NULL,
  icon TEXT,
  color TEXT,
  is_income BOOLEAN DEFAULT FALSE,
  is_hidden BOOLEAN DEFAULT FALSE,
  display_order INTEGER
)

-- category_id on finance_transactions
```

## API / UI surfaces

- `GET/POST/PATCH /api/finance/categories`
- `POST /api/finance/categories/merge` — merge A into B
- `PATCH /api/finance/transactions/{id}` — set category
- `POST /api/finance/transactions/bulk-categorize` — `{ ids, category_id }`
- Category picker dropdown on transaction row
- Settings: manage category tree

## Implementation phases

### MVP

- Default category seed per owner on first finance visit
- CRUD categories (one level groups + children)
- Manual assign + bulk assign
- "Uncategorized" filter view

### Polish

- Nested subcategories (3 levels)
- Category icons/colors
- LLM suggest for batch uncategorized (opt-in, local model)
- Income vs expense category types

## Dependencies

- [transaction-import-parsing.md](transaction-import-parsing.md)
- [rules-auto-categorization.md](rules-auto-categorization.md)
- [category-budgets.md](category-budgets.md)

## Security considerations

- Category names not sensitive; plaintext OK
- LLM categorization: send only payee strings, not full account context; no cloud without user consent

## Open questions / risks

- Category tree sync in household sharing — phase 3
- Transfer categories vs linked transfer pairs — use `is_transfer` flag

## Effort estimate

**M**
