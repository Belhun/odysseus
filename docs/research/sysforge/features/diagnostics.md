# Diagnostics

## What it does in SysForge

Internal diagnostics view: DB stats, migration version, environment info for troubleshooting.

**Paths**

- `SysForge/ViewModels/DiagnosticsViewModel.cs`
- `SysForge/Views/DiagnosticsView.axaml`
- `SysForge/Database/DatabaseDiagnostics.cs`

## Status

**Done**

## Dependencies

- `DatabaseService`, `MigrationRunner`

## Port approach

Admin-only page at `diagnostics` route or Odysseus admin settings subsection. JSON API `GET /api/sysforge/diagnostics` for scripted health checks.

## Effort

**S**

## Risks / open questions

- Avoid leaking paths/secrets in multi-tenant Odysseus
