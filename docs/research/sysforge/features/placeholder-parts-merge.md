# Placeholder parts merge

## What it does in SysForge

Resolve placeholder parts to catalog parts: grouping, merge UI, SKU conflict handling.

**Paths**

- `SysForge/ViewModels/PlaceholderMergeViewModel.cs`
- `SysForge/Views/PlaceholderMergeView.axaml`
- `SysForge/Models/PlaceholderGroup.cs`
- `PartService` merge methods
- `Phase1VerificationService` (creation side)

## Status

**Done** (merge UI). Workflow plan doc empty.

## Dependencies

- `PartService`, transactions across placeholder updates
- Invoice line items referencing placeholders

## Port approach

Dedicated route + panel. Port merge transaction logic with tests from `SysForge.Tests`. Creation flow stays in calculator API.

## Effort

**M**

## Risks / open questions

- Merge irreversible — confirm dialog pattern
- Empty `Placeholder-Parts-Workflow-Plan.md` — behavior only in code/tests
