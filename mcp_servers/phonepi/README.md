# PhonePi MCP (vendored)

Vendored from the local `phonepi-mcp` server (MIT). Odysseus ships this so a git pull plus image rebuild includes the phone bridge and the Google Messages Go wrapper.

Enable at runtime with `PHONEPI_ENABLED=true` in the host `.env`, then recreate the container. Pair and repair from **Settings → Phone** in the Odysseus UI. Do not add a Settings → MCP row that points at a Windows `phonepi-mcp` path; that fights this builtin for loopback 11041.

Do not copy `node_modules`, `dist`, or the built `phonepi-gmessages` binary into git. Docker runs `npm ci && npm run build` and compiles the Go bridge during the image build.

## Phone companion (Android)

The Node WebSocket stays on loopback (`PHONEPI_WS_HOST`, default `127.0.0.1:11041`). Odysseus proxies it at the UI host on path `/phonepi`.

Tailscale Serve HTTPS example: `wss://dell-mini-pc.tailcbcc46.ts.net/phonepi` (phone app Host = that hostname, Port = `443`).

`/phonepi` is not cookie-auth'd. The tailnet is the gate. Do not enable Tailscale Funnel.

Settings → Phone shows the host/port to copy and a Restart PhonePi button.

## Google Messages

The image contains `mcp_servers/phonepi/messages-bridge/phonepi-gmessages`. Pairing writes `session.json`, `qr-url.txt`, and `pair-status.json` under `PHONEPI_GMESSAGES_DATA_DIR` (Docker: `/app/.local/share/phonepi-gmessages`, host volume `./data/local`).

Settings → Phone:

1. **Pair with Google account** — Firefox private window → sign in at the config URL → paste cURL → tap emoji on phone.
2. **Reset pairing** — drops the session; paste fresh cookies to pair again.
3. **Restart sync** — starts `phonepi-gmessages serve` on loopback 11042 if already paired.

`gm_*` MCP tools talk to `http://127.0.0.1:11042`. That path does not need the Android PhonePi WebSocket.
