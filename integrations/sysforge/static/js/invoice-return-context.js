/**
 * Invoice navigation return context (desktop InvoiceNavigationReturnContext).
 *
 * Capture only when leaving a non-invoice screen into viewer/calculator.
 * Viewer → Edit must NOT overwrite the stored origin.
 */

/** Routes treated as in-invoice-flow (do not capture over these). */
export const INVOICE_FLOW_ROUTES = Object.freeze([
  'invoice-view',
  'invoice-calculator',
  'invoice-edit',
]);

/**
 * @param {string|null|undefined} routeKey
 */
export function isInvoiceFlowRoute(routeKey) {
  if (!routeKey) return false;
  return INVOICE_FLOW_ROUTES.includes(String(routeKey));
}

/** @type {{ originRoute: string, clientId: string|null, projectId: string|null, workOrderId: string|null } | null} */
let _store = null;

/**
 * @param {string|number|null|undefined} v
 * @returns {string|null}
 */
function _idOrNull(v) {
  if (v == null || v === '') return null;
  return String(v);
}

/**
 * Store origin if current route is outside invoice flow.
 * @param {string} currentRouteKey
 * @param {{ clientId?: string|number|null, projectId?: string|number|null, workOrderId?: string|number|null }} [ids]
 * @returns {boolean} true when context was written
 */
export function captureIfStartingInvoiceFlow(currentRouteKey, ids = {}) {
  if (isInvoiceFlowRoute(currentRouteKey)) {
    return false;
  }
  _store = {
    originRoute: String(currentRouteKey || ''),
    clientId: _idOrNull(ids.clientId),
    projectId: _idOrNull(ids.projectId),
    workOrderId: _idOrNull(ids.workOrderId),
  };
  return true;
}

export function clear() {
  _store = null;
}

/** Peek without clearing. */
export function peek() {
  if (!_store) return null;
  return {
    originRoute: _store.originRoute,
    clientId: _store.clientId,
    projectId: _store.projectId,
    workOrderId: _store.workOrderId,
  };
}

/** Take and clear. */
export function consume() {
  const ctx = peek();
  _store = null;
  return ctx;
}

/** Test helper. */
export function _resetForTests() {
  _store = null;
}

export default {
  INVOICE_FLOW_ROUTES,
  isInvoiceFlowRoute,
  captureIfStartingInvoiceFlow,
  clear,
  peek,
  consume,
  _resetForTests,
};
