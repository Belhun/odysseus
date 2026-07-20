# Remaining Business plugin areas

**Updated:** 2026-07-19 · Plugin `0.17.0` · Source: [`STATUS.md`](STATUS.md)  
Machine list: [`remaining-areas.json`](remaining-areas.json)

Parity MVP (quote → Classic → viewer → backup) is **complete**. All **shippable** leftover slices from this list are **Done**. `remaining[]` is empty.

People-dossier is host-owned and **Done** — not listed.

---

## Remaining (ship next)

_None._ No open shippable slices.

All 18 STATUS workstreams are **Done** (including `future-ui-mru-shell-polish` after in-Business shortcuts).

---

## Recently shipped (this fleet)

| Id | Version | What |
|----|---------|------|
| `screw-map-review-0.16.1` | `0.16.1` | `0031` UNIQUE; zero-photo publish block; DeviceModel sync; `max_results` caps |
| `future-ui-in-business-shortcuts` | `0.17.0` | Host `sysforge_home` / `clients` / `calculator` |
| `screw-maps-canvas-depth` | `0.17.0` | Zoom/pan + note markers (image delete/reorder skipped) |
| `backup-json-document-binaries` | `0.17.0` | JSON `invoiceDocuments[].contentBase64` round-trip |
| `projects-display-code` | `0.17.0` | Human-readable DisplayCode + `0032` |
| `projects-rich-notes-p4` | `0.17.0` | Markdown toolbar + preview (P4 light) |
| `projects-inventory-light-p6` | `0.17.0` | PartStock `0033` + project reserve/release |

---

## Deferred epics (not next)

| Id | Why parked |
|----|------------|
| `roles-rbac` | Invoice-ops out of scope; A–E Done |
| `quickbooks-sync` | External accounting; CSV already ships |
| `screw-maps-s5-mobile` | Explicit defer; tablet browser substitutes |
| `screw-map-image-delete-reorder` | Not on desktop; skipped with canvas polish |
| `multi-jurisdiction-tax` | Single-rate settings Done |
| `recurring-invoices` | v3+ automations |
| `host-integrations-phase-10` | Snipe-IT / Wazuh / NetBox / n8n — MASTER Phase 10 |
| `future-ui-nav-themes-profiles` | VI2 = no nav persist; no Avalonia dual themes/profiles |
| `projects-notes-embed-wysiwyg` | Beyond P4 light toolbar/preview |
| `projects-inventory-depth` | Beyond PartStock soft reserve |

---

## Spawn guide

No agents to spawn from `remaining[]`. New work should come from deferred epics (product ask) or fresh gap discovery — not from this empty leftover list.
