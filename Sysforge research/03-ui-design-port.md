# UI design port: SysForge → Odysseus

Preserve SysForge's repair-shop UX metaphors while fitting Odysseus's web design system.

## SysForge design system (source)

| Element | Implementation | Path |
|---------|----------------|------|
| Framework | Avalonia 11 Fluent theme | `SysForge/App.axaml` |
| Icons | Material.Icons.Avalonia | NuGet ref in `SysForge.csproj` |
| Layout | Collapsible left sidebar + content | `MainWindow.axaml` |
| Dashboard | WrapPanel card grid, favorites | `DashboardView.axaml`, `DashboardViewModel.cs` |
| Typography | Inter (Avalonia.Fonts.Inter) | csproj package |
| Colors/branding | Logo assets | `SysForge/Assets/Images/` |
| Toasts | Bottom-right notifications | `ToastService.cs` |
| Data grids | Avalonia DataGrid | Invoice/part lists |
| Dialogs | Modal windows | `*Dialog.axaml` files |

Reference docs:

- `SysForge/UI-Redesign-Complete-Documentation.md` — sidebar 250px expanded / 60px collapsed
- `SysForge/Main-Menu-UI-Plan.md`
- `Plans/UI-Plans/Future-UI-Features.md` — themes, shortcuts, user favorites (planned)

## Odysseus design system (target)

| Element | Implementation | Path |
|---------|----------------|------|
| Shell | Left sidebar + main content | `static/index.html` `#sidebar` |
| CSS variables | Theme tokens | `--sidebar-bg`, `--section-accent`, `--brand-color` |
| Tool panels | Full-screen overlays / sections | `tool-cookbook-btn`, `static/js/cookbook*.js` |
| Settings | Modal with left nav | `.settings-sidebar`, `.settings-nav-item` |
| Icons | Inline SVG in HTML/JS | Throughout `static/index.html` |
| Toasts | Existing notification patterns | Chat/status areas |
| Mobile | Hamburger, off-canvas sidebar | `#mobile-menu-btn`, `#hamburger-btn` |

## Mapping patterns

### Sidebar navigation

| SysForge | Odysseus port |
|----------|---------------|
| `NavigationItem` list in sidebar | New **Business** tool opens inner sidebar OR sub-nav strip inside panel |
| Collapse to icons-only | CSS class `sysforge-sidebar-collapsed`; persist in `localStorage` + user prefs |
| Settings gear at bottom | Link to Odysseus settings → SysForge tab (tax defaults, backup) |
| Back button + `NavigationHistory` | Browser-style back within `sysforge/router.js` stack |

**Recommendation:** Use a **dedicated full-height panel** (like Cookbook) with internal sidebar mirroring SysForge, rather than adding many items to main Odysseus sidebar.

### Dashboard cards

| SysForge | Odysseus port |
|----------|---------------|
| `DashboardCard` with `IsFavorite` | Card grid using Odysseus `.list-item` / custom `.sf-card` |
| Hardcoded favorites | Phase 1: same hardcoded set; Phase 2: user prefs API |
| Card click → navigate | `router.navigate('invoice-calculator')` |

Preserve card titles: Invoice Calculator, Client Dashboard, Drafts, Parts, Projects, Settings.

### Invoice calculator layout

SysForge uses dense desktop forms (client search, line items grid, tax/shipping toggles).

Port targets:

- Sticky header with client search (typeahead)
- Virtualized line items table (performance for long invoices)
- Footer totals bar (parts subtotal, labor, tax, shipping, total)
- Primary actions: Save, Save as draft, Finalize

Reference: `InvoiceCalculatorView.axaml`, `InvoiceCalculatorViewModel.cs` (~1000+ lines — extract pure calculation helpers for shared Python + JS tests).

### Client dashboard

- Master-detail: client header + invoice list + inline edit
- Search overlay pattern in sandbox: `Views/Sandbox/ClientSearchOverlayBar.axaml` — consider Odysseus command palette style (`static/js/slashCommands.js`)

### Dialogs

| SysForge dialog | Odysseus pattern |
|-----------------|------------------|
| `DraftNameDialog` | Modal component in `static/js/sysforge/modals.js` |
| `InvoiceNameDialog` | Same |
| `CreateProjectDialog` | Same |
| `ClientAcceptanceDialog` | Same |

Reuse Odysseus modal overlay CSS from settings modal.

### Screw map annotation

Desktop canvas control `ScrewMapImageCanvas.axaml` → HTML `<canvas>` or SVG overlay on `<img>`, similar to Odysseus image editor (`static/js/editor/`). Pinch/zoom on mobile is a plus over Avalonia.

## CSS strategy

1. Scope all SysForge styles under `.sysforge-panel` to avoid leaking into chat UI.
2. Map SysForge accent to `--section-accent` for theme continuity.
3. Port logo as `static/icons/sysforge-mark.png` (from `Assets/sysforge_transparent.png`).
4. Do not import Avalonia or Material Icons npm wholesale; copy needed SVGs only.

## Accessibility

- SysForge desktop: keyboard tab order in forms
- Odysseus: match `role="navigation"`, `aria-label` patterns from main sidebar
- Ensure calculator grid is keyboard-navigable (arrow keys between cells)

## Future UI backlog (defer)

From `Plans/UI-Plans/Future-UI-Features.md`:

- User-configurable dashboard favorites
- Global keyboard shortcuts
- Plugin system, themes, profiles
- Breadcrumbs, status bar

Document as Phase 2+; not required for MVP add-on.

## Assets to copy

| Source | Destination (add-on bundle) |
|--------|----------------------------|
| `SysForge/Assets/sysforge_transparent.png` | `static/icons/sysforge-mark.png` |
| `SysForge/Assets/Images/Navigation Icons/Sysforge Invoice Icon.png` | `static/icons/sysforge-invoice.png` |
| `SysForge-Logo.ico` | favicon optional |

## Effort

| Area | Estimate |
|------|----------|
| Shell + dashboard cards | M |
| Invoice calculator UI | L |
| Client dashboard UI | L |
| Edit/viewer/merge UIs | L |
| Projects + screw maps | XL |
| CSS theming integration | S |
