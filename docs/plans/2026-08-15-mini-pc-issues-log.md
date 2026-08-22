# Mini PC Odysseus issues log

Created: 2026-08-15
Host: `dell-mini-pc` (`~/odysseus`, Docker Compose, Tailscale Serve `https://dell-mini-pc.tailcbcc46.ts.net`)
Branch: `belhun/playground`

Running log. Append dated entries. Do not delete resolved items; change **Status**.

Statuses: `open` | `workaround` | `fixed`

---

## 2026-08-15 — Linux move (known before this session)

### Attachment `local_path` still Windows

- **Severity:** medium
- **Symptom:** Rows in `email_store.db` attachments still point at `E:\odysseus\data\mail-attachments\...`. Linux cannot open those files.
- **Likely cause:** DB copied from the Windows live tree. Paths were stored as absolute Windows strings.
- **Status:** fixed (2026-08-15, remap-on-read)
- **Notes:** DB rows are unchanged. `resolve_stored_attachment_path()` remaps a missing Windows path onto `MAIL_ATTACHMENTS_DIR` / `ODYSSEUS_DATA_DIR` / `DATA_DIR` / `/app/data` plus the `mail-attachments` tail. If the stored `E:\` file exists (Windows local testing), that path is used. Verified on Mini PC: `E:\odysseus\data\mail-attachments\INBOX_49130\...` → `/app/data/mail-attachments/INBOX_49130/...` and the file is present. ~2239 attachment dirs on the host.

### Dual Windows + Mini PC IMAP sync will drift

- **Severity:** high if both stay live
- **Symptom:** Two Odysseus instances syncing the same Gmail accounts will fight over flags, UID windows, and local rows.
- **Likely cause:** One mailbox, two writers (`email_store.db` + IMAP `\Seen`).
- **Status:** open
- **Notes:** Keep Windows Odysseus stopped while Mini PC is the live box.

### User MCP servers with `F:\Codeing Project\...` paths fail on Linux

- **Severity:** medium
- **Symptom:** Settings MCP list shows foundry / PhonePi / Fantasia. They do not connect. Logs: `Cannot find module '/app/F:\Codeing Project\phonepi-mcp\...'`.
- **Likely cause:** `app.db` `mcp_servers` rows still have Windows command/args.
- **Status:** open (host-specific)
- **Notes:** Builtin email MCP is a different server (`id=email`). Re-enabling Gmail/PhonePi/Fantasia in Settings does not start it. `manage_mcp list` only shows DB rows, not builtins. Mini PC rows (2026-08-15): `foundry-mcp` / `PhonePi` / `Fantasia Archive` all use `node` plus `F:/Codeing Project/...` JS entrypoints. Not npx. Do not invent Linux binaries. Leave Windows `app.db` on `E:\odysseus` as-is. To run these on Mini PC, clone each MCP repo onto that host and edit only the Mini PC `mcp_servers.args` to the Linux path. `node` is already in the image.

### Chroma / memory degraded if host has no chromadb

- **Severity:** low (Compose has Chroma)
- **Symptom:** Memory search weak if embeddings never rebuilt on Linux.
- **Likely cause:** Windows used native `data/chroma` or a different volume. Docker Chroma is named volume `chromadb-data`.
- **Status:** workaround
- **Notes:** `odysseus-chromadb-1` is up on `127.0.0.1:8100`. Rebuild embeddings if search feels empty.

### MagicDNS + Tailscale Serve operator

- **Severity:** high (access)
- **Symptom:** `https://dell-mini-pc.tailcbcc46.ts.net` failed until MagicDNS was on tailnet-wide and Serve ran as `belhun`.
- **Likely cause:** Serve HTTPS + MagicDNS are tailnet settings, not Odysseus config.
- **Status:** fixed
- **Notes:** Serve: `tailscale serve --bg 7000`. `APP_BIND=127.0.0.1`. Do not enable Funnel.

### Models / `LLM_HOST=localhost` empty until providers restored

- **Severity:** medium
- **Symptom:** Local/Ollama-style endpoints empty. Chat can still use cloud providers (this session used `deepseek/deepseek-v4-pro`).
- **Likely cause:** Mini PC `.env` has `LLM_HOST=localhost` and no local LLM. Endpoint IDs live in `app.db`.
- **Status:** workaround
- **Notes:** Point providers at the machine that serves models (often `hp1`). Do not run 30B vLLM on 7.6 GB RAM.

### `ODYSSEUS_DATA_DIR` leftover

- **Severity:** low
- **Symptom:** Windows `.env` still has `ODYSSEUS_DATA_DIR=E:\odysseus\data`.
- **Likely cause:** Compose on Mini PC dropped that key so `./data` is used.
- **Status:** fixed (Mini PC)
- **Notes:** Mini PC `.env` has no `ODYSSEUS_DATA_DIR`. `.app_key` is present (44 bytes). Do not restore the Windows `.env`.

---

## 2026-08-15 — Email cleanup session (this diagnosis)

### Builtin email MCP not connected (`MCP server not connected: email`)

- **Severity:** high
- **Symptom:** Chat tools `list_email_accounts`, `mark_email_read`, `bulk_email` fail with `MCP server not connected: email`. `read_local_emails` and `sync_local_emails` work (~37k msgs, 3 Gmail accounts, All Mail up to date). UI `/api/email/mark-read` works (live IMAP + token decrypt are fine).
- **Likely cause:** Docker image installed **mcp 2.0.0**. SDK v2 removed `@server.list_tools()`. All four builtin Python MCP servers crash on import (`email`, `memory`, `rag`, `image_gen`): `AttributeError: 'Server' object has no attribute 'list_tools'`. `requirements.txt` had an unpinned `mcp`.
- **Status:** fixed (repo + rebuilt image, 2026-08-15)
- **Notes:** `requirements.txt` pins `mcp>=1.9,<2`. Mini PC `docker compose up --build` installed **mcp 1.29.0**. After recreate: `Built-in: Email (email) - 14 tools via stdio` plus memory / image_gen / rag. Windows venv: mcp **1.28.1** (`pip install "mcp>=1.9,<2"`). `manage_mcp list` showing 0 email tools is still expected: builtins are not DB rows. Do not tell the user to reconnect Gmail MCP in Settings for this.

### Local-only mode cannot mark read without email MCP

- **Severity:** high
- **Symptom:** User has Local only on. Expectation: mark-read should update `email_store.db` and push `\Seen` on the next sync. Agent still routed `mark_email_read` / `bulk_email` to `mcp__email__*`, which needs the crashed builtin server.
- **Likely cause:** Product gap. `LOCAL_EMAIL_TOOLS` is only `read_local_emails` + `sync_local_emails`. Bare email names always dispatch to MCP. Local-only only blocks live *reads* (`list_emails` / `read_email` / `search_emails`).
- **Status:** fixed in playground (uncommitted) and in the rebuilt Mini PC image
- **Notes:** Local-only `list_email_accounts` / `mark_email_read` / `bulk_email` mark_read|mark_unread write `email_store.db` with `read_dirty=1`. Archive/delete/junk still refused in local-only (nothing deleted). Code lives in the git repo (`src/tool_execution.py`, `src/tool_implementations.py`, `src/tool_security.py`). Image check: `LOCAL_ONLY_NATIVE_EMAIL_TOOLS` = bulk_email, list_email_accounts, mark_email_read. Retry the mark-read sweep now. Prefer `bulk_email` with `all_unread: true` (omit `account` to hit all three Gmail accounts). Then `sync_local_emails` to push `\Seen`.

### IMAP / `.app_key` on Mini PC

- **Severity:** info
- **Symptom:** None for this session. Local sync and UI mark-read succeeded.
- **Likely cause:** `.app_key` copied with prefs; Gmail tokens decrypt.
- **Status:** fixed (for this move)
- **Notes:** No IMAP_HOST leftover in Mini PC `.env`. Account IMAP hosts live in `app.db`.

---

## 2026-08-15 — Cross-platform stay-fixed pass

Verified on both hosts. Did not `git pull`. Did not delete `E:\odysseus`. Did not commit.

### Mini PC rebuild

- Copied playground source into `~/odysseus` (no git pull).
- `docker compose up --build -d` succeeded. Image pip line: `Collecting mcp<2,>=1.9` → **mcp-1.29.0**.
- Containers up. `curl 127.0.0.1:7000` → **302 /login**.
- Builtins connected: Email 14 tools, Memory, Image Generation, RAG.
- Attachment remap verified inside the new image (Windows `E:\` path → `/app/data/mail-attachments/...`, file exists).

### Windows repo / venv

- Branch: `belhun/playground` (ahead of origin; not pulled).
- Same source files as Mini PC.
- venv mcp **1.28.1** (satisfies `>=1.9,<2`).
- Tests: `tests/test_attachment_path_remap.py` + `tests/test_email_local_only_mode.py` — 16 passed.

### Still host-specific

- PhonePi / Fantasia Archive / foundry-mcp: Mini PC `app.db` still has `node` + `F:/Codeing Project/...` args. Need per-machine paths if you want them on Linux. Windows `E:\odysseus` MCP rows stay Windows.
- Keep Windows Odysseus stopped while Mini PC is the live IMAP writer.

---

## 2026-08-21 — PhonePi native optional builtin

- **Symptom:** Mini PC PhonePi MCP row still used Windows `F:\Codeing Project\phonepi-mcp\...`. Port 11041 was not listening. Phone could not connect.
- **Likely cause:** User MCP paths copied from Windows `app.db`.
- **Status:** fixed (playground): PhonePi server vendored at `mcp_servers/phonepi`, image `npm ci && npm run build`, runtime `PHONEPI_ENABLED=true`. Odysseus proxies `wss://<UI-host>/phonepi` to loopback 11041. Disable the old Settings MCP row (`332defb9`) so it does not fight the builtin.
- **Phone address:** Host `dell-mini-pc.tailcbcc46.ts.net`, Port `443` (same host as the UI). Needs an updated companion APK that speaks `wss` + `/phonepi`. Tailscale on the phone must be on. Do not Funnel.

---

## 2026-08-21 — Google Messages pairing in Settings → Phone

- **What:** Vendored `messages-bridge` + openmessage. Docker builds `phonepi-gmessages`. Settings → Phone shows a scannable QR, Repair pairing, Restart PhonePi / Restart sync.
- **Session:** `/app/.local/share/phonepi-gmessages/` on the Mini PC volume (`data/local`).
- **Status:** image rebuilt; binary present; PhonePi 33 tools; 11042 waits until a phone scans the QR. Pairing is independent of the Android companion app.

