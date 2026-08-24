# PhoneApp Calendar

Date: 2026-08-23
Status: implementation-ready
Type: feat

## Problem

More → Calendar is a labeled placeholder ("Not in v1."). The web calendar already stores events in SQLite (`CalendarCal` / `CalendarEvent`) and exposes `/api/calendar/*`. PhoneApp should show and edit those same rows. No second calendar database. CalDAV sync stays server-side; the app consumes Odysseus event JSON.

## Slice (ship this)

- Month grid with weekday headers, today highlight, and per-day dots (calendar colors, max 3).
- Day sheet: tap a day → list that day's events (API-expanded recurrence instances included).
- Event editor: create / edit / delete. Fields: title (`summary`), all-day, start/end, calendar id, notes (`description`), simple repeat dropdown.
- Calendar picker when more than one calendar exists (filter + create target).
- Pull-to-refresh, empty copy, error + retry.
- Recurring: **display** instances the list endpoint already expands. **Create** uses the same RRULE presets as the web form because `POST /api/calendar/events` already accepts `rrule`. Editing an occurrence updates the series (server `_resolve_base_uid`). Deleting an occurrence can pass `scope=occurrence`.

## Out of scope (v1.1+)

- Week / year / agenda views, pinch zoom, drag-resize, quick-parse, reminders, ICS import/export.
- CalDAV account setup / sync button (server still pulls; phone does not configure URLs or passwords).
- Moving an event to another calendar on PUT (`EventUpdate` has no `calendar_href`).
- Custom RRULE builder, EXDATE editor, per-event color picker, week-start toggle (phone defaults Monday like web).
- Wiring More → Calendar (`more_screen.dart` / `app_controller.dart` are exclusive to other agents).
- PhonePi / QR / connect.

## Screens

### `CalendarScreen` (`PhoneApp/lib/screens/calendar_screen.dart`)

- App bar: month title (`August 2026`), prev/next, Today, optional calendar dropdown.
- FAB: new event on the selected day (09:00–10:00 local, or all-day if the user last used all-day — default timed).
- Body: 6-week Monday-start grid (same window as web `_monthRange`: 42 days, fetch `start`/`end` as `YYYY-MM-DD`).
- Cells: date number; muted if other month; accent ring for today; selected fill; up to 3 color dots.
- Tap cell: select day and open a modal bottom sheet (day sheet) with that day's events.
- Event row: time (or "All day"), title, calendar color stripe. Tap → editor.
- Empty sheet: "No events this day".
- Error: `ErrorBody` + Retry. 403 mapped to calendar scopes (not the finance-generic OdyHttp copy).
- Pull-to-refresh reloads calendars + events for the visible grid.

### `CalendarEventScreen` (`PhoneApp/lib/screens/calendar_event_screen.dart`)

- Title field, all-day switch, start date/time, end date/time, calendar dropdown (create only; edit is read-only because PUT cannot change calendar), notes, optional location, repeat dropdown.
- Repeat values (web `cal-f-rrule`):
  - `""` Does not repeat
  - `FREQ=DAILY` Daily
  - `FREQ=WEEKLY` Weekly
  - `FREQ=WEEKLY;BYDAY=MO,TU,WE,TH,FR` Weekdays
  - `FREQ=MONTHLY` Monthly
  - `FREQ=YEARLY` Yearly
- Occurrence banner when `uid` contains `::`: edits apply to the whole series.
- Delete: confirm. If occurrence uid, choose "This day" (`scope=occurrence`) vs "All events" (default series).
- Save: POST create or PUT series uid. Pop `true` so the month reloads.

## API (existing — prefer these)

Prefix `/api/calendar`. Same JSON as `static/js/calendar.js`.

| Method | Path | Phone use |
|--------|------|-----------|
| GET | `/calendars` | `{calendars:[{name,href,color,source}]}`. `href` is calendar id. |
| GET | `/events?start=&end=&calendar=` | Expanded instances. `start`/`end` required, date or ISO. `calendar` matches id or name. |
| POST | `/events` | Body: `EventCreate` — `summary`, `dtstart`, `dtend`, `all_day`, `description`, `location`, `calendar_href`, `rrule`, `color`. Returns `{ok,uid}`. |
| PUT | `/events/{uid}` | `EventUpdate` (no `calendar_href`). Compound uid `base::date` resolves to series. |
| DELETE | `/events/{uid}?scope=series\|occurrence\|instance` | Occurrence delete writes EXDATE when uid has `::` and row has `rrule`. |

Not used in v1: `/config`, `/config/accounts`, `/sync`, `/import`, `/export/{id}`, `/quick-parse`, calendar create/rename/delete.

### Event JSON (list)

`uid`, `summary`, `dtstart`, `dtend`, `all_day`, `is_utc`, `description`, `location`, `rrule`, `recurrence_exdates`, `calendar` (name), `calendar_href` (id), `color`, `event_type`, `importance`, plus expansion: `is_recurrence`, `series_uid`, `truncated`.

Occurrence uids: `{base}::{YYYY-MM-DD}` all-day, `{base}::{YYYY-MM-DDTHH:MM}` timed.

## Auth

Cookie sessions already work (`require_user`). Bearer `ody_` tokens currently 403 on `_require_user` ("API tokens must use a scope-aware API route").

**Additive fix (not a new URL, not a rewrite):** make `_require_user` in `routes/calendar_routes.py` token-aware, same shape as `notes_owner` / finance `require_user`:

- If `request.state.api_token`: require `calendar:read` (GET/HEAD/OPTIONS; write also counts) or `calendar:write` (mutating). Owner = `effective_user(request)` (`api_token_owner`). 401 if no owner.
- Else: existing cookie / single-user `FALLBACK_OWNER` path.

Add token profile `phone_calendar`: `["calendar:read","calendar:write"]` in `routes/api_token_routes.py`. `calendar:write` already implies `calendar:read` via `_normalize_scopes`.

A `phone_finance` token is **not** enough. Cookie login sees the same events. Pairing/QR is untouched.

Do **not** add `routes/calendar_mobile_routes.py` unless `_require_user` cannot be touched; prefer `/api/calendar/*`.

## Timezone

Match web `_localDateOf` / `_tzOffset`:

- All-day: `YYYY-MM-DD` only. List overlap: equal start/end → that day; else `[dtstart, dtend)` exclusive end (RFC all-day).
- Timed with `Z` or `±HH:MM`: parse as an instant, bucket by the **device local** date.
- Timed naive ISO: take the date prefix as written (legacy local rows). Do not convert through UTC.
- Create/update timed: stamp `yyyy-MM-ddTHH:mm:00±HH:MM` so `_parse_dt_pair` sets `is_utc` and stores UTC. Same as the web form.

Phone does not send `X-User-Timezone`; list range is explicit `start`/`end`.

## Empty / error

| State | Copy |
|-------|------|
| No events that day | "No events this day" |
| No calendars (should not happen; server `_ensure_default_calendar`) | "No calendars yet" |
| Not connected | "Not connected." |
| 403 | "This token needs calendar:read and calendar:write. Cookie login works. A phone_finance token is not enough." |
| Other | `ErrorBody` with Retry |

## Gap vs web

| Web | Phone v1 |
|-----|----------|
| Month / week / year / agenda | Month + day sheet |
| Quick add NL parse | Manual editor |
| CalDAV settings + sync button | Hidden (server sync still fills the same table) |
| Drag, resize, multi-day bars | Dots + list |
| Reminders → notes | Skip |
| ICS import/export, new calendar | Skip |
| Week-start Sunday toggle | Monday only |
| Per-event color / maps | Skip color; location is a text field |

Same events, same uids, same expansion.

## Wiring (other agent — do not edit these files here)

`more_screen.dart` currently `_placeholder(..., 'Calendar', 'Not in v1.', null)`.

```dart
import 'calendar_screen.dart';
// replace placeholder:
_tile(context, Icons.calendar_month, 'Calendar',
    () => CalendarScreen(controller: controller)),
```

Do not put a `CalendarClient` on `AppController`. Screens follow Notes: `CalendarClient(controller.finance!.httpClient)` with an optional injected `client` for tests.

## Files

Exclusive to this slice:

- `docs/plans/phoneapp/2026-08-23-001-feat-phoneapp-calendar.md` (this file)
- `PhoneApp/lib/api/calendar_client.dart`
- `PhoneApp/lib/screens/calendar_screen.dart`
- `PhoneApp/lib/screens/calendar_event_screen.dart`
- `PhoneApp/test/calendar_test.dart`

Additive server (small):

- `routes/calendar_routes.py` — `_require_user` token gate only
- `routes/api_token_routes.py` — `phone_calendar` profile
- `tests/test_calendar_api_token.py`

## Tests

`PhoneApp/test/calendar_test.dart`:

- `localDateOf` naive vs `Z` vs offset
- `eventOccursOn` all-day exclusive end + timed local bucket
- `stampLocalDateTime` includes an offset
- `CalendarEvent.fromJson` maps `calendar_href`, `all_day`, occurrence uid
- `CalendarClient.listEvents` hits `/api/calendar/events` with `start`/`end`
- `CalendarClient.createEvent` POSTs `summary` / `dtstart` / `calendar_href`
- Widget: empty day copy; 403 calendar-scope copy + Retry; event title after tapping a dotted day; editor Save POSTs

`tests/test_calendar_api_token.py`:

- `calendar:read` / `calendar:write` in `ALLOWED_SCOPES`; `phone_calendar` profile
- `_require_user` GET with read; POST requires write; chat/finance tokens 403; missing owner 401/403; cookie path unchanged

## How to try

1. Mint an `ody_` token with `calendar:read` + `calendar:write` (profile `phone_calendar`) **or** password-login so the app has a session cookie.
2. Temporarily wire More → Calendar with the snippet above (or `Navigator.push` CalendarScreen from a debug button).
3. From `PhoneApp/`: `F:\FlutterDev\flutter\bin\flutter test test/calendar_test.dart`
4. From repo root: `pytest tests/test_calendar_api_token.py -q`
5. Confirm events created on the phone appear on web `/calendar` and the reverse.
