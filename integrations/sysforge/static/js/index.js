/**
 * SysForge Business Management — dashboard shell + inner router.
 * Domain modules (clients, calculator, drafts, parts) plug into named routes in P1.
 */

import { makeWindowDraggable } from '/static/js/windowDrag.js';
import * as router from './router.js';
import { normalizeRouteKey, parseHash, ROUTE } from './routes-contract.js';
import { sysforgeShortcutTarget } from './sysforge-shortcuts.js';
import { mountDashboard, activateDashboard } from './views/dashboard.js';
import { mountSettings, activateSettings } from './views/settings.js';
import {
  mountDiagnostics,
  activateDiagnostics,
  deactivateDiagnostics,
} from './views/diagnostics.js';
import { mountClients, activateClients, deactivateClients } from './views/clients.js';
import { mountPartsCatalog, activatePartsCatalog } from './views/parts-catalog.js';
import {
  mountPlaceholderMerge,
  activatePlaceholderMerge,
} from './views/placeholder-merge.js';
import {
  mountPartsTriage,
  activatePartsTriage,
} from './views/parts-triage.js';
import {
  mountSupplierDetail,
  activateSupplierDetail,
  deactivateSupplierDetail,
} from './views/supplier-detail.js';
import { mountDrafts, activateDrafts, deactivateDrafts } from './views/drafts.js';
import {
  mountCalculator,
  activateCalculator,
  deactivateCalculator,
} from './views/calculator.js';
import {
  mountInvoiceViewer,
  activateInvoiceViewer,
  deactivateInvoiceViewer,
} from './views/invoice-viewer.js';
import {
  mountOutstandingInvoices,
  activateOutstandingInvoices,
} from './views/outstanding-invoices.js';
import {
  mountSalesReport,
  activateSalesReport,
} from './views/sales-report.js';
import {
  mountClientMerge,
  activateClientMerge,
} from './views/client-merge.js';
import {
  mountClientDashboard,
  activateClientDashboard,
  deactivateClientDashboard,
} from './views/client-dashboard.js';
import {
  mountProjectsHub,
  activateProjectsHub,
  deactivateProjectsHub,
} from './views/projects-hub.js';
import {
  mountProjectDetail,
  activateProjectDetail,
  deactivateProjectDetail,
} from './views/project-detail.js';
import {
  mountScrewMapView,
  activateScrewMapView,
  deactivateScrewMapView,
} from './views/screw-map-view.js';

const API = `${window.location.origin}/api/sysforge`;
let _open = false;
let _modal = null;
let _shellReady = false;

function _el(id) {
  return document.getElementById(id);
}

function _ensureStyles() {
  if (!document.getElementById('sysforge-shell-css')) {
    const link = document.createElement('link');
    link.id = 'sysforge-shell-css';
    link.rel = 'stylesheet';
    link.href = '/static/plugins/sysforge/css/shell.css';
    document.head.appendChild(link);
  }
  if (!document.getElementById('sysforge-screw-map-css')) {
    const sm = document.createElement('link');
    sm.id = 'sysforge-screw-map-css';
    sm.rel = 'stylesheet';
    sm.href = '/static/plugins/sysforge/css/screw-map.css';
    document.head.appendChild(sm);
  }
}

function _errorMessage(data, status) {
  if (!data || typeof data !== 'object') {
    return `Request failed (${status})`;
  }
  if (data.code === 'sku_conflict') {
    const name = data.conflicting_part?.name || 'another part';
    return `SKU already exists on «${name}»`;
  }
  if (data.code === 'foreign_key') {
    return data.message || data.detail || 'Re-pick the part or fix the supplier.';
  }
  const detail = data.detail;
  if (typeof detail === 'string') return detail;
  if (detail && typeof detail === 'object') {
    if (detail.code === 'sku_conflict') {
      const name = detail.conflicting_part?.name || 'another part';
      return `SKU already exists on «${name}»`;
    }
    if (detail.code === 'foreign_key') {
      return detail.message || detail.detail || 'Re-pick the part or fix the supplier.';
    }
    if (typeof detail.message === 'string') return detail.message;
    if (typeof detail.detail === 'string') return detail.detail;
  }
  if (typeof data.message === 'string') return data.message;
  return `Request failed (${status})`;
}

async function _api(path, opts = {}) {
  const res = await fetch(`${API}${path}`, { credentials: 'same-origin', ...opts });
  if (res.status === 204) return {};
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    const err = new Error(_errorMessage(data, res.status));
    err.status = res.status;
    err.payload = data;
    throw err;
  }
  return data;
}

function _syncChrome(state) {
  const titleEl = _el('sysforge-view-title');
  if (titleEl) {
    const crumbs = typeof router.getBreadcrumb === 'function' ? router.getBreadcrumb() : null;
    titleEl.textContent =
      crumbs && crumbs.length > 1 ? crumbs.join(' › ') : state.title || 'Business Management';
  }
  const backBtn = _el('sysforge-back-btn');
  if (backBtn) {
    backBtn.disabled = !state.canGoBack;
  }
  document.querySelectorAll('.sysforge-nav-btn').forEach((btn) => {
    const route = btn.getAttribute('data-route');
    btn.classList.toggle(
      'is-active',
      normalizeRouteKey(route || '') === state.routeId
    );
  });
}

function _registerRoutes() {
  router.register('dashboard', {
    title: 'Shop home',
    mount: (el) =>
      mountDashboard(el, {
        navigate: (id) => router.navigate(id),
        api: _api,
      }),
    activate: (el) => activateDashboard(el),
  });

  // Canonical id is invoice-calculator; dashboard "calculator" alias still works.
  router.register('invoice-calculator', {
    title: 'Quick Invoice Calculator',
    mount: (el) =>
      mountCalculator(el, {
        api: _api,
        navigate: (id, opts) => router.navigate(id, opts),
        navigateAfterInvoiceSave: (clientId) => router.navigateAfterInvoiceSave(clientId),
        navigateToViewerAfterSaveAsNew: (invoiceId, clientId) =>
          router.navigateToViewerAfterSaveAsNew(invoiceId, clientId),
      }),
    activate: (el, params) => activateCalculator(el, params),
    deactivate: (el) => deactivateCalculator(el),
  });

  // View contract: read-only. Edit CTA → invoice-calculator?invoiceId=
  router.register('invoice-view', {
    title: 'Invoice',
    mount: (el) =>
      mountInvoiceViewer(el, {
        api: _api,
        navigate: (id, opts) => router.navigate(id, opts),
        navigateToInvoiceEdit: (invoiceId) =>
          router.navigateToInvoiceCalculatorEdit(invoiceId),
      }),
    activate: (el, params) => activateInvoiceViewer(el, params),
    deactivate: (el) => deactivateInvoiceViewer(el),
  });

  router.register(ROUTE.INVOICES_OUTSTANDING, {
    title: 'Outstanding invoices',
    mount: (el) =>
      mountOutstandingInvoices(el, {
        api: _api,
        navigate: (id, opts) => router.navigate(id, opts),
        navigateToInvoiceViewer: (invoiceId) =>
          router.navigateToInvoiceViewer(invoiceId),
      }),
    activate: (el) => activateOutstandingInvoices(el),
  });

  router.register(ROUTE.REPORTS_SALES, {
    title: 'Sales report',
    mount: (el) =>
      mountSalesReport(el, {
        api: _api,
        apiBase: API,
      }),
    activate: (el) => activateSalesReport(el),
  });

  router.register('clients', {
    title: 'Clients',
    mount: (el) =>
      mountClients(el, {
        api: _api,
        navigate: (id, opts) => router.navigate(id, opts),
      }),
    activate: (el) => activateClients(el),
    deactivate: (el) => deactivateClients(el),
  });

  router.register(ROUTE.CLIENT_MERGE, {
    title: 'Client merge',
    mount: (el) =>
      mountClientMerge(el, {
        api: _api,
        navigate: (id, opts) => router.navigate(id, opts),
      }),
    activate: (el) => activateClientMerge(el),
  });

  router.register(ROUTE.CLIENT_DASHBOARD, {
    title: 'Client Dashboard',
    mount: (el) =>
      mountClientDashboard(el, {
        api: _api,
        navigate: (id, opts) => router.navigate(id, opts),
        navigateToInvoiceViewer: (invoiceId) => router.navigateToInvoiceViewer(invoiceId),
        navigateToInvoiceEdit: (invoiceId) =>
          router.navigateToInvoiceCalculatorEdit(invoiceId),
        navigateToNewInvoice: (clientId) =>
          router.navigateToInvoiceCalculatorWithClient(clientId),
        apiBase: API,
      }),
    activate: (el, params) => activateClientDashboard(el, params),
    deactivate: (el) => deactivateClientDashboard(el),
  });

  router.register('drafts', {
    title: 'Drafts',
    mount: (el) =>
      mountDrafts(el, {
        api: _api,
        navigate: (id, opts) => router.navigate(id, opts),
      }),
    activate: (el) => activateDrafts(el),
    deactivate: (el) => deactivateDrafts(el),
  });

  router.register('parts', {
    title: 'Parts',
    mount: (el) => mountPartsCatalog(el, { api: _api, navigate: (id, opts) => router.navigate(id, opts) }),
    activate: (el) => activatePartsCatalog(el),
  });

  router.register(ROUTE.PARTS_TRIAGE, {
    title: 'Placeholder triage',
    mount: (el) =>
      mountPartsTriage(el, {
        api: _api,
        navigate: (id, opts) => router.navigate(id, opts),
      }),
    activate: (el) => activatePartsTriage(el),
  });

  router.register('placeholder-merge', {
    title: 'Placeholder Merge',
    mount: (el) => mountPlaceholderMerge(el, { api: _api }),
    activate: (el) => activatePlaceholderMerge(el),
  });

  router.register(ROUTE.SUPPLIER, {
    title: 'Supplier',
    mount: (el) =>
      mountSupplierDetail(el, {
        api: _api,
        navigate: (id, opts) => router.navigate(id, opts),
      }),
    activate: (el, params) =>
      activateSupplierDetail(
        el,
        { api: _api, navigate: (id, opts) => router.navigate(id, opts) },
        params
      ),
    deactivate: (el) => deactivateSupplierDetail(el),
  });

  router.register('settings', {
    title: 'Settings',
    mount: (el) => mountSettings(el, { api: _api }),
    activate: (el) => activateSettings(el),
  });

  router.register(ROUTE.DIAGNOSTICS, {
    title: 'Business Diagnostics',
    mount: (el) => mountDiagnostics(el, { api: _api }),
    activate: (el) => activateDiagnostics(el),
    deactivate: (el) => deactivateDiagnostics(el),
  });

  router.register(ROUTE.PROJECTS, {
    title: 'Projects',
    mount: (el) =>
      mountProjectsHub(el, {
        api: _api,
        navigate: (id, opts) => router.navigate(id, opts),
      }),
    activate: (el) => activateProjectsHub(el, { api: _api, navigate: (id, opts) => router.navigate(id, opts) }),
    deactivate: (el) => deactivateProjectsHub(el),
  });

  router.register(ROUTE.PROJECT, {
    title: 'Project',
    mount: (el) =>
      mountProjectDetail(el, {
        api: _api,
        navigate: (id, opts) => router.navigate(id, opts),
        navigateToInvoiceViewer: (invoiceId) => router.navigateToInvoiceViewer(invoiceId),
      }),
    activate: (el, params) =>
      activateProjectDetail(
        el,
        {
          api: _api,
          navigate: (id, opts) => router.navigate(id, opts),
          navigateToInvoiceViewer: (invoiceId) => router.navigateToInvoiceViewer(invoiceId),
        },
        params
      ),
    deactivate: (el) => deactivateProjectDetail(el),
  });

  router.register(ROUTE.SCREW_MAP, {
    title: 'Screw map',
    mount: (el) =>
      mountScrewMapView(el, {
        api: _api,
        apiBase: API,
        navigate: (id, opts) => router.navigate(id, opts),
      }),
    activate: (el, params) =>
      activateScrewMapView(
        el,
        {
          api: _api,
          apiBase: API,
          navigate: (id, opts) => router.navigate(id, opts),
        },
        params
      ),
    deactivate: (el) => deactivateScrewMapView(el),
  });
}

function _wireChrome() {
  _el('sysforge-close-btn')?.addEventListener('click', closeSysforge);
  _el('sysforge-back-btn')?.addEventListener('click', () => router.back());
  _el('sysforge-home-btn')?.addEventListener('click', () => router.goHome());
  document.querySelectorAll('.sysforge-nav-btn').forEach((btn) => {
    btn.addEventListener('click', () => {
      const route = btn.getAttribute('data-route');
      if (!route) return;
      if (route === 'dashboard') {
        router.goHome();
      } else {
        router.navigate(route);
      }
    });
  });
  _modal?.addEventListener('click', (e) => {
    if (e.target === _modal) closeSysforge();
  });
}

function _getModal() {
  if (_modal) return _modal;
  _ensureStyles();
  _modal = document.createElement('div');
  _modal.id = 'sysforge-modal';
  _modal.className = 'modal';
  _modal.innerHTML = `
    <div class="modal-content sysforge-modal-content">
      <div class="modal-header">
        <h2 style="margin:0;font-size:1.1rem;">Business Management</h2>
        <button type="button" class="modal-close" id="sysforge-close-btn" aria-label="Close">&times;</button>
      </div>
      <div class="sysforge-chrome">
        <h3 class="sysforge-chrome-title" id="sysforge-view-title">Shop home</h3>
        <div class="sysforge-chrome-actions">
          <button type="button" class="btn-secondary" id="sysforge-back-btn" aria-label="Back" disabled>Back</button>
          <button type="button" class="btn-secondary" id="sysforge-home-btn" aria-label="Dashboard">Home</button>
        </div>
      </div>
      <div class="sysforge-body">
        <nav class="sysforge-nav" aria-label="Business modules">
          <button type="button" class="sysforge-nav-btn" data-route="dashboard">Dashboard</button>
          <button type="button" class="sysforge-nav-btn" data-route="calculator">Calculator</button>
          <button type="button" class="sysforge-nav-btn" data-route="client-dashboard">Clients</button>
          <button type="button" class="sysforge-nav-btn" data-route="clients">All clients</button>
          <button type="button" class="sysforge-nav-btn" data-route="client-merge">Client merge</button>
          <button type="button" class="sysforge-nav-btn" data-route="invoices-outstanding">Outstanding</button>
          <button type="button" class="sysforge-nav-btn" data-route="reports-sales">Reports</button>
          <button type="button" class="sysforge-nav-btn" data-route="drafts">Drafts</button>
          <button type="button" class="sysforge-nav-btn" data-route="parts">Parts</button>
          <button type="button" class="sysforge-nav-btn" data-route="parts-triage">Triage</button>
          <button type="button" class="sysforge-nav-btn" data-route="placeholder-merge">Merge</button>
          <button type="button" class="sysforge-nav-btn" data-route="settings">Settings</button>
          <button type="button" class="sysforge-nav-btn" data-route="diagnostics">Diagnostics</button>
        </nav>
        <div id="sysforge-view-host"></div>
      </div>
      <div class="sysforge-footer" id="sysforge-status">Loading status…</div>
    </div>`;
  document.body.appendChild(_modal);
  const content = _modal.querySelector('.sysforge-modal-content');
  const header = _modal.querySelector('.modal-header');
  if (content && header) {
    makeWindowDraggable(_modal, {
      content,
      header,
      skipSelector: 'button, input, select, textarea, label',
    });
  }
  _wireChrome();
  return _modal;
}

function _initShell() {
  if (_shellReady) return;
  const host = _modal?.querySelector('#sysforge-view-host') || _el('sysforge-view-host');
  if (!host) return;
  _registerRoutes();
  router.mount(host, { onChange: _syncChrome });
  router.startHashListener();
  // Deep link: #sysforge/... opens that route; else dashboard.
  const hash = typeof window !== 'undefined' ? window.location.hash : '';
  if (parseHash(hash)) {
    if (!router.applyFromHash(hash)) {
      router.navigate(ROUTE.DASHBOARD, { replace: true });
    }
  } else {
    router.navigate(ROUTE.DASHBOARD, { replace: true });
  }
  _shellReady = true;
}

async function _loadStatus() {
  const statusEl = _el('sysforge-status');
  try {
    const data = await _api('/status');
    const schema = data.schema || {};
    const parts = [];
    if (data.version) parts.push(`v${data.version}`);
    if (schema.latest_id != null) {
      parts.push(`schema ${String(schema.latest_id).padStart(4, '0')}`);
    }
    if (statusEl) {
      statusEl.textContent = parts.length
        ? `Installed ${parts.join(' · ')}`
        : 'Installed and active';
    }
  } catch (err) {
    if (statusEl) statusEl.textContent = err.message || String(err);
  }
}

export function isSysforgeOpen() {
  return _open;
}

/** True when host feature flag allows Business (button may still be hidden). */
export function isSysforgeFeatureOn() {
  if (typeof window !== 'undefined' && window._pluginFeaturesOff?.has('sysforge')) {
    return false;
  }
  return true;
}

/**
 * Host shortcut target for in-Business actions (pure; used by tests).
 * @param {string} action
 * @returns {{ kind: 'home' } | { kind: 'navigate', routeId: string } | null}
 */
export { sysforgeShortcutTarget } from './sysforge-shortcuts.js';

/**
 * Run a host-registered in-Business shortcut. Opens Business if closed.
 * No-ops when the plugin feature is off. Does not use a plugin-local keybind store.
 * @param {string} action
 * @returns {Promise<boolean>}
 */
export async function runSysforgeShortcut(action) {
  const target = sysforgeShortcutTarget(action);
  if (!target) return false;
  if (!isSysforgeFeatureOn()) return false;

  if (!_open) {
    await openSysforge();
  }
  if (target.kind === 'home') {
    router.goHome();
    return true;
  }
  router.navigate(target.routeId);
  return true;
}

export async function openSysforge() {
  _getModal();
  _open = true;
  _modal.style.display = 'flex';
  if (!_shellReady) {
    _initShell();
  } else {
    // Keep cache/stack across close/reopen (P0 policy).
    router.activateCurrent();
  }
  await _loadStatus();
  const Modals = await import('/static/js/modalManager.js');
  Modals.register('sysforge-modal', {
    railBtnId: 'rail-sysforge',
    sidebarBtnId: 'tool-sysforge-btn',
    closeFn: () => closeSysforge(),
    restoreFn: () => {
      if (_shellReady) router.activateCurrent();
    },
  });
}

export function closeSysforge() {
  _open = false;
  router.deactivateCurrent();
  if (_modal) _modal.style.display = 'none';
}

export default {
  openSysforge,
  closeSysforge,
  isSysforgeOpen,
  isSysforgeFeatureOn,
  sysforgeShortcutTarget,
  runSysforgeShortcut,
};
