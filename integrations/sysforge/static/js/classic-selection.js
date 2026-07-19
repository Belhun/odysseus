/**
 * Classic Client Dashboard selection / overlay / MRU helpers (pure).
 * SearchListSelection: clear query does not clear selectedClient.
 */

export const MAX_RECENT_CLIENTS = 6;

/**
 * Overlay guard: selected client + query == display_name → keep closed.
 * @param {string} query
 * @param {{ display_name?: string, displayName?: string } | null | undefined} selectedClient
 */
export function shouldOpenClassicOverlay(query, selectedClient) {
  if (!selectedClient) return true;
  const q = (query || '').trim().toLowerCase();
  const name = String(selectedClient.display_name || selectedClient.displayName || '')
    .trim()
    .toLowerCase();
  if (!q || !name) return true;
  return q !== name;
}

/**
 * Clear search keeps selectedClient; only nulls searchListSelection.
 * @param {{ selectedClient: object|null, searchListSelection: object|null, searchQuery: string }} state
 */
export function clearSearchQuery(state) {
  return {
    ...state,
    searchQuery: '',
    searchListSelection: null,
    // selectedClient unchanged
  };
}

/**
 * Apply a non-null search pick → selectedClient + close overlay + fill query.
 * @param {object} state
 * @param {object} client
 */
export function pickClientFromSearch(state, client) {
  if (!client) return state;
  const name = client.display_name || client.displayName || '';
  return {
    ...state,
    searchListSelection: client,
    selectedClient: client,
    searchQuery: name,
    overlayOpen: false,
  };
}

/**
 * Prepend client to session recent (cap 6). Moves existing to front.
 * @param {object[]} recent
 * @param {object} client
 * @param {number} [max]
 */
export function trackRecentClient(recent, client, max = MAX_RECENT_CLIENTS) {
  if (!client || client.id == null) return [...(recent || [])];
  const next = (recent || []).filter((c) => Number(c.id) !== Number(client.id));
  next.unshift(client);
  return next.slice(0, max);
}

/**
 * Seed recent from first N active clients when empty (legacy wireframe pad).
 * Classic dashboard no longer uses this — prefer GET /clients/recent (no pad).
 * @param {object[]} recent
 * @param {object[]} clients
 * @param {number} [max]
 */
export function seedRecentIfEmpty(recent, clients, max = MAX_RECENT_CLIENTS) {
  if ((recent || []).length > 0) return [...recent];
  return (clients || []).slice(0, max);
}

export default {
  MAX_RECENT_CLIENTS,
  shouldOpenClassicOverlay,
  clearSearchQuery,
  pickClientFromSearch,
  trackRecentClient,
  seedRecentIfEmpty,
};
