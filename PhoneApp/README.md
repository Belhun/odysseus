# Odysseus phone client

Flutter client for Odysseus. v1 is **finance sync only**. The app is a shell (auth, nav, theme, settings, placeholders) so later modules can land in the same project.

Path: `PhoneApp/` inside the Odysseus repo.

## Source of truth

Odysseus server: `data/plugins/finance/finance.db` via `/api/finance/*`.

No Firebase, Google Drive, Plaid, envelope budgeting, or cloud relay.

## Network

The phone must be on **Tailscale**. Point the server URL at your Tailscale IP or MagicDNS hostname, including port:

```
http://100.x.x.x:7000
http://your-machine:7000
```

Do not expose Odysseus to the public internet.

## Auth

Preferred: an `ody_` API token with **`finance:read` and `finance:write`**.

1. Open Odysseus in a browser (on the same Tailscale host).
2. Admin → Tokens (or Settings → tokens).
3. Create a token, enable Finance read + write. Profile `phone_finance` also selects those scopes.
4. Paste the token into this app.

Companion pairing tokens are **chat-only**. They get `403` on finance routes.

Password login is also supported. It stores the `odysseus_session` cookie. That path is for native Android. Flutter **web** is cross-origin, so cookie login needs `ALLOWED_ORIGINS` to include the Flutter origin (for example `http://localhost:xxxxx`). Token auth avoids that.

## Run

Flutter SDK used here: `F:\FlutterDev\flutter`. Android SDK: `F:\AndroidSDKManager`. JDK: `F:\Java\jdk-21.0.12`.

```powershell
$env:JAVA_HOME = "F:\Java\jdk-21.0.12"
$env:ANDROID_HOME = "F:\AndroidSDKManager"
$env:ANDROID_SDK_ROOT = "F:\AndroidSDKManager"
$env:PATH = "F:\FlutterDev\flutter\bin;F:\Java\jdk-21.0.12\bin;F:\AndroidSDKManager\platform-tools;" + $env:PATH

cd "F:\Codeing Project\odysseus\PhoneApp"
flutter pub get
flutter analyze
flutter test
```

### Web (local smoke)

```powershell
flutter build web
flutter run -d chrome
# or: flutter run -d web-server --web-port 8080
```

If the UI loads but API calls fail in Chrome, either:

- Use an `ody_` token **and** set Odysseus `ALLOWED_ORIGINS` to the Flutter origin, or
- Skip live API on web and use Android over Tailscale.

### Android later

```powershell
flutter run -d <device-id>
# or
flutter build apk
```

## Navigation

One bottom bar: **Home · Transactions · Budget · Recurring · More**.

FAB on Home and Transactions adds a transaction.

More: Accounts, Import, Reports, Rules, Settings, future modules.

**A/B test (one):** `Budget (test: month-close)` on More. Same budget API, last-month review + copy-forward.

**Placeholders (no API):** Goals, Investing, Sankey, Chat, Email, Calendar, Notes.

## Odysseus server change for this client

Finance routes accept scoped `ody_` tokens as the token owner (same ledger as the web UI). See `integrations/finance/routes.py` `require_user` and `finance:read` / `finance:write` in `routes/api_token_routes.py`.
