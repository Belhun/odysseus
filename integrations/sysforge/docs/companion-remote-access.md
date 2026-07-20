# Screw map phone companion — remote access (S5d)

SysForge Business phone upload is **LAN-first** (Method A). This note covers HTTPS / off-LAN options (Method C) without shipping a custom relay server.

## Default: LAN browser (Method A)

1. Odysseus must listen on the LAN, not only loopback.
   - Native: bind host `0.0.0.0` (or your NIC IP), port usually `7000`.
   - Docker Compose: set `APP_BIND=0.0.0.0` (default is often `127.0.0.1`, which blocks phones).
2. Open an HW/Other project → **Show QR / pair code**.
3. Phone on the **same Wi-Fi** scans the QR → enters the 6-digit code once.
4. Take photos; they land on the **active** project screw map within seconds.

Pairing + short-lived sessions stop random guests from uploading. Phone APIs live under `/api/sysforge/companion/phone/*` and are auth-exempt by design (session token required).

### Shop Wi-Fi client isolation

If the phone cannot open the laptop URL:

- Turn on the **laptop hotspot**, join it from the phone, regenerate QR.
- Or use **inbox mode** (Method B) below.

## Method B — Inbox folder

Settings → **Phone companion** → enable inbox → set folder (default `data/plugins/sysforge/Inbox`).

Phone saves/shares photos into that folder (network share, USB copy, or cloud-sync folder). On the project screen: **Scan inbox** → **Import pending**. Optional auto-import when scan runs.

## Method C — Tailscale / HTTPS (no custom relay)

Full phone→relay→desktop VPS is **out of scope** for this release. Use Tailscale (or similar) as the tunnel:

1. Install Tailscale on the shop PC and the phone; join the same tailnet.
2. Confirm Odysseus is reachable at the MagicDNS name (example: `http://shop-pc:7000` or HTTPS if you terminate TLS).
3. In Business **Settings → Phone companion**, set **Public base URL** to that origin, e.g. `https://shop-pc.tailnet-name.ts.net:7000`.
4. Regenerate the QR. The phone opens the Tailscale URL instead of a LAN IP.

### HTTPS notes

- Some mobile browsers restrict camera capture on plain `http://` outside localhost. LAN HTTP often works; if capture fails, prefer Tailscale HTTPS or a reverse proxy with a real cert.
- Do **not** port-forward the companion to the public internet without pairing + TLS + a firewall plan.
- `public_base_url` only changes QR link generation. It does not start a tunnel for you.

### Cloudflare Tunnel / custom relay

Not built into the plugin. If you run your own tunnel:

1. Point the tunnel at Odysseus.
2. Set `companion.public_base_url` to the HTTPS origin.
3. Keep pairing enabled; revoke sessions from Settings if a phone is lost.

## Config keys (`config.json` → `companion`)

| Key | Default | Meaning |
|-----|---------|---------|
| `enabled` | `true` | Master switch |
| `pair_code_minutes` | `15` | QR / code lifetime |
| `session_hours` | `48` | Trusted phone session |
| `inbox_enabled` | `false` | Method B |
| `inbox_path` | `null` | Folder (default plugin `Inbox`) |
| `inbox_auto_import` | `false` | Import on scan |
| `public_base_url` | `null` | QR origin override (Tailscale / HTTPS) |

## Security checklist

- Pairing required; no anonymous upload.
- Locked screw maps reject phone and inbox writes (`409`).
- Revoke all sessions from Settings when needed.
- Prefer LAN or private VPN; avoid exposing `/api/sysforge/companion/phone` on the open internet.
