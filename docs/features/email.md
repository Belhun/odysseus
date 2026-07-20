# Local email sync

Owner-scoped local email sync (IMAP orchestration, SQLite store, MIME/attachments, settings) plus follow-on cleanup and people-dossier plans.

## Code

| Area | Path |
|------|------|
| Email UI / host | `static/` email surfaces, related `routes/` |
| Outlook notes | [`docs/email-outlook.md`](../email-outlook.md) |
| Related tests | `tests/test_*email*`, `tests/test_icloud_*` |

Exact service module names evolve; search for `local_email` / IMAP sync under `src/` and `routes/` when extending.

## Docs

| Kind | Path |
|------|------|
| P0 / P1 sync plans | [`docs/plans/email/`](../plans/email/) |
| Controlled inbox cleanup | [`docs/plans/email/2026-07-17-001-feat-controlled-inbox-cleanup-plan.md`](../plans/email/2026-07-17-001-feat-controlled-inbox-cleanup-plan.md) |
| People dossier | [`docs/plans/email/2026-07-17-001-feat-people-dossier-archive-plan.md`](../plans/email/2026-07-17-001-feat-people-dossier-archive-plan.md) |
| Follow-ups | [`docs/plans/followups/`](../plans/followups/) (MIME golden tests, iCloud peek) |

## Extend it

1. Read the matching plan under `docs/plans/email/` (orchestration → IMAP → attachments → SQLite → MIME / settings).
2. Keep cleanup and sync jobs on the same owner-lock + Activity log pattern as existing local sync.
3. Add tests next to the existing email / IMAP suites.
4. Update this page and the [feature INDEX](INDEX.md) when the API surface changes.
