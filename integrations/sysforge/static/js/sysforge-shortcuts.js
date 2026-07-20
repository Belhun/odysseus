/**
 * Host-registered in-Business shortcut targets (no DOM).
 * Keybinds live in Odysseus Settings → Shortcuts; this only maps action → route.
 */

import { ROUTE } from './routes-contract.js';

/**
 * @param {string} action
 * @returns {{ kind: 'home' } | { kind: 'navigate', routeId: string } | null}
 */
export function sysforgeShortcutTarget(action) {
  if (action === 'sysforge_home') return { kind: 'home' };
  if (action === 'sysforge_clients') {
    // Classic workspace (same as dashboard Clients card), not All clients list.
    return { kind: 'navigate', routeId: ROUTE.CLIENT_DASHBOARD };
  }
  if (action === 'sysforge_calculator') {
    return { kind: 'navigate', routeId: ROUTE.INVOICE_CALCULATOR };
  }
  return null;
}

/** Action ids registered in host keyboard-shortcuts + Settings catalog. */
export const SYSFORGE_SHORTCUT_ACTIONS = Object.freeze([
  'sysforge_home',
  'sysforge_clients',
  'sysforge_calculator',
]);
