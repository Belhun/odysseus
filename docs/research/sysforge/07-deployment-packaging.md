# Deployment and packaging

What happens when the user clicks **Install Business Management** in Odysseus Settings.

## User-facing experience

Settings → Integrations → Business Management:

1. Description: "Repair shop clients, invoices, parts, projects."
2. Button: **Install** (admin only).
3. Inline progress (not a file download):
   - Preparing plugin
   - Creating database
   - Enabling Business tool
4. Button changes to **Open Business**; sidebar item appears.

**No zip in Downloads. No terminal commands. No import step.**

## Plugin source layout (in main repo)

```
integrations/sysforge/
├── manifest.json
├── install.py
├── uninstall.py
├── services/sysforge/          # Python modules
├── routes/sysforge_routes.py   # FastAPI router
├── migrations/                 # 0002-0021 .sql (from SysForge)
├── static/
│   ├── js/sysforge/
│   └── css/sysforge.css
├── schemas/                    # JSON schemas for validation
└── assets/icons/
```

## manifest.json

```json
{
  "id": "sysforge",
  "name": "Business Management",
  "version": "1.0.0",
  "min_odysseus_version": "0.9.0",
  "requires": {
    "python": ">=3.11",
    "disk_mb": 100
  },
  "features": ["sysforge"],
  "install_entry": "install.py",
  "routes_prefix": "/api/sysforge"
}
```

For lean Docker images, CI may also publish a signed tarball to GitLab/GitHub releases. The **install API** fetches and extracts it server-side; users never interact with the artifact format.

## install.py responsibilities

1. Verify `DATA_DIR` writable and admin authorized
2. Create `data/plugins/sysforge/` tree
3. Run SQLite migrations on **new empty** `sysforge.db`
4. Write default `config.json` and empty `drafts/`
5. Write `installed.json` with version + timestamp
6. Set `features.sysforge = true` in `data/features.json`
7. Return report JSON for Settings UI progress steps

No .NET runtime. No desktop import.

## uninstall.py responsibilities

1. Set `features.sysforge = false`
2. Optionally archive `data/plugins/sysforge/` to `data/backups/sysforge-uninstall-{date}.tar.gz`
3. Remove `installed.json` (keep DB if user selects "keep data")

## Delivery modes

| Mode | When | Install behavior |
|------|------|------------------|
| **Bundled** (default) | Standard Docker / dev checkout | Run `integrations/sysforge/install.py` in place |
| **Lean image** | IT-focused minimal container | `POST /api/plugins/sysforge/install` fetches release artifact internally, then runs `install.py` |

Both modes expose the **same one-click UI**.

### Not the delivery model

| Avoid | Why |
|-------|-----|
| `GET /api/sysforge/addon.zip` for users | Manual download; Codex pattern is for external agents |
| curl + unzip in docs | Wrong UX for in-app Business tool |
| Import from desktop on install | No production SysForge data exists |

## Docker considerations

Base `docker-compose.yml` unchanged for MVP.

Optional `docker/sysforge.yml` overlay only if future deps need JVM (PyLucene) or OpenCV for screw maps. MVP uses Pillow + SQLite FTS5.

## Build pipeline

1. Plugin lives in `integrations/sysforge/` on main branch
2. CI (optional for lean images):
   - Package `integrations/sysforge/` → signed tarball
   - Attach to Odysseus release
   - Record SHA-256 in release notes
3. Install API verifies checksum when fetching lean-image artifact

## Versioning

- Plugin semver independent of Odysseus core
- `min_odysseus_version` in manifest guards incompatible API changes
- Upgrades run new SQL migrations on existing plugin DB (append-only migrations)

## Size estimate

| Component | Approx size |
|-----------|-------------|
| Python services | < 500 KB |
| JS UI | 200–800 KB |
| SQL migrations | < 50 KB |
| Icons/assets | < 2 MB |
| **Total plugin** | **< 5 MB** |

## Rollback

`install.py` backs up DB before migrate on **upgrade**. Admin can restore from `data/plugins/sysforge/backups/`.

## Security

- Install requires admin session
- Lean-image fetch: HTTPS + SHA-256 verify
- Extract only into `data/plugins/sysforge/`
- No executable binaries in plugin package

## What gets created at install (not shipped)

| Item | Created at install |
|------|-------------------|
| `sysforge.db` | Empty DB after migrations |
| `drafts/` | Empty folder |
| `config.json` | Defaults |
| User business data | Added through Business UI after install |
