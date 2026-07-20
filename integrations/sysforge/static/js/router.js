/**
 * Business Management inner router: navigate / back / apply / LRU cache / hash.
 *
 * applyNavigation identity rule (desktop CurrentView / chat 014ea2dd):
 * Only deactivate + unbind when the panel controller identity changes.
 * Same-surface re-apply (ViewChanged + openPanel duplicate) must NOT tear down
 * live handlers (dashboard cards, View/Edit). See state-and-event-lifecycle.mdc.
 *
 * Invoice return-context (BUG-008 / chats 21972123, 67a4ed8b):
 * Capture origin when leaving Classic → viewer/calculator; Viewer Edit must not
 * overwrite; trim invoice-flow history before save-as-new viewer / after-save return.
 */

import {
  ROUTE,
  buildHash,
  isInvoiceFlowRoute,
  normalizeParams,
  normalizeRouteKey,
  parseHash,
  panelCacheKey,
  shallowEqualParams,
} from './routes-contract.js';
import { isSameSurface, makeSurface, shouldUnbindShellHandlers } from './panel-lifecycle.js';
import * as returnContext from './invoice-return-context.js';

const MAX_CACHE = 5;
const MAX_HISTORY = 20;

/** @typedef {{ title: string, mount: Function, activate?: Function, deactivate?: Function }} RouteDef */

/** @type {Map<string, RouteDef>} */
const _routes = new Map();

/** @type {Map<string, { el: HTMLElement, lastUsed: number, routeKey: string }>} */
const _cache = new Map();

/** @type {{ routeKey: string, params: Record<string, string>, cacheKey: string }[]} */
let _history = [];

/** @type {{ routeKey: string, params: Record<string, string>, cacheKey: string, controller: HTMLElement } | null} */
let _current = null;

/** @type {HTMLElement | null} */
let _host = null;

/** @type {((state: object) => void) | null} */
let _onChange = null;

/** @type {((surface: object|null) => void) | null} */
let _onShellBind = null;

/** @type {((surface: object|null) => void) | null} */
let _onShellUnbind = null;

let _clock = 0;
let _hashSyncEnabled = true;
let _applyingHash = false;
let _hashListener = null;

function _emit() {
  if (typeof _onChange === 'function') {
    _onChange(getState());
  }
}

function _touch(cacheKey) {
  const entry = _cache.get(cacheKey);
  if (entry) entry.lastUsed = ++_clock;
}

function _evictIfNeeded() {
  while (_cache.size > MAX_CACHE) {
    let oldestId = null;
    let oldestTs = Infinity;
    for (const [id, entry] of _cache) {
      if (_current && id === _current.cacheKey) continue;
      if (entry.lastUsed < oldestTs) {
        oldestTs = entry.lastUsed;
        oldestId = id;
      }
    }
    if (oldestId == null) break;
    const entry = _cache.get(oldestId);
    const def = entry ? _routes.get(entry.routeKey) : null;
    if (entry && def?.deactivate) {
      try {
        def.deactivate(entry.el);
      } catch (_) {
        /* ignore */
      }
    }
    entry?.el.remove();
    _cache.delete(oldestId);
  }
}

function _createViewEl(routeKey) {
  if (typeof document !== 'undefined' && document.createElement) {
    const el = document.createElement('div');
    el.className = 'sysforge-view';
    el.dataset.route = routeKey;
    el.hidden = true;
    return el;
  }
  // Node / unit-test fallback (no DOM)
  return {
    className: 'sysforge-view',
    dataset: { route: routeKey },
    hidden: true,
    remove() {},
  };
}

/**
 * @param {string} routeId
 * @param {RouteDef} definition
 */
export function register(routeId, definition) {
  if (!routeId || typeof definition?.mount !== 'function') {
    throw new Error(`Invalid route registration: ${routeId}`);
  }
  const key = normalizeRouteKey(routeId);
  _routes.set(key, {
    title: definition.title || key,
    mount: definition.mount,
    activate: definition.activate,
    deactivate: definition.deactivate,
  });
}

/**
 * @param {HTMLElement} hostEl
 * @param {{
 *   onChange?: (state: object) => void,
 *   onShellBind?: (surface: object|null) => void,
 *   onShellUnbind?: (surface: object|null) => void,
 *   syncHash?: boolean,
 * }} [opts]
 */
export function mount(hostEl, opts = {}) {
  if (!hostEl) throw new Error('router.mount requires a host element');
  _host = hostEl;
  _onChange = opts.onChange || null;
  _onShellBind = opts.onShellBind || null;
  _onShellUnbind = opts.onShellUnbind || null;
  if (opts.syncHash === false) _hashSyncEnabled = false;
}

function _showOnly(cacheKey) {
  for (const [id, entry] of _cache) {
    entry.el.hidden = id !== cacheKey;
  }
}

function _ensureEntry(routeKey, params) {
  const key = normalizeRouteKey(routeKey);
  const normalized = normalizeParams(params);
  const cacheKey = panelCacheKey(key, normalized);
  const def = _routes.get(key);
  if (!def) throw new Error(`Unknown route: ${key}`);

  let entry = _cache.get(cacheKey);
  if (!entry) {
    const el = _createViewEl(key);
    if (_host && typeof _host.appendChild === 'function') {
      _host.appendChild(el);
    }
    def.mount(el, normalized);
    entry = { el, lastUsed: ++_clock, routeKey: key };
    _cache.set(cacheKey, entry);
    _evictIfNeeded();
  }
  return { def, entry, cacheKey, params: normalized, routeKey: key };
}

function _pushHistory(surface, replace) {
  const item = {
    routeKey: surface.routeKey,
    params: { ...surface.params },
    cacheKey: surface.cacheKey,
  };
  if (replace) {
    if (_history.length === 0) {
      _history = [item];
    } else {
      _history[_history.length - 1] = item;
    }
    return;
  }
  const top = _history[_history.length - 1];
  if (
    top &&
    top.cacheKey === item.cacheKey &&
    shallowEqualParams(top.params, item.params)
  ) {
    return;
  }
  _history.push(item);
  while (_history.length > MAX_HISTORY) {
    _history.shift();
  }
}

function _writeHash(surface) {
  if (!_hashSyncEnabled || _applyingHash) return;
  if (typeof window === 'undefined' || !window.location) return;
  const next = buildHash(surface.routeKey, surface.params);
  const current = window.location.hash || '';
  if (current === next) return;
  try {
    const url = `${window.location.pathname}${window.location.search}${next}`;
    window.history.replaceState(window.history.state, '', url);
  } catch (_) {
    window.location.hash = next;
  }
}

/**
 * Core apply path — single writer for current panel.
 *
 * @param {string} routeKey
 * @param {Record<string, string|number|undefined|null>} [params]
 * @param {{ replace?: boolean, reason?: string, pushHistory?: boolean }} [opts]
 */
export function applyNavigation(routeKey, params = {}, opts = {}) {
  if (!_host) throw new Error('router.mount must be called before applyNavigation');

  const key = normalizeRouteKey(routeKey);
  const { def, entry, cacheKey, params: normalized } = _ensureEntry(key, params);
  const next = makeSurface(key, normalized, entry.el);
  const prev = _current;
  const same = isSameSurface(prev, next);
  const reason = opts.reason || (same ? 'reapply' : 'enter');
  const pushHistory = opts.pushHistory !== false;

  if (!same) {
    if (prev && shouldUnbindShellHandlers(prev, next)) {
      if (typeof _onShellUnbind === 'function') {
        try {
          _onShellUnbind(prev);
        } catch (_) {
          /* ignore */
        }
      }
    }
    if (prev) {
      const prevDef = _routes.get(prev.routeKey);
      if (prevDef?.deactivate) {
        try {
          prevDef.deactivate(prev.controller);
        } catch (_) {
          /* ignore */
        }
      }
    }

    _current = next;
    _showOnly(cacheKey);
    // Subscribe only when controller identity changes (including first enter).
    if (!prev || prev.controller !== next.controller) {
      if (typeof _onShellBind === 'function') {
        try {
          _onShellBind(next);
        } catch (_) {
          /* ignore */
        }
      }
    }
    if (def.activate) def.activate(entry.el, normalized, { reason });
    _touch(cacheKey);
    if (pushHistory) _pushHistory(next, Boolean(opts.replace));
  } else {
    // SAME instance / same route re-apply — DO NOT unsubscribe shell handlers.
    _showOnly(cacheKey);
    if (def.activate) def.activate(entry.el, normalized, { reason: 'reapply' });
    _touch(cacheKey);
    // Do not push history on pure re-apply.
  }

  _writeHash(next);
  _emit();
  return next;
}

/**
 * @param {string} routeId
 * @param {{ replace?: boolean, params?: object, reason?: string }} [opts]
 */
export function navigate(routeId, opts = {}) {
  return applyNavigation(routeId, opts.params || {}, {
    replace: Boolean(opts.replace),
    reason: opts.reason || 'enter',
    pushHistory: true,
  });
}

/**
 * Read Classic (and future project/WO) ids from the active panel instance.
 * @param {import('./panel-lifecycle.js').PanelSurface|null} surface
 */
function _readOriginExtras(surface) {
  const el = surface?.controller;
  const classic = el?._sysforgeClassic;
  let clientId = null;
  if (classic?.selectedClient?.id != null) {
    clientId = String(classic.selectedClient.id);
  }
  return {
    clientId,
    projectId: el?._sysforgeProject?.projectId
      ? String(el._sysforgeProject.projectId)
      : null,
    workOrderId: null,
  };
}

/**
 * Capture return context when entering invoice flow from outside.
 * No-op when already on invoice-view / invoice-calculator / invoice-edit
 * (Viewer → Edit must keep Classic origin).
 */
export function captureInvoiceReturnContextIfStartingFlow() {
  const cur = getCurrent();
  if (!cur) return false;
  if (isInvoiceFlowRoute(cur.routeKey)) return false;
  const extras = _readOriginExtras(_current);
  return returnContext.captureIfStartingInvoiceFlow(cur.routeKey, {
    clientId: extras.clientId ?? cur.params.clientId ?? null,
    projectId: extras.projectId ?? cur.params.projectId ?? null,
    workOrderId: extras.workOrderId ?? cur.params.workOrderId ?? null,
  });
}

/**
 * Pop consecutive invoice-flow entries from history (desktop TrimInvoiceFlowFromHistory).
 * Does not change the current panel — caller navigates next.
 */
export function trimInvoiceFlowFromHistory() {
  while (_history.length > 0) {
    const top = _history[_history.length - 1];
    if (!isInvoiceFlowRoute(top.routeKey)) break;
    _history.pop();
  }
  return _history.map((h) => ({
    routeKey: h.routeKey,
    params: { ...h.params },
  }));
}

/** Open read-only viewer; captures origin when leaving Classic. */
export function navigateToInvoiceViewer(invoiceId) {
  captureInvoiceReturnContextIfStartingFlow();
  return navigate(ROUTE.INVOICE_VIEW, { params: { id: invoiceId } });
}

/** Calculator edit; captures origin unless already in invoice flow. */
export function navigateToInvoiceCalculatorEdit(invoiceId) {
  captureInvoiceReturnContextIfStartingFlow();
  return navigate(ROUTE.INVOICE_CALCULATOR, { params: { invoiceId } });
}

/** New invoice with client; captures origin. */
export function navigateToInvoiceCalculatorWithClient(clientId) {
  captureInvoiceReturnContextIfStartingFlow();
  return navigate(ROUTE.INVOICE_CALCULATOR, { params: { clientId } });
}

/**
 * Save-as-new: trim calculator/viewer stack, then push viewer for the new id.
 * Desktop NavigateToInvoiceViewerAfterSaveAsNewAsync.
 * @param {number|string} invoiceId
 * @param {number|string} [_clientId] — kept for API parity; return context already holds origin
 */
export function navigateToViewerAfterSaveAsNew(invoiceId, _clientId) {
  trimInvoiceFlowFromHistory();
  return navigate(ROUTE.INVOICE_VIEW, { params: { id: invoiceId } });
}

/**
 * After create/edit save: trim invoice-flow, restore origin (Classic + client refresh).
 * Desktop NavigateAfterInvoiceSaveAsync.
 * @param {number|string|null|undefined} savedClientId
 */
export function navigateAfterInvoiceSave(savedClientId) {
  trimInvoiceFlowFromHistory();
  const ctx = returnContext.consume();
  const fallbackId =
    savedClientId != null && savedClientId !== '' ? String(savedClientId) : null;

  if (ctx) {
    if (ctx.originRoute === ROUTE.CLIENT_DASHBOARD) {
      const clientId = ctx.clientId || fallbackId;
      return applyNavigation(
        ROUTE.CLIENT_DASHBOARD,
        clientId ? { clientId } : {},
        { replace: true, reason: 'after-save', pushHistory: true }
      );
    }
    // Typed hooks for projects / work orders.
    if (
      (ctx.originRoute === 'project' || ctx.originRoute === 'project-detail') &&
      ctx.projectId
    ) {
      return applyNavigation(
        'project',
        { id: ctx.projectId },
        { replace: true, reason: 'after-save', pushHistory: true }
      );
    }
    if (ctx.originRoute === 'work-order' && ctx.workOrderId) {
      return applyNavigation(
        'work-order',
        { workOrderId: ctx.workOrderId },
        { replace: true, reason: 'after-save', pushHistory: true }
      );
    }
    if (ctx.originRoute === 'projects' || ctx.originRoute === 'projects-hub') {
      return applyNavigation('projects', {}, {
        replace: true,
        reason: 'after-save',
        pushHistory: true,
      });
    }
    if (ctx.originRoute && !isInvoiceFlowRoute(ctx.originRoute)) {
      try {
        return applyNavigation(ctx.originRoute, {}, {
          replace: true,
          reason: 'after-save',
          pushHistory: true,
        });
      } catch (_) {
        /* unknown route — fall through */
      }
    }
  }

  return applyNavigation(
    ROUTE.CLIENT_DASHBOARD,
    fallbackId ? { clientId: fallbackId } : {},
    { replace: true, reason: 'after-save', pushHistory: true }
  );
}

export function back() {
  if (_history.length <= 1) return false;
  _history.pop();
  const prev = _history[_history.length - 1];
  if (!prev || !_host) return false;
  applyNavigation(prev.routeKey, prev.params, {
    replace: true,
    reason: 'back',
    pushHistory: false,
  });
  // replace:true already set top; ensure stack top matches (apply with pushHistory false).
  if (_history.length === 0) {
    _history = [
      {
        routeKey: prev.routeKey,
        params: { ...prev.params },
        cacheKey: prev.cacheKey,
      },
    ];
  } else {
    _history[_history.length - 1] = {
      routeKey: prev.routeKey,
      params: { ...prev.params },
      cacheKey: prev.cacheKey,
    };
  }
  return true;
}

/** Home jumps to dashboard with replace so the stack does not grow unbounded. */
export function goHome() {
  navigate(ROUTE.DASHBOARD, { replace: true });
}

export function getState() {
  const def = _current ? _routes.get(_current.routeKey) : null;
  return {
    routeId: _current?.routeKey || null,
    routeKey: _current?.routeKey || null,
    params: _current ? { ..._current.params } : {},
    canGoBack: _history.length > 1,
    title: def?.title || '',
    cacheSize: _cache.size,
    historyLength: _history.length,
  };
}

/**
 * Breadcrumb labels for chrome: Business › current route title
 * (in-session only; VI2 = no persist across restart).
 * @returns {string[]}
 */
export function getBreadcrumb() {
  const crumbs = ['Business'];
  if (!_current) return crumbs;
  const def = _routes.get(_current.routeKey);
  const title = def?.title || _current.routeKey;
  if (title && title !== 'Business') {
    crumbs.push(title);
  }
  return crumbs;
}

export function getCurrent() {
  if (!_current) return null;
  return {
    routeKey: _current.routeKey,
    params: { ..._current.params },
    panelKey: _current.cacheKey,
  };
}

/** Re-activate current route after modal reopen (keeps cache/stack). */
export function activateCurrent() {
  if (!_current) return;
  applyNavigation(_current.routeKey, _current.params, {
    replace: true,
    reason: 'reapply',
    pushHistory: false,
  });
}

/**
 * Apply `#sysforge/...` hash. Returns false if hash is not a sysforge route.
 * @param {string} [hash]
 */
export function applyFromHash(hash) {
  const source =
    hash != null
      ? hash
      : typeof window !== 'undefined'
        ? window.location.hash
        : '';
  const parsed = parseHash(source);
  if (!parsed) return false;
  if (!_routes.has(normalizeRouteKey(parsed.routeKey))) return false;
  _applyingHash = true;
  try {
    applyNavigation(parsed.routeKey, parsed.params, {
      replace: true,
      reason: 'enter',
      pushHistory: true,
    });
  } finally {
    _applyingHash = false;
  }
  return true;
}

/** Listen for `#sysforge/` hash changes (ignore foreign Odysseus chat hashes). */
export function startHashListener() {
  if (typeof window === 'undefined') return;
  stopHashListener();
  _hashListener = () => {
    const h = window.location.hash || '';
    if (!h.startsWith('#sysforge/')) return;
    applyFromHash(h);
  };
  window.addEventListener('hashchange', _hashListener);
}

export function stopHashListener() {
  if (typeof window === 'undefined' || !_hashListener) return;
  window.removeEventListener('hashchange', _hashListener);
  _hashListener = null;
}

/** Deactivate current panel (modal close). Keeps cache/stack. */
export function deactivateCurrent() {
  if (!_current) return;
  const def = _routes.get(_current.routeKey);
  if (def?.deactivate) {
    try {
      def.deactivate(_current.controller);
    } catch (_) {
      /* ignore */
    }
  }
}

/** Test helper — reset in-memory router state. */
export function _resetForTests() {
  stopHashListener();
  _routes.clear();
  _cache.clear();
  _history = [];
  _current = null;
  _host = null;
  _onChange = null;
  _onShellBind = null;
  _onShellUnbind = null;
  _clock = 0;
  _hashSyncEnabled = true;
  _applyingHash = false;
  returnContext._resetForTests();
}

/** Test helper — history snapshot (routeKey + params). */
export function _getHistoryForTests() {
  return _history.map((h) => ({
    routeKey: h.routeKey,
    params: { ...h.params },
    cacheKey: h.cacheKey,
  }));
}

export default {
  register,
  mount,
  navigate,
  applyNavigation,
  back,
  goHome,
  getState,
  getBreadcrumb,
  getCurrent,
  activateCurrent,
  applyFromHash,
  startHashListener,
  stopHashListener,
  deactivateCurrent,
  captureInvoiceReturnContextIfStartingFlow,
  trimInvoiceFlowFromHistory,
  navigateToInvoiceViewer,
  navigateToInvoiceCalculatorEdit,
  navigateToInvoiceCalculatorWithClient,
  navigateToViewerAfterSaveAsNew,
  navigateAfterInvoiceSave,
};
