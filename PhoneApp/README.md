# PhoneApp

Flutter client for Odysseus finance. Token auth is the path that works on
**web**. Password login is for native (Android/iOS) where `dart:io` can read
the `odysseus_session` cookie.

## Run

```bash
# Odysseus must already be on :7000 with the finance plugin installed.
cd PhoneApp
flutter run -d chrome --web-hostname 127.0.0.1 --web-port 8088
# or
flutter build web
python3 -m http.server 8088 --directory build/web
```

Set Odysseus `ALLOWED_ORIGINS` to include the Flutter origin if it is not
loopback (loopback any-port is allowed by default). See
[`docs/phone-client-connect-guide.md`](../docs/phone-client-connect-guide.md).

## Connect fields

- **Server URL** — Odysseus origin, e.g. `http://127.0.0.1:7000`
- **API token** tab — paste `ody_…` with `finance:read` + `finance:write`. Optional username is a label only.
- **Password** tab — username, password, TOTP if 2FA. POST `/api/auth/login` only.

Android MagicDNS workaround lives in `lib/ody_http_factory_io.dart`.
