# Companion tokens and the phone client

Spec only. Do not implement in this pass.

## What is true today

Finance HTTP uses `require_user(request)` on every handler in `integrations/finance/routes.py`.

`require_user` in `src/auth_helpers.py`:

- Cookie sessions → logged-in username (owner of `finance_*` rows).
- Bearer API tokens (`ody_` prefix, minted for companion pairing) → **403** `"API tokens must use a scope-aware API route"`.

Companion pairing (`companion/pairing.py`) mints `ody_` + 32 bytes urlsafe, scope **`chat` only** (`COMPANION_SCOPE = "chat"`). `effective_user()` would map `request.state.api_token_owner` to the real human, but finance never calls it.

So: the web modal (cookie) and a paired phone (Bearer `ody_`) do **not** share finance. The phone cannot read or write books through `/api/finance`.

Agent `manage_finance` is a different path (server-side tool with the chat user’s owner). It is not a substitute for a phone REST client.

## Why this blocks Flutter

The later phone client must show the **same** accounts, txs, budgets, and reports as `/finance` on the desktop. That data is owner-scoped in `finance.db`. Without a finance-aware token route, the app would have to embed a browser cookie session (bad) or duplicate the DB (forbidden).

## Need (directional)

1. **Scope.** Add a token scope such as `finance` (name can change). Companion or Settings → API tokens can mint `ody_` with `chat`, `finance`, or both. Default pairing stays `chat` so existing phones do not gain books by accident.
2. **Route gate.** Finance handlers should accept:
   - cookie `require_user`, or
   - Bearer token with `finance` in `request.state.api_token_scopes` **and** `effective_user()` as owner.
3. **Same owner.** `api_token_owner` must equal the desktop username. No `"api"` pseudo-user silo (that is why `effective_user` exists).
4. **Confirmation gates.** Mutating routes already use the finance confirmation gate for the agent. Phone mutations need the same owner checks; UX can confirm in-app instead of chat `confirmation_token`. Do not weaken owner isolation.
5. **Import.** Multipart upload must work with the token (preview/commit). Clipboard paste is web-first; phone uses file/share into the same preview API.
6. **Do not** put finance on the unscoped `/api/companion/*` chat routes. Keep `/api/finance/*` as the only books API.

## Phone vs web (same JSON)

| Client | Auth | UI |
|--------|------|-----|
| Desktop `/finance` | Session cookie | Modal tabs (this spec’s IA) |
| Flutter later | `Authorization: Bearer ody_…` with `finance` scope | Native screens; Cashew-like tabs allowed |
| Agent | Tool owner | No file import |

Privacy blur and inline math may stay client-side. Heatmap, caps, rules apply, budgets, recurring, reports must be HTTP for both.

## Out of this spec

Token mint UI, scope column in `auth` JSON, middleware changes, Flutter. Track as a prerequisite issue before any phone finance client. Implementers should read `companion/README.md` and `src/auth_helpers.py` first.
