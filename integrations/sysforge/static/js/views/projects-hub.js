/**
 * Projects hub — active / estimates not accepted / accepted-missing + search.
 */

import { startCreateProjectFromInvoice } from '../create-project-wizard.js';

async function _toast(message, kind) {
  try {
    const ui = await import('/static/js/ui.js');
    if (typeof ui.showToast === 'function') {
      ui.showToast(message, kind === 'error' ? 'error' : 'success');
      return;
    }
  } catch (_) {
    /* fall through */
  }
  console.log(message);
}

function escapeHtml(s) {
  return String(s ?? '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

/**
 * @param {HTMLElement} container
 * @param {{ api: Function, navigate: Function }} deps
 */
export function mountProjectsHub(container, deps) {
  if (container.dataset.mounted === '1') return;

  container.innerHTML = `
    <div class="sysforge-projects-hub">
      <h3 class="sysforge-view-heading" tabindex="-1">Projects</h3>
      <p class="sysforge-dashboard-lead">Active work, estimates waiting accept, and accepted devices missing projects.</p>
      <div class="sysforge-hub-toolbar">
        <input type="search" id="sysforge-hub-q" class="sysforge-clients-q" placeholder="Search Device ID, DisplayCode, title…" />
        <label class="sysforge-field-check">
          <input type="checkbox" id="sysforge-hub-archived" />
          <span>Include archived in search</span>
        </label>
        <button type="button" class="btn-secondary" id="sysforge-hub-create">Create project from invoice</button>
      </div>
      <div id="sysforge-hub-search" class="sysforge-hub-section" hidden>
        <h4>Search results</h4>
        <ul id="sysforge-hub-search-list" class="sysforge-hub-list"></ul>
      </div>
      <div class="sysforge-hub-section">
        <h4>Active projects</h4>
        <ul id="sysforge-hub-active" class="sysforge-hub-list"></ul>
      </div>
      <div class="sysforge-hub-section">
        <h4>Estimates not accepted</h4>
        <ul id="sysforge-hub-estimates" class="sysforge-hub-list"></ul>
      </div>
      <div class="sysforge-hub-section">
        <h4>Accepted — missing projects</h4>
        <ul id="sysforge-hub-missing" class="sysforge-hub-list"></ul>
      </div>
      <p class="sysforge-settings-error" id="sysforge-hub-error" hidden></p>
    </div>`;

  container._sysforgeHub = { includeArchived: false };
  container.dataset.mounted = '1';

  const qInput = container.querySelector('#sysforge-hub-q');
  const archCb = container.querySelector('#sysforge-hub-archived');
  let searchTimer = null;

  archCb?.addEventListener('change', async () => {
    const flagged = Boolean(archCb.checked);
    container._sysforgeHub.includeArchived = flagged;
    try {
      await deps.api('/settings', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ include_archived_in_search: flagged }),
      });
    } catch (_) {
      /* non-fatal */
    }
    await reloadHub(container, deps);
    if ((qInput?.value || '').trim()) {
      await runSearch(container, deps, qInput.value);
    }
  });

  qInput?.addEventListener('input', () => {
    clearTimeout(searchTimer);
    searchTimer = setTimeout(() => {
      void runSearch(container, deps, qInput.value);
    }, 250);
  });

  container.querySelector('#sysforge-hub-create')?.addEventListener('click', () => {
    void startCreateProjectFromInvoice({
      api: deps.api,
      navigate: deps.navigate,
      invoiceId: null,
    });
  });

  container.addEventListener('click', (e) => {
    const projBtn = e.target.closest('[data-project-id]');
    if (projBtn) {
      deps.navigate('project', { params: { id: projBtn.getAttribute('data-project-id') } });
      return;
    }
    const invBtn = e.target.closest('[data-invoice-id]');
    if (invBtn) {
      deps.navigate('invoice-view', {
        params: { id: invBtn.getAttribute('data-invoice-id') },
      });
    }
  });
}

async function runSearch(container, deps, q) {
  const section = container.querySelector('#sysforge-hub-search');
  const list = container.querySelector('#sysforge-hub-search-list');
  const needle = (q || '').trim();
  if (!needle) {
    if (section) section.hidden = true;
    return;
  }
  const flagged = Boolean(container._sysforgeHub?.includeArchived);
  try {
    const data = await deps.api(
      `/projects?q=${encodeURIComponent(needle)}&include_archived=${flagged ? 1 : 0}`
    );
    const projects = data.projects || [];
    if (section) section.hidden = false;
    if (list) {
      list.innerHTML = projects.length
        ? projects
            .map(
              (p) => `<li>
              <button type="button" data-project-id="${p.id}">
                <strong>${escapeHtml(p.display_code || p.device_id)}</strong>
                <span>${escapeHtml(p.title || '')}</span>
                <span class="sysforge-hub-status">${escapeHtml(p.status || '')}</span>
              </button>
            </li>`
            )
            .join('')
        : `<li class="sysforge-classic-empty">No matches.</li>`;
    }
  } catch (err) {
    await _toast(err.message || String(err), 'error');
  }
}

async function reloadHub(container, deps) {
  const errEl = container.querySelector('#sysforge-hub-error');
  if (errEl) {
    errEl.hidden = true;
    errEl.textContent = '';
  }
  const flagged = Boolean(container._sysforgeHub?.includeArchived);
  try {
    const settings = await deps.api('/settings');
    const include =
      settings.include_archived_in_search ??
      settings.projects?.include_archived_in_search ??
      false;
    container._sysforgeHub.includeArchived = Boolean(include);
    const archCb = container.querySelector('#sysforge-hub-archived');
    if (archCb) archCb.checked = Boolean(include);

    const hub = await deps.api(
      `/projects/hub?include_archived=${flagged || include ? 1 : 0}`
    );
    renderList(
      container.querySelector('#sysforge-hub-active'),
      (hub.active || []).map((r) => ({
        kind: 'project',
        id: r.project_id,
        title: r.display_code || r.device_id,
        sub: [r.title, r.device_id].filter(Boolean).join(' · ') || r.client_name || '',
        status: r.status,
      }))
    );
    renderList(
      container.querySelector('#sysforge-hub-estimates'),
      (hub.estimates_not_accepted || []).map((r) => ({
        kind: 'invoice',
        id: r.invoice_id,
        title: r.invoice_name || r.client_info || `Invoice #${r.invoice_id}`,
        sub: 'Open estimate',
        status: '',
      }))
    );
    renderList(
      container.querySelector('#sysforge-hub-missing'),
      (hub.accepted_missing || []).map((r) => ({
        kind: 'invoice',
        id: r.invoice_id,
        title: r.device_label,
        sub: `Invoice #${r.invoice_id}`,
        status: '',
      }))
    );
  } catch (err) {
    if (errEl) {
      errEl.hidden = false;
      errEl.textContent = err.message || String(err);
    }
  }
}

function renderList(el, rows) {
  if (!el) return;
  if (!rows.length) {
    el.innerHTML = `<li class="sysforge-classic-empty">None.</li>`;
    return;
  }
  el.innerHTML = rows
    .map((r) => {
      const attr = r.kind === 'project' ? 'data-project-id' : 'data-invoice-id';
      return `<li>
        <button type="button" ${attr}="${r.id}">
          <strong>${escapeHtml(r.title)}</strong>
          <span>${escapeHtml(r.sub)}</span>
          ${r.status ? `<span class="sysforge-hub-status">${escapeHtml(r.status)}</span>` : ''}
        </button>
      </li>`;
    })
    .join('');
}

/**
 * @param {HTMLElement} container
 * @param {{ api: Function, navigate: Function }} deps
 */
export async function activateProjectsHub(container, deps) {
  container.querySelector('.sysforge-view-heading')?.focus?.({ preventScroll: true });
  await reloadHub(container, deps);
}

export function deactivateProjectsHub() {
  /* no-op */
}
