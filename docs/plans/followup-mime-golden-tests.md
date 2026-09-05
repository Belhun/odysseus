# Follow-up: MIME golden fixtures + flag parity

Brief plan for closing gaps left after Phase 1 MIME parser wiring.

## Scope

1. **Golden fixtures** — extend `tests/test_email_mime_parse_golden.py` inline builders to cover every case listed in `email-local-sync-p1-mime.md` that was not yet parametrized.
2. **Flag parity** — add `test_email_local_store_sync.py` integration test: sync the same RFC822 bytes with `email_local_sync_single_pass_mime` off vs on; stored message fields and attachment files must match.
3. **Doc drift** — `routes/email_mime_parse.py` docstring should reference the golden test module only (no `tests/fixtures/email_mime/` until that directory exists).

## Fixtures to add

| Key | Exercises |
|-----|-----------|
| `charset_iso8859_plain` | Non-UTF-8 `text/plain` decode |
| `rfc2047_subject_and_filename` | `_decode_header` on Subject + attachment filename |
| `inline_image_skipped` | Inline `image/png` in meta; body from plain part |
| `nested_multipart_related` | `multipart/related` wrapping `multipart/alternative` |
| `empty_body` | Multipart with no text parts; empty snippet |
| `multiple_attachments_order` | Stable attachment index ordering |
| `html_only_alternative` | **Fix** existing builder: true `multipart/alternative` with only `text/html` (not single-part HTML) |

Existing builders (`plain_only`, `plain_and_html_alternative`, `single_attachment`, `attached_message_rfc822`) stay unchanged.

## Parity test design

- Build a small dict of UIDs → raw bytes: plain, alternative, attachment, html-only alternative.
- Run `sync_account_folder` twice into isolated tmp DB + attachment dirs.
- Monkeypatch `load_settings` for `email_local_sync_single_pass_mime` false then true.
- Compare per UID: `subject`, `body_text`, `body_html`, `snippet`, `has_attachments`.
- Compare attachments: `filename`, `content_type`, `size`, `is_inline`, on-disk SHA256.

## Acceptance

- `pytest tests/test_email_mime_parse_golden.py tests/test_email_local_store_sync.py -q` green.
- No commit in this pass.
