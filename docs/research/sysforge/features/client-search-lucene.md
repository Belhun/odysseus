# Client search (Lucene)

## What it does in SysForge

Full-text client search for calculator typeahead and dashboard; index rebuild on client changes.

**Paths**

- `SysForge/Search/SearchService.cs`, `SearchIndex.cs`, `QueryBuilder.cs`
- `SysForge/Search/ClientDocumentMapper.cs`, `IndexPaths.cs`
- `ClientService` index hooks
- Config: `search.indexPath`

## Status

**Done** for clients. Parts Lucene **not started**.

## Dependencies

- Lucene.NET packages in `SysForge.csproj`
- On-disk index directory

## Port approach

Options ranked:

1. **SQLite FTS5** on clients table — simplest, no JVM
2. **PyLucene** — closest parity, heavy add-on dep
3. **Odysseus embeddings** — semantic search, different UX

Recommend FTS5 for MVP; optional Lucene in add-on v2.

## Effort

**M** (FTS5) / **L** (PyLucene)

## Risks / open questions

- Query behavior parity with `ClientQueryParser.cs`
- Reindex time on large client lists after bulk import (future; not needed for greenfield install)
