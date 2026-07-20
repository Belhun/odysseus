/**
 * Panel surface identity helpers (desktop CurrentView ReferenceEquals lesson).
 *
 * BUG-001 / BUG-002 (chat 014ea2dd): assigning the same panel twice must NOT
 * unsubscribe shell handlers. Only tear down when the controller identity changes.
 *
 * See SysForge `.cursor/rules/state-and-event-lifecycle.mdc`.
 */

import { panelCacheKey, shallowEqualParams, normalizeParams, normalizeRouteKey } from './routes-contract.js';

/**
 * @typedef {{
 *   routeKey: string,
 *   params: Record<string, string>,
 *   cacheKey: string,
 *   controller: object|null,
 * }} PanelSurface
 */

/**
 * @param {string} routeKey
 * @param {Record<string, string|number|undefined|null>} [params]
 * @param {object|null} [controller] — stable panel instance (DOM el or controller)
 * @returns {PanelSurface}
 */
export function makeSurface(routeKey, params = {}, controller = null) {
  const key = normalizeRouteKey(routeKey);
  const normalized = normalizeParams(params);
  return {
    routeKey: key,
    params: normalized,
    cacheKey: panelCacheKey(key, normalized),
    controller,
  };
}

/**
 * Same surface = same cached controller + same cache key + same params.
 * When true, applyNavigation must NOT deactivate / unbind shell handlers.
 *
 * @param {PanelSurface|null|undefined} prev
 * @param {PanelSurface|null|undefined} next
 */
export function isSameSurface(prev, next) {
  if (!prev || !next) return false;
  if (prev.controller == null || next.controller == null) return false;
  if (prev.controller !== next.controller) return false;
  if (prev.cacheKey !== next.cacheKey) return false;
  return shallowEqualParams(prev.params, next.params);
}

/**
 * Shell handler unbind only when leaving a different controller instance.
 * @param {PanelSurface|null|undefined} prev
 * @param {PanelSurface|null|undefined} next
 */
export function shouldUnbindShellHandlers(prev, next) {
  if (!prev?.controller) return false;
  if (!next?.controller) return true;
  return prev.controller !== next.controller;
}

export default {
  makeSurface,
  isSameSurface,
  shouldUnbindShellHandlers,
};
