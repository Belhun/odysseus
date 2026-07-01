# Optional plugin architecture for SysForge in Odysseus

How Odysseus supports a **one-click optional plugin** for Business Management (SysForge port). The user never downloads or unzips anything manually.

## Design goals

1. **Lean base runtime** — SysForge code is not imported, routed, or served until install completes.
2. **One button** — Settings → Integrations → **Install Business Management** → progress → done.
3. **In main GitHub repo** — source under `integrations/sysforge/` for co-development; optional lean Docker images can omit the folder and fetch on install.
4. **Fresh start** — new empty DB on install; no desktop SysForge data import (project is unused in production).

## UX model (what the user sees)

Match Cookbook dependency install and remote setup, not the Codex agent curl+unzip flow:

| Pattern | User experience | Use for SysForge? |
|---------|-----------------|-------------------|
| Codex `plugin.zip` + terminal commands | Download zip, unzip, run scripts | **No** — too manual |
| Cookbook `/api/cookbook/setup` | Click Install → server runs steps → toast | **Yes** — same feel |
| Cookbook pip deps via `/api/model/serve` | Click Install → progress in UI | **Yes** — for optional Python deps |

**Target flow**

1. User opens Settings → Integrations.
2. Card: **Business Management** — "Clients, invoices, parts, projects for repair shops."
3. Button: **Install** (admin only).
4. UI shows progress: `Preparing…` → `Setting up database…` → `Enabling…` → `Ready`.
5. Sidebar shows **Business** tool; user opens it immediately.

No zip file in Downloads. No terminal. No import wizard.

## Existing Odysseus precedents

### 1. Feature flags (`src/settings.py`)

```python
DEFAULT_FEATURES = {
    "web_search": True,
    "gallery": True,
    "deep_research": False,
    ...
}
```

Add:

```python
"sysforge": False,  # default off; set true when plugin install completes
```

Flags load from `data/features.json` and gate UI in `static/js/init.js`.

### 2. Integrations folder (`integrations/`)

Codex and Claude live as source trees in the repo:

- `integrations/codex/` — scripts, skills, plugin metadata
- `integrations/claude/` — skills bundle

SysForge follows the same layout:

```
integrations/sysforge/
  manifest.json           # id, version, min_odysseus_version
  install.py              # idempotent setup (migrations, dirs)
  services/               # Python business logic
  routes/                 # FastAPI router
  migrations/             # 0002-0021 .sql from SysForge
  static/js/sysforge/     # UI panels
  static/css/sysforge.css
```

**Difference from Codex:** Codex zip is for *external* agents. SysForge is an *internal* Odysseus plugin activated in-process.

### 3. One-click server install (Cookbook reference)

`POST /api/cookbook/setup` (`routes/cookbook_routes.py`) + Settings UI in `static/js/cookbook-hwfit.js`:

- Client sends one POST
- Server runs SSH/setup steps
- Returns `{ ok: true, platform: "..." }`
- UI shows toast + updates button to "Done"

SysForge install API should mirror this shape:

```python
@router.post("/api/plugins/sysforge/install")
async def sysforge_install(request: Request):
    # admin check, then orchestrate install pipeline
    return {"ok": True, "version": "1.0.0", "steps": [...]}
```

### 4. Sidebar tools (`static/index.html`)

`tool-sysforge-btn` hidden until:

- `features.sysforge === true`, and
- `data/plugins/sysforge/installed.json` exists

Same gating as cookbook, notes, gallery (feature flags + privileges).

### 5. Conditional router mount (`app.py`)

At startup, check install marker before importing plugin code:

```python
def _maybe_mount_sysforge(app):
    installed = Path(DATA_DIR) / "plugins" / "sysforge" / "installed.json"
    if not installed.exists():
        return
    from integrations.sysforge.routes import router  # or dynamic path after copy
    app.include_router(router)
```

After first install, prompt for **one uvicorn reload** (or use plugin loader that registers routes without restart — harder).

### 6. Data directory (`docker-compose.yml` volume)

```
data/
  plugins/
    sysforge/
      installed.json       # version, installed_at, source
      sysforge.db          # fresh SQLite DB (created on install)
      config.json          # tax defaults, autosave, UI prefs
      drafts/              # empty JSON draft folder
      search/              # FTS index (built on first use)
      backups/
  features.json
```

## Install pipeline (server-side)

Single endpoint orchestrates everything. ZIP may be used **internally** by CI or lean Docker images; the user never handles it.

### Bundled install (default — full repo / standard Docker image)

Plugin source already on disk at `integrations/sysforge/`:

1. Verify admin session.
2. Run `integrations/sysforge/install.py`:
   - Create `data/plugins/sysforge/` dirs
   - Run SQL migrations on new `sysforge.db`
   - Write default `config.json`
   - Write `installed.json`
3. Set `features.sysforge = true` in `data/features.json`.
4. Return success + optional `reload_required: true`.

### Lean image install (optional — plugin not in container)

For images that exclude `integrations/sysforge/` to save size:

1. Server fetches plugin artifact from `SYSFORGE_PLUGIN_URL` (GitHub release, GitLab package registry).
2. Verifies SHA-256 from `manifest.json`.
3. Extracts to `data/plugins/sysforge/package/` (internal only).
4. Runs same `install.py` as bundled path.

User still clicks one button; download happens server-side.

## Uninstall

`POST /api/plugins/sysforge/uninstall` (admin, confirm dialog):

1. Set `features.sysforge = false`.
2. Optionally archive `data/plugins/sysforge/` to `data/backups/sysforge-{date}.tar.gz`.
3. Remove route registration on next reload.
4. Offer "keep business data" vs "remove everything".

## Main repo vs runtime load

| In GitHub repo | Loaded at Odysseus startup? |
|----------------|----------------------------|
| `integrations/sysforge/**` | **No** — until installed |
| `routes/plugin_routes.py` (registry + install API) | Yes — tiny stub |
| `src/plugins/registry.py` | Yes |
| Settings card (disabled state) | Yes |
| `sysforge: false` in defaults | Yes |
| `Sysforge research/` | N/A (docs only) |

Repo size includes plugin source for developers who want it. **Runtime bloat is zero** for users who never install.

## What we are NOT building

| Out of scope | Reason |
|--------------|--------|
| Desktop SysForge import wizard | No production data exists |
| User-facing zip download | Replaced by one-click install |
| Codex-style terminal setup | Wrong audience for in-app Business tool |
| Merging into core `core/database.py` | Keeps uninstall clean |

## Security

- Install/uninstall = **admin-only** (same as cookbook launch).
- Lean-image fetch: verify SHA-256; HTTPS only; pin version in manifest.
- Extract only under `data/plugins/sysforge/` (path traversal safe).
- All `/api/sysforge/*` routes require `require_user`; scope by Odysseus owner.

## Open decisions

1. **Reload policy** — require uvicorn restart after install vs hot-register routes?
2. **Multi-user** — shared shop DB vs per-user business data?
3. **Search** — SQLite FTS5 vs Odysseus embeddings for client search?
4. **Lean Docker** — ship bundled vs download-on-install for plugin bytes?

See [07-deployment-packaging.md](07-deployment-packaging.md) for plugin layout and CI notes.
