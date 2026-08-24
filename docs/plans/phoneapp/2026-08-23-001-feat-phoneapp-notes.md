---
title: "PhoneApp Notes client - Plan"
type: feat
date: 2026-08-23
status: implemented
branch: belhun/playground
---

# PhoneApp Notes client

Ship a real mobile Notes client against the existing Keep-style `/api/notes` API. Same `Note` rows as the web panel. Do not port `static/js/notes.js`. Do not add a second notes database.

**Not budget.** Do not touch PhonePi / QR / connect. Do not edit `PhoneApp/lib/state/app_controller.dart` in this slice.

---

## Goal

- List, search, open, create, edit, pin, archive, delete, and toggle checklist items on the phone.
- Cookie sessions keep working as they do today.
- `ody_` tokens work only with new `notes:read` / `notes:write` scopes, attributed to `api_token_owner` (same notes as the desktop user). Tokens without those scopes stay 403.
- Stop when the exclusive files below exist, fail-closed auth still holds, and you can exercise list + editor against a running Odysseus.

---

## Screens

### Notes list (`PhoneApp/lib/screens/notes_list_screen.dart`)

- App bar title `Notes`.
- Archive toggle (active vs archived). Uses `GET /api/notes` vs `GET /api/notes?archived=true`.
- Search field. Filter client-side on title, content, label, and checklist item text (web does this in `notes.js`; the list API has no `q=`).
- Label chips from the loaded set. Filter client-side by space-separated tags on `label`. Server `?label=` is exact-match only; chips do not rely on it.
- Cards in API order: pinned first, then `sort_order`, then `updated_at`. Show a Pinned section header when any pinned notes are in the current filter.
- Card: color stripe (preset names), title or first line, snippet or checklist progress (`done/total`), pin icon, optional due date.
- Checklist rows: checkbox on the card calls `POST /api/notes/{id}/items/{index}/toggle`.
- FAB creates a note (opens editor with no id).
- Pull to refresh.
- Loading: centered spinner. Empty: "No notes yet" / "No archived notes" / "No matches". Error: `ErrorBody` + Retry. Map HTTP 403 to copy that the token needs `notes:read` / `notes:write` (cookie login still works; `phone_finance` tokens do not include notes).

Constructor keeps `controller` so More can push `NotesListScreen(controller: controller)` without this slice editing `app_controller.dart`. Optional `client` is for tests. HTTP is taken from `controller.http` or `controller.finance.httpClient`.

### Note editor (`PhoneApp/lib/screens/note_editor_screen.dart`)

- Title, body (plain notes) or checklist items (todo / goal / checklist).
- Switch between note and checklist. Checklist create/update sends `note_type` + `items: [{text, done}]`.
- Color: none + web presets `red orange yellow green blue purple`. Store the preset name, not a hex. Skip `custom` / `bg:<url>` uploads.
- Label: single text field (space-separated tags, same as web).
- Pin and archive: dedicated `POST .../pin` and `POST .../archive` when the note already has an id; otherwise send on create/update.
- Delete: confirm, then `DELETE /api/notes/{id}`.
- Due date: optional date+time picker writing the ISO-ish string the PUT body already accepts. Repeat / fire-reminder stay out (see holes).
- App bar Save. Pop on success.

---

## API (existing, prefix `/api/notes`)

| Method | Path | Mobile use |
|--------|------|------------|
| GET | `""` | List. Query `archived`, optional `label` (exact). Default hides archived. Order: `pinned desc, sort_order asc, updated_at desc`. |
| POST | `""` | Create. Body: title, content, items, note_type, color, label, pinned, due_date, … |
| GET | `/{id}` | Open one note (editor can also use list payload). |
| PUT | `/{id}` | Update fields including items, color, label, due_date. |
| DELETE | `/{id}` | Delete. |
| POST | `/{id}/pin` | Toggle pin. |
| POST | `/{id}/archive` | Toggle archive. |
| POST | `/{id}/items/{index}/toggle` | Flip `items[i].done`. |
| POST | `/reorder` | Not used on phone. |
| POST | `/fire-reminder` | Not used on phone. Still cookie `require_user` (tokens 403). |

Same SQLite `notes` table. No new tables.

---

## Token scopes

Today `require_user` 403s every `ody_` caller on these routes (`"API tokens must use a scope-aware API route"`). Cookie works. `ALLOWED_SCOPES` has no notes entries.

**Additive only:**

- `routes/api_token_routes.py`: add `notes:read`, `notes:write` to `ALLOWED_SCOPES`. `ensure_before("notes:write", "notes:read")`. Add profile `phone_notes: ["notes:read", "notes:write"]`. Do not change `phone_finance` or other profiles.
- `routes/note_routes.py`: module-level `notes_owner(request)` used by existing CRUD/pin/archive/toggle/reorder. Cookie path still `require_user`. Bearer path: GET/HEAD needs `notes:read` or `notes:write`; mutating methods need `notes:write`; identity is `request.state.api_token_owner`. Missing owner → 401. Missing scope → 403. Unscoped `x-test-api-token` in fail-closed tests stays 403.
- `fire_reminder` keeps cookie `require_user` (token remains 403).

Do not mint notes scopes onto companion QR tokens in this slice.

---

## Empty / error / loading

| State | List | Editor |
|-------|------|--------|
| Loading | Spinner | Spinner if refetching one note |
| Empty | Copy + FAB still available | n/a |
| HTTP error | `ErrorBody` + Retry | Dialog via `showBusyError` |
| 403 | Token-scope copy | Same |
| Search miss | "No matches" | n/a |
| Offline / timeout | Same error body | Dialog |

---

## Labels / pin / archive

- **Pin:** API already sorts pinned first. List shows a pin glyph. Editor pin calls `/pin` or create `pinned: true`.
- **Archive:** List app-bar toggle loads `archived=true` (server sorts by `updated_at desc`). Editor archive calls `/archive`. Archived notes leave the active list.
- **Labels:** stored as one string; web splits on whitespace. Phone editor is a text field. List chips filter client-side. Exact `?label=` is unused because a note can carry several tags.

---

## Gap vs web (`static/js/notes.js`)

In this slice:

- List + editor on the same rows
- Client search, pin, archive, labels, color presets, checklist toggle, create/delete
- Simple due_date field

Documented holes (web-only or later):

- Grid vs list toggle
- Reminder firing (`/fire-reminder`, LLM synthesis, email / ntfy / webhook, browser Notification poll, 25-minute dedupe)
- Recurring `repeat` advancement (`daily` / `weekly` / nth-weekday / `monthly` / `yearly`)
- Custom color = uploaded background image (`bg:<url>`)
- Goal "Today" view, agent-solve session, AI classification
- Drag reorder (`POST /reorder`)
- Bulk select / bulk archive
- Note images (`image_url`)
- Undo-archive toast stack

`due_date` exists on the row and is editable. Reminders do not fire from the phone. A finance-only `phone_finance` token will 403 Notes until an admin mints `notes:read,notes:write` (or the user signs in with a session cookie).

---

## Wiring

More can push:

```dart
import 'notes_list_screen.dart';

_tile(
  context,
  Icons.sticky_note_2,
  'Notes',
  () => NotesListScreen(controller: controller),
),
```

Screens resolve HTTP from `controller.http` or `controller.finance.httpClient`. Tests pass `client:` and do not import `AppController`.

Do not attach notes onto connect / QR.

---

## Exclusive files

- `docs/plans/phoneapp/2026-08-23-001-feat-phoneapp-notes.md` (this file)
- `PhoneApp/lib/api/notes_client.dart`
- `PhoneApp/lib/screens/notes_list_screen.dart`
- `PhoneApp/lib/screens/note_editor_screen.dart`
- `PhoneApp/test/notes_test.dart`
- additive `routes/api_token_routes.py`
- additive token-aware owner in `routes/note_routes.py`
- `tests/test_notes_api_token.py`

---

## Tests

- Keep `tests/test_notes_fail_closed_auth.py`: no identity → 401; unscoped api token → 403; alice cannot see bob.
- New `tests/test_notes_api_token.py`: scopes allowed; write implies read; GET as owner lists only owner rows; POST needs write; chat token 403; cookie path unchanged.
- Flutter `PhoneApp/test/notes_test.dart`: JSON parse, client paths, empty/error/list/search widgets, editor fields.

---

## How to try

1. Odysseus running with your notes (cookie session on the desktop Notes panel).
2. Mint a token with `notes:read,notes:write` (profile `phone_notes`) **or** connect PhoneApp with username/password so the session cookie is used.
3. PhoneApp → More → Notes (once More is wired).
4. Create a note on the phone; confirm it appears in the web Notes panel. Pin/archive/checklist on one side; refresh the other.

Flutter SDK: `F:\FlutterDev\flutter`. From `PhoneApp`: `flutter test test/notes_test.dart`.
