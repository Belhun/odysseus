# Screw maps and repair documentation

## What it does in SysForge

Visual screw position maps on device images; markers; screw library; annotation UI for repair documentation.

**Paths**

- `SysForge/Database/ScrewMapService.cs`
- Migrations: `0019_screw_maps.sql`, `0020_screw_map_markers.sql`, `0021_screw_map_library.sql`
- `SysForge/ViewModels/ScrewMapViewModel.cs`, `ScrewMapAnnotationViewModel.cs`
- `SysForge/Views/ScrewMapView.axaml`, `ScrewMapAnnotationView.axaml`
- `SysForge/Views/Controls/ScrewMapImageCanvas.axaml`
- Plan: `Plans/Product-Vision/Repair-Documentation-System.md`, `Screw-Map-S5-Mobile-Companion-Plan.md`

## Status

**In progress** — S0+S1 in working tree per `Plans/README.md`. Timeline/library/mobile deferred.

## Dependencies

- Image storage (filesystem or blob in DB)
- Canvas hit-testing for markers
- Project/device linkage

## Port approach

HTML canvas/SVG annotation layer. Image upload API storing under `data/addons/sysforge/images/`. Defer mobile companion; Odysseus web UI may suffice on shop tablets.

## Effort

**XL**

## Risks / open questions

- Custom Avalonia canvas control does not port 1:1
- Image size/storage quotas in Docker
- Open product decisions in questionnaire Part IV
