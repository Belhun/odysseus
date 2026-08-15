# Odysseus on the Dell Mini PC

Created: 2026-08-15

Bring playground Odysseus up on `your-mini-host`, prove Tailscale access from this PC, then copy live data and fix Linux breakage. Do not do a one-shot dump.

## Goal

Odysseus stays up on the Mini PC even when this Windows box is off. You reach it only on the tailnet. LAN and the public internet do not get a bind.

## What we already know

| Item | Fact |
|------|------|
| Live data | `E:\odysseus\data` (last write 2026-07-21). C: wipe did not touch this. |
| Stale clone | `F:\Codeing Project\odysseus\data` is older and smaller. Do not restore from it. |
| Code to run | `belhun/playground` in this repo (356 local commits not on GitHub). |
| Mini PC | Ubuntu Server, Docker 29 + Compose, Tailscale, user `belhun` (uid/gid 1000), docker group. |
| Hardware | i5-7600T, 7.6 GB RAM, 419 GB free. No GPU. Do not serve local LLMs here. |
| Tailnet name | `your-host.tailXXXXXX.ts.net` |
| Tailscale IP | `100.x.y.z` |
| LAN IP (bulk copy) | `192.168.1.206` |
| SSH | `ssh your-mini-host` |

Windows used `APP_BIND=0.0.0.0`. That also opens the LAN. The Mini PC keeps `APP_BIND=127.0.0.1` and uses Tailscale Serve instead. Do not enable Tailscale Funnel.

## Gates

Work stops at each gate until you say go.

1. **Empty playground is up** on the Mini PC, settings copied, login works on the box itself (`curl` to `127.0.0.1:7000`).
2. **This Windows PC** opens Odysseus over Tailscale and you confirm the UI.
3. **Live data lands** on the Mini PC. Windows copies stay untouched as fallback.
4. **Breakage list** gets fixed (models, email, paths, Chroma, Cookbook).

## Phase 0 — Inventory (this Windows PC)

Confirm the source of truth before any copy.

- Treat `E:\odysseus\data` as canonical.
- Record sizes and dates for `app.db`, `email_store.db`, `.app_key`, `auth.json`, `settings.json`, `user_prefs.json`.
- Skip `data/local` forever on this move (~7.8 GB of Windows Python packages; they will not run on Linux).
- Skip `data/huggingface` (empty here).
- Leave `mail-attachments/` for Phase 3 (optional; IMAP can refill it).
- Make a `git bundle` of `belhun/playground` so the Mini PC gets the 356 unpushed commits. A `git clone` from GitHub would miss them.

Settings that can move in Phase 1 (no chat/email databases):

- Rewritten `.env` (paths, bind, CORS, cookies)
- `data/.app_key` with `data/user_prefs.json` (prefs hold Fernet-encrypted CalDAV secrets)
- `data/auth.json` (same login)
- `data/settings.json`, `data/presets.json`, `data/features.json`
- `data/cookbook_state.json` only as a reminder of remote servers; this box will not run those vLLM jobs

Settings that wait for Phase 3:

- `app.db` (chats, providers/endpoint IDs that `settings.json` points at)
- `email_store.db`, `scheduled_emails.db`
- `mail-attachments/`
- uploads, plugins, skills, memory files

Phase 1 will look “empty” for chats and models. That is expected. Endpoint IDs in `settings.json` live in `app.db`.

## Phase 1 — Playground up on the Mini PC

### Code

- Bundle `belhun/playground` on this PC.
- Copy the bundle over Tailscale (`scp` to `your-mini-host`).
- On the Mini PC: clone the bundle into `~/odysseus`, check out `belhun/playground`.
- Do not copy `venv/`, `data/local/`, or Windows launch scripts as the runtime.

### Config

Write a Linux `.env` from the Windows one. Change these:

- `APP_BIND=127.0.0.1` (not `0.0.0.0`)
- `APP_PORT=7000`
- Drop `ODYSSEUS_DATA_DIR=E:\odysseus\data` so Compose uses `./data`
- `PUID=1000` / `PGID=1000`
- `AUTH_ENABLED=true`
- `LOCALHOST_BYPASS=false`
- `SECURE_COOKIES=true` (Serve is HTTPS)
- `ALLOWED_ORIGINS=https://your-host.tailXXXXXX.ts.net`
- Keep API keys you already have in `.env`; do not commit this file

Copy the Phase 1 settings files into `~/odysseus/data/`.

### Run

- `docker compose up -d --build` from `~/odysseus`
- Compose already restarts with `unless-stopped` (survives reboot and `docker` restarts)
- First image build on this CPU takes a while; that is the slow step
- Confirm: `docker compose ps` healthy, `curl -sS http://127.0.0.1:7000/` returns the app

### Tailscale-only access

- `tailscale serve --bg 7000`
- Serve persists across Tailscale/reboot when started with `--bg`
- Confirm `tailscale serve status` shows a proxy to `http://127.0.0.1:7000`
- Do not publish port 7000 on `0.0.0.0` or on the LAN firewall
- Do not run `tailscale funnel`
- Keep Chroma (`8100`), SearXNG (`8080`), and ntfy (`8091`) on loopback until you later decide ntfy needs a Tailscale bind for phone push

URL to use from other tailnet devices:

`https://your-host.tailXXXXXX.ts.net`

**Gate 1:** SSH session can hit loopback 7000. Serve is on. You have not copied `app.db` yet.

## Phase 2 — Prove access from this PC

From `belhuns-main` (this Windows box), Tailscale connected:

- Open `https://your-host.tailXXXXXX.ts.net`
- First HTTPS hit can sit 5–10s while the cert is issued
- Log in with the copied `auth.json` account (or the first-boot admin password in `docker compose logs odysseus` if auth was not copied)
- Confirm the shell loads. Chats/models may be empty. Theme/prefs should look familiar if `user_prefs.json` + `.app_key` copied.

If the page fails:

- Tailscale down on this PC → sign in, then retry
- Cert/CORS → `ALLOWED_ORIGINS` must be the exact `https://…ts.net` origin
- Cookies → `SECURE_COOKIES=true` with Serve HTTPS
- Serve off after reboot → `tailscale serve status`; re-run `--bg` if needed

**Gate 2:** You say from this PC that you can reach Odysseus. Only then copy databases.

## Phase 3 — Move live data

Odysseus is not running on Windows, so a file copy is safe (no live SQLite writers).

- Stop Compose on the Mini PC (`docker compose stop`) so Linux is not writing `data/`
- Snapshot `E:\odysseus\data` excluding `local/` (and optionally excluding `mail-attachments/` if you want a smaller first pass)
- Copy over **LAN** (`192.168.1.206`) when both machines are home. Current Tailscale path from this PC was a relay; a 2–4 GB copy is faster on LAN
- Restore into `~/odysseus/data/` (keep the Linux `.env`; do not restore the Windows `.env`)
- Keep `.app_key` from the E: snapshot so encrypted prefs and vault material decrypt
- `docker compose up -d`
- Leave `E:\odysseus` untouched until Linux has been good for a few days

Default payload:

- Must-have: `app.db`, `email_store.db`, `.app_key`, auth/settings/prefs, uploads, plugins, skills, memory files
- Include `mail-attachments/` unless the first pass is too slow (~2 GB extra; IMAP can rebuild it)
- Never include `data/local/`

**Gate 3:** Login still works, chats exist, email DB is present. Windows tree is still the fallback.

## Phase 4 — Fix what Linux will break

Expect these. None of them mean the copy failed.

| Symptom | Likely cause | Fix direction |
|---------|--------------|----------------|
| Models empty / “Nobody” | Endpoint IDs in `settings.json` need rows in `app.db` (should appear after Phase 3). `LLM_HOST=localhost` on a box with no Ollama. | After data restore, point providers at the machine that actually serves models (often `hp1` on the tailnet). Do not try 30B vLLM on 7.6 GB RAM. |
| CalDAV / vault secrets fail | `.app_key` did not travel with `user_prefs.json` | Copy `.app_key` from E: and restart |
| Email empty or re-syncing | `email_store.db` or `mail-attachments/` not copied yet | Phase 3 copy; IMAP backfill if attachments were skipped |
| Chroma / memory search weak | Windows used native `data/chroma` (empty here) or Docker volume `chromadb-data` | Rebuild embeddings on Linux if needed; Docker Chroma is a named volume, not inside `data/` |
| Cookbook / local engines missing | Skipped `data/local/` on purpose | Reinstall Linux engines through Cookbook only if this box should serve models (it should not) |
| Windows paths in settings | Old `E:\` or `C:\` strings | Edit in Settings after boot; grep `data/*.json` for drive letters |
| ntfy never reaches the phone | ntfy bound to loopback | Later: `NTFY_BIND` = Mini PC Tailscale IP, `NTFY_BASE_URL` to match; keep Odysseus itself on Serve |
| RAM pressure | App + Chroma + SearXNG + ntfy on 7.6 GB | Do not add Ollama/vLLM on this host. Restart Compose if the box swaps hard. |

Keep iterating until the Mini PC matches how you used Odysseus on Windows, minus local GPU serving.

## Always-on checklist

- Docker `restart: unless-stopped` on `odysseus`, `chromadb`, `searxng`, `ntfy`
- Mini PC does not sleep (Ubuntu Server headless; confirm no idle suspend)
- `tailscale serve --bg 7000` (Serve resumes after Tailscale restart)
- `AUTH_ENABLED=true` — anyone on the tailnet who knows the URL can reach Serve, so login stays on
- After a Mini PC reboot: `docker compose ps` and `tailscale serve status`

## Out of scope

- Serving local models on the Mini PC
- Exposing Odysseus on the LAN or via Funnel
- Replacing the Windows copies on E:/F: until Linux has been stable
- Changing Odysseus product code except as needed to run on Linux

## Rollback

- Mini PC: `docker compose down`, data stays in `~/odysseus/data`
- Windows fallback: `E:\odysseus` + `ODYSSEUS_DATA_DIR=E:\odysseus\data` still has the last good tree
- Serve off: `tailscale serve off` (only if you need to shut the URL)

## Next action

Phase 0 + Phase 1 on this machine and `your-mini-host`: bundle playground, rewrite `.env`, Compose up, Tailscale Serve, then you try the URL from this PC.
