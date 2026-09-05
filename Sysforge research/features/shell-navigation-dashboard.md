# Shell, navigation, and dashboard

## What it does in SysForge

Central app chrome: collapsible sidebar, dashboard card grid, view switching, back navigation, window state persistence.

**Paths**

- `SysForge/ViewModels/MainWindowViewModel.cs`
- `SysForge/Services/NavigationService.cs`, `ViewCache.cs`, `NavigationHistory.cs`
- `SysForge/ViewModels/DashboardViewModel.cs`
- `SysForge/Views/MainWindow.axaml`, `DashboardView.axaml`
- `SysForge/Models/NavigationItem.cs`, `DashboardCard.cs`
- Docs: `SysForge/UI-Redesign-Complete-Documentation.md`

## Status

**Done** — Phases 1–9 shell complete. Nav history persist across restarts deferred.

## Dependencies

- Avalonia UI, `CommunityToolkit.Mvvm`
- `SettingsService` for sidebar/window state
- DI: `ServiceCollectionExtensions.cs`

## Port approach

Rebuild as Odysseus full-height tool panel with internal sidebar + card dashboard. Port navigation state machine to `static/js/sysforge/router.js`. LRU view cache in JS. Window geometry → `localStorage` + optional user prefs API.

## Effort

**M**

## Risks / open questions

- Whether Business tool uses inner sidebar vs sub-tabs in main Odysseus sidebar
- Favorites cards still hardcoded in SysForge; defer user favorites to phase 2
