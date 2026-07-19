/**
 * SysForge View/Edit route contract — single source of truth for hash destinations.
 *
 * View  → invoice-view/:id          (read-only viewer)
 * Edit  → invoice-calculator?invoiceId=  (NOT invoice-edit)
 * New   → invoice-calculator?clientId=
 * Save-as-new → trim → invoice-view/:id  (NavigateToInvoiceViewerAfterSaveAsNewAsync)
 * Edit-save → trim → origin restore     (NavigateAfterInvoiceSaveAsync)
 *
 * Desktop: NavigateToInvoiceViewerAsync / NavigateToInvoiceCalculatorEditAsync.
 */

export {
  INVOICE_FLOW_ROUTES,
  isInvoiceFlowRoute,
} from './invoice-return-context.js';

/** @type {Readonly<Record<string, string>>} */
export const ROUTE = Object.freeze({
  DASHBOARD: 'dashboard',
  CLIENT_DASHBOARD: 'client-dashboard',
  INVOICE_VIEW: 'invoice-view',
  INVOICE_CALCULATOR: 'invoice-calculator',
  CLIENTS: 'clients',
  CLIENT_MERGE: 'client-merge',
  INVOICES_OUTSTANDING: 'invoices-outstanding',
  REPORTS_SALES: 'reports-sales',
  DRAFTS: 'drafts',
  PARTS: 'parts',
  PARTS_TRIAGE: 'parts-triage',
  PLACEHOLDER_MERGE: 'placeholder-merge',
  SUPPLIER: 'supplier',
  SETTINGS: 'settings',
  DIAGNOSTICS: 'diagnostics',
  PROJECTS: 'projects',
  PROJECT: 'project',
  SCREW_MAP: 'screw-map',
  WORK_ORDER: 'work-order',
});

/** Legacy alias used by older dashboard/nav buttons. */
export const ROUTE_ALIASES = Object.freeze({
  calculator: ROUTE.INVOICE_CALCULATOR,
  'projects-hub': ROUTE.PROJECTS,
  'project-detail': ROUTE.PROJECT,
  'parts/triage': ROUTE.PARTS_TRIAGE,
  'clients/merge': ROUTE.CLIENT_MERGE,
  'invoices/outstanding': ROUTE.INVOICES_OUTSTANDING,
  'reports/sales': ROUTE.REPORTS_SALES,
});

const HASH_PREFIX = '#sysforge/';

/**
 * @param {string} routeKey
 * @returns {string}
 */
export function normalizeRouteKey(routeKey) {
  if (!routeKey) return routeKey;
  return ROUTE_ALIASES[routeKey] || routeKey;
}

/**
 * @param {Record<string, string|number|undefined|null>|null|undefined} params
 * @returns {Record<string, string>}
 */
export function normalizeParams(params) {
  /** @type {Record<string, string>} */
  const out = {};
  if (!params || typeof params !== 'object') return out;
  for (const [k, v] of Object.entries(params)) {
    if (v == null || v === '') continue;
    out[k] = String(v);
  }
  return out;
}

/**
 * @param {Record<string, string>} a
 * @param {Record<string, string>} b
 */
export function shallowEqualParams(a, b) {
  const left = a || {};
  const right = b || {};
  const keys = new Set([...Object.keys(left), ...Object.keys(right)]);
  for (const key of keys) {
    if (left[key] !== right[key]) return false;
  }
  return true;
}

/**
 * Cache / surface identity key. Param changes that affect loaded data get distinct keys
 * for parameterized panels; calculator keeps one panel and reloads on activate.
 *
 * @param {string} routeKey
 * @param {Record<string, string>} params
 */
export function panelCacheKey(routeKey, params = {}) {
  const key = normalizeRouteKey(routeKey);
  const p = normalizeParams(params);
  if (key === ROUTE.INVOICE_VIEW) {
    return `${ROUTE.INVOICE_VIEW}:${p.id || ''}`;
  }
  if (key === ROUTE.PROJECT) {
    // One four-column surface — id loads on activate (picker can change project).
    return ROUTE.PROJECT;
  }
  if (key === ROUTE.SUPPLIER) {
    return `${ROUTE.SUPPLIER}:${p.id || ''}`;
  }
  if (key === ROUTE.SCREW_MAP) {
    return `${ROUTE.SCREW_MAP}:${p.projectId || p.id || ''}`;
  }
  // One Classic surface — clientId loads on activate; selection survives Back.
  // One calculator surface — invoiceId/clientId/draftId load on activate.
  return key;
}

/** View invoice (read-only). */
export function buildInvoiceViewRoute(invoiceId) {
  return {
    routeKey: ROUTE.INVOICE_VIEW,
    params: normalizeParams({ id: invoiceId }),
  };
}

/**
 * Edit invoice — always calculator, never invoice-edit.
 * @param {number|string} invoiceId
 */
export function buildInvoiceEditRoute(invoiceId) {
  return {
    routeKey: ROUTE.INVOICE_CALCULATOR,
    params: normalizeParams({ invoiceId }),
  };
}

/** New invoice for a client (calculator with client pre-selected). */
export function buildNewInvoiceRoute(clientId) {
  return {
    routeKey: ROUTE.INVOICE_CALCULATOR,
    params: normalizeParams({ clientId }),
  };
}

export function buildClientDashboardRoute(clientId) {
  return {
    routeKey: ROUTE.CLIENT_DASHBOARD,
    params: normalizeParams({ clientId }),
  };
}

/**
 * Build `#sysforge/<route>[/id][?query]` hash fragment (includes leading #).
 * @param {string} routeKey
 * @param {Record<string, string|number|undefined|null>} [params]
 */
export function buildHash(routeKey, params = {}) {
  const key = normalizeRouteKey(routeKey);
  const p = normalizeParams(params);
  let path = key;

  if (key === ROUTE.INVOICE_VIEW && p.id) {
    path = `${ROUTE.INVOICE_VIEW}/${encodeURIComponent(p.id)}`;
  }
  if (key === ROUTE.PROJECT && p.id) {
    path = `${ROUTE.PROJECT}/${encodeURIComponent(p.id)}`;
  }
  if (key === ROUTE.SUPPLIER && p.id) {
    path = `${ROUTE.SUPPLIER}/${encodeURIComponent(p.id)}`;
  }
  if (key === ROUTE.SCREW_MAP && (p.projectId || p.id)) {
    path = `${ROUTE.SCREW_MAP}/${encodeURIComponent(p.projectId || p.id)}`;
  }
  if (key === ROUTE.PARTS_TRIAGE) {
    path = 'parts/triage';
  }
  if (key === ROUTE.CLIENT_MERGE) {
    path = 'clients/merge';
  }
  if (key === ROUTE.INVOICES_OUTSTANDING) {
    path = 'invoices/outstanding';
  }
  if (key === ROUTE.REPORTS_SALES) {
    path = 'reports/sales';
  }

  const query = new URLSearchParams();
  for (const [k, v] of Object.entries(p)) {
    if (key === ROUTE.INVOICE_VIEW && k === 'id') continue;
    if (key === ROUTE.PROJECT && k === 'id') continue;
    if (key === ROUTE.SUPPLIER && k === 'id') continue;
    if (key === ROUTE.SCREW_MAP && (k === 'projectId' || k === 'id')) continue;
    if (key === ROUTE.PARTS_TRIAGE) continue;
    if (key === ROUTE.CLIENT_MERGE) continue;
    if (key === ROUTE.INVOICES_OUTSTANDING) continue;
    if (key === ROUTE.REPORTS_SALES) continue;
    query.set(k, v);
  }
  const qs = query.toString();
  return qs ? `${HASH_PREFIX}${path}?${qs}` : `${HASH_PREFIX}${path}`;
}

/**
 * @param {string} hash
 * @returns {{ routeKey: string, params: Record<string, string> } | null}
 */
export function parseHash(hash) {
  if (!hash || typeof hash !== 'string') return null;
  let raw = hash.trim();
  if (raw.startsWith('#')) raw = raw.slice(1);
  if (!raw.startsWith('sysforge/')) return null;

  const rest = raw.slice('sysforge/'.length);
  if (!rest) return { routeKey: ROUTE.DASHBOARD, params: {} };

  const qIndex = rest.indexOf('?');
  const pathPart = qIndex >= 0 ? rest.slice(0, qIndex) : rest;
  const queryPart = qIndex >= 0 ? rest.slice(qIndex + 1) : '';

  const segments = pathPart.split('/').filter(Boolean);
  let routeKey = normalizeRouteKey(segments[0] || ROUTE.DASHBOARD);
  /** @type {Record<string, string>} */
  const params = {};

  // #sysforge/parts/triage → parts-triage (before treating as parts catalog)
  if (segments[0] === 'parts' && segments[1] === 'triage') {
    routeKey = ROUTE.PARTS_TRIAGE;
  }
  // #sysforge/clients/merge → client-merge
  if (segments[0] === 'clients' && segments[1] === 'merge') {
    routeKey = ROUTE.CLIENT_MERGE;
  }
  // #sysforge/invoices/outstanding → invoices-outstanding
  if (segments[0] === 'invoices' && segments[1] === 'outstanding') {
    routeKey = ROUTE.INVOICES_OUTSTANDING;
  }
  // #sysforge/reports/sales → reports-sales
  if (segments[0] === 'reports' && segments[1] === 'sales') {
    routeKey = ROUTE.REPORTS_SALES;
  }

  if (routeKey === ROUTE.INVOICE_VIEW && segments[1]) {
    params.id = decodeURIComponent(segments[1]);
  }
  if (routeKey === ROUTE.PROJECT && segments[1]) {
    params.id = decodeURIComponent(segments[1]);
  }
  if (routeKey === ROUTE.SUPPLIER && segments[1]) {
    params.id = decodeURIComponent(segments[1]);
  }
  if (routeKey === ROUTE.SCREW_MAP && segments[1]) {
    params.projectId = decodeURIComponent(segments[1]);
  }

  if (queryPart) {
    const qs = new URLSearchParams(queryPart);
    for (const [k, v] of qs.entries()) {
      params[k] = v;
    }
  }

  return { routeKey, params: normalizeParams(params) };
}

/**
 * Reject ambiguous Client-Dashboard Edit targets.
 * @param {string} routeKey
 */
export function isForbiddenClientDashboardEditRoute(routeKey) {
  return normalizeRouteKey(routeKey) === 'invoice-edit';
}

export default {
  ROUTE,
  ROUTE_ALIASES,
  normalizeRouteKey,
  normalizeParams,
  shallowEqualParams,
  panelCacheKey,
  buildInvoiceViewRoute,
  buildInvoiceEditRoute,
  buildNewInvoiceRoute,
  buildClientDashboardRoute,
  buildHash,
  parseHash,
  isForbiddenClientDashboardEditRoute,
};
