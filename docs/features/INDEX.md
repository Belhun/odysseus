# Feature map

Canonical index for fork features that used to live on separate branches. Everything below ships on the trunk (`belhun/playground` until renamed to `main`).

Use short-lived branches only for risky work. Keep durable knowledge here and under `docs/research/` + `docs/plans/`.

| Feature | Status | Code | Feature guide | Research | Plans |
|---------|--------|------|---------------|----------|-------|
| Finance / banking | Active | `integrations/finance/` | [finance.md](finance.md) | [research/finance](../research/finance/) | [plans/finance](../plans/finance/) |
| PhoneApp connect / tokens | Active | `PhoneApp/` + Settings token UI | [phone-client-connect-guide.md](../phone-client-connect-guide.md) | — | — |
| Local email sync | Active | email routes + local sync services | [email.md](email.md) | — | [plans/email](../plans/email/) |
| SysForge Business | Active | `integrations/sysforge/` | [sysforge.md](sysforge.md) | [research/sysforge](../research/sysforge/) | [plans/sysforge](../plans/sysforge/) + [migration-audit](../migration-audit/) |
| Performance tracking | Active | diagnostics / perf event bus | [performance.md](performance.md) | [research/performance](../research/performance/) | roadmap in research |
| CalDAV same-owner UID | Merged fix | CalDAV / calendar paths | — | — | see git tag `archive/fix-caldav-same-owner-uid` when archived |
| MCP stdio reconnect | Merged fix | MCP client reconnect | — | — | see git tag when archived |

## How to add or update a feature

1. Put product/research notes under `docs/research/<area>/` (create the folder if needed).
2. Put implementation plans under `docs/plans/<area>/` with the usual dated filename.
3. Add or update a row in this INDEX and a short guide in `docs/features/<area>.md`.
4. Link the code entry points (plugin folder, routes, tests).
5. Prefer one trunk checkout. Do not keep a permanent worktree per feature.

## Former branches

| Former branch | Now |
|---------------|-----|
| `feature/banking-budgeting` | Finance rows above |
| `feat/local-email-sync` | Email rows above |
| `SysForge-Implementation` | SysForge rows above |
| `feat/performance-tracking` | Performance rows above |
| `fix/caldav-same-owner-uid` | Merged into trunk |
| `fix/mcp-stdio-reconnect` | Merged into trunk |
