# PhoneApp connect guide

How to run Odysseus locally, mint a Phone finance `ody_` token, run PhoneApp
(Flutter web; Android when the SDK is present), and what each login path does.
Local-only tests cannot prove Tailnet DNS. That research is in the last section.

This fork’s home Mini PC uses Tailscale Serve to `127.0.0.1:7000` at
`https://dell-mini-pc.tailcbcc46.ts.net`. Do not copy that URL into a cloud VM.
Point PhoneApp at the origin you actually started.

## 1. Run Odysseus locally

Native (this is what the cloud VM used):

```bash
python3 -m venv venv
source venv/bin/activate   # Windows: venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
# Optional: pre-seed the first admin. Do not commit a real password.
# ODYSSEUS_ADMIN_PASSWORD=...
python setup.py            # or first-run POST /api/auth/setup
python -m uvicorn app:app --host 127.0.0.1 --port 7000
```

Docker:

```bash
cp .env.example .env
docker compose up -d --build
```

Open `http://127.0.0.1:7000`. Create an admin you control (home uses `belhun`).

Enable **Banking & Budgeting**:

1. Settings → Integrations → Optional plugins → **Install** on Banking & Budgeting
2. Or as admin: `POST /api/plugins/finance/install` with the session cookie
3. Confirm `GET /api/finance/accounts` exists (401/403 without auth; 200 with a cookie or a finance-scoped token)

Keep `APP_BIND=127.0.0.1` unless you intentionally want LAN access. Home Mini PC
does **not** publish `:7000` on the LAN or Tailscale IP. Phone clients reach it
through Tailscale Serve HTTPS, not a raw port.

Flutter web on another origin needs CORS. Loopback with any port is allowed by
`LOCALHOST_ORIGIN_REGEX` in `core/middleware.py`. A Tailscale `*.ts.net` origin
is **not** in that regex. Put it in `ALLOWED_ORIGINS`:

```bash
ALLOWED_ORIGINS=http://localhost:8088,https://dell-mini-pc.tailcbcc46.ts.net
```

## 2. Mint a Phone finance token (click path)

Admin only. User `belhun` is admin at home.

1. Sign in to Odysseus in a browser
2. Open **Settings**
3. Admin section → **Phone app token**
   - Or click the **key** icon in the user bar (admins only)
4. Optionally name the token (default `Phone finance`)
5. Click **Create Phone finance token**
6. Copy the `ody_` secret **once**. The server stores a bcrypt hash and an 8-character prefix only

That POST is `POST /api/tokens` with form field `profile=phone_finance`, which
expands to `finance:read,finance:write` and **does not** include `chat`.

Do not confuse this with:

| UI | What it is |
|----|------------|
| Settings → **Phone app token** (or user-bar key) | PhoneApp `ody_` with finance scopes |
| Settings → Integrations → Codex / Claude **Create token** | Chat-only. Must **403** `/api/finance` |
| Settings → Phone / **PhonePi** | MCP server for the phone, not PhoneApp tokens |
| Companion pairing (`/api/companion/pair`) | Chat-scoped companion token. Ping works; finance does not |

Generic tokens still live under Settings → System → **API tokens**. You can type
`finance:read,finance:write` there, but PhoneApp should use the Phone app token
button so the profile stays correct.

## 3. Run PhoneApp

Flutter **web is required**. Android is optional and needs an emulator/device.

```bash
cd PhoneApp
flutter pub get
flutter run -d chrome --web-hostname 127.0.0.1 --web-port 8088
# or a static build:
flutter build web
python3 -m http.server 8088 --directory build/web
```

Point **Server URL** at the Odysseus origin this PhoneApp can reach
(`http://127.0.0.1:7000` when both run on one machine).

Android:

```bash
flutter run -d android   # only if `flutter devices` lists an emulator or phone
```

This cloud VM had Chrome and no Android emulator. Native password+cookie login
was verified with `dart run tool/live_connect.dart` (dart:io cookie jar), the
same stack Android would use.

## 4. Connect fields

| Field | Token tab | Password tab |
|-------|-----------|--------------|
| Server URL | Odysseus origin, including scheme and port | Same |
| API token | Paste `ody_…` with finance scopes | Unused |
| Username | Optional **label only**. Not sent as a password | Required |
| Password | Unused | Required |
| TOTP | Unused | If 2FA is on, after password succeeds the API returns `requires_totp` |

Connect with token sends `Authorization: Bearer ody_…` to
`GET /api/finance/accounts`. It never POSTs login.

Connect with password POSTs JSON to **`/api/auth/login`**:

```json
{"username":"belhun","password":"…","remember":true}
```

Add `"totp_code":"123456"` when 2FA is enabled.

Empty token: PhoneApp shows `Paste an ody_ API token` and does **not** send a
fake password login.

## 5. Every login method and what should happen

| Method | Client | Expected |
|--------|--------|----------|
| Password `POST /api/auth/login` | curl, native PhoneApp, browser same-origin | **200** `{ok:true}` + `Set-Cookie: odysseus_session=…` (HttpOnly, SameSite=Lax) |
| Wrong password | same | **401** `Invalid credentials` (not `Not authenticated`) |
| `POST /api/login` | any | **401** `Not authenticated` — middleware never checks the password. This path is a trap |
| Phone finance token | `Authorization: Bearer ody_…` | **200** on `GET /api/finance/accounts` as the **token owner**, not the `"api"` pseudo-user |
| Chat-only / Codex / companion token | Bearer | **403** missing `finance:read` on `/api/finance/*` |
| Token without finance scopes | Bearer | **403** |
| Empty token in PhoneApp | Flutter | Client error; no login POST |
| PhoneApp web + token | Flutter web | Accounts load if CORS allows the origin |
| PhoneApp web + password | Flutter web | Often fails: HttpOnly cookie is invisible to Dart, SameSite=Lax is not sent on cross-site POST, Secure cookies need HTTPS |
| PhoneApp Android + password | dart:io | Reads `odysseus_session` from `HttpClientResponse.cookies` |
| Companion `GET /api/companion/ping` | any valid cookie or Bearer | **200** `{ok:true}`. Ping does not grant finance |
| Cookie session in the Odysseus UI | browser | Finance panel works without a token |

## 6. Failure table

| Failure | What you see | Why | Fix |
|---------|--------------|-----|-----|
| `POST /api/login` | 401 `Not authenticated` | Auth middleware requires a cookie/Bearer before any handler. `/api/login` is not exempt and is not the login route | Use `/api/auth/login` |
| Chat / Codex / Claude token on `/api/finance` | 403 `API token missing required scope: finance:read` | Create token starts as `chat` only | Mint **Phone finance token** |
| CORS blocked in Flutter web | Browser console: origin not allowed | Exact `ALLOWED_ORIGINS` miss, or a `*.ts.net` origin | Loopback ports are regex-allowed. Add ts.net origins explicitly |
| HttpOnly cookies on Flutter web | Password “succeeds” or 401 on the next call; Dart never sees `odysseus_session` | Cookie is HttpOnly; cross-origin POST is SameSite=Lax | Use the token tab on web |
| Android Private DNS / MagicDNS | Pixel pings `100.79.4.36` but cannot resolve `dell-mini-pc.tailcbcc46.ts.net` | Private DNS (CleanBrowsing, `dns.google`) bypasses Tailscale MagicDNS | Off/Automatic Private DNS, or connect by IP with TLS SNI = MagicDNS name (`curl --resolve`, PhoneApp `ody_http_factory_io.dart`) |
| Serve vs `:7000` on `0.0.0.0` | Phone can hit MagicDNS HTTPS but `http://100.x:7000` times out | Home binds `APP_BIND=127.0.0.1`. Serve proxies 443 → loopback 7000. Raw Tailscale IP:7000 is closed | Keep Serve; do not open 7000 on LAN/tailnet |
| Funnel accidentally on | Same URL is on the public internet | `tailscale funnel` vs `tailscale serve` | `tailscale serve status`. Funnel off |
| Secure cookie on HTTP | Browser drops `odysseus_session` | `SECURE_COOKIES=true` while talking HTTP | Set Secure only when Serve/HTTPS is in front |

## 7. Tailnet research (will not show up on a local-only test)

Local cloud tests used `http://127.0.0.1:7000`. They cannot catch Tailscale DNS,
TLS SNI, or Android Private DNS. These did show up on the home Pixel.

### What we already hit on the Pixel

- Tailscale IP `100.79.4.36` **pinged**
- MagicDNS name `dell-mini-pc.tailcbcc46.ts.net` **did not resolve**
- Android **Private DNS** was `family-filter-dns.cleanbrowsing.org`
- Fix used in the field: connect to the Tailscale IP with TLS SNI = MagicDNS
  name (`curl --resolve dell-mini-pc.tailcbcc46.ts.net:443:100.79.4.36`)
- PhoneApp `lib/ody_http_factory_io.dart` maps that hostname → `100.79.4.36`
  and keeps the Host/SNI as the MagicDNS name

### MagicDNS vs Android Private DNS

MagicDNS only works when the lookup hits Tailscale’s on-device resolver
(`100.100.100.100`), not a public DoT/DoH server.

- **Private DNS = Off or Automatic**: Android can use Tailscale DNS. MagicDNS
  names often work.
- **Private DNS = hostname** (`dns.google`, `family-filter-dns.cleanbrowsing.org`,
  Cloudflare): Android sends **all** DNS over TLS to that provider. That
  provider does not know `*.ts.net`. Symptoms: ping/IP works, hostname fails.
  This is the Pixel bug we hit.
- Firefox **Max Protection** / Chrome **Use secure DNS** can do the same from
  inside the browser even when system DNS is fine
  ([tailscale#18091](https://github.com/tailscale/tailscale/issues/18091)).
- Android 14 + “Use Tailscale DNS” still has open MagicDNS bugs
  ([tailscale#14109](https://github.com/tailscale/tailscale/issues/14109)).
- CNAMEs that point a public name at `*.ts.net` often NXDOMAIN on Android
  ([akpain.net write-up](https://www.akpain.net/blog/fixing-tailscale-dns/),
  [tailscale#14258](https://github.com/tailscale/tailscale/issues/14258)).

Workarounds: turn Private DNS off; use the Tailscale IP; or `--resolve` / the
PhoneApp host→IP map so TLS still validates the Serve certificate.

### Tailscale Serve HTTPS vs binding 7000 on the Tailscale IP

Home:

- `APP_BIND=127.0.0.1`
- `tailscale serve --bg 7000` (HTTPS on the MagicDNS name, proxy to loopback)
- No Funnel
- No LAN `:7000`

Serve terminates TLS with the `*.ts.net` certificate and forwards **plain HTTP**
to `127.0.0.1:7000`. Binding Odysseus to `100.x.y.z:7000` is a different
listener. Phones that try `http://100.79.4.36:7000` fail when 7000 is loopback
only. That will never appear in a localhost cloud test.

### SNI and `curl --resolve`

If you connect to `https://100.79.4.36` without a hostname, the client sends
SNI=`100.79.4.36`. Serve’s cert is for `dell-mini-pc.tailcbcc46.ts.net`, so TLS
fails. `--resolve` (and the Dart `SecureSocket.startConnect(..., host: magicDns)`)
connects to the IP while sending the right SNI.

### Secure cookies on HTTPS Serve

`odysseus_session` is HttpOnly + SameSite=Lax. `SECURE_COOKIES` defaults false
(HTTP loopback). Behind Serve the browser sees **HTTPS**. If you set
`SECURE_COOKIES=true`, cookies are stored on `https://*.ts.net` and will **not**
be sent to `http://127.0.0.1:7000`. Leave Secure off for local HTTP; turn it on
only for the HTTPS name.

SameSite=Lax: a Flutter web app on `http://localhost:8088` posting to
`https://dell-mini-pc.tailcbcc46.ts.net` is cross-site. The session cookie is
not sent on that POST. Token auth is the web path.

### Flutter web CORS from localhost to ts.net

Loopback regex does not match `https://dell-mini-pc.tailcbcc46.ts.net`. A PhoneApp
web build hosted on localhost talking to Serve **must** list that origin in
`ALLOWED_ORIGINS`. Preflight is already auth-exempt (`is_cors_preflight`).

### Split DNS, subnet routers, expired Serve, Funnel

- **Split DNS**: tailnet DNS for `ts.net` plus a public resolver for everything
  else. Android Private DNS ignores split DNS and sends all names to CleanBrowsing
  / `dns.google`.
- **Subnet routers**: advertising `192.168.x.0/24` does not publish Odysseus if
  it still binds 127.0.0.1. The phone would need Serve or a bind on the LAN IP.
- **Expired / stopped Serve**: `tailscale serve status` empty → MagicDNS:443
  connection refused. Odysseus can still be healthy on loopback. Local tests pass;
  the phone fails.
- **Funnel on by accident**: `tailscale funnel 7000` publishes the same proxy
  to the public internet. Finance tokens and cookies would then be on a public
  HTTPS URL. Check `tailscale serve status` / Funnel node attributes. Keep Funnel
  off for this setup.

## Verify on a running server

```bash
export ODYSSEUS_URL=http://127.0.0.1:7000
export ODYSSEUS_USER=belhun
export ODYSSEUS_PASSWORD='…'   # not a live secret; yours
./venv/bin/python scripts/phone_client_connect_matrix.py
```

Unit coverage: `tests/test_finance_tokens.py`, `tests/test_api_token_routes.py`,
`tests/test_cors_preflight.py`, `tests/test_phone_app_token_ui_static.py`,
`tests/test_phoneapp_connect_static.py`, `PhoneApp/test/connect_logic_test.dart`.

Native HTTP (same stack as Android `dart:io`):

```bash
ODY_URL=http://127.0.0.1:7000 \
ODY_TOKEN='ody_…' \
ODY_USER=belhun \
ODY_PASSWORD='…' \
dart run tool/live_connect.dart
```

`flutter test integration_test/connect_live_test.dart -d chrome` is **not supported**
on Flutter 3.47 (`Web devices are not supported for integration tests yet`).
Use the Dart live runner, or `flutter build web` + a browser on `:8088`.

## Cloud VM results (2026-08-22)

Isolated data dir `/tmp/odysseus-phone-test`, admin `belhun`, finance plugin
installed, Odysseus on `127.0.0.1:7000`, PhoneApp web on `127.0.0.1:8088`.
No Tailscale in this VM. No Android emulator (`flutter devices`: Linux + Chrome).

| ID | Result | Evidence |
|----|--------|----------|
| A | PASS 200 | `{"ok":true,"username":"belhun"}` + `odysseus_session` |
| A2 | PASS 401 | `Invalid credentials` |
| B | PASS 401 | `POST /api/login` → `Not authenticated` |
| C | PASS 200 | `phone_finance` = `finance:read`,`finance:write` |
| C2 | PASS 200 | chat-only token |
| D | PASS 200 | phone token `GET /api/finance/accounts` → `{"accounts":[]}` |
| D2 | PASS 403 | chat token missing `finance:read` |
| E | PASS 403 | token without finance scopes |
| F | PASS | empty Bearer → 401; PhoneApp `Paste an ody_ API token` before network |
| G | PASS | CORS preflight ACAO `http://127.0.0.1:8088`; Flutter web token Connect → Accounts |
| H | PASS (expected web fail) | Password login 200 but Flutter web cannot see HttpOnly cookie; `dart:io` live runner **does** capture a 64-char session cookie |
| I | PASS | companion ping 200 with chat token; finance still 403 |

Remaining gaps: Android emulator, Tailscale Serve / MagicDNS / Private DNS (section 7).
