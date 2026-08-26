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

### First-time setup

Configure **server URL**, **username**, and **`ody_` API token** (pre-filled from deploy config or a setup link when available). Enter your **password** to sign in. Password is never stored on the device.

After login, the app asks whether to enable **biometric unlock** (optional). If you decline, the app **stays signed in** and opens without a lock screen.

### Return visits

| Biometric unlock | What happens |
|------------------|--------------|
| **On** (Android) | Biometric lock screen (fingerprint, face, or device PIN) |
| **Off** | Auto login — session and token reused, no lock screen |
| **Web** | Auto login; biometrics skipped |

Toggle biometric unlock under **More → Security**. Turning it on requires your password once plus a biometric check. Turning it off returns to stay-signed-in mode.

Token scopes: **`finance:read` and `finance:write`**. Mint from Odysseus gear → Phone app token.

Companion pairing tokens are **chat-only** (`403` on finance).

The legacy Connect screen remains for token-only reconnect. **Sign out** clears the session and returns to setup with fields pre-filled. Flutter **web** cookie login needs `ALLOWED_ORIGINS`; token auth avoids that.

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
