# Follow-up: email local sync plan doc status updates

Brief checklist for reflecting Phase 0+1 implementation in plan documents (2026-07-01). Markdown only; no code changes.

## Files to update

| File | Prior status | Shipped (high level) | Deferred |
|------|--------------|----------------------|----------|
| `email-local-sync-p0-orchestration.md` | Plan only (not implemented) | `forward_uids` cap, per-owner `sync_all` lock, top-level `busy` response, caller handling (cron/tool/API/CLI) | HTTP 409, frontend busy UI, cross-process lock, parallel folder sync |
| `email-local-sync-p0-imap.md` | Plan only (not implemented) | `BODY.PEEK[] FLAGS`, `_group_uid_fetch_records`, SEARCH/FETCH reconnect | — |
| `email-local-sync-p0-attachments.md` | Plan only — do not implement | `_iter_attachment_parts`, `include_payload`, removed `_get_attachment_part`, payload reuse in extract | `email_routes` dedupe, `mcp_servers/email_server.py` cleanup |
| `email-local-sync-p1-mime.md` | Implementation guidance only | `routes/email_mime_parse.py`, golden tests, flag wiring (`email_local_sync_single_pass_mime`) | Flag default **off**; PR3 default-on and legacy branch removal |
| `email-local-sync-p1-settings.md` | Plan only | Lowered defaults, `max_sync_seconds`, account/chunk pacing, partial-run logging | Cron interval unchanged (`*/20`), `ship_paused` still true, settings UI, `tool_schemas` `full` description |
| `email-local-sync-p1-sqlite.md` | (no status line) | SQL anti-join gap detection, `RETURNING id`, `executemany`, `ix_attachments_message_row_id`, attachment skip-on-unchanged | Composite `ix_messages_sync_uid` (skipped; unique index sufficient) |

## Edits per file

1. Set status header: **Implemented (Phase 0+1, 2026-07-01)**.
2. Add **Implementation notes** section (shipped vs deferred tables) immediately after the header block.
3. Remove or reword stale "plan only", "not implemented", and "do not implement" language.
4. Update **Definition of done** / acceptance checklists to checked or "met at implementation".
5. Preserve original technical plan body as design reference.

## Verification

- `rg -i "plan only|not implemented|do not implement" docs/plans/email-local-sync-*.md` should return no stale status lines (deferred-item prose is fine).
- Each of the six `email-local-sync-*.md` files has an **Implementation notes** section.
