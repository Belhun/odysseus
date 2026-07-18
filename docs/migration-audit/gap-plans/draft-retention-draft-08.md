# Optional DRAFT-08 retention (safe defaults)

| Field | Value |
|-------|-------|
| **Issue id** | `draft-retention-draft-08` |
| **Title** | Optional DRAFT-08 retention (safe defaults) |
| **Phase** | P2 |
| **Priority** | medium |
| **Effort** | **M** |
| **Primary sources** | Chat [bfe03bf6](../chat-reviews/bfe03bf6-e707-4b67-bb29-017762d3a091.md) (intentionally unwired); MASTER §4 DRAFT-08 + §6 checklist + §7 P2; `DraftService.DeleteOldDraftsAsync`; chats `97aa3734`, `a162de19`; research `features/draft-management.md` |
| **Manifest** | `gap-plans/gap-manifest.json` → `draft-retention-draft-08` |
| **Master plan** | `synthesis/MASTER-MIGRATION-PLAN.md` → must-not-lose DRAFT-08; deferred P2 “wire optional draft retention” |

---

## Goal / success

Ship **optional** old-draft cleanup for the SysForge Business plugin with **safe defaults**:

1. Retention auto-delete is **OFF** by default (`drafts.auto_delete_old: false`).
2. No cleanup runs on plugin install, plugin load, app boot, or first request.
3. Cleanup runs only after the user opts in via Business settings **and** a deliberate trigger (manual “Clean up now” and/or an Odysseus scheduled task that still respects the OFF gate).
4. Every successful purge surfaces a **non-blocking notice** (count deleted + retention window). Never silent.
5. Autosave slots are never deleted by retention (match desktop `!draft.IsAutosave`).
6. Optional pin/keep-forever on named drafts survives retention when auto-delete is on.

**Done when:**

- Fresh install config has `auto_delete_old: false` (and existing installs that lack the key treat missing as **false**).
- `POST` cleanup with auto-delete off returns `deleted: 0` and deletes zero files.
- With auto-delete on + old drafts present, cleanup deletes only named drafts older than `retention_months`, skips autosaves and pinned drafts, and returns a notice payload the UI shows.
- Plugin load / app start path has **no** call to cleanup (regression test / code search assertion).
- Settings UI can toggle auto-delete, set retention months (clamped), and run “Clean up now” with a confirm when the preview count is &gt; 0.
- QA checklist item MASTER §6 “DRAFT-08: retention default off; no silent purge” passes.

---

## Current state

### SysForge desktop (source of truth)

| Piece | Status |
|-------|--------|
| `DraftService.DeleteOldDraftsAsync` | **Exists** + unit tests (`DraftServiceTests`) |
| `RetentionSettings` → `(RetentionMonths, AutoDeleteOld)` | **Exists**; reads `Config.Drafts` |
| Call from `Program.cs` / `App.axaml.cs` | **Intentionally absent** (DRAFT-08 / BUG-017 = not a bug) |
| Settings UI for draft retention | **Missing** (Settings covers backup retention days, not draft retention) |
| Post-delete notice / pin | **Missing** (documented as future when re-opening DRAFT-08) |
| Config defaults | `RetentionMonths = 6`, `AutoDeleteOld = true` — **unsafe** if anyone calls the method |

Desktop method behavior (port this logic, not the default):

```text
DeleteOldDraftsAsync:
  if not AutoDeleteOld → return 0
  cutoff = UtcNow - RetentionMonths
  for each draft in GetAllDrafts:
    if IsAutosave → skip
    if LastModifiedAt >= cutoff → skip
    else delete file; count++
  if count > 0 → invalidate drafts cache
  return count
```

Chat [bfe03bf6](../chat-reviews/bfe03bf6-e707-4b67-bb29-017762d3a091.md) verdict:

- Method + tests shipped as scaffold for optional cleanup (DRAFT-14), **not** as an unfinished startup hook.
- Bare `Program.cs` one-liner without settings / warn / pin is exactly what DRAFT-08 blocked.
- v1 verification: “No auto-delete runs on startup.”

### Odysseus web (target today)

| Piece | Status |
|-------|--------|
| `integrations/sysforge/install.py` | mkdirs `drafts/`; default `config.json` has tax/currency/`autosave_drafts` only — **no** retention keys |
| Draft service / list / autosave APIs | **Missing** until `drafts-service-autosave` |
| Business settings UI | **Missing** until `business-settings-mvp` |
| Cleanup on plugin load | **Must stay absent** |

### Gap

Desktop already has the dangerous half (method + default `true`) and correctly refuses to wire it. Odysseus must:

1. Port the cleanup algorithm behind an API.
2. **Flip the default to OFF** (do not copy desktop `AutoDeleteOld = true`).
3. Add settings + notice (+ pin) before any scheduler/startup-adjacent trigger.
4. Never treat “method exists but unused” as a migration bug to “fix” with a silent boot hook.

---

## Scope

### In scope

- Config schema for plugin `config.json`:
  - `drafts.auto_delete_old` (bool, **default false**)
  - `drafts.retention_months` (int, default **6**, clamp e.g. 1–60)
  - Optional: `drafts.folder` override (only if drafts workstream already has it)
- Backend: `delete_old_drafts()` (or service method) mirroring desktop rules + **pin skip**.
- Preview endpoint: count how many drafts **would** be deleted under current settings (no writes).
- Execute endpoint: perform cleanup; return `{ deleted, skipped_pinned, skipped_autosave, retention_months, notice }`.
- Settings UI controls under Business settings → Drafts retention.
- Manual “Clean up now” with confirm when preview `would_delete > 0`.
- Non-blocking toast/banner after execute (and after scheduled run via notification).
- Optional Odysseus `TaskScheduler` job that calls execute **only if** `auto_delete_old` is true; job registration does not imply enable.
- Pin / keep-forever on named draft metadata (JSON field) so retention skips those files.
- Tests for default-off, gate, autosave exclusion, pin exclusion, no boot wiring.
- Docs note in plugin README / research: BUG-017-style “unwired” is deferred-by-design until this workstream.

### Out of scope

- Wiring cleanup on plugin install, `run_install`, app lifespan startup, or first `/api/sysforge/*` hit.
- Per-draft custom retention months (global policy only; pin is binary keep).
- Changing desktop SysForge defaults / wiring desktop startup (optional follow-up; this plan is Odysseus port).
- Full draft list / autosave / name dialog (owned by `drafts-service-autosave`).
- Backup retention days (separate Backup settings; do not conflate).
- Recycle bin / undo-delete for purged drafts (deleted files are gone; notice is informational).
- Multi-tenant per-owner draft isolation beyond whatever `drafts-service-autosave` already defines (reuse that boundary).

---

## Dependencies

| Depends on | Why |
|------------|-----|
| `drafts-service-autosave` | Needs draft file layout, list/load/delete primitives, `last_modified_at`, autosave flags, cache invalidation |
| `business-settings-mvp` | Surface for retention toggles + “Clean up now”; persists `config.json` |

| Soft / parallel | Why |
|-----------------|-----|
| Odysseus `TaskScheduler` (`src/task_scheduler.py`) | Optional scheduled purge; can ship manual-only first, then register a task |
| `diagnostics-readonly-panel` | Optional “last retention run” / draft count diagnostics; not required to ship |
| Desktop ConfigService default flip | Nice hygiene; not required for Odysseus success |

**Blocked by this workstream:** none for MVP shop flow. Retention is optional hygiene after drafts exist.

**Product conflict to resolve in step 1 (do not re-litigate forever):**

- Older draft-plan text: “global only, no `IsPinned`.”
- DRAFT-08 + MASTER + chat bfe03bf6: warn **and** optional pin before enabling auto-delete.

**Decision for this workstream:** include **pin** (binary). Global retention months still apply to unpinned drafts. Document the override of the “no pin” note as required by MASTER §4.

---

## Concrete steps

### 1. Freeze the safety contract (before code)

Write acceptance bullets into the ticket / this plan’s Tests section and treat them as blockers:

| Rule | Requirement |
|------|-------------|
| Default | `auto_delete_old = false` for new and missing-key configs |
| Boot | Zero calls from install, plugin activate, FastAPI startup, or module import |
| Gate | Execute path returns immediately when flag is false |
| Notice | UI (and scheduler notification) must show delete count when `deleted > 0` |
| Autosave | `autosave_1..3` / `is_autosave` never deleted by retention |
| Pin | Pinned named drafts never deleted by retention |
| Confirm | Manual run confirms when preview count &gt; 0 |

### 2. Extend plugin config (safe defaults)

Update `write_default_config()` / settings load merge:

```json
{
  "tax_rate_bps": 0,
  "currency": "USD",
  "autosave_drafts": true,
  "drafts": {
    "auto_delete_old": false,
    "retention_months": 6
  }
}
```

Loader rules:

- Missing `drafts` object → treat as defaults above.
- Missing `auto_delete_old` → **false** (do not inherit desktop `true`).
- `retention_months` clamp to `[1, 60]` on read and on save.
- Settings PUT merges without wiping unrelated keys.

### 3. Port cleanup logic into draft service

Add to the drafts service from `drafts-service-autosave`:

```text
preview_old_drafts() -> { would_delete, candidates[], retention_months, auto_delete_old }
delete_old_drafts(*, force: bool = false) -> result
```

Semantics:

- `preview_*` always works (read-only); shows what **would** happen if execute ran with current flag/months (still list candidates even when flag is false, so Settings can explain “N drafts older than X months” while toggle is off).
- `delete_old_drafts`:
  - If `auto_delete_old` is false and `force` is false → `{ deleted: 0, reason: "disabled" }` (no file IO deletes).
  - If true → delete eligible files; skip autosave + pinned; invalidate list cache.
- Do **not** expose `force=true` from the scheduled task. Reserve `force` only for an explicit Settings “Clean up now” path that already confirmed, **or** omit `force` entirely and require the toggle on for both manual and scheduled (preferred: **toggle must be on**; manual confirm is extra UX, not a bypass).

**Preferred product rule:** Manual “Clean up now” also requires `auto_delete_old == true`. That keeps one mental model: the setting is the master switch; the button runs cleanup now; the scheduler runs it later.

### 4. Add pin field on draft JSON

- Named drafts only: `"pinned": false` default.
- Drafts list UI: pin/unpin control (icon or menu).
- Retention skips `pinned == true`.
- Autosaves: no pin UI; already excluded.

### 5. API routes

Under `/api/sysforge/` (auth/owner scope same as other Business routes):

| Method | Path | Behavior |
|--------|------|----------|
| `GET` | `/drafts/retention` | Current settings + last_run metadata if stored |
| `PUT` | `/drafts/retention` | Update `auto_delete_old`, `retention_months` |
| `GET` | `/drafts/retention/preview` | Candidate count + sample names (cap list length) |
| `POST` | `/drafts/retention/cleanup` | Execute cleanup; require toggle on; return notice payload |
| `PATCH` | `/drafts/{id}/pin` | `{ "pinned": true\|false }` |

Reject any “run on startup” hook in `install.py`, `app.py` lifespan, or plugin `__init__`.

### 6. Settings UI

In Business settings (from `business-settings-mvp`), add a **Draft retention** group:

1. Checkbox: “Automatically delete old drafts” (bound to `auto_delete_old`, default unchecked).
2. Number: “Keep drafts for (months)” (enabled when checkbox on, or always editable for preview clarity).
3. Read-only line: “N drafts older than M months” from preview (refresh on open / after toggle).
4. Button: “Clean up now…” → confirm dialog: “Delete N drafts older than M months? Autosaves and pinned drafts are kept.” → POST cleanup → toast.
5. Helper text: “Off by default. Cleanup never runs when the app or plugin starts.”

Enabling the checkbox the first time:

- Show a one-shot warning: “Old unpinned drafts will be removable by cleanup / schedule. Pin drafts you want to keep.”
- Do not run cleanup on toggle alone.

### 7. Post-delete notice

After `deleted > 0`:

- In-app toast: “Removed {n} old draft(s) (older than {m} months).”
- If scheduled: use `TaskScheduler.add_notification(...)` with the same body so Activity / notification pop shows it.
- If `deleted == 0`: quiet success or subtle “Nothing to clean up” (no alarm).

Persist optional `drafts.last_cleanup_at` / `last_cleanup_deleted` in config or a tiny sidecar for Diagnostics; not required for MVP notice.

### 8. Optional scheduler wiring (same workstream or thin follow-up)

Only after settings + manual cleanup work:

1. Register a SysForge-owned task definition, e.g. weekly, calling `POST /drafts/retention/cleanup` (or internal service function) with plugin owner scope.
2. Task no-op success when toggle is off (`deleted: 0`, reason disabled) — **do not** fail the run.
3. Never auto-enable the task on install; either create disabled, or create enabled but rely on the toggle gate (prefer **task exists, gate in code** so mis-scheduled runs stay safe).

### 9. Explicit non-goals for “startup”

Code review checklist before merge:

```text
rg -n "delete_old_drafts|retention/cleanup|DeleteOldDrafts" integrations/sysforge app.py
```

Allowed hits: service, routes, settings JS, tests, scheduler task module.  
Forbidden: `install.py`, plugin load side effects, FastAPI `on_event("startup")` / lifespan without a settings-gated scheduler that still no-ops when OFF.

### 10. Align research / inventory wording

When shipping:

- Update `Sysforge research/features/draft-management.md` status from “wire optional cleanup job” to “optional; default off; settings + notice + pin.”
- Point BUG-017 / Partial rows at this issue id so future audits do not “fix” silent startup wiring.

---

## Files

### Create

| Path | Role |
|------|------|
| `integrations/sysforge/drafts_retention.py` (or methods on draft service module) | Preview + delete + pin helpers |
| `integrations/sysforge/static/js/settings_drafts_retention.js` (or section in settings module) | Settings controls + confirm + toast |
| `tests/test_sysforge_draft_retention.py` | Default-off, gate, autosave, pin, no-boot |

### Modify

| Path | Role |
|------|------|
| `integrations/sysforge/install.py` | Default config keys; **no** cleanup call |
| `integrations/sysforge/routes.py` (or drafts routes module) | Retention + pin endpoints |
| Draft service module from `drafts-service-autosave` | Cleanup + pin field on read/write |
| Business settings UI (`static/js/...`) | Retention group |
| Drafts list UI | Pin/unpin control |
| `integrations/sysforge/README.md` | Document safe defaults + DRAFT-08 contract |
| Optional: task registration module near host scheduler integration | Weekly cleanup task |

### Reference only (do not “fix” by wiring desktop)

| Path | Note |
|------|------|
| `SysForge/Services/DraftService.cs` `DeleteOldDraftsAsync` | Algorithm source |
| `SysForge/Services/ConfigService.cs` `DraftsConfig` | Field names; **do not copy default true** |
| `SysForge.Tests/Database/DraftServiceTests.cs` | Test matrix to mirror |
| `SysForge/Program.cs` / `App.axaml.cs` | Confirm still unwired; keep that way |

---

## API / UI contracts

### Config

```json
"drafts": {
  "auto_delete_old": false,
  "retention_months": 6,
  "last_cleanup_at": null,
  "last_cleanup_deleted": 0
}
```

### `GET /api/sysforge/drafts/retention`

```json
{
  "auto_delete_old": false,
  "retention_months": 6,
  "last_cleanup_at": null,
  "last_cleanup_deleted": 0
}
```

### `GET /api/sysforge/drafts/retention/preview`

```json
{
  "auto_delete_old": false,
  "retention_months": 6,
  "would_delete": 2,
  "candidates": [
    { "id": "...", "name": "Old estimate", "last_modified_at": "2025-10-01T12:00:00Z", "pinned": false }
  ],
  "skipped_pinned": 1,
  "skipped_autosave": 3
}
```

### `POST /api/sysforge/drafts/retention/cleanup`

Preconditions: `auto_delete_old === true`; otherwise `400` or `200` with `{ "deleted": 0, "reason": "disabled" }` (pick one; prefer **200 + reason** so scheduler stays green).

Success:

```json
{
  "deleted": 2,
  "skipped_pinned": 1,
  "skipped_autosave": 3,
  "retention_months": 6,
  "notice": "Removed 2 old draft(s) (older than 6 months)."
}
```

### `PATCH /api/sysforge/drafts/{id}/pin`

```json
{ "pinned": true }
```

Errors: 404 unknown id; 400 if target is autosave.

### UI binding

| Control | Binding |
|---------|---------|
| Auto-delete checkbox | `auto_delete_old` |
| Months input | `retention_months` |
| Preview label | `preview.would_delete` |
| Clean up now | confirm → `POST .../cleanup` → toast `notice` |
| Pin on row | `PATCH .../pin` |

---

## UX contracts

| Contract | Detail |
|----------|--------|
| Default off | New users never lose drafts without action |
| No silent boot purge | Plugin/app start never deletes |
| Settings before automation | Scheduler is useless without understanding the toggle |
| Confirm manual cleanup | Name the count and the month window |
| Notice after delete | Non-blocking; include count |
| Pin survives | Pinned drafts remain when cleanup runs |
| Autosaves untouched | Triple-buffer slots managed only by autosave/clear paths |
| Toggle ≠ run | Turning the setting on does not delete immediately |
| Disabled cleanup | Button disabled or explains “Turn on automatic deletion first” |

Copy guidance (short):

- Helper: “Off by default. Never runs when the plugin starts.”
- Confirm: “Delete {n} drafts older than {m} months? Pinned drafts and autosaves are kept.”
- Toast: “Removed {n} old draft(s) (older than {m} months).”

---

## Tests / verification

### Automated

| Test | Expect |
|------|--------|
| `test_default_config_auto_delete_off` | Fresh `write_default_config` → `auto_delete_old is False` |
| `test_missing_key_treated_as_off` | Config without key → cleanup deletes 0 |
| `test_cleanup_disabled_returns_zero` | Old files present; flag false → 0 deleted; files remain |
| `test_cleanup_enabled_deletes_old_named` | Flag true; 7-month-old named deleted; 1-month-old kept |
| `test_cleanup_skips_autosaves` | Old autosave files remain |
| `test_cleanup_skips_pinned` | Old pinned named draft remains |
| `test_preview_does_not_delete` | Preview leaves files intact |
| `test_pin_rejects_autosave` | 400 on autosave id |
| `test_no_cleanup_on_install` | `run_install` does not reduce draft file count |
| `test_retention_months_clamped` | 0 → 1; 999 → 60 (or chosen max) |

Mirror desktop cases from `DraftServiceTests` where applicable, with default-off as the Odysseus delta.

### Manual / QA

- [ ] Install plugin → open Settings → retention unchecked.
- [ ] Create old fixture drafts (or backdate `last_modified_at`) → Clean up now blocked or no-ops while off.
- [ ] Enable toggle → preview shows N → confirm → files gone → toast shown.
- [ ] Pin one old draft → cleanup → pinned remains.
- [ ] Restart app / reload plugin → draft counts unchanged without running cleanup.
- [ ] If scheduler registered: with toggle off, task run notifies 0 deleted and leaves files.

### Code search gate (CI or PR checklist)

```text
No delete_old_drafts / retention/cleanup call from install.py or app lifespan.
```

---

## Risks

| Risk | Mitigation |
|------|------------|
| Copying desktop `AutoDeleteOld = true` | Explicit default false + missing-key → false tests |
| “Helpful” startup wire during drafts port | Keep cleanup in this P2 workstream; drafts P1 checklist forbids boot purge |
| Scheduler runs before user understands setting | Gate in code; task may exist but no-ops when off; notice when deletes happen |
| Users lose work without pin | Ship pin with the feature; warn on first enable |
| Conflating backup retention days with draft months | Separate Settings group labels (“Draft retention (months)” vs “Backup retention (days)”) |
| Preview lists huge directories | Cap `candidates` array (e.g. 20) but return full `would_delete` count |
| Two browser tabs race on cleanup | Reuse drafts service file lock / single-writer from autosave workstream |
| Doc drift reopens BUG-017 as a bug | Point inventory at this issue; “deferred by design until safe defaults” |

---

## Effort

**M** (medium)

- Roughly 1–2 focused days after `drafts-service-autosave` + `business-settings-mvp` land.
- Breakdown: config + service port (**S**), settings UI + notice (**S**), pin field + list control (**S**), scheduler registration (**S** optional same PR or immediate follow-up).
- If scheduler is deferred, the manual path alone is closer to **S**, but the workstream goal includes safe automation, so track as **M**.

---

## Implementation order (checklist)

1. Config defaults + load merge (OFF).
2. Service preview/delete port (gate + autosave skip).
3. API routes + tests for gate/default.
4. Pin field + PATCH + skip in delete.
5. Settings UI + confirm + toast.
6. Drafts list pin control.
7. Optional TaskScheduler job (still gated).
8. Research/README wording update.
9. MASTER §6 QA tick: retention default off; no silent purge.
