# Clients management (CRUD + search)

## What it does in SysForge

Create, read, update, delete clients; validation; duplicate detection; feeds invoice calculator and dashboard.

**Paths**

- `SysForge/Database/ClientService.cs`
- `SysForge/Models/Client.cs`, `ClientSearchResult.cs`
- `SysForge/Helpers/ClientValidationHelpers.cs`, `ClientQueryParser.cs`
- Migration: `SysForge/Database/Migrations/0005_clients.sql`
- Search: `SysForge/Search/SearchService.cs`

## Status

**Done** — including `FindPotentialDuplicatesAsync`.

## Dependencies

- SQLite `Clients` table
- Lucene.NET index (client search)
- Dapper

## Port approach

Python `ClientService` with same SQL. Expose REST CRUD under `/api/sysforge/clients`. Choose Lucene port vs SQLite FTS5 vs Odysseus embedding search for typeahead.

## Effort

**M**

## Risks / open questions

- Lucene.NET → Python equivalent adds install weight
- Multi-user: attach `owner` to all client rows in Odysseus
