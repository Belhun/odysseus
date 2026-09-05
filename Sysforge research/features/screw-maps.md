# Screw maps and repair documentation



## What it does in SysForge



Visual screw position maps on device images; markers; screw library; annotation UI for repair documentation.



**Paths (desktop)**



- `SysForge/Database/ScrewMapService.cs`

- Migrations: `0019_screw_maps.sql`, `0020_screw_map_markers.sql`, `0021_screw_map_library.sql`

- `SysForge/ViewModels/ScrewMapViewModel.cs`, `ScrewMapAnnotationViewModel.cs`

- `SysForge/Views/ScrewMapView.axaml`, `ScrewMapAnnotationView.axaml`

- `SysForge/Views/Controls/ScrewMapImageCanvas.axaml`

- Plan: `Plans/Product-Vision/Repair-Documentation-System.md`, `Screw-Map-S5-Mobile-Companion-Plan.md`



**Paths (odysseus-sysforge plugin)**



- Runtime: `integrations/sysforge/` (not `addons/sysforge/`)

- Migrations: `0020_screw_maps.sql`, `0021_screw_map_markers.sql`, `0022_screw_map_library.sql`, `0031_screw_map_sets_source_unique.sql`, `0034_companion.sql`

- Service: `integrations/sysforge/services/screw_maps.py`, `companion.py`, `companion_inbox.py`

- UI: `static/js/views/screw-map-view.js`, `static/js/screw-map-canvas.js`, project-detail phone QR, `static/companion/`

- Images: `{plugin_data}/ScrewMapImages/screwmap-{id}/`

- Remote access: `integrations/sysforge/docs/companion-remote-access.md`



## Status



**Done (Odysseus S0–S2 + lock + S3/S4 library)** — ScrewMapView port: single-click place, numbered dots, autosave + undo, HW/Other gate, 1:1 map/project, four-column preview above Before/After, manual + auto lock. S3 measurement lookup + library publish/browse/clone shipped in plugin `0.16.0`+ (`0.16.1` publish/UNIQUE tighten).



**Done (depth)** — Canvas zoom/pan; note-marker UI (Place mode + right-click; `NoteMarkers` CRUD).



**Done (S5 mobile companion — `0.18.0`)** — LAN pair + QR upload (Method A); context sync poll/SSE (S5b); inbox folder import (S5c); Tailscale/HTTPS `public_base_url` + docs (S5d). Locked maps reject phone/inbox writes.



**Deferred:** Image delete/reorder (desktop has neither); custom VPS photo relay.



## Dependencies



- Projects four-column (`projects-wo-four-column`)

- Image storage under plugin data dir

- Canvas/SVG hit-testing for markers

- Odysseus LAN bind (`APP_BIND=0.0.0.0`) for phone reachability



## Port approach



HTML canvas/SVG rewrite of ScrewMapView (not Avalonia control 1:1). Primary UX = ScrewMapView single-click; older AnnotationView double-click deferred. Companion uses same FastAPI host (no separate Kestrel).



## Effort



**L** (S5 shipped; lookup / library already in)



## Risks / open questions



- Image size/storage quotas in Docker (20 MB soft cap per image)

- Guest Wi-Fi client isolation → hotspot or inbox fallback

- Some phones restrict camera on non-HTTPS LAN; Tailscale HTTPS via `public_base_url`

- Open product decisions in questionnaire Part IV (unlock, category change)


