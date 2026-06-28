# Future UI backlog (planned)

## What it does in SysForge

Post-MVP UX: user favorites, keyboard shortcuts, themes, profiles, breadcrumbs, status bar, sidebar-dashboard sync.

**Paths**

- `Plans/UI-Plans/Future-UI-Features.md`
- `SysForge/Future-UI-Features.md` (copy)
- Partial: hardcoded `DashboardCard.IsFavorite` in `DashboardViewModel.InitializeCards`

## Status

**Planned** — Phase 1 shell features done; Phase 2–3 not started.

## Dependencies

- Config extensions
- Possible plugin architecture (not built)

## Port approach

MVP uses Odysseus global theming (`--section-accent`). Defer favorites/shortcuts until core Business flows ship. Document as add-on v1.1+.

## Effort

**M** per feature area

## Risks / open questions

- Odysseus already has shortcuts settings — avoid duplicate shortcut systems
- "Plugins" in SysForge vision may overlap Odysseus MCP/skills model
