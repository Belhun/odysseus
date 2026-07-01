# Frontend routing in Odysseus

How the SysForge Business Management section appears in Odysseus UI.

## Odysseus navigation model (today)

Main shell: `static/index.html`

```
#sidebar (left)
  ├── Chats section
  ├── Email
  ├── Tools section
  │     ├── tool-memory-btn
  │     ├── tool-calendar-btn
  │     ├── tool-compare-btn
  │     ├── tool-cookbook-btn
  │     ├── tool-research-btn
  │     ├── tool-gallery-btn
  │     ├── tool-library-btn
  │     ├── tool-notes-btn
  │     └── tool-tasks-btn
  └── sidebar-user-bar
#main content (chat, or tool overlay)
```

Tool buttons wire in `static/app.js` and individual `static/js/*.js` modules. Visibility gated in `static/js/init.js` via `privs` and feature flags from `/api/features`.

Settings modal uses tab routing: `.settings-nav-item[data-settings-tab="..."]` (`static/js/settings.js`).

## Proposed SysForge integration

### 1. Sidebar entry

Add to Tools section in `static/index.html`:

```html
<div class="list-item" id="tool-sysforge-btn" style="display:none">
  <!-- SysForge icon -->
  <span>Business</span>
</div>
```

Show when:

- `features.sysforge === true`
- `GET /api/sysforge/addon/status` returns `installed: true`

### 2. Panel container

Add overlay root (pattern matches cookbook/research panels):

```html
<div id="sysforge-panel" class="tool-panel sysforge-panel" hidden>
  <div class="sysforge-shell">
    <aside class="sysforge-sidebar">...</aside>
    <main class="sysforge-content" id="sysforge-content"></main>
  </div>
</div>
```

### 3. JS module structure (add-on bundle)

```
static/js/sysforge/
  index.js           # init, open/close panel
  router.js          # hash or path routing
  api.js             # fetch wrapper for /api/sysforge/*
  state.js           # lightweight store
  views/
    dashboard.js
    invoice-calculator.js
    client-dashboard.js
    invoice-edit.js
    invoice-viewer.js
    drafts.js
    placeholder-merge.js
    projects-hub.js
    work-order-detail.js
    screw-map.js
    settings.js
  components/
    toast.js
    modals.js
    data-grid.js
    client-search.js
```

Load via dynamic `import()` when add-on installed (keeps base bundle lean):

```javascript
// static/app.js or init hook
if (features.sysforge) {
  import('/static/js/sysforge/index.js').then(m => m.initSysForge());
}
```

### 4. Internal route table

Map SysForge `NavigationService` destinations:

| Route key | View | SysForge source |
|-----------|------|-----------------|
| `dashboard` | Dashboard cards | `DashboardViewModel` |
| `invoice-calculator` | Calculator | `InvoiceCalculatorViewModel` |
| `client-dashboard` | Client hub | `ClientDashboardViewModel` |
| `drafts` | Draft list | `DraftsViewModel` |
| `invoice-edit/:id` | Edit finalized | `InvoiceEditViewModel` |
| `invoice-view/:id` | Read-only viewer | `InvoiceViewerViewModel` |
| `placeholder-merge` | Merge UI | `PlaceholderMergeViewModel` |
| `projects` | Projects hub | `ProjectsHubViewModel` |
| `work-order/:id` | WO detail | `WorkOrderDetailViewModel` |
| `screw-map/:id` | Annotation | `ScrewMapViewModel` |
| `settings` | Business settings | `SettingsViewModel` |
| `diagnostics` | Admin diagnostics | `DiagnosticsViewModel` |

Router API:

```javascript
// router.js
export function navigate(route, params = {}) { ... }
export function back() { ... }  // NavigationHistory stack, max 20
```

Use hash routes (`#sysforge/invoice-calculator`) to avoid conflicting with Odysseus chat routing.

### 5. View cache

Port `ViewCache.cs` LRU (max 5): cache DOM subtrees or preloaded JS module state in `router.js` to speed navigation.

### 6. Settings integration

Add settings tab **Add-ons** or subsection under **Integrations**:

- Install / uninstall buttons
- Link to Business settings (tax rate, backup schedule)

Pattern: `INTG_TYPES` in `static/js/settings.js` — add `sysforge` type. Install UX matches Cookbook setup (one POST, progress in UI), not Codex curl+unzip.

### 7. Feature flag + UI visibility

Extend `DEFAULT_FEATURES` with `sysforge: false`.

Admin flow:

1. Install add-on → sets `installed.json`
2. Admin enables `sysforge` in features OR install auto-enables
3. `init.js` shows `tool-sysforge-btn`
4. Per-user UI toggle: `data-ui-key="tool-sysforge"` in appearance settings (optional)

### 8. Privileges

Extend server-side privilege map (like `can_use_research`) with `can_use_sysforge` — default admin + shop role.

### 9. Deep links

Support opening specific invoice from email tool future integration:

`/app#sysforge/invoice-view/123`

### 10. Mobile

Full-screen panel; collapse inner sidebar to hamburger on narrow viewports (match Odysseus `#mobile-menu-btn` behavior).

## Files to touch in main repo (minimal)

| File | Change |
|------|--------|
| `static/index.html` | Hidden sidebar button + panel shell (or load shell from add-on) |
| `static/app.js` | Hook to dynamic import |
| `static/js/init.js` | Privilege + visibility gate |
| `static/js/settings.js` | Add-on install UI |
| `src/settings.py` | `sysforge` feature flag |

Most UI lives in `integrations/sysforge/` and loads only after install.

## Reference implementations in Odysseus

| Tool | JS entry | Pattern to follow |
|------|----------|-------------------|
| Cookbook | `static/js/cookbook*.js` | Heavy tool panel, multi-step UI |
| Notes | `static/js/notes*.js` | CRUD list + editor |
| Calendar | `static/js/calendar.js` | Complex state, view switching |
| Email | email routes + UI | Sync jobs + inbox (relevant on email-sync branch) |

Cookbook is the closest analog for a large optional subsystem with background tasks.
