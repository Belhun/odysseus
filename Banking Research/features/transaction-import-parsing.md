# Transaction import & parsing

## What it is / user value

Upload bank-exported CSV, OFX, or QFX files and turn them into normalized transactions. Supports Wells Fargo, Navy Federal presets, and generic column mapping.

**User value:** Get bank data into Odysseus without Plaid; repeatable monthly workflow.

## Competitor examples

- **YNAB:** File import on web; CSV with Date, Payee, Memo, Amount; native OFX/QFX
- **Tiller:** CSV Importer with column mapping, polarity reverse, import tags
- **Actual Budget:** QIF/OFX import; rule engine runs on import
- **Copilot:** CSV import for Mint migration

## Odysseus-specific approach

See [02-manual-import.md](../02-manual-import.md) for full pipeline. Summary:

1. Upload → format detect → preset or generic parse
2. Normalize to canonical row (integer cents, ISO date)
3. Dedup by FITID or content hash
4. Preview → user confirm → commit with `import_batch_id`

Post-commit: run categorization rules automatically.

## Data model changes

```sql
finance_import_batches (
  id TEXT PK,
  owner TEXT NOT NULL,
  account_id TEXT FK,
  filename TEXT,                -- encrypted optional
  format TEXT,                  -- csv_wf|csv_nfcu|csv_generic|ofx|qfx
  row_count INTEGER,
  imported_count INTEGER,
  duplicate_count INTEGER,
  created_at
)

finance_transactions (
  id TEXT PK,
  owner TEXT NOT NULL INDEX,
  account_id TEXT FK NOT NULL,
  import_batch_id TEXT FK,
  date DATE NOT NULL,
  amount_cents INTEGER NOT NULL,
  payee TEXT,                   -- encrypted
  memo TEXT,                    -- encrypted
  check_number TEXT,
  fitid TEXT,                   -- from OFX
  dedup_hash TEXT NOT NULL,
  category_id TEXT FK,
  status TEXT DEFAULT 'cleared', -- pending_review|cleared|reconciled
  is_transfer BOOLEAN DEFAULT FALSE,
  transfer_pair_id TEXT,
  created_at, updated_at,
  UNIQUE(account_id, fitid) WHERE fitid IS NOT NULL,
  INDEX(owner, date),
  INDEX(account_id, dedup_hash)
)
```

## API / UI surfaces

- `POST /api/finance/import/preview` — multipart upload
- `POST /api/finance/import/commit` — `{ preview_id, account_id }`
- `GET/DELETE /api/finance/import/batches/{id}`
- Import wizard UI with drag-drop, preview table, duplicate highlighting

## Implementation phases

### MVP

- OFX/QFX parser
- Wells Fargo + Navy Federal CSV presets
- Generic CSV mapper (save user mapping)
- Dedup + batch rollback

### Polish

- Fuzzy duplicate review
- Multi-account CSV split
- User-defined bank presets
- Import from Document Library CSV file

## Dependencies

- [account-aggregation.md](account-aggregation.md)
- [import-dedup-review.md](import-dedup-review.md)
- [rules-auto-categorization.md](rules-auto-categorization.md)

## Security considerations

- Temp file cleanup after parse
- Upload size/row limits
- No file content in logs
- See [financial-data-security.md](../security/financial-data-security.md)

## Open questions / risks

- `ofxparse` maintenance and license — evaluate alternatives
- Navy Federal encoding edge cases — need real sample files in tests (synthetic only in repo)

## Effort estimate

**XL** (parsing + institution edge cases)
