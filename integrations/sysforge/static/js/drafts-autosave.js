/**
 * Calculator autosave client: timer, skip-if-busy lock, debounce, leave flush, recovery.
 * Calculator UI can attach later via createDraftAutosaveController.
 */

const DEFAULT_INTERVAL_SEC = 60;
const DEBOUNCE_MS = 500;

/**
 * @typedef {object} AutosaveDeps
 * @property {(path: string, opts?: object) => Promise<object>} api
 * @property {() => object | null} getSnapshot  full draft body (camelCase)
 * @property {() => boolean} [hasItems]
 * @property {(draft: object) => void} [onRecover]
 * @property {(message: string, kind?: string) => void} [toast]
 */

/**
 * @param {AutosaveDeps} deps
 */
export function createDraftAutosaveController(deps) {
  let _enabled = true;
  let _intervalSec = DEFAULT_INTERVAL_SEC;
  let _timer = null;
  let _dirty = false;
  let _debounceTimer = null;
  let _inFlight = false;
  let _currentDraftId = null;
  let _invoiceWasSaved = false;
  let _pageHideBound = null;
  let _started = false;

  function toast(message, kind) {
    if (typeof deps.toast === 'function') {
      deps.toast(message, kind);
      return;
    }
    console.log(message);
  }

  function hasItems() {
    if (typeof deps.hasItems === 'function') return Boolean(deps.hasItems());
    const snap = deps.getSnapshot?.();
    return Array.isArray(snap?.items) && snap.items.length > 0;
  }

  async function refreshSettings() {
    try {
      const data = await deps.api('/settings');
      _enabled = data.autosave_drafts !== false;
      const n = Number(data.autosave_interval_seconds);
      _intervalSec = Number.isFinite(n) && n >= 5 ? n : DEFAULT_INTERVAL_SEC;
    } catch (_) {
      _enabled = true;
      _intervalSec = DEFAULT_INTERVAL_SEC;
    }
  }

  function markDirty() {
    _dirty = true;
    _invoiceWasSaved = false;
    if (_debounceTimer != null) clearTimeout(_debounceTimer);
    _debounceTimer = setTimeout(() => {
      _debounceTimer = null;
    }, DEBOUNCE_MS);
  }

  function setCurrentDraftId(id) {
    _currentDraftId = id || null;
  }

  function getCurrentDraftId() {
    return _currentDraftId;
  }

  async function performAutosave() {
    if (!_enabled) return false;
    if (_inFlight) return false; // desktop WaitAsync(0) skip-if-busy
    if (_debounceTimer != null) return false;
    if (!_dirty) return false;
    if (!hasItems()) return false;

    const snap = deps.getSnapshot?.();
    if (!snap || typeof snap !== 'object') return false;

    _inFlight = true;
    try {
      const body = {
        ...snap,
        id: snap.id || _currentDraftId || undefined,
        invoiceWasSaved: Boolean(_invoiceWasSaved),
      };
      const res = await deps.api('/drafts/autosave', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      });
      if (res?.draft?.id) _currentDraftId = res.draft.id;
      _dirty = false;
      return true;
    } catch (err) {
      toast(err?.message || 'Unable to access draft files…', 'error');
      return false;
    } finally {
      _inFlight = false;
    }
  }

  function startTimer() {
    stopTimer();
    if (!_enabled) return;
    const ms = Math.max(5, _intervalSec) * 1000;
    _timer = setInterval(() => {
      performAutosave().catch(() => {});
    }, ms);
  }

  function stopTimer() {
    if (_timer != null) {
      clearInterval(_timer);
      _timer = null;
    }
  }

  async function flush() {
    if (!_dirty || !hasItems()) return false;
    // Bypass debounce for leave flush
    if (_debounceTimer != null) {
      clearTimeout(_debounceTimer);
      _debounceTimer = null;
    }
    return performAutosave();
  }

  async function clearAutosaves() {
    try {
      await deps.api('/drafts/autosave', { method: 'DELETE' });
    } catch (_) {
      /* ignore */
    }
    _dirty = false;
  }

  function formatRecoveredLocal(iso) {
    try {
      const d = iso ? new Date(iso) : new Date();
      const mm = String(d.getMonth() + 1).padStart(2, '0');
      const dd = String(d.getDate()).padStart(2, '0');
      const yyyy = d.getFullYear();
      const hh = String(d.getHours()).padStart(2, '0');
      const mi = String(d.getMinutes()).padStart(2, '0');
      return `${mm}/${dd}/${yyyy} ${hh}:${mi}`;
    } catch (_) {
      return '';
    }
  }

  async function tryRecover() {
    if (!_enabled) return null;
    try {
      const res = await deps.api('/drafts/autosave/latest');
      const draft = res?.draft;
      if (!draft || draft.invoiceWasSaved) return null;
      if (typeof deps.onRecover === 'function') {
        deps.onRecover(draft);
      }
      if (draft.id) _currentDraftId = draft.id;
      const when = formatRecoveredLocal(draft.lastModifiedAt);
      toast(when ? `Recovered work from ${when}` : 'Recovered work from autosave', 'info');
      _dirty = false;
      return draft;
    } catch (_) {
      // 204 / empty → no recovery
      return null;
    }
  }

  function onPageHide() {
    if (!_dirty || !hasItems()) return;
    const snap = deps.getSnapshot?.();
    if (!snap) return;
    const body = JSON.stringify({
      ...snap,
      id: snap.id || _currentDraftId || undefined,
      invoiceWasSaved: Boolean(_invoiceWasSaved),
    });
    // Best-effort keepalive fetch (sendBeacon is POST-only; autosave is PUT)
    try {
      fetch(`${window.location.origin}/api/sysforge/drafts/autosave`, {
        method: 'PUT',
        credentials: 'same-origin',
        headers: { 'Content-Type': 'application/json' },
        body,
        keepalive: true,
      });
      _dirty = false;
    } catch (_) {
      /* ignore */
    }
  }

  async function start() {
    if (_started) return;
    _started = true;
    await refreshSettings();
    await tryRecover();
    startTimer();
    _pageHideBound = onPageHide;
    window.addEventListener('pagehide', _pageHideBound);
    window.addEventListener('beforeunload', _pageHideBound);
  }

  async function stop({ flushOnStop = true } = {}) {
    if (!_started) return;
    stopTimer();
    if (_pageHideBound) {
      window.removeEventListener('pagehide', _pageHideBound);
      window.removeEventListener('beforeunload', _pageHideBound);
      _pageHideBound = null;
    }
    if (flushOnStop) {
      await flush();
    }
    _started = false;
  }

  /** Call after successful invoice save or Discard. */
  async function onInvoiceSavedOrDiscard() {
    _invoiceWasSaved = true;
    _dirty = false;
    await clearAutosaves();
  }

  return {
    start,
    stop,
    flush,
    markDirty,
    performAutosave,
    tryRecover,
    clearAutosaves,
    onInvoiceSavedOrDiscard,
    setCurrentDraftId,
    getCurrentDraftId,
    refreshSettings,
    isDirty: () => _dirty,
  };
}

export default { createDraftAutosaveController };
