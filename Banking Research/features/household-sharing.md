# Household sharing

## What it is / user value

Two Odysseus users (e.g., partners) share a unified view of accounts, budgets, and transactions while keeping separate logins.

**User value:** Monarch and YNAB Together; couples finance without one shared password.

## Competitor examples

- **Monarch:** Household shared view; partner logins at no extra cost
- **YNAB:** YNAB Together — up to 6 people on one subscription
- **PocketGuard:** Family sharing in premium
- **Goodbudget:** Sync envelopes across devices/users

## Odysseus-specific approach

Odysseus already has multi-user auth with `owner` scoping. Household model:

```sql
finance_households (
  id TEXT PK,
  name TEXT,
  created_at
)

finance_household_members (
  household_id TEXT FK,
  username TEXT NOT NULL,       -- Odysseus user
  role TEXT DEFAULT 'member', -- owner|member|read_only
  PRIMARY KEY (household_id, username)
)

-- finance_* tables gain optional household_id;
-- queries use household membership OR owner
```

**Sharing rules:**

- Members see all accounts tagged to household
- Either member can import to shared accounts
- Personal accounts stay `owner`-only (not in household)
- Budgets and goals can be household-level

Manual import: either partner can upload bank CSV; dedup shared.

## API / UI surfaces

- `POST /api/finance/household/invite` — add existing Odysseus user
- `GET /api/finance/household/members`
- Account setting: "Share with household"
- UI badge for shared vs personal accounts

## Implementation phases

### MVP

- Defer — single-user only initially

### Phase 3

- Create household, invite member
- Shared accounts visible to both
- Shared budget view
- Audit log: who imported batch

### Polish

- Read-only member role (financial advisor)
- Per-account visibility toggles

## Dependencies

- All core finance features stable first
- Odysseus user management (`auth_routes.py`)

## Security considerations

- Invite requires accepting user to confirm
- No cross-household data leak — test matrix like email owner scope
- Read-only role cannot import or delete
- Encrypt shared data same as personal

## Open questions / risks

- Two users on same self-hosted instance only — not cross-instance sync
- Conflict when both edit same transaction — last-write-wins + audit

## Effort estimate

**L** (authorization complexity)
