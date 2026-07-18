# Business settings UI (tax / currency / autosave)

| Field | Value |
|-------|-------|
| **Issue id** | `business-settings-mvp` |
| **Title** | Business settings UI (tax/currency/autosave) |
| **Phase** | **P1** (MASTER §5 Phase 1 — Invoice MVP) |
| **Priority** | high |
| **Domain** | settings |
| **Effort** | **S** |
| **Depends on** | `business-shell-dashboard-router` |
| **Sources** | gap-manifest · MASTER §5 Phase 1 / §2.9 · feature-gap-matrix §1 Settings window + §8 Config.json · future-plans-roadmap §3 Phase 1 · `Sysforge research/features/settings-backup.md` · SysForge `ConfigService` / `SettingsViewModel` / `SettingsWindow` · `integrations/sysforge/install.py` |

**Constraint for this doc:** planning only. No product code changes in this workstream write-up.

---

## Goal / success

Give installed Business Management users an in-app Settings surface for the three daily knobs already written to plugin `config.json` on install: **tax rate**, **currency**, and **draft autosave**. After this ships, shop techs never hand-edit JSON for those values.

### Success criteria (exit)

1. With the plugin installed and active, Business shell exposes a **Settings** view (card, sidebar item, or gear) that loads current plugin config.
2. User can change **tax** (shown as percent), **currency** (ISO code), and **autosave drafts** (on/off); Save persists to `data/plugins/sysforge/config.json`.
3. `GET` / `PUT` (or `PATCH`) under `/api/sysforge/settings` work when the plugin is active; return **404** when inactive (same gate as `/api/sysforge/status`).
4. Validation rejects out-of-range tax and bad currency; UI shows an inline error; file on disk is unchanged on failed PUT.
5. Calculator / drafts consumers can read the same config helper (or GET response) and pick up saved tax + autosave without a server restart.
6. Odysseus global Settings (`/api/auth/settings`, `data/settings.json`) stays untouched; Business config stays under the plugin data dir.
7. Automated tests cover install defaults, GET/PUT round-trip, validation, and inactive-plugin 404. Manual check: change tax → open new calculator → default tax matches.

---

## Current state

### SysForge desktop (source of truth)

| Piece | Status | Notes |
|-------|--------|-------|
| `ConfigService` + `config.json` | Done | `Defaults.TaxRate` (percent, default `7.75`), `Defaults.ShippingRate`, `Autosave.Enabled` / `IntervalSeconds`, `Drafts.*`, backup, paths, UI window state |
| `SettingsService` | Done | Maps config ↔ `Settings` model; `GetSettings` / `UpdateSettings` |
| `SettingsWindow` / `SettingsViewModel` | Done | Tax % + shipping $ + paths + backup expander; Save / Apply / Cancel; tax range **0–100** |
| Invoice calculator | Done | New invoice loads `settings.TaxRate` from `SettingsService.GetSettings()` (`InvoiceCalculatorViewModel` ~1191) |
| Money storage | Done | Invoices store `TaxRateBasisPoints`; `MoneyHelpers.ToBasisPoints(7.75)` → `775` |

Desktop Settings is a full window (shipping, index path, DB path, backup). Odysseus P1 MVP is intentionally smaller: tax / currency / autosave only (MASTER exit: “No hand-editing JSON for daily use”).

### odysseus-sysforge today

| Piece | Status |
|-------|--------|
| Install pipeline | `write_default_config()` writes once if missing: `{ "tax_rate_bps": 0, "currency": "USD", "autosave_drafts": true }` under `plugin_data_dir("sysforge") / config.json` |
| Plugin routes | `/api/sysforge/status` only (`integrations/sysforge/routes.py`) |
| Business UI | Stub modal in `integrations/sysforge/static/js/index.js` — status text; no Settings form |
| Host settings | Rich modal + `/api/auth/settings` GET/POST in `static/js/settings.js` / `routes/auth_routes.py`; Integrations Install/Uninstall for plugins |
| Money helpers | Not ported yet (`schema-money-utc-foundation`); plan assumes bps helpers land with P0 or a tiny local convert in this workstream |

**Verdict (matrix §1 / ease-of-use #4):** Config without UI. Defaults exist on disk; users cannot change them in-app.

### Config shape mismatch to resolve in this workstream

| Concern | Desktop | Odysseus install default | MVP decision |
|---------|---------|--------------------------|--------------|
| Tax storage | Percent in config (`7.75`); bps on invoices | `tax_rate_bps` integer (`0`) | **Keep `tax_rate_bps` on disk** (aligns with invoice DB). UI edits percent; API accepts either percent (UI) or bps (internal) — see contracts |
| Default tax | `7.75%` → 775 bps | `0` | Prefer **775** on fresh install going forward; migrate existing `0` only if product wants desktop parity (document in steps) |
| Currency | Not a first-class desktop setting today | `"USD"` | Keep; web needs explicit currency for money display |
| Autosave | `Autosave.Enabled` + interval seconds | `autosave_drafts: true` | Keep boolean for MVP; interval deferred |
| Shipping | `Defaults.ShippingRate` in Settings UI | Absent | **Out of MVP** (add later or with calculator) |

---

## Scope

### In scope

- Plugin config module: load / save / validate `data/plugins/sysforge/config.json` (merge missing keys with defaults; never wipe unknown future keys).
- REST: `GET` + `PUT` `/api/sysforge/settings` behind `_require_sysforge_plugin`.
- Business Settings view inside the plugin shell (route e.g. `#sysforge/settings` or Settings card on dashboard).
- Fields: tax (percent UX ↔ `tax_rate_bps`), `currency`, `autosave_drafts`.
- Save / Cancel (or Save + revert) with toast via existing `uiModule.showToast`.
- Tests in `tests/test_sysforge_plugin.py` (or sibling) for API + config helper.
- Align `write_default_config()` defaults with the validated schema (document tax default choice).
- Thin read helper other modules call (e.g. `integrations/sysforge/config.py::load_business_config()`).

### Out of scope

- Backup / restore / scheduled backups / export JSON (→ `backup-restore-post-import-reindex`, P2; Settings UI will grow a Backup section later).
- Shipping rate, include-tax toggles, draft retention (`draft-retention-draft-08`), custom drafts folder, DB/index paths, window state, theme.
- Odysseus global Settings tabs, Integrations card redesign, or writing Business keys into `data/settings.json`.
- Multi-rate tax jurisdictions (roadmap deferred).
- Autosave debounce / lock / flush (→ `drafts-service-autosave`); this workstream only persists the **flag**.
- Calculator tax wiring end-to-end if calculator is not ready; still ship config API + UI, and a one-line “consumer hook” note for the calculator workstream.

---

## Dependencies

| Depends on | Why |
|------------|-----|
| `business-shell-dashboard-router` | Settings needs a real Business panel route / card, not the status stub |

| Soft / parallel | Why |
|-----------------|-----|
| `schema-money-utc-foundation` | Prefer shared `to_basis_points` / `from_basis_points`; if P0 lags, ship local convert matching `MoneyHelpers` (percent × 100, AwayFromZero) |
| `drafts-service-autosave` | Reads `autosave_drafts`; settings can land first with flag unused until drafts wires it |
| `invoice-calculator-save-contracts` | New invoices should seed tax from `tax_rate_bps`; calculator workstream owns the call site |
| Admin-auth pattern from Odysseus | Mirror who may mutate plugin config (recommend: same session rules as other `/api/sysforge/*`; if multi-user later, admin-only write) |

| Downstream | Why |
|------------|-----|
| `backup-restore-post-import-reindex` | Backup UI mounts under Business Settings |
| `draft-retention-draft-08` | Manifest depends on this + drafts |

---

## Concrete steps

### 1. Freeze the config schema

Document and code the canonical file:

```json
{
  "tax_rate_bps": 775,
  "currency": "USD",
  "autosave_drafts": true
}
```

Rules:

- `tax_rate_bps`: int, **0–10000** (0%–100.00%).
- `currency`: 3-letter uppercase ISO 4217 string; MVP allowlist at least `USD` (expandable list in UI).
- `autosave_drafts`: bool.
- On load: if file missing, write defaults (same as install). If file exists with partial keys, fill missing from defaults; preserve unknown keys on save.
- Decide default tax: **recommend 775** to match desktop `7.75%`; keep install idempotent (`write_default_config` still “write only if missing”).

### 2. Add `integrations/sysforge/config.py`

- `DEFAULTS` dict matching schema.
- `config_path() -> Path` via `plugin_data_dir("sysforge") / "config.json"`.
- `load_config() -> dict` (read + merge defaults).
- `save_config(partial: dict) -> dict` (validate → merge → atomic write: write temp + replace).
- `tax_percent_from_bps(bps) -> float` / `tax_bps_from_percent(percent) -> int` matching desktop `MoneyHelpers` (round AwayFromZero / Python `decimal` with `ROUND_HALF_UP` equivalent — match P0 helper if present).

### 3. Extend plugin routes

In `integrations/sysforge/routes.py` (or `routes/settings.py` included by setup):

- `GET /api/sysforge/settings` → `{ ok, tax_rate_bps, tax_rate_percent, currency, autosave_drafts }` (percent is derived for UI convenience).
- `PUT /api/sysforge/settings` → body may send `tax_rate_percent` **or** `tax_rate_bps` (prefer one; reject if both disagree), plus `currency`, `autosave_drafts`.
- 400 on validation failure with `{ detail: "..." }`.
- 404 when plugin inactive.

Do **not** put these keys on `/api/auth/settings`.

### 4. Wire Settings into the Business shell

After `business-shell-dashboard-router`:

- Register route `settings` (e.g. `#sysforge/settings`).
- Dashboard card or sidebar label: **Settings**.
- View module (suggested): `integrations/sysforge/static/js/views/settings.js` (or `static/js/sysforge/views/settings.js` if shell moved).

UI fields:

| Control | Binding | Notes |
|---------|---------|-------|
| Tax rate (%) | number / text | Show percent; watermark e.g. `7.75`; help: “Stored as basis points” |
| Currency | select | Start with USD; add CAD/EUR/GBP only if needed |
| Autosave drafts | checkbox | Label: “Automatically save invoice calculator drafts” |

Actions: **Save** (PUT + toast), **Cancel** (reload from GET / revert dirty state). Optional: disable Save when clean.

Reuse Odysseus patterns from `settings.js`: `fetch(..., { credentials: 'same-origin' })`, JSON body, toast on success/error. Prefer explicit Save over per-field autosave for this form (matches desktop Save/Apply, avoids partial writes).

### 5. Consumer hooks (minimal)

- Export `load_config` for Python services.
- Document JS: calculator opens → `GET /api/sysforge/settings` once (or shell state store) → set default tax percent from `tax_rate_percent`; respect `autosave_drafts` when drafts workstream lands.
- No need to push into Odysseus `DEFAULT_SETTINGS`.

### 6. Align install defaults

Update `write_default_config()` in `install.py` to the frozen schema (tax default decision from step 1). Re-run install tests; ensure “already installed” path does not overwrite user config.

### 7. Tests + manual verification

See Tests / verification below. Land tests in the same PR as the API.

### 8. Stop conditions for this workstream

Stop when exit criteria 1–7 pass. Do not start backup UI, shipping, or retention controls here.

---

## Files

| Path | Action |
|------|--------|
| `integrations/sysforge/config.py` | **Create** — load/save/validate/helpers |
| `integrations/sysforge/routes.py` | **Edit** — register GET/PUT settings |
| `integrations/sysforge/install.py` | **Edit** — align default `config.json` |
| `integrations/sysforge/static/js/index.js` (or shell router) | **Edit** — register Settings route / card |
| `integrations/sysforge/static/js/views/settings.js` | **Create** — form UI |
| `integrations/sysforge/README.md` | **Edit** — document config path + API |
| `tests/test_sysforge_plugin.py` (or `tests/test_sysforge_settings.py`) | **Edit/Create** — API + config tests |
| `docs/migration-audit/gap-plans/business-settings-mvp.md` | This plan (done) |

Reference only (do not port wholesale):

- `SysForge/Services/ConfigService.cs` (`DefaultsConfig`, `AutosaveConfig`)
- `SysForge/ViewModels/SettingsViewModel.cs` (validation 0–100%, Save/Cancel)
- `SysForge/Views/SettingsWindow.axaml`
- `SysForge/Helpers/MoneyHelpers.cs` (bps convert)
- `static/js/settings.js` (fetch/toast patterns; Integrations install stays separate)
- `Sysforge research/features/settings-backup.md`

---

## API / UI contracts

### `GET /api/sysforge/settings`

**Auth / gate:** plugin active (`is_plugin_active("sysforge")`); otherwise 404.

**200 body (example):**

```json
{
  "ok": true,
  "tax_rate_bps": 775,
  "tax_rate_percent": 7.75,
  "currency": "USD",
  "autosave_drafts": true
}
```

### `PUT /api/sysforge/settings`

**Body (example):**

```json
{
  "tax_rate_percent": 8.25,
  "currency": "USD",
  "autosave_drafts": false
}
```

**Rules:**

- Prefer `tax_rate_percent` from the UI. Server converts with `tax_bps_from_percent` and stores `tax_rate_bps`.
- If only `tax_rate_bps` is sent, accept and derive percent for the response.
- If both sent, they must round-trip equal or return 400.
- Omit keys = leave unchanged (partial update).
- Response = full config same shape as GET.

**Errors:**

| Status | When |
|--------|------|
| 404 | Plugin not installed / feature off |
| 400 | Tax out of range, currency not 3-letter, non-bool autosave, JSON not object |
| 403 | If you later require admin; MVP may allow any authenticated Odysseus user who can open Business |

### File contract

- Path: `{DATA_DIR}/plugins/sysforge/config.json`
- Encoding: UTF-8 JSON, indent 2
- Atomic replace on save
- Unknown keys preserved for forward compatibility

### Shell / UI contract

- Route id: `settings` (hash `#sysforge/settings` once router exists)
- Opening Settings does not tear down other panel subscriptions (follow `nav-lifecycle-view-edit-routes` same-panel rules when that lands)
- Dirty form: Cancel restores last loaded values; navigating away with dirty state — prompt or silent discard (pick one; recommend discard + toast only if Save failed)

---

## UX contracts

1. **Separation:** Business Settings live inside the Business panel. Odysseus Settings → Integrations remains install/uninstall only (research: two config systems, clear UX separation).
2. **Tax UX:** Humans edit **percent** (0–100). Never show raw bps as the primary field; optional small helper text “775 basis points” after save is fine.
3. **Desktop parity (subset):** Save commits; Cancel reverts. No Apply-without-close required for web modal.
4. **Feedback:** Success toast “Business settings saved”; failure toast with server `detail`.
5. **Empty / first run:** Form shows defaults even if file was just created by install.
6. **Currency:** Changing currency in MVP updates display defaults only; do not rewrite historical invoice cents (invoices stay integer money; currency is a presentation default).
7. **Autosave label:** Clear that it applies to **invoice calculator drafts**, not Odysseus notes/docs autosave.

---

## Tests / verification

### Automated

| Test | Expect |
|------|--------|
| Install writes config | After `run_install`, `config.json` exists with schema keys |
| Install idempotent | Second install does not overwrite edited tax |
| GET settings | 200 + defaults when active |
| GET when inactive | 404 |
| PUT percent → bps | `7.75` → `tax_rate_bps == 775`; file updated |
| PUT validation | `tax_rate_percent: 101` → 400; file unchanged |
| PUT currency | `"usd"` normalized to `"USD"` (or reject lowercase — pick one and test it) |
| PUT autosave | `false` persists; GET returns false |
| Partial PUT | Sending only `autosave_drafts` leaves tax/currency intact |
| Preserve unknown keys | File with `"future_flag": true` survives save |

### Manual

1. Install Business Management from Settings → Integrations.
2. Open Business → Settings; confirm defaults.
3. Set tax to `7.75`, currency USD, autosave on → Save → reload page → values stick.
4. Set tax to `-1` or `101` → see error; disk unchanged.
5. Uninstall (keep data) → `/api/sysforge/settings` 404; reinstall without wiping data → prior config still loads if file kept.
6. When calculator exists: new invoice default tax matches saved percent.

---

## Risks

| Risk | Mitigation |
|------|------------|
| Dual config confusion (Odysseus vs plugin) | Keep API under `/api/sysforge/*`; never merge into `settings.json`; README + Integrations copy stays “Install only” |
| Tax percent vs bps off-by-100 bugs | Shared helper + table-driven tests (`7.75↔775`, `0↔0`, `100↔10000`) |
| Default `0` vs desktop `7.75` surprises shops | Prefer default **775** on new installs; document in README |
| Settings UI blocked on shell workstream | Hard depend on dashboard router; can stub route early behind feature flag for API-first |
| Autosave flag ignored until drafts land | Acceptable; document soft dependency; drafts workstream must read the flag |
| Concurrent writes | Atomic replace; single-user MVP; later add simple file lock if needed |
| Multi-user auth | Solo Odysseus today; if shared host, tighten PUT to admin before exposing |

---

## Effort

**S** (small).

Rough shape: one config module, two routes, one settings view, install default tweak, ~8–12 tests. No backup, no shipping, no DB migrations.

If shell routing is unfinished and this workstream also builds temporary navigation chrome, treat that overflow as part of `business-shell-dashboard-router`, not a scope creep here.

---

## Implementation order (checklist)

- [ ] Freeze schema + default tax decision (775 vs 0)
- [ ] `config.py` load/save/validate + bps helpers
- [ ] GET/PUT `/api/sysforge/settings`
- [ ] Align `install.py` defaults
- [ ] Settings view + shell route/card
- [ ] Tests (API + file semantics)
- [ ] Manual walkthrough
- [ ] README note for consumers (calculator / drafts)

**Exit quote (MASTER Phase 1):** Minimal Business settings (tax/currency/autosave) — *No hand-editing JSON for daily use.*
