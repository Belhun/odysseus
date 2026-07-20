# Product vision integrations (planned)

## What it does in SysForge

Long-term integrations for security, asset tracking, network inventory, and automation — planning docs only.

**Paths (docs)**

- `Plans/Product-Vision/README.md`
- `Plans/Product-Vision/Integrations.md`
- `Plans/Product-Vision/Roadmap.md`, `Invoice-Roadmap.md`
- `Plans/Product-Vision/Repair-Documentation-System.md`

## Status

**Planned** — no code matches per `Plans/README.md`.

Targets: Wazuh, Snipe-IT, NetBox, n8n.

## Dependencies

- Core invoice/parts/projects stable
- External API credentials
- Likely Odysseus MCP or webhook infrastructure

## Port approach

Do not bundle in MVP add-on. Implement as separate micro-add-ons or MCP tools leveraging Odysseus `routes/mcp_routes.py` and agent tools. Snipe-IT asset sync could map to `InvoiceDevices` / projects.

## Effort

**XL** (per integration)

## Risks / open questions

- AGPL interaction with external service terms
- Which integrations shop operators need first — product decision open
