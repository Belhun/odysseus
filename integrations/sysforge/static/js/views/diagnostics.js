/**
 * Business Diagnostics — read-only live DB snapshot.
 * Product panel only (strip agent debug-session file writers — chat b89af01b).
 * Diagnostics list ≠ search proof (BUG-018).
 */

let _abort = null;
let _busy = false;

/**
 * @param {HTMLElement} container
 * @param {{ api: (path: string, opts?: object) => Promise<object> }} deps
 */
export function mountDiagnostics(container, deps) {
  if (container.dataset.mounted === '1') return;

  container.innerHTML = `
    <div class="sysforge-diagnostics">
      <div class="sysforge-diagnostics-header">
        <div>
          <h3 class="sysforge-view-heading" tabindex="-1">Business Diagnostics</h3>
          <p class="sysforge-dashboard-lead">
            Live snapshot of what is stored in the Business database.
          </p>
        </div>
        <button type="button" class="btn-primary" id="sysforge-diagnostics-refresh">
          Refresh
        </button>
      </div>
      <p class="sysforge-diagnostics-error" id="sysforge-diagnostics-error" hidden></p>
      <dl class="sysforge-diagnostics-summary" id="sysforge-diagnostics-summary">
        <div><dt>Health</dt><dd id="sysforge-diag-health">—</dd></div>
        <div><dt>Path</dt><dd id="sysforge-diag-path">—</dd></div>
        <div><dt>Size</dt><dd id="sysforge-diag-size">—</dd></div>
        <div><dt>Latest migration</dt><dd id="sysforge-diag-migration">—</dd></div>
        <div><dt>Applied</dt><dd id="sysforge-diag-applied">—</dd></div>
        <div><dt>Clients</dt><dd id="sysforge-diag-clients">—</dd></div>
        <div><dt>Invoices</dt><dd id="sysforge-diag-invoices">—</dd></div>
        <div><dt>Parts</dt><dd id="sysforge-diag-parts">—</dd></div>
      </dl>
      <p class="sysforge-diagnostics-message" id="sysforge-diagnostics-message" hidden></p>
      <p class="sysforge-diagnostics-note" id="sysforge-diagnostics-note">
        Showing rows here means they are in SQLite. Client search may still miss
        them until search reindex runs after import/restore.
      </p>
    </div>`;

  const refreshBtn = container.querySelector('#sysforge-diagnostics-refresh');

  function setBusy(on) {
    _busy = on;
    if (refreshBtn) refreshBtn.disabled = on;
  }

  function showError(msg) {
    const el = container.querySelector('#sysforge-diagnostics-error');
    if (!el) return;
    if (msg) {
      el.textContent = msg;
      el.hidden = false;
    } else {
      el.textContent = '';
      el.hidden = true;
    }
  }

  function applySnapshot(data) {
    const db = data.db || {};
    const schema = data.schema || {};
    const counts = data.counts || {};
    const setText = (id, value) => {
      const el = container.querySelector(id);
      if (el) el.textContent = value == null || value === '' ? '—' : String(value);
    };
    setText('#sysforge-diag-health', data.health || '—');
    setText('#sysforge-diag-path', db.path_display || 'plugins/sysforge/sysforge.db');
    setText('#sysforge-diag-size', db.size_display || '(missing)');
    setText(
      '#sysforge-diag-migration',
      schema.latest_migration_id || schema.latest_migration_name || '(none)'
    );
    setText(
      '#sysforge-diag-applied',
      schema.applied_count != null ? String(schema.applied_count) : '—'
    );
    setText('#sysforge-diag-clients', counts.clients != null ? String(counts.clients) : '—');
    setText('#sysforge-diag-invoices', counts.invoices != null ? String(counts.invoices) : '—');
    setText(
      '#sysforge-diag-parts',
      counts.parts == null ? '—' : String(counts.parts)
    );

    const msgEl = container.querySelector('#sysforge-diagnostics-message');
    if (msgEl) {
      if (data.message) {
        msgEl.textContent = data.message;
        msgEl.hidden = false;
      } else {
        msgEl.textContent = '';
        msgEl.hidden = true;
      }
    }
    const noteEl = container.querySelector('#sysforge-diagnostics-note');
    if (noteEl && data.note) {
      noteEl.textContent = data.note;
    }
  }

  async function reload() {
    if (_busy) return;
    showError('');
    if (_abort) _abort.abort();
    _abort = typeof AbortController !== 'undefined' ? new AbortController() : null;
    setBusy(true);
    try {
      const data = await deps.api('/diagnostics', {
        signal: _abort?.signal,
      });
      if (_abort?.signal?.aborted) return;
      applySnapshot(data || {});
    } catch (err) {
      if (err?.name === 'AbortError') return;
      showError(err?.message || String(err));
    } finally {
      setBusy(false);
    }
  }

  refreshBtn?.addEventListener('click', () => {
    reload().catch(() => {});
  });

  container.dataset.mounted = '1';
  container._sysforgeReloadDiagnostics = reload;
  container._sysforgeAbortDiagnostics = () => {
    if (_abort) _abort.abort();
    _abort = null;
  };
}

/**
 * @param {HTMLElement} container
 */
export async function activateDiagnostics(container) {
  const heading = container.querySelector('.sysforge-view-heading');
  heading?.focus?.({ preventScroll: true });
  if (typeof container._sysforgeReloadDiagnostics === 'function') {
    try {
      await container._sysforgeReloadDiagnostics();
    } catch (_) {
      /* errors rendered in panel */
    }
  }
}

/**
 * @param {HTMLElement} container
 */
export function deactivateDiagnostics(container) {
  if (typeof container._sysforgeAbortDiagnostics === 'function') {
    container._sysforgeAbortDiagnostics();
  }
}

export default { mountDiagnostics, activateDiagnostics, deactivateDiagnostics };
