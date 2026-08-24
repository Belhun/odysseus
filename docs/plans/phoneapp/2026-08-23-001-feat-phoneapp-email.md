---
title: PhoneApp Email
date: 2026-08-23
type: feat
artifact_contract: ce-unified-plan/v1
artifact_readiness: implementation-ready
product_contract_source: ce-plan-bootstrap
execution: code
---

# PhoneApp Email

## Goal Capsule

Ship a real Odysseus-themed mail client in PhoneApp that talks to the existing IMAP/SMTP stack (`/api/email/*`).
More → Email is a labeled placeholder today (`more_screen.dart`); this work builds the screens and client so a later wiring pass can swap the placeholder.
Cookie sessions keep working.
Bearer `ody_` tokens must resolve to `api_token_owner` with `email:read` / `email:draft` / `email:send` — the stock `require_user` 403s tokens, and the email helper `require_owner` currently treats tokens as the `"api"` sandbox user.
IMAP on the server remains the source of truth.
No local mailbox database on the phone.

Stop when the vertical slice works: accounts, folders, list, read, compose/reply, mark read/unread, pull-to-refresh, empty/error/loading — plus tests.
Do not edit `more_screen.dart`, `app_controller.dart`, or PhonePi/QR files.

## Product Contract

### Requirements

- R1. List mail for a chosen account and folder (subject, from, date, unread).
- R2. Open a message as plain text. HTML-only mail is shown as stripped text, not a WebView.
- R3. Compose and reply through `POST /api/email/send` when the session or token may send.
- R4. Mark read/unread. Opening a message uses the existing `mark_seen` default on read.
- R5. Pull-to-refresh re-hits live IMAP list (cache-bust `_` query like the web client).
- R6. Empty: zero accounts tells the user to add mail on the web (Google OAuth is browser-only). Empty folder is a distinct copy.
- R7. Error/loading: `ErrorBody` + Retry; spinner while IMAP is in flight.
- R8. Multiple IMAP/SMTP accounts: mailbox switcher. Disabled rows are skipped.
- R9. Same records as web: `account_id` + IMAP UID + folder. No second mailbox store.

### Actors and flow

Logged-in phone user (cookie or scoped `ody_` token) opens Email → picks account/folder → reads → replies.
Operator who has not configured mail sees the empty-account card.

### Out of scope (v1 holes)

- Google OAuth authorize/callback in the app (browser-only; tell the user to add accounts on web).
- Attachment download/upload, HTML WebView, AI reply, schedule, local-only SQLite mirror as the list source, spam tools, archive/delete/move.

## Planning Contract

### Auth (load-bearing)

`src.auth_helpers.require_user` 403s `ody_` tokens.
`routes.email_helpers.require_owner` uses `get_current_user`, so a Bearer token becomes owner `"api"` and would miss the human's accounts.

Additive wrap in `routes/email_routes.py` (imported names only — do not rewrite the IMAP handlers):

- Cookie: keep `email_helpers.require_owner` / `require_user`.
- Bearer: require `email:read` (GET + mark-read/unread), `email:draft` or `email:send` (POST `/draft`), `email:send` (POST `/send`); owner = `request.state.api_token_owner` / `effective_user`.

PhoneApp already sends `Authorization: Bearer ody_…` or the session cookie via `OdyHttp`.

### Existing APIs (use these; no parallel mailbox)

| Action | Method | Path |
|---|---|---|
| Accounts | GET | `/api/email/accounts` → `{accounts:[{id,name,is_default,enabled,from_address,display_name,oauth_provider,...}]}` |
| Folders | GET | `/api/email/folders?account_id=` → `{folders:[...]}` (IMAP names, often `INBOX`) |
| List | GET | `/api/email/list?folder=&limit=&offset=&filter=&account_id=&_=` → `{emails,total,folder,error?}` |
| Search | GET | `/api/email/search?q=&folder=&account_id=` |
| Read | GET | `/api/email/read/{uid}?folder=&account_id=&mark_seen=` → `{subject,from_name,from_address,to,cc,date,body,body_html,message_id,in_reply_to,references,attachments,error?}` |
| Mark read | POST | `/api/email/mark-read/{uid}?folder=&account_id=` |
| Mark unread | POST | `/api/email/mark-unread/{uid}?folder=&account_id=` |
| Send | POST | `/api/email/send` JSON `SendEmailRequest`: `to,cc,bcc,subject,body,body_html?,in_reply_to?,references?,account_id?,wait_for_delivery?` |
| Draft | POST | `/api/email/draft` same body |

List row fields used by web (`emailLibrary.js`): `uid`, `subject`, `from_name`, `from_address`, `date`, `is_read`, `is_flagged`, `has_attachments`.
Default folder is `INBOX` (API + `emailApi.js`).
List `filter`: `all` / `unread` (web also has unanswered/flagged — phone v1: All + Unread).
Read may return HTTP 200 with `{error}` on IMAP failure; the client must treat that as failure.
Send queues unless `wait_for_delivery=true`. Phone queues (web default) and shows the returned message.

### Screens

1. **Mailbox list** (`EmailListScreen`): account dropdown, folder dropdown, All/Unread, optional search, message rows, FAB compose, pull-to-refresh.
2. **Read** (`EmailReadScreen`): headers, selectable plain body, attachment names only, Mark unread, Reply.
3. **Compose** (`EmailComposeScreen`): to, optional cc, subject, body, Send; reply prefills `Re:`, `in_reply_to`, `references`, quoted text.

Theme: `OdyTheme` / `OdyCard` / `ErrorBody` like finance and notes.
Screens take `AppController` and an optional `EmailClient` (tests inject a fake). Live client is `EmailClient(controller.finance!.httpClient)` — do not edit `app_controller.dart`.

### Empty / error / sync

- No connection: "Not connected."
- No accounts: card — add IMAP or Google under web Settings → Email. OAuth is not in this app.
- Folder empty: "No messages".
- IMAP `{error}` or HTTP 4xx/5xx: `ErrorBody` + Retry.
- 403: "This token needs email:read (and email:send to compose). Cookie login works. A phone_finance token is not enough."
- Sync: each refresh is a new GET list/search (pass `_` cache buster). No phone-side mailbox DB.

### Gap vs web inbox/compose

Web has HTML rendering, attachments, AI reply, schedule, tags/spam, archive/delete/move, local-only SQLite mirror, style extraction, Google OAuth in Settings.
Phone v1 is list/read/plain compose against the same IMAP accounts.

### Wiring (later; this agent must not edit these files)

`more_screen.dart` today:

```dart
_placeholder(context, 'Email', 'Not in v1.', null),
```

Replace with:

```dart
import 'email_list_screen.dart';
// ...
_item(context, Icons.email_outlined, 'Email', () => EmailListScreen(controller: controller)),
```

`_item` is the existing navigator helper used by Accounts/Import.

## Implementation Units

### U1. Token-aware email owner

Wrap `require_owner` / `require_user` at module level in `routes/email_routes.py` so `setup_email_routes()` binds the wrappers.
Keep IMAP handlers untouched.
Python tests: cookie path unchanged; token without email scopes 403s; token with `email:read` resolves to `api_token_owner`; send requires `email:send`.

### U2. `EmailClient` + models

`PhoneApp/lib/api/email_client.dart`: parse accounts/folders/list/read/send; `htmlToPlainText`; 403 copy.
No new Flutter dependencies.

### U3. Screens

List / read / compose as specified. Unread rows use stronger weight + accent. Dates via `intl`.

### U4. Flutter tests

`PhoneApp/test/email_test.dart`: JSON parse, HTML strip, client paths, empty accounts, list rows, 403 retry copy.

## Verification Contract

- `F:\FlutterSDK\flutter test test/email_test.dart` from `PhoneApp/`
- `python -m pytest tests/test_email_phone_token.py -q`

## Definition of Done

- Plan path is this file.
- Exclusive Dart files exist and tests pass.
- Existing `/api/email/*` used for list/read/send.
- Token owner is the human, not `"api"`.
- Wiring snippet documented; `more_screen.dart` / `app_controller.dart` untouched.

## Appendix

Web references: `routes/email_routes.py`, `routes/email_helpers.py` (`SendEmailRequest`), `static/js/emailApi.js`, `static/js/emailLibrary.js`, `static/js/emailInbox.js`.
Phone references: `PhoneApp/lib/api/ody_http.dart`, `finance_client.dart`, `notes_client.dart`, `widgets/common.dart`, `theme/ody_theme.dart`.
Scopes already in `routes/api_token_routes.py` `ALLOWED_SCOPES`.
`TOKEN_PROFILES` has `phone_finance` / `phone_notes` but no `phone_email`; minting a custom token with `email:read,email:draft,email:send` is enough for v1.
