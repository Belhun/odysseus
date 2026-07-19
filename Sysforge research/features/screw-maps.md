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
- Migrations: `0020_screw_maps.sql`, `0021_screw_map_markers.sql`, `0022_screw_map_library.sql` (desktop 0019–0021)
- Service: `integrations/sysforge/services/screw_maps.py`
- UI: `static/js/views/screw-map-view.js`, `static/js/screw-map-canvas.js`
- Images: `{plugin_data}/ScrewMapImages/screwmap-{id}/`

## Status

**Done (Odysseus S0–S2 + lock)** — ScrewMapView port: single-click place, numbered dots, autosave + undo, HW/Other gate, 1:1 map/project, four-column preview above Before/After, manual + auto lock.

**Deferred:** S5 mobile companion; zoom/pan; note-marker UI; S3 measurement lookup; library publish/browse UI (schema present in `0022`).

## Dependencies

- Projects four-column (`projects-wo-four-column`)
- Image storage under plugin data dir
- Canvas/SVG hit-testing for markers

## Port approach

HTML canvas/SVG rewrite of ScrewMapView (not Avalonia control 1:1). Primary UX = ScrewMapView single-click; older AnnotationView double-click deferred.

## Effort

**L** (S5 / lookup / library UI cut)

## Risks / open questions

- Image size/storage quotas in Docker (20 MB soft cap per image)
- Open product decisions in questionnaire Part IV (unlock, category change)
