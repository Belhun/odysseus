/**
 * Shared client typeahead: debounce, abort, matches-before-Add-New.
 * Calculator and Classic overlay reuse this helper later.
 */

const DEFAULT_DEBOUNCE_MS = 250;
const DEFAULT_LIMIT = 20;

/**
 * @param {string} apiBase e.g. `${origin}/api/sysforge`
 * @param {{ debounceMs?: number, limit?: number }} [opts]
 */
export function createClientSearch(apiBase, opts = {}) {
  const debounceMs = opts.debounceMs ?? DEFAULT_DEBOUNCE_MS;
  const limit = opts.limit ?? DEFAULT_LIMIT;

  let _timer = null;
  let _controller = null;
  let _seq = 0;

  function cancel() {
    if (_timer != null) {
      clearTimeout(_timer);
      _timer = null;
    }
    if (_controller) {
      _controller.abort();
      _controller = null;
    }
  }

  /**
   * Build dropdown model: matches first, then optional Add New sentinel.
   * @param {object[]} results
   * @param {string} query
   * @returns {Array<{kind:'match', client:object}|{kind:'add_new', query:string}>}
   */
  function buildItems(results, query) {
    const q = (query || '').trim();
    const items = (results || []).map((client) => ({ kind: 'match', client }));
    if (q) {
      items.push({ kind: 'add_new', query: q });
    }
    return items;
  }

  /**
   * @param {string} query
   * @param {{ signal?: AbortSignal }} [fetchOpts]
   */
  async function searchNow(query, fetchOpts = {}) {
    const q = (query || '').trim();
    if (!q) {
      return { query: q, results: [], items: [] };
    }
    const url = `${apiBase}/clients/search?q=${encodeURIComponent(q)}&limit=${limit}`;
    const res = await fetch(url, {
      credentials: 'same-origin',
      signal: fetchOpts.signal,
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) {
      throw new Error(data.detail || data.message || `Search failed (${res.status})`);
    }
    const results = data.results || [];
    return { query: q, results, items: buildItems(results, q) };
  }

  /**
   * Debounced search. Invokes onResult with latest completed response only.
   * @param {string} query
   * @param {(payload: {query:string, results:object[], items:object[]}|null, err?: Error) => void} onResult
   */
  function search(query, onResult) {
    cancel();
    const q = (query || '').trim();
    if (!q) {
      onResult({ query: '', results: [], items: [] });
      return;
    }
    const mySeq = ++_seq;
    _timer = setTimeout(async () => {
      _timer = null;
      _controller = new AbortController();
      try {
        const payload = await searchNow(q, { signal: _controller.signal });
        if (mySeq !== _seq) return;
        onResult(payload);
      } catch (err) {
        if (err?.name === 'AbortError') return;
        if (mySeq !== _seq) return;
        onResult(null, err instanceof Error ? err : new Error(String(err)));
      } finally {
        _controller = null;
      }
    }, debounceMs);
  }

  /**
   * Keyboard helper: Up/Down/Enter on items list.
   * @param {KeyboardEvent} e
   * @param {{ items: object[], index: number, onIndex: (n:number)=>void, onSelect: (item:object)=>void }} state
   */
  function handleKeydown(e, state) {
    const items = state.items || [];
    if (!items.length) return false;
    let idx = state.index;
    if (e.key === 'ArrowDown') {
      e.preventDefault();
      idx = Math.min(items.length - 1, (idx < 0 ? 0 : idx + 1));
      state.onIndex(idx);
      return true;
    }
    if (e.key === 'ArrowUp') {
      e.preventDefault();
      idx = Math.max(0, (idx < 0 ? 0 : idx - 1));
      state.onIndex(idx);
      return true;
    }
    if (e.key === 'Enter' && idx >= 0 && idx < items.length) {
      e.preventDefault();
      state.onSelect(items[idx]);
      return true;
    }
    return false;
  }

  return {
    search,
    searchNow,
    buildItems,
    handleKeydown,
    cancel,
    debounceMs,
  };
}

export default { createClientSearch };
