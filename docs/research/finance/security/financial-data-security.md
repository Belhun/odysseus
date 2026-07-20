# Financial data security standards

Security requirements for Odysseus banking and budgeting features. This is engineering guidance, not legal advice. Consult counsel for PCI, GLBA, or regulatory obligations in your jurisdiction.

## Threat model

| Threat | Likelihood | Impact | Mitigation |
|--------|------------|--------|------------|
| Stolen SQLite backup (`app.db` + `.app_key`) | Medium | Critical | Fernet encryption at rest; user educates on backup protection |
| Unauthenticated API access | Low (if configured) | Critical | Require auth; disable localhost bypass in production |
| XSS stealing finance data from browser | Medium | High | CSP, sanitize rendered payees, HttpOnly cookies |
| Agent/tool prompt leakage | Medium | High | Finance tools read-only by default; scrub prompts |
| Log injection / accidental PII in logs | Medium | High | Never log payee, amount, account numbers |
| Malicious CSV (zip bomb, parser exploit) | Low | Medium | Size limits, sandboxed parse, no eval |
| Insider (multi-user host) | Low | Medium | Owner-scoped rows; optional household ACL later |
| Ransomware on host | Medium | Critical | Backup guide; encrypted offsite backups |

**Out of scope (by design):** Live bank credentials and Plaid tokens are not stored because manual import only.

## Encryption at rest

### Reuse existing Odysseus patterns

Odysseus already encrypts sensitive columns via `EncryptedText` in `core/database.py` and `src/secret_storage.py` (Fernet, key at `data/.app_key`).

**Encrypt these finance fields:**

| Field | Encrypt? | Rationale |
|-------|----------|-----------|
| `payee` | Yes | Reveals spending habits |
| `memo` | Yes | May contain account refs, PII |
| `account_name` | Yes | Identifies institutions |
| `account_mask` (last 4) | Optional | Low sensitivity alone; encrypt with name |
| `amount_cents` | No* | Needed for SQL aggregation |
| `date` | No | Needed for indexing |
| `category_id` | No | FK reference |
| Import file blob (if stored) | Yes | Full transaction history |

*Amounts in plaintext enable efficient SUM/GROUP BY. If threat model requires encrypted amounts, use deterministic encryption or application-layer aggregation only (significant complexity). **Recommend plaintext amounts with encrypted payee** for MVP.

### Key management

- Single Fernet key per Odysseus instance (`data/.app_key`) — same as email passwords today
- Key file mode `0o600` via `safe_chmod`
- **Document:** Backup tarball includes `.app_key`; losing key = unrecoverable ciphertext
- Future: optional user-provided passphrase wrapping app key (phase 3)

## Encryption in transit

- HTTPS required for any non-localhost deployment (`SECURE_COOKIES=true`)
- No finance API over plain HTTP except explicit local dev
- Reverse proxy (Tailscale, Cloudflare Access) recommended per `SECURITY.md`

## Access control

### Authentication

- All `/api/finance/*` routes require authenticated session (pattern from `routes/email_helpers.py` `_require_auth`)
- Reuse existing 2FA (`totp_code` on login) — recommend enabling for finance users

### Authorization

- **Owner scope:** Every finance row has `owner` column matching `request.state.user`
- No cross-user reads (test like `tests/test_email_owner_scope.py`)
- Admin users do not bypass owner scope for finance data unless explicit admin-audit feature added later
- Agent finance tools: default **read-only**, owner-scoped, admin-gated write tools

### API tokens

- Odysseus API tokens (`api_tokens` table) must not grant finance write unless scoped (new scope: `finance:read`, `finance:write`)

## Audit logging

Log security-relevant events **without PII:**

| Event | Log fields |
|-------|------------|
| Import started/completed | `owner`, `batch_id`, `row_count`, `format` |
| Import batch deleted | `owner`, `batch_id` |
| Account created/deleted | `owner`, `account_id`, `type` |
| Export downloaded | `owner`, `format`, `date_range` |
| Failed auth on finance route | `ip`, `username` (if known) |

**Do not log:** payee, memo, amounts, file contents, account numbers.

Optional `finance_audit_log` table for user-visible activity feed (encrypted metadata only).

## Secure deletion

- **Import batch delete:** Hard-delete transactions with matching `import_batch_id` (CASCADE splits, tags)
- **Account delete:** CASCADE transactions after confirmation modal ("permanently delete N transactions")
- **User delete:** Include finance tables in user data purge routine
- SQLite `VACUUM` not required per delete; document that deleted rows may remain in DB file until vacuum (backup concern)

## Input validation

- Max upload size: 10 MB per file (align with `upload_routes` limits)
- Max rows per import: 50,000 (reject with clear error)
- CSV: strip null bytes, limit line length
- OFX: use maintained parser library; no regex-on-XML for amounts
- Reject files with wrong MIME/extension mismatch only as warning, not blocker

## Agent and AI safety

Finance data in agent context is high risk for prompt injection and accidental exfiltration.

- Finance agent tools return **aggregates** by default ("$450 on Dining in May"), not raw transaction dumps
- Raw transaction lists require explicit user request and row cap (50)
- Never include finance data in webhook payloads, error reports, or telemetry
- Memory extractor must not auto-ingest finance payees into long-term memory

## Backup and restore

- Finance data lives in `data/app.db` — covered by `scripts/odysseus-backup`
- Update `docs/backup-restore.md` with finance section: tarball contains full spending history
- Recommend encrypted offsite storage for backups
- Restore test: verify encrypted payees decrypt after restore

## Compliance considerations (not legal advice)

| Topic | Notes |
|-------|-------|
| **PCI DSS** | Manual CSV import of card *transactions* is generally not cardholder data storage; do not collect full PAN, CVV, or magnetic stripe data |
| **GLBA** | Self-hosted personal use likely outside scope; business deployments should consult counsel |
| **GDPR/CCPA** | User is data controller on self-hosted; provide export/delete for finance data |
| **SOC 2** | Not applicable to typical self-hosted single-user deployment |

## Security testing checklist

- [ ] Owner A cannot read Owner B transactions via API
- [ ] Unauthenticated requests return 401 on all finance endpoints
- [ ] Payee not present in application logs during import
- [ ] `git grep` finance test fixtures contain no real account data
- [ ] Encrypted columns unreadable in raw SQLite browser
- [ ] Import batch delete removes all associated rows
- [ ] XSS payload in CSV payee field renders escaped in UI
- [ ] Oversized file rejected before parse

## Incident response

1. Rotate session tokens / force re-login if auth bypass suspected
2. Rotate `data/.app_key` only with full re-encryption migration (document procedure)
3. Review audit log for anomalous imports/exports
4. Notify household members if shared finance enabled

## Related documents

- [Odysseus SECURITY.md](../SECURITY.md)
- [secret_storage.py](../src/secret_storage.py)
- [00-overview.md](00-overview.md)
