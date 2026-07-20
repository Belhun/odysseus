# Future UI backlog (planned)

## What it does in SysForge

Post-MVP UX: user favorites, keyboard shortcuts, themes, profiles, breadcrumbs, status bar, sidebar-dashboard sync.

**Paths**

- `Plans/UI-Plans/Future-UI-Features.md`
- `SysForge/Future-UI-Features.md` (copy)
- Partial: hardcoded `DashboardCard.IsFavorite` in `DashboardViewModel.InitializeCards`

## Status

**Partial (odysseus-sysforge 2026-07-19)** — shipped M+ slice of `future-ui-mru-shell-polish`:

- Persistent client MRU (`LastInteractedAt`, recent-6, Classic empty-search + autoselect)
- Host shortcuts (Settings → Shortcuts; no plugin-local keybinds):
  - `open_sysforge` — Open Business
  - `sysforge_home` / `sysforge_clients` / `sysforge_calculator` — in-Business routes (open Business if closed; hidden when plugin inactive)
- Dashboard card favorites (`dashboard_favorites` in plugin config)
- Light chrome breadcrumb (`Business › …`); themes stay Odysseus global
- Nav history across restart: **deferred** (VI2 = no)

Still out: Avalonia plugin marketplace, user profiles, custom theme editor, dual shortcut systems.

## Dependencies

- Config extensions
- Possible plugin architecture (not built)

## Port approach

MVP uses Odysseus global theming (`--section-accent`). Host shortcuts registry only; no Business Settings → Shortcuts clone.

## Effort

**M** for the shipped MRU + host shortcuts (open + in-Business) + favorites/breadcrumb slice; remaining Future UI Phase 3 items stay deferred.

## Risks / open questions

- Odysseus already has shortcuts settings — avoid duplicate shortcut systems
- "Plugins" in SysForge vision may overlap Odysseus MCP/skills model
