# PhonePi Google Messages bridge

Wraps vendored openmessage (`mcp_servers/phonepi/vendor/openmessage`) for SMS + RCS via Google Messages web pairing.

In Odysseus, pair from **Settings → Phone**. Docker builds this binary; do not commit `phonepi-gmessages` / `.exe`.

Standalone Windows build (optional, outside Docker):

```powershell
cd messages-bridge
go build -o phonepi-gmessages.exe .
.\phonepi-gmessages.exe pair
```

Session directory: `PHONEPI_GMESSAGES_DATA_DIR` or `~/.local/share/phonepi-gmessages`.
Port 11042 stays on loopback. The Node MCP `gm_*` tools POST to `PHONEPI_GMESSAGES_URL`.
