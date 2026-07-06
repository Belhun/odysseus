# Database infrastructure

## What it does in SysForge

SQLite connection management, embedded migrations with checksums, seed/init, retry policy, enum type handlers.

**Paths**

- `SysForge/Database/DatabaseService.cs`
- `SysForge/Database/MigrationRunner.cs`, `Migration.cs`, `DatabaseInitializer.cs`
- `SysForge/Database/DatabaseRetryHelper.cs`, `EnumStringTypeHandler.cs`
- `SysForge/Database/Migrations/*.sql`
- Docs: `SERVICE_PATTERN.md`, `ERROR_HANDLING_POLICY.md`, `AI_LEARNINGS.md`

## Status

**Done**

## Dependencies

- `Microsoft.Data.Sqlite`, Dapper
- `ConfigService` for DB path

## Port approach

Python migration runner executing same SQL files; checksum table; `sqlite3` with WAL. Port `DatabaseRetryHelper` for locked DB retries. Foundation for all other features — build first in add-on install.

## Effort

**M**

## Risks / open questions

- Never edit shipped migrations — append only
- Multi-instance policy documented but not implemented — single Odysseus writer assumed
