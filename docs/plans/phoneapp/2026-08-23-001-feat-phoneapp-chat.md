# PhoneApp Chat

Date: 2026-08-23  
Status: implementation-ready

## Goal

Ship a real Chat module in PhoneApp. More → Chat is already labeled; this work fills the list → thread → send slice against the same session/history/LLM store as the Odysseus web sidebar. Not a finance feature. Not a cramped desktop screenshot.

Do not edit PhonePi/QR files, `more_screen.dart`, or `app_controller.dart`.

## Screens

1. **Chat list** (`ChatListScreen`) — full-screen list of the caller's sessions (title + updated time). FAB / empty CTA starts a new chat. Pull to refresh. Push (not split pane) into the thread.
2. **Chat thread** (`ChatThreadScreen`) — history bubbles, composer, send. Streaming tokens into the assistant bubble when `/api/chat_stream` is usable from Dart. Stop while generating. Loading / empty / error+retry.

Theme: `OdyColors` / `OdyTheme` (panel, border, accent, hlBg, muted). User bubbles on the right, assistant on the left. Composer pinned above the keyboard.

Constructor (already used by More): `ChatListScreen(controller: controller)`.

## Web IA → phone

| Web | Phone |
|---|---|
| Sidebar session list | Chat list screen |
| Sidebar “New chat” (materializes `POST /api/session` on first send) | FAB creates a session immediately, then opens the thread |
| `#chat-box` + `#message` composer | Thread bubbles + bottom composer |
| Model picker, folders, search, tools, attachments, compare | Out of scope |

Same `Session` / `ChatMessage` rows. No second chat database.

## Why a small mobile route file

Existing `GET /api/sessions`, `POST /api/session` (form), `GET /api/history/{id}`, `POST /api/chat`, `POST /api/chat_stream` already use `effective_user`, so a Bearer token sees the owner's chats — but they never check the `chat` scope. A finance-only `ody_` token would list and send. `require_user` 403s every API token ("API tokens must use a scope-aware API route").

PhoneApp connects with `ody_` Bearer tokens. Chat needs a finance-style gate: cookie → `require_user`; token → require `chat` in `api_token_scopes`; identity → `effective_user` (token owner, not the `"api"` sandbox). Do not put finance scopes on chat routes.

`POST /api/session` is `application/x-www-form-urlencoded` and wants an endpoint + model. Phone v1 has no model picker, so create would otherwise mint a session that 400s on send (“No model selected”).

New file only: `routes/chat_mobile_routes.py` with `setup_chat_mobile_routes(session_manager)`. Helper: `src/chat_token_auth.py` `require_chat_user`. Do not rewrite `routes/chat_routes.py`.

## API

### Existing (send / history / stop)

| Action | Method | Path | Notes |
|---|---|---|---|
| History | GET | `/api/history/{session_id}` | `{history:[{role,content,...}]}` |
| Send (blocking) | POST | `/api/chat` | JSON `{message, session}` → `{response}` |
| Send (stream) | POST | `/api/chat_stream` | JSON or form `{message, session}`; SSE `data: {"delta":"..."}` then `data: [DONE]` |
| Stop | POST | `/api/chat/stop/{session_id}` | `{stopped: bool}` |

Stream protocol is existing SSE. Dart uses `OdyHttp.sendMultipart` so the response is a `StreamedResponse` (JSON `sendJson` would buffer the whole stream). Fallback: if the stream cannot start, `POST /api/chat`.

### New (scope + JSON create)

Prefix `/api/mobile/chat`.

| Action | Method | Path | Body / result |
|---|---|---|---|
| List | GET | `/api/mobile/chat/sessions` | `{sessions:[{id,name,model,updated_at,last_message_at,message_count}]}` |
| Create | POST | `/api/mobile/chat/sessions` | optional `{name}`; picks the owner's first enabled LLM (same rule as companion `/models`); 400 if none |

Auth on both: `require_chat_user`. Owner for `session_manager.create_session` / list filter: `effective_user`.

Client fallback if mobile routes are not mounted (404): `GET /api/sessions` + form `POST /api/session` with `skip_validation=true` after reading `/api/companion/models`. Cookie-only until `app.py` includes the router.

## Empty / error

| State | UI |
|---|---|
| No sessions | “No chats yet” + New chat |
| Loading | Centered spinner; pull-to-refresh on list |
| HTTP error | `ErrorBody` + Retry |
| 403 missing `chat` scope | “This token cannot use Chat. It needs the chat scope. A finance-only token is not enough. Cookie login still works.” |
| No models on create | 400 “No models configured” — tell the user to add a model in Odysseus Settings on the web |
| Stream drop | Keep partial assistant text; offer retry; fallback send if the stream never started |
| Stop | `POST /api/chat/stop/{id}`; composer returns to Send |

## Sync

Every open/refresh hits the server. No on-device chat DB. List and thread reload after returning from a thread. Same owner as web because `effective_user` is the token owner.

## Gaps vs web (v1 holes)

Attachments, tools/agent chrome, web search toggle, research, model picker, folders, archive, search, compare, voice, markdown rendering, RAG, workspace/bash. Session auto-title after first reply (web post-task) may lag until the next list refresh.

## Tests

- `PhoneApp/test/chat_test.dart` — parse list JSON; 403 copy; stream `delta` parser; widget empty list; widget 403 retry; thread bubbles.
- `tests/test_chat_mobile.py` — cookie `require_chat_user`; token + `chat` → owner; finance-only token 403; list is owner-scoped; create 400 without models; create with mocked LLM.

Flutter: `F:\FlutterDev\flutter test test/chat_test.dart` from `PhoneApp/`.  
Python: `python -m pytest tests/test_chat_mobile.py -q`.

## Wiring (do not apply in this agent)

More already pushes `ChatListScreen` (leave `more_screen.dart` alone).

`app.py` after `setup_chat_routes(...)`:

```python
from routes.chat_mobile_routes import setup_chat_mobile_routes
app.include_router(setup_chat_mobile_routes(session_manager))
```

Token: mint `ody_` with scope `chat` (default profile). Finance-only `phone_finance` must 403 the list.

## How to try

1. Include the router in `app.py` and restart Odysseus.
2. Connect PhoneApp with a `chat`-scoped token (or username/password cookie).
3. More → Chat → New chat → send a message. Bubbles should stream. Stop should halt. Pull to refresh the list.
4. Repeat with a finance-only token: list shows the 403 copy + Retry.
5. With no model endpoints: New chat shows “No models configured”.
