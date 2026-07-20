# Import deduplication & review queue

## What it is / user value

Prevent duplicate transactions when users re-import overlapping date ranges. Surface uncertain matches for human review before commit.

**User value:** Safe to re-download bank CSVs without corrupting data; confidence in register accuracy.

## Competitor examples

- **Tiller:** Import Tag column; delete import batch to remove duplicates when feed resumes
- **YNAB:** Import matching; duplicate detection on file import
- **Actual Budget:** Transfer matching and duplicate detection

## Odysseus-specific approach

Three-tier dedup (see [02-manual-import.md](../02-manual-import.md)):

1. FITID exact match → skip silently, count as duplicate
2. Content hash match → skip
3. Fuzzy match → **review queue** before commit

**Review queue UI:** User sees possible duplicates side-by-side; actions: import as new, skip, merge.

## Data model changes

```sql
finance_import_preview (
  id TEXT PK,
  owner TEXT NOT NULL,
  account_id TEXT,
  expires_at,                   -- temp preview TTL 1 hour
  payload_json TEXT             -- encrypted preview rows
)
```

No permanent table for queue — preview is ephemeral. Post-commit, `import_batch_id` enables rollback.

## API / UI surfaces

- Preview response includes `{ new: [], duplicate: [], review: [] }`
- Review row actions in commit payload: `{ action: 'import'|'skip'|'merge', preview_row_id }`
- Post-import: "Undo import" deletes batch

## Implementation phases

### MVP

- FITID + hash dedup
- Preview counts
- Batch delete rollback

### Polish

- Fuzzy review UI
- "Merge" keeps one row, links metadata
- Dedup report after import

## Dependencies

- [transaction-import-parsing.md](transaction-import-parsing.md)

## Security considerations

- Preview payload encrypted at rest if cached in DB
- TTL cleanup job for expired previews

## Open questions / risks

- Merge semantics for split transactions — defer merge to phase 2

## Effort estimate

**M**
