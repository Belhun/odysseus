# Account aggregation

## What it is / user value

A registry of financial accounts (checking, savings, credit card, loan, cash) that groups imported transactions and powers net worth, budgets, and reports. Users create accounts manually and assign each import file to the correct account. No live bank linking.

**User value:** One place to see all accounts; foundation for every other finance feature.

## Competitor examples

- **Monarch:** Connect all bank accounts, credit cards, loans, investments in one view
- **YNAB:** Budget accounts vs tracking accounts; manual unlinked accounts supported
- **Actual Budget:** On-budget and off-budget accounts
- **Tiller:** Sheet per account; manual balance tracking for unsupported institutions

## Odysseus-specific approach

- User creates account with name, type, institution label (e.g., "Wells Fargo Checking"), optional last-4 mask
- Opening balance + as-of date set at creation; updated by reconciliation or manual adjustment
- Credit cards: store credit limit optional for utilization display
- Loans: principal, APR, minimum payment (feeds debt planner later)
- All accounts `owner`-scoped; no Plaid institution search

## Data model changes

```sql
-- Conceptual
finance_accounts (
  id TEXT PK,
  owner TEXT NOT NULL INDEX,
  name TEXT NOT NULL,           -- encrypted
  institution TEXT,             -- encrypted, e.g. "Wells Fargo"
  account_type TEXT NOT NULL,   -- checking|savings|credit_card|loan|cash|other
  currency TEXT DEFAULT 'USD',
  mask_last4 TEXT,                -- encrypted optional
  opening_balance_cents INTEGER DEFAULT 0,
  opening_balance_date DATE,
  credit_limit_cents INTEGER,   -- nullable
  is_closed BOOLEAN DEFAULT FALSE,
  display_order INTEGER DEFAULT 0,
  created_at, updated_at
)
```

## API / UI surfaces

**API:**

- `GET/POST /api/finance/accounts`
- `GET/PATCH/DELETE /api/finance/accounts/{id}`
- `POST /api/finance/accounts/{id}/adjust-balance` — manual correction

**UI:**

- Accounts sidebar in Finance tile
- Add account modal (type picker, institution autocomplete from presets)
- Account detail: recent transactions, current balance, import button

## Implementation phases

### MVP

- CRUD for 5 account types
- Opening balance
- Display current balance = opening + sum(transactions)
- Closed account hides from default views

### Polish

- Reorder accounts (drag)
- Institution icons/presets (WF, NFCU)
- Account notes field
- Archive vs delete

## Dependencies

- None (foundation feature)
- Required by: transaction import, budgets, net worth

## Security considerations

- Encrypt `name`, `institution`, `mask_last4` via `EncryptedText`
- Owner-scoped queries on every endpoint
- DELETE requires confirmation with transaction count

## Open questions / risks

- Multi-currency? Defer; USD-only MVP
- Joint accounts in household sharing — phase 3

## Effort estimate

**S**
