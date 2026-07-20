/**
 * Drafts list — search, open → calculator, rename, delete, multi-select delete.
 */

import { openDraftNameDialog } from '../draft-name-dialog.js';

async function _toast(message, isError) {
  try {
    const ui = await import('/static/js/ui.js');
    if (typeof ui.showToast === 'function') {
      ui.showToast(message, isError ? 'error' : 'success');
      return;
    }
  } catch (_) {
    /* fall through */
  }
  console[isError ? 'error' : 'log'](message);
}

function _escape(s) {
  return String(s ?? '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

function _formatMoney(n) {
  const v = Number(n);
  if (!Number.isFinite(v)) return '—';
  return v.toLocaleString(undefined, { style: 'currency', currency: 'USD' });
}

function _formatLocal(iso) {
  if (!iso) return '—';
  try {
    const d = new Date(iso);
    const mm = String(d.getMonth() + 1).padStart(2, '0');
    const dd = String(d.getDate()).padStart(2, '0');
    const yyyy = d.getFullYear();
    const hh = String(d.getHours()).padStart(2, '0');
    const mi = String(d.getMinutes()).padStart(2, '0');
    return `${mm}/${dd}/${yyyy} ${hh}:${mi}`;
  } catch (_) {
    return String(iso);
  }
}

/**
 * Prefer newest autosave only in the list (recovery semantics).
 * @param {object[]} drafts
 */
function _dedupeAutosaves(drafts) {
  let newestAuto = null;
  const manuals = [];
  for (const d of drafts || []) {
    if (d.isAutosave) {
      if (
        !newestAuto ||
        String(d.lastModifiedAt || '') > String(newestAuto.lastModifiedAt || '')
      ) {
        newestAuto = d;
      }
    } else {
      manuals.push(d);
    }
  }
  const out = [...manuals];
  if (newestAuto) out.push(newestAuto);
  out.sort((a, b) => String(b.lastModifiedAt || '').localeCompare(String(a.lastModifiedAt || '')));
  return out;
}

/**
 * @param {HTMLElement} container
 * @param {{
 *   api: (path: string, opts?: object) => Promise<object>,
 *   navigate: (routeId: string, opts?: object) => void,
 * }} deps
 */
export function mountDrafts(container, deps) {
  if (container.dataset.mounted === '1') return;

  container.innerHTML = `
    <div class="sysforge-drafts">
      <h3 class="sysforge-view-heading" tabindex="-1">Drafts</h3>
      <p class="sysforge-dashboard-lead">Resume calculator work. Autosaves rotate on disk. Pin named drafts to keep them when retention runs.</p>
      <div class="sysforge-drafts-toolbar">
        <input type="search" id="sysforge-drafts-q" class="sysforge-drafts-q"
          placeholder="Search name, client, phone…" autocomplete="off" />
        <select id="sysforge-drafts-client" class="sysforge-drafts-client" hidden aria-label="Filter by client">
          <option value="">All clients</option>
        </select>
        <button type="button" class="btn-secondary" id="sysforge-drafts-refresh">Refresh</button>
        <button type="button" class="btn-secondary" id="sysforge-drafts-delete-selected" disabled>Delete selected</button>
      </div>
      <p class="sysforge-drafts-error" id="sysforge-drafts-error" hidden></p>
      <div id="sysforge-drafts-list" class="sysforge-drafts-list" role="list"></div>
      <p class="sysforge-drafts-empty" id="sysforge-drafts-empty" hidden>No drafts yet. Work in the calculator autosaves here.</p>
    </div>`;

  const listEl = container.querySelector('#sysforge-drafts-list');
  const emptyEl = container.querySelector('#sysforge-drafts-empty');
  const errorEl = container.querySelector('#sysforge-drafts-error');
  const qInput = container.querySelector('#sysforge-drafts-q');
  const clientSelect = container.querySelector('#sysforge-drafts-client');
  const deleteSelectedBtn = container.querySelector('#sysforge-drafts-delete-selected');

  let _drafts = [];
  let _selected = new Set();

  function showError(msg) {
    if (!errorEl) return;
    if (!msg) {
      errorEl.hidden = true;
      errorEl.textContent = '';
      return;
    }
    errorEl.textContent = msg;
    errorEl.hidden = false;
  }

  function syncDeleteSelected() {
    if (deleteSelectedBtn) {
      deleteSelectedBtn.disabled = _selected.size === 0;
    }
  }

  function render() {
    if (!listEl) return;
    const q = (qInput?.value || '').trim().toLowerCase();
    const clientFilter = clientSelect?.value || '';
    let rows = _dedupeAutosaves(_drafts);
    if (clientFilter) {
      rows = rows.filter((d) => String(d.clientId || '') === clientFilter);
    }
    if (q) {
      rows = rows.filter((d) => {
        const hay = [
          d.displayName,
          d.name,
          d.clientName,
          d.clientPhone,
        ]
          .map((x) => String(x || '').toLowerCase())
          .join(' ');
        return hay.includes(q);
      });
    }

    if (!rows.length) {
      listEl.innerHTML = '';
      if (emptyEl) emptyEl.hidden = false;
      return;
    }
    if (emptyEl) emptyEl.hidden = true;

    listEl.innerHTML = rows
      .map((d) => {
        const id = d.isAutosave ? 'autosave' : d.id;
        const badge = d.isAutosave
          ? '<span class="sysforge-draft-badge">AUTOSAVE</span>'
          : d.pinned
            ? '<span class="sysforge-draft-badge sysforge-draft-badge-pin">PINNED</span>'
            : '';
        const checked = _selected.has(d.id) ? 'checked' : '';
        const selectDisabled = d.isAutosave ? 'disabled' : '';
        const pinLabel = d.pinned ? 'Unpin' : 'Pin';
        return `
        <div class="sysforge-draft-row" role="listitem" data-id="${_escape(d.id)}" data-open-id="${_escape(id)}">
          <label class="sysforge-draft-check">
            <input type="checkbox" data-select="${_escape(d.id)}" ${checked} ${selectDisabled} />
          </label>
          <div class="sysforge-draft-main">
            <div class="sysforge-draft-title">
              ${_escape(d.displayName || d.name || 'Untitled Draft')}
              ${badge}
            </div>
            <div class="sysforge-draft-meta">
              ${_escape(d.clientName || 'Unknown Client')}
              · ${d.itemCount ?? 0} item(s)
              · ${_formatMoney(d.finalTotal)}
              · ${_formatLocal(d.lastModifiedAt)}
            </div>
          </div>
          <div class="sysforge-draft-actions">
            <button type="button" class="btn-primary" data-action="open">Open</button>
            ${
              d.isAutosave
                ? ''
                : `<button type="button" class="btn-secondary" data-action="pin">${pinLabel}</button>
                   <button type="button" class="btn-secondary" data-action="rename">Rename</button>
                   <button type="button" class="btn-secondary" data-action="delete">Delete</button>`
            }
          </div>
        </div>`;
      })
      .join('');
  }

  async function reload() {
    showError('');
    try {
      const data = await deps.api('/drafts');
      _drafts = data.drafts || [];
      // Client filter once clients API exists
      try {
        const clients = await deps.api('/clients');
        const list = clients.clients || [];
        if (clientSelect && list.length) {
          const prev = clientSelect.value;
          clientSelect.hidden = false;
          clientSelect.innerHTML =
            '<option value="">All clients</option>' +
            list
              .map(
                (c) =>
                  `<option value="${_escape(c.id)}">${_escape(c.display_name || c.id)}</option>`
              )
              .join('');
          clientSelect.value = prev;
        }
      } catch (_) {
        if (clientSelect) clientSelect.hidden = true;
      }
      render();
      syncDeleteSelected();
    } catch (err) {
      showError(err?.message || String(err));
      await _toast(err?.message || String(err), true);
    }
  }

  function openDraft(openId, draftId) {
    deps.navigate('invoice-calculator', {
      params: { draftId: openId === 'autosave' ? 'autosave' : draftId },
    });
  }

  listEl?.addEventListener('click', async (e) => {
    const btn = e.target.closest('[data-action]');
    const row = e.target.closest('.sysforge-draft-row');
    if (!row) return;
    const draftId = row.getAttribute('data-id');
    const openId = row.getAttribute('data-open-id');
    const action = btn?.getAttribute('data-action');

    if (action === 'open') {
      openDraft(openId, draftId);
      return;
    }
    if (action === 'pin' && draftId) {
      const draft = _drafts.find((d) => d.id === draftId);
      const next = !draft?.pinned;
      try {
        await deps.api(`/drafts/${encodeURIComponent(draftId)}/pin`, {
          method: 'PATCH',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ pinned: next }),
        });
        await _toast(next ? 'Draft pinned' : 'Draft unpinned', false);
        await reload();
      } catch (err) {
        await _toast(err?.message || String(err), true);
      }
      return;
    }
    if (action === 'rename' && draftId) {
      const draft = _drafts.find((d) => d.id === draftId);
      openDraftNameDialog({
        prefill: draft?.name || '',
        onSave: async (name) => {
          await deps.api(`/drafts/${encodeURIComponent(draftId)}`, {
            method: 'PATCH',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ name }),
          });
          await _toast('Draft renamed', false);
          await reload();
        },
      });
      return;
    }
    if (action === 'delete' && draftId) {
      if (!window.confirm('Delete this draft?')) return;
      try {
        await deps.api(`/drafts/${encodeURIComponent(draftId)}`, { method: 'DELETE' });
        _selected.delete(draftId);
        await _toast('Draft deleted', false);
        await reload();
      } catch (err) {
        await _toast(err?.message || String(err), true);
      }
    }
  });

  listEl?.addEventListener('change', (e) => {
    const cb = e.target.closest('[data-select]');
    if (!cb) return;
    const id = cb.getAttribute('data-select');
    if (!id) return;
    if (cb.checked) _selected.add(id);
    else _selected.delete(id);
    syncDeleteSelected();
  });

  qInput?.addEventListener('input', () => render());
  clientSelect?.addEventListener('change', () => render());

  container.querySelector('#sysforge-drafts-refresh')?.addEventListener('click', () => {
    reload().catch(() => {});
  });

  deleteSelectedBtn?.addEventListener('click', async () => {
    const ids = [..._selected];
    if (!ids.length) return;
    if (!window.confirm(`Delete ${ids.length} selected draft(s)?`)) return;
    try {
      const res = await deps.api('/drafts/delete', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ ids }),
      });
      _selected.clear();
      await _toast(res.message || `Deleted ${res.deleted} of ${ids.length} draft(s)`, false);
      await reload();
    } catch (err) {
      await _toast(err?.message || String(err), true);
    }
  });

  container.dataset.mounted = '1';
  container._sysforgeReloadDrafts = reload;
}

/**
 * @param {HTMLElement} container
 */
export async function activateDrafts(container) {
  const heading = container.querySelector('.sysforge-view-heading');
  heading?.focus?.({ preventScroll: true });
  if (typeof container._sysforgeReloadDrafts === 'function') {
    try {
      await container._sysforgeReloadDrafts();
    } catch (err) {
      const errorEl = container.querySelector('#sysforge-drafts-error');
      if (errorEl) {
        errorEl.textContent = err?.message || String(err);
        errorEl.hidden = false;
      }
    }
  }
}

export function deactivateDrafts() {
  /* list has no leave flush; calculator owns autosave flush */
}
