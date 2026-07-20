# Feature gap summary — SysForge → odysseus-sysforge

**Audit date:** 2026-07-17  
**Full matrix:** [feature-gap-matrix.md](feature-gap-matrix.md)

## Verdict

odysseus-sysforge has a working **optional Business Management plugin shell** (install/uninstall, feature flag, nav gate, stub modal, gated `/api/sysforge/status`). It does **not** yet port SysForge’s repair-shop product. Desktop SysForge already ships clients, invoices, drafts, parts/placeholders, dashboard, settings/backup, and diagnostics (Phases 1–9). Projects/work orders and screw maps are in progress on desktop only.

## Top gaps (highest impact)

1. **Empty product after install** — Users can Install from Settings and open Business, but the panel is a status placeholder. No clients, invoices, or parts.
2. **No schema / domain APIs** — Install touches an empty `sysforge.db`; migrations `0002`–`0021` and services (`ClientService`, `InvoiceService`, `PartService`, `DraftService`, …) are not ported.
3. **Invoice calculator** — Desktop’s primary workflow (`InvoiceCalculatorViewModel`) is missing entirely. Highest-value, highest-risk port (research effort XL).
4. **Business shell** — Desktop has sidebar + dashboard cards + navigation cache. Web uses a single stub modal with no inner router.
5. **Search & autosave UX** — Lucene client search and local draft triple-buffer autosave have no web equivalents yet; naive ports will feel worse than SysForge.
6. **Backup / settings** — Desktop Settings backup is Done. Web only creates `config.json` + `backups/` dirs with no Business settings or restore UI.
7. **Projects & screw maps** — Present (partial) on desktop; absent on web. Defer UI until desktop stabilizes; still plan schema after invoice MVP.
8. **Docs drift** — Research pack is strong but path names lag (`addons/` vs `integrations/`). Plugin README and host `ROADMAP.md` do not list Business port milestones.

## What already works on odysseus

- Feature flag `sysforge` (default off)
- Plugin registry + catalog + admin install/uninstall
- Static mount `/static/plugins/sysforge`
- Sidebar/rail visibility when installed
- Tests for install marker and API 404 when inactive

## Recommended next focus

**P0:** port SQL migrations + money/UTC conventions + Business dashboard shell.  
**P1:** clients (FTS), drafts, parts/placeholders, invoice calculator/edit.  
**P2+:** viewer, projects, plugin backup/settings, diagnostics; then screw maps and vision work.

## Documentation note

SysForge `Plans/README.md` remains the best desktop status source. Odysseus research under `docs/research/sysforge/` remains the best port plan. This audit bridges them to current runtime evidence.
