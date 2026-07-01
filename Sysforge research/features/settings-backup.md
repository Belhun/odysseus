# Settings, config, and backup

## What it does in SysForge

App configuration (`config.json`), DB-backed settings, tax/shipping defaults, window state, user backup/restore, scheduled backups.

**Paths**

- `SysForge/Services/ConfigService.cs`
- `SysForge/Database/SettingsService.cs`
- `SysForge/ViewModels/SettingsViewModel.cs`, `Views/SettingsWindow.axaml`
- `SysForge/Services/BackupService.cs`, `ScheduledBackupService.cs`
- `SysForge/Services/BackupModels.cs`
- Docs: `Plans/Database-Design-Document.md` (config section)

## Status

**Done** — backup UI in settings. Import conflict UI partially deferred per Plans README.

## Dependencies

- JSON config file separate from SQLite
- File system zip for backups
- `Microsoft.Extensions.Hosting` for scheduled backup timer

## Port approach

`config.json` under add-on data dir. Settings UI as tab inside Business panel + Odysseus integrations card. Scheduled backup via Odysseus `task_scheduler`. Align backup ZIP structure with `routes/backup_routes.py` where sensible.

## Effort

**M**

## Risks / open questions

- Two config systems (Odysseus global + SysForge add-on) — clear UX separation
- Scheduled backup timing in Docker vs desktop sleep behavior
