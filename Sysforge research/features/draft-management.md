# Draft management

## What it does in SysForge

JSON file drafts outside SQLite; triple-buffer autosave; draft list; load into calculator; retention settings.

**Paths**

- `SysForge/Services/DraftService.cs`
- `SysForge/Models/DraftData.cs`, `DraftItem.cs`
- `SysForge/ViewModels/DraftsViewModel.cs`, `Views/DraftsView.axaml`, `DraftNameDialog.axaml`
- Config: `drafts.*` in `config.json`

## Status

**Done** — auto-delete on startup **partial** (`DeleteOldDrafts` not wired to startup).

## Dependencies

- Filesystem under `%LOCALAPPDATA%\SysForge\Drafts\`
- `JsonSchemaValidator` for draft payload shape

## Port approach

Near-direct port: same JSON files in `data/addons/sysforge/drafts/`. File APIs + calculator autosave debounce in JS. Wire optional cleanup job in Odysseus task scheduler.

## Effort

**M**

## Risks / open questions

- Concurrent edit from two browser tabs — need optimistic locking or single-writer warning
