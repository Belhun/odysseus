# Draft management

## What it does in SysForge

JSON file drafts outside SQLite; triple-buffer autosave; draft list; load into calculator; retention settings.

**Paths**

- `SysForge/Services/DraftService.cs`
- `SysForge/Models/DraftData.cs`, `DraftItem.cs`
- `SysForge/ViewModels/DraftsViewModel.cs`, `Views/DraftsView.axaml`, `DraftNameDialog.axaml`
- Config: `drafts.*` in `config.json`

## Status

**Done (Odysseus)** — optional retention with safe defaults (`draft-retention-draft-08`):

- `auto_delete_old` defaults **false**; missing key → false
- No cleanup on install / startup / plugin load
- Settings UI + confirm + post-delete notice + pin
- Lazy weekly schedule gated by toggle (default schedule off)

Desktop SysForge still has `DeleteOldDrafts` unwired (BUG-017 / DRAFT-08 by design). Do not “fix” by adding a silent boot hook.

## Dependencies

- Filesystem under `%LOCALAPPDATA%\SysForge\Drafts\` (desktop) / `data/plugins/sysforge/drafts/` (Odysseus)
- `JsonSchemaValidator` for draft payload shape (desktop)

## Port approach

Near-direct port: same JSON files. File APIs + calculator autosave debounce in JS. Optional cleanup is settings-gated (default off); pin survives retention.

## Effort

**M**

## Risks / open questions

- Concurrent edit from two browser tabs — need optimistic locking or single-writer warning
