/**
 * Classic four-column Client Dashboard.
 * Columns: invoice cards | in-page preview | projects host | client info/edit.
 * Overlay search: persistent recent-6 (LastInteractedAt), clear keeps selection,
 * no auto-open when query equals display_name.
 *
 * View → invoice-view/:id
 * Edit → invoice-calculator?invoiceId=
 * New  → invoice-calculator?clientId=
 */

import {
  buildInvoiceEditRoute,
  buildInvoiceViewRoute,
  buildNewInvoiceRoute,
} from '../routes-contract.js';
import { createClientSearch } from '../clientSearch.js';
import {
  clearSearchQuery,
  pickClientFromSearch,
  shouldOpenClassicOverlay,
  trackRecentClient,
  MAX_RECENT_CLIENTS,
} from '../classic-selection.js';
import { startCreateProjectFromInvoice } from '../create-project-wizard.js';

function escapeHtml(s) {
  return String(s ?? '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

function formatMoney(cents) {
  const n = Number(cents || 0) / 100;
  return n.toLocaleString(undefined, { style: 'currency', currency: 'USD' });
}

function formatDate(iso) {
  if (!iso) return '';
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return String(iso).slice(0, 10);
  return d.toLocaleDateString(undefined, {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
  });
}

function clientLabel(c) {
  if (!c) return '';
  return c.display_name || c.displayName || '';
}

/**
 * @param {HTMLElement} container
 * @param {{
 *   api: (path: string, opts?: object) => Promise<object>,
 *   navigate: (routeKey: string, opts?: object) => void,
 *   apiBase?: string,
 * }} deps
 */
export function mountClientDashboard(container, deps) {
  if (container.dataset.mounted === '1') return;

  const apiBase =
    deps.apiBase ||
    `${typeof window !== 'undefined' ? window.location.origin : ''}/api/sysforge`;

  container.innerHTML = `
    <div class="sysforge-classic" data-classic="1">
      <div class="sysforge-classic-search-wrap">
        <label class="visually-hidden" for="sysforge-classic-search">Search clients</label>
        <input type="search" id="sysforge-classic-search" class="sysforge-classic-search"
          placeholder="Search by name, phone, or email..." autocomplete="off" />
        <ul id="sysforge-classic-overlay" class="sysforge-classic-overlay" hidden role="listbox"></ul>
      </div>
      <p class="sysforge-clients-error" id="sysforge-classic-error" hidden></p>
      <div class="sysforge-classic-grid">
        <section class="sysforge-classic-col sysforge-classic-invoices" aria-label="Invoices">
          <div class="sysforge-classic-col-head">
            <h4>Invoices</h4>
            <div class="sysforge-classic-col-actions">
              <button type="button" class="btn-secondary" id="sysforge-classic-refresh" title="Refresh">Refresh</button>
              <button type="button" class="btn-primary" id="sysforge-classic-new-invoice" disabled>Create invoice</button>
            </div>
          </div>
          <div id="sysforge-classic-invoice-rail" class="sysforge-classic-invoice-rail"></div>
        </section>
        <section class="sysforge-classic-col sysforge-classic-preview" aria-label="Invoice preview">
          <div id="sysforge-classic-preview-body" class="sysforge-classic-preview-body"></div>
        </section>
        <section class="sysforge-classic-col sysforge-classic-projects" aria-label="Projects">
          <h4>Projects</h4>
          <div id="sysforge-classic-projects-body" class="sysforge-classic-projects-body"></div>
        </section>
        <section class="sysforge-classic-col sysforge-classic-client" aria-label="Client info">
          <div class="sysforge-classic-col-head">
            <h4>Client info</h4>
            <button type="button" class="btn-secondary" id="sysforge-classic-edit-btn" hidden>Edit</button>
          </div>
          <div id="sysforge-classic-client-body" class="sysforge-classic-client-body"></div>
        </section>
      </div>
      <p class="sysforge-classic-footer-link">
        <button type="button" class="btn-secondary" id="sysforge-classic-all-clients">All clients</button>
      </p>
    </div>`;

  const state = {
    deps,
    selectedClient: null,
    searchListSelection: null,
    searchQuery: '',
    overlayOpen: false,
    sessionRecent: [],
    mruSeeded: false,
    invoices: [],
    projects: [],
    hasInvoices: false,
    selectedInvoiceId: null,
    previewInvoice: null,
    previewItems: [],
    hasPreview: false,
    isEditingClient: false,
    editDraft: null,
    overlayItems: [],
    highlightIndex: -1,
    suppressOverlayOnce: false,
  };

  const abortRef = { controller: null };
  const searcher = createClientSearch(apiBase, { debounceMs: 250, limit: 20 });

  container.dataset.mounted = '1';
  container._sysforgeClassic = state;
  container._sysforgeClientDashAbort = abortRef;
  container._sysforgeClassicSearcher = searcher;
  container._sysforgeClassicRender = () => renderAll(container);
  container._sysforgeClassicSelectClient = (client, opts) =>
    selectClient(container, client, opts);
  container._sysforgeClassicLoadInvoices = () => loadInvoices(container);
  container._sysforgeClassicLoadPreview = (id) => loadPreview(container, id);
  container._sysforgeClassicEnsureMru = () => ensureMruSeeded(container);

  const searchInput = container.querySelector('#sysforge-classic-search');
  const overlayEl = container.querySelector('#sysforge-classic-overlay');

  function syncOverlayWidth() {
    if (!searchInput || !overlayEl) return;
    const w = searchInput.getBoundingClientRect().width;
    if (w > 0) overlayEl.style.width = `${Math.round(w)}px`;
  }

  function setOverlayOpen(open) {
    state.overlayOpen = Boolean(open);
    if (overlayEl) {
      overlayEl.hidden = !state.overlayOpen;
      if (state.overlayOpen) syncOverlayWidth();
    }
  }

  function setError(msg) {
    const errorEl = container.querySelector('#sysforge-classic-error');
    if (!errorEl) return;
    if (msg) {
      errorEl.textContent = msg;
      errorEl.hidden = false;
    } else {
      errorEl.textContent = '';
      errorEl.hidden = true;
    }
  }

  function renderOverlay() {
    if (!overlayEl) return;
    const items = state.overlayItems || [];
    const emptyQ = !(state.searchQuery || '').trim();
    if (!items.length) {
      overlayEl.innerHTML = emptyQ
        ? `<li class="sysforge-classic-overlay-empty">Interact with a client to see them here.</li>`
        : `<li class="sysforge-classic-overlay-empty">No matches.</li>`;
      return;
    }
    const label = emptyQ
      ? `<li class="sysforge-classic-overlay-label" role="presentation">Recent clients</li>`
      : '';
    overlayEl.innerHTML =
      label +
      items
        .map((item, i) => {
          const c = item.client || item;
          const active = i === state.highlightIndex ? ' is-active' : '';
          return `<li class="sysforge-classic-overlay-item${active}" role="option"
            data-index="${i}" data-id="${c.id}">
            <span class="sysforge-classic-overlay-name">${escapeHtml(clientLabel(c))}</span>
            <span class="sysforge-classic-overlay-meta">${escapeHtml(
              [c.phone_number, c.email].filter(Boolean).join(' · ')
            )}</span>
          </li>`;
        })
        .join('');
  }

  function showRecentInOverlay() {
    state.overlayItems = (state.sessionRecent || []).map((c) => ({
      kind: 'match',
      client: c,
    }));
    state.highlightIndex = state.overlayItems.length ? 0 : -1;
    renderOverlay();
  }

  async function openOverlayForUser() {
    if (state.suppressOverlayOnce) {
      state.suppressOverlayOnce = false;
      setOverlayOpen(false);
      return;
    }
    if (!shouldOpenClassicOverlay(state.searchQuery, state.selectedClient)) {
      setOverlayOpen(false);
      return;
    }
    const q = (state.searchQuery || '').trim();
    if (!q) {
      await ensureMruSeeded(container);
      showRecentInOverlay();
      setOverlayOpen(true);
      return;
    }
    setOverlayOpen(true);
  }

  function onSearchInput() {
    const q = searchInput?.value || '';
    state.searchQuery = q;
    if (!(q || '').trim()) {
      const cleared = clearSearchQuery(state);
      state.searchQuery = cleared.searchQuery;
      state.searchListSelection = cleared.searchListSelection;
      searcher.cancel();
      showRecentInOverlay();
      // Keep overlay open only if focused; clear does not deselect client.
      if (document.activeElement === searchInput) {
        setOverlayOpen(true);
      }
      return;
    }
    if (!shouldOpenClassicOverlay(q, state.selectedClient)) {
      setOverlayOpen(false);
      searcher.cancel();
      return;
    }
    setOverlayOpen(true);
    searcher.search(q, (payload, err) => {
      if (err) {
        setError(err.message || String(err));
        return;
      }
      setError('');
      // Classic: matches only — no Add New sentinel.
      state.overlayItems = (payload?.results || []).map((c) => ({
        kind: 'match',
        client: c,
      }));
      state.highlightIndex = state.overlayItems.length ? 0 : -1;
      renderOverlay();
    });
  }

  async function applyPick(client) {
    if (!client) return;
    const next = pickClientFromSearch(state, client);
    state.searchListSelection = next.searchListSelection;
    state.selectedClient = next.selectedClient;
    state.searchQuery = next.searchQuery;
    state.overlayOpen = false;
    state.sessionRecent = trackRecentClient(state.sessionRecent, client);
    state.isEditingClient = false;
    state.editDraft = null;
    state.selectedInvoiceId = null;
    state.previewInvoice = null;
    state.previewItems = [];
    state.hasPreview = false;
    if (searchInput) searchInput.value = state.searchQuery;
    setOverlayOpen(false);
    renderAll(container);
    void touchClientMru(container, client.id);
    await loadInvoices(container);
  }

  searchInput?.addEventListener('input', () => onSearchInput());
  searchInput?.addEventListener('focus', () => {
    void openOverlayForUser();
  });
  searchInput?.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') {
      e.preventDefault();
      setOverlayOpen(false);
      return;
    }
    if (!state.overlayOpen) {
      if (e.key === 'ArrowDown') {
        e.preventDefault();
        void openOverlayForUser();
      }
      return;
    }
    const items = state.overlayItems || [];
    searcher.handleKeydown(e, {
      items,
      index: state.highlightIndex,
      onIndex: (n) => {
        state.highlightIndex = n;
        renderOverlay();
      },
      onSelect: (item) => {
        void applyPick(item.client || item);
      },
    });
    // Enter with no highlight → first item
    if (e.key === 'Enter' && state.highlightIndex < 0 && items.length) {
      e.preventDefault();
      void applyPick(items[0].client || items[0]);
    }
  });

  overlayEl?.addEventListener('mousedown', (e) => {
    // Prevent input blur before click registers.
    e.preventDefault();
  });
  overlayEl?.addEventListener('click', (e) => {
    const li = e.target.closest('[data-id]');
    if (!li) return;
    const id = Number(li.getAttribute('data-id'));
    const item = (state.overlayItems || []).find(
      (it) => Number((it.client || it).id) === id
    );
    if (item) void applyPick(item.client || item);
  });

  document.addEventListener(
    'pointerdown',
    (e) => {
      if (!state.overlayOpen) return;
      const wrap = container.querySelector('.sysforge-classic-search-wrap');
      if (wrap && !wrap.contains(e.target)) {
        setOverlayOpen(false);
      }
    },
    true
  );

  if (typeof ResizeObserver !== 'undefined' && searchInput) {
    const ro = new ResizeObserver(() => {
      if (state.overlayOpen) syncOverlayWidth();
    });
    ro.observe(searchInput);
    container._sysforgeClassicResize = ro;
  }

  container.querySelector('#sysforge-classic-new-invoice')?.addEventListener('click', () => {
    const client = state.selectedClient;
    if (!client?.id) return;
    if (typeof deps.navigateToNewInvoice === 'function') {
      deps.navigateToNewInvoice(client.id);
      return;
    }
    const target = buildNewInvoiceRoute(client.id);
    deps.navigate(target.routeKey, { params: target.params });
  });

  container.querySelector('#sysforge-classic-refresh')?.addEventListener('click', () => {
    void loadInvoices(container);
  });

  container.querySelector('#sysforge-classic-all-clients')?.addEventListener('click', () => {
    deps.navigate('clients');
  });

  container.querySelector('#sysforge-classic-edit-btn')?.addEventListener('click', () => {
    startEdit(container);
  });

  // Invoice rail: select card / View / Edit — bind once.
  container.querySelector('#sysforge-classic-invoice-rail')?.addEventListener('click', (e) => {
    const btn = e.target.closest('[data-action]');
    if (btn) {
      const id = btn.getAttribute('data-id');
      if (!id) return;
      const action = btn.getAttribute('data-action');
      if (action === 'view') {
        if (typeof deps.navigateToInvoiceViewer === 'function') {
          deps.navigateToInvoiceViewer(id);
          return;
        }
        const target = buildInvoiceViewRoute(id);
        deps.navigate(target.routeKey, { params: target.params });
        return;
      }
      if (action === 'edit') {
        if (typeof deps.navigateToInvoiceEdit === 'function') {
          deps.navigateToInvoiceEdit(id);
          return;
        }
        const target = buildInvoiceEditRoute(id);
        deps.navigate(target.routeKey, { params: target.params });
        return;
      }
    }
    const card = e.target.closest('[data-invoice-id]');
    if (card) {
      const id = Number(card.getAttribute('data-invoice-id'));
      if (id) void loadPreview(container, id);
    }
  });

  container.querySelector('#sysforge-classic-preview-body')?.addEventListener('click', (e) => {
    const btn = e.target.closest('[data-action]');
    if (!btn) return;
    const id = btn.getAttribute('data-id') || state.selectedInvoiceId;
    if (!id) return;
    const action = btn.getAttribute('data-action');
    if (action === 'view') {
      if (typeof deps.navigateToInvoiceViewer === 'function') {
        deps.navigateToInvoiceViewer(id);
        return;
      }
      const target = buildInvoiceViewRoute(id);
      deps.navigate(target.routeKey, { params: target.params });
      return;
    }
    if (action === 'edit') {
      if (typeof deps.navigateToInvoiceEdit === 'function') {
        deps.navigateToInvoiceEdit(id);
        return;
      }
      const target = buildInvoiceEditRoute(id);
      deps.navigate(target.routeKey, { params: target.params });
      return;
    }
    if (action === 'create-project') {
      void startCreateProjectFromInvoice({
        api: deps.api,
        navigate: deps.navigate,
        invoiceId: Number(id),
      }).then((projectId) => {
        if (projectId) void loadProjects(container);
      });
    }
  });

  container.querySelector('#sysforge-classic-client-body')?.addEventListener('click', (e) => {
    const btn = e.target.closest('[data-action]');
    if (!btn) return;
    const action = btn.getAttribute('data-action');
    if (action === 'save-client') {
      void saveClientEdit(container);
    } else if (action === 'cancel-client') {
      cancelEdit(container);
    }
  });

  container.querySelector('#sysforge-classic-projects-body')?.addEventListener('click', (e) => {
    const btn = e.target.closest('[data-project-id]');
    if (!btn) return;
    const id = btn.getAttribute('data-project-id');
    deps.navigate('project', { params: { id } });
  });

  renderAll(container);
}

function renderAll(container) {
  const state = container._sysforgeClassic;
  if (!state) return;
  renderInvoiceRail(container);
  renderPreview(container);
  renderProjects(container);
  renderClientColumn(container);
  const newBtn = container.querySelector('#sysforge-classic-new-invoice');
  if (newBtn) newBtn.disabled = !state.selectedClient?.id;
  const editBtn = container.querySelector('#sysforge-classic-edit-btn');
  if (editBtn) {
    editBtn.hidden = !state.selectedClient || state.isEditingClient;
  }
}

function renderInvoiceRail(container) {
  const state = container._sysforgeClassic;
  const rail = container.querySelector('#sysforge-classic-invoice-rail');
  if (!rail || !state) return;

  if (!state.selectedClient) {
    rail.innerHTML = `<p class="sysforge-classic-empty">Select a client first.</p>`;
    return;
  }
  if (!state.hasInvoices) {
    rail.innerHTML = `<p class="sysforge-classic-empty">No invoices yet. Create one with Create invoice.</p>`;
    return;
  }
  rail.innerHTML = (state.invoices || [])
    .map((inv) => {
      const selected =
        Number(inv.id) === Number(state.selectedInvoiceId) ? ' is-selected' : '';
      return `<button type="button" class="sysforge-classic-inv-card${selected}"
        data-invoice-id="${inv.id}">
        <span class="sysforge-classic-inv-name">${escapeHtml(
          inv.display_label || inv.name || `Invoice #${inv.id}`
        )}</span>
        <span class="sysforge-classic-inv-status">${escapeHtml(inv.status || '')}</span>
        <span class="sysforge-classic-inv-total">${formatMoney(inv.final_total_cents)}</span>
        ${inv.date_created ? `<span class="sysforge-classic-inv-date">${escapeHtml(formatDate(inv.date_created))}</span>` : ''}
      </button>`;
    })
    .join('');
}

function renderPreview(container) {
  const state = container._sysforgeClassic;
  const body = container.querySelector('#sysforge-classic-preview-body');
  if (!body || !state) return;

  if (!state.hasPreview || !state.previewInvoice) {
    body.innerHTML = `<p class="sysforge-classic-empty">Pick an invoice card on the left to preview it here.</p>`;
    return;
  }
  const inv = state.previewInvoice;
  const clientName =
    inv.client?.display_name ||
    state.selectedClient?.display_name ||
    inv.client_info ||
    '';
  const items = state.previewItems || [];
  const rows = items.length
    ? items
        .map(
          (it) => `<tr>
            <td>${escapeHtml(it.part_name || '')}</td>
            <td>${escapeHtml(String(it.quantity ?? (Number(it.quantity_milliunits || 0) / 1000)))}</td>
            <td>${formatMoney(it.unit_price_cents)}</td>
            <td>${formatMoney(it.line_total_cents)}</td>
          </tr>`
        )
        .join('')
    : `<tr><td colspan="4">No line items.</td></tr>`;

  body.innerHTML = `
    <div class="sysforge-classic-preview-toolbar">
      <h4 class="sysforge-classic-preview-title">${escapeHtml(
        inv.display_label || inv.name || `Invoice #${inv.id}`
      )}</h4>
      <div class="sysforge-classic-preview-actions">
        <button type="button" class="btn-primary" data-action="edit" data-id="${inv.id}">Edit</button>
        <button type="button" class="btn-secondary" data-action="view" data-id="${inv.id}">Full screen</button>
        <button type="button" class="btn-secondary" data-action="create-project" data-id="${inv.id}">Create project</button>
      </div>
    </div>
    <dl class="sysforge-classic-preview-meta">
      <div><dt>Client</dt><dd>${escapeHtml(clientName)}</dd></div>
      <div><dt>Total</dt><dd>${formatMoney(inv.final_total_cents)}</dd></div>
      <div><dt>Status</dt><dd>${escapeHtml(inv.status || '')}</dd></div>
      <div><dt>Date</dt><dd>${escapeHtml(formatDate(inv.date_created))}</dd></div>
    </dl>
    <table class="sysforge-clients-table sysforge-classic-preview-items">
      <thead><tr><th>Part</th><th>Qty</th><th>Unit</th><th>Line</th></tr></thead>
      <tbody>${rows}</tbody>
    </table>`;
}

function renderProjects(container) {
  const state = container._sysforgeClassic;
  const body = container.querySelector('#sysforge-classic-projects-body');
  if (!body || !state) return;
  if (!state.selectedClient) {
    body.innerHTML = `<p class="sysforge-classic-empty">Select a client first.</p>`;
    return;
  }
  const projects = state.projects || [];
  if (!projects.length) {
    body.innerHTML = `<p class="sysforge-classic-empty">No projects for this client.</p>`;
    return;
  }
  body.innerHTML = projects
    .map(
      (p) => `<button type="button" class="sysforge-classic-project-card" data-project-id="${p.id}">
        <span class="sysforge-classic-inv-name">${escapeHtml(p.device_id || '')}</span>
        <span class="sysforge-classic-inv-status">${escapeHtml(p.status || '')}</span>
        <span class="sysforge-classic-inv-date">${escapeHtml(p.title || '')}</span>
      </button>`
    )
    .join('');
}

function renderClientColumn(container) {
  const state = container._sysforgeClassic;
  const body = container.querySelector('#sysforge-classic-client-body');
  if (!body || !state) return;

  if (!state.selectedClient) {
    body.innerHTML = `<p class="sysforge-classic-empty">Pick a client to see details.</p>`;
    return;
  }
  const c = state.selectedClient;
  if (state.isEditingClient && state.editDraft) {
    const d = state.editDraft;
    body.innerHTML = `
      <div class="sysforge-classic-edit-form">
        <label class="sysforge-field">First
          <input type="text" id="sf-classic-first" value="${escapeHtml(d.first_name || '')}" />
        </label>
        <label class="sysforge-field">Last
          <input type="text" id="sf-classic-last" value="${escapeHtml(d.last_name || '')}" />
        </label>
        <label class="sysforge-field">Phone
          <input type="text" id="sf-classic-phone" value="${escapeHtml(d.phone_number || '')}" />
        </label>
        <label class="sysforge-field">Email
          <input type="text" id="sf-classic-email" value="${escapeHtml(d.email || '')}" />
        </label>
        <label class="sysforge-field">Address
          <input type="text" id="sf-classic-address" value="${escapeHtml(d.address || '')}" />
        </label>
        <label class="sysforge-field">Notes
          <textarea id="sf-classic-notes" rows="4">${escapeHtml(d.notes || '')}</textarea>
        </label>
        <div class="sysforge-classic-edit-actions">
          <button type="button" class="btn-primary" data-action="save-client">Save</button>
          <button type="button" class="btn-secondary" data-action="cancel-client">Cancel</button>
        </div>
      </div>`;
    return;
  }
  body.innerHTML = `
    <p class="sysforge-classic-client-name">${escapeHtml(clientLabel(c))}</p>
    <dl class="sysforge-classic-client-fields">
      <div><dt>Phone</dt><dd>${escapeHtml(c.phone_number || '—')}</dd></div>
      <div><dt>Email</dt><dd>${escapeHtml(c.email || '—')}</dd></div>
      <div><dt>Address</dt><dd>${escapeHtml(c.address || '—')}</dd></div>
      <div><dt>Notes</dt><dd class="sysforge-classic-notes">${escapeHtml(c.notes || '—')}</dd></div>
    </dl>`;
}

function startEdit(container) {
  const state = container._sysforgeClassic;
  if (!state?.selectedClient) return;
  const c = state.selectedClient;
  state.isEditingClient = true;
  state.editDraft = {
    first_name: c.first_name || '',
    last_name: c.last_name || '',
    phone_number: c.phone_number || '',
    email: c.email || '',
    address: c.address || '',
    notes: c.notes || '',
  };
  renderAll(container);
}

function cancelEdit(container) {
  const state = container._sysforgeClassic;
  if (!state) return;
  state.isEditingClient = false;
  state.editDraft = null;
  renderAll(container);
}

async function saveClientEdit(container) {
  const state = container._sysforgeClassic;
  const deps = state?.deps;
  if (!state?.selectedClient || !deps) return;
  const payload = {
    first_name: container.querySelector('#sf-classic-first')?.value || null,
    last_name: container.querySelector('#sf-classic-last')?.value || null,
    phone_number: container.querySelector('#sf-classic-phone')?.value || null,
    email: container.querySelector('#sf-classic-email')?.value || null,
    address: container.querySelector('#sf-classic-address')?.value || null,
    notes: container.querySelector('#sf-classic-notes')?.value || null,
  };
  try {
    const updated = await deps.api(`/clients/${encodeURIComponent(state.selectedClient.id)}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    state.selectedClient = updated;
    state.isEditingClient = false;
    state.editDraft = null;
    state.searchQuery = clientLabel(updated);
    const searchInput = container.querySelector('#sysforge-classic-search');
    if (searchInput) searchInput.value = state.searchQuery;
    state.sessionRecent = trackRecentClient(state.sessionRecent, updated);
    renderAll(container);
  } catch (err) {
    const errorEl = container.querySelector('#sysforge-classic-error');
    if (errorEl) {
      errorEl.textContent = err?.message || String(err);
      errorEl.hidden = false;
    }
  }
}

async function ensureMruSeeded(container) {
  const state = container._sysforgeClassic;
  const deps = state?.deps;
  if (!state || !deps) return;
  if (state.mruSeeded) return;
  try {
    const data = await deps.api(`/clients/recent?limit=${MAX_RECENT_CLIENTS}`);
    const clients = data.clients || [];
    // Merge API order with any session touches already tracked.
    const session = state.sessionRecent || [];
    if (session.length) {
      const seen = new Set(session.map((c) => Number(c.id)));
      const merged = [...session];
      for (const c of clients) {
        if (!seen.has(Number(c.id))) merged.push(c);
      }
      state.sessionRecent = merged.slice(0, MAX_RECENT_CLIENTS);
    } else {
      state.sessionRecent = clients.slice(0, MAX_RECENT_CLIENTS);
    }
    state.mruSeeded = true;
  } catch (_) {
    state.mruSeeded = true;
  }
}

async function touchClientMru(container, clientId) {
  const deps = container._sysforgeClassic?.deps;
  if (!deps?.api || clientId == null) return;
  try {
    await deps.api(`/clients/${encodeURIComponent(clientId)}/touch`, {
      method: 'POST',
    });
  } catch (_) {
    /* best-effort */
  }
}

async function selectClient(container, client, opts = {}) {
  const state = container._sysforgeClassic;
  if (!state || !client) return;
  if (state.isEditingClient) {
    state.isEditingClient = false;
    state.editDraft = null;
  }
  state.selectedClient = client;
  state.searchListSelection = client;
  state.searchQuery = clientLabel(client);
  state.sessionRecent = trackRecentClient(state.sessionRecent, client);
  state.selectedInvoiceId = null;
  state.previewInvoice = null;
  state.previewItems = [];
  state.hasPreview = false;
  state.overlayOpen = false;
  if (opts.suppressOverlay !== false) {
    state.suppressOverlayOnce = true;
  }
  const searchInput = container.querySelector('#sysforge-classic-search');
  if (searchInput) searchInput.value = state.searchQuery;
  const overlayEl = container.querySelector('#sysforge-classic-overlay');
  if (overlayEl) overlayEl.hidden = true;
  renderAll(container);
  if (opts.touch !== false) {
    void touchClientMru(container, client.id);
  }
  await loadInvoices(container);
}

async function loadInvoices(container) {
  const state = container._sysforgeClassic;
  const deps = state?.deps;
  const abortRef = container._sysforgeClientDashAbort;
  if (!state || !deps || !state.selectedClient?.id) {
    if (state) {
      state.invoices = [];
      state.hasInvoices = false;
    }
    renderInvoiceRail(container);
    return;
  }
  if (abortRef?.controller) {
    try {
      abortRef.controller.abort();
    } catch (_) {
      /* ignore */
    }
  }
  const ac = typeof AbortController !== 'undefined' ? new AbortController() : null;
  if (abortRef) abortRef.controller = ac;

  try {
    const invRes = await deps.api(
      `/clients/${encodeURIComponent(state.selectedClient.id)}/invoices`,
      { signal: ac?.signal }
    );
    if (ac?.signal?.aborted) return;
    state.invoices = invRes.invoices || [];
    state.hasInvoices = state.invoices.length > 0;
    // Keep preview if still in list; else clear.
    if (
      state.selectedInvoiceId &&
      !state.invoices.some((i) => Number(i.id) === Number(state.selectedInvoiceId))
    ) {
      state.selectedInvoiceId = null;
      state.previewInvoice = null;
      state.previewItems = [];
      state.hasPreview = false;
    }
    await loadProjects(container);
    renderAll(container);
  } catch (err) {
    if (err?.name === 'AbortError') return;
    const errorEl = container.querySelector('#sysforge-classic-error');
    if (errorEl) {
      errorEl.textContent = err?.message || String(err);
      errorEl.hidden = false;
    }
  }
}

async function loadProjects(container) {
  const state = container._sysforgeClassic;
  const deps = state?.deps;
  if (!state || !deps || !state.selectedClient?.id) {
    if (state) state.projects = [];
    renderProjects(container);
    return;
  }
  try {
    const res = await deps.api(
      `/projects?client_id=${encodeURIComponent(state.selectedClient.id)}`
    );
    state.projects = res.projects || [];
    renderProjects(container);
  } catch (_) {
    state.projects = [];
    renderProjects(container);
  }
}

async function loadPreview(container, invoiceId) {
  const state = container._sysforgeClassic;
  const deps = state?.deps;
  if (!state || !deps || !invoiceId) return;
  state.selectedInvoiceId = Number(invoiceId);
  renderInvoiceRail(container);
  try {
    const inv = await deps.api(`/invoices/${encodeURIComponent(invoiceId)}`);
    state.previewInvoice = inv;
    state.previewItems = inv.items || [];
    state.hasPreview = true;
    renderPreview(container);
  } catch (err) {
    state.hasPreview = false;
    state.previewInvoice = null;
    state.previewItems = [];
    renderPreview(container);
    const errorEl = container.querySelector('#sysforge-classic-error');
    if (errorEl) {
      errorEl.textContent = err?.message || String(err);
      errorEl.hidden = false;
    }
  }
}

/**
 * @param {HTMLElement} container
 * @param {Record<string, string>} [params]
 */
export async function activateClientDashboard(container, params = {}) {
  const heading = container.querySelector('.sysforge-view-heading');
  heading?.focus?.({ preventScroll: true });

  const state = container._sysforgeClassic;
  const deps = state?.deps;
  if (!state || !deps) return;

  const errorEl = container.querySelector('#sysforge-classic-error');
  if (errorEl) {
    errorEl.hidden = true;
    errorEl.textContent = '';
  }

  await ensureMruSeeded(container);

  const clientId = params.clientId;
  if (clientId) {
    // Deep link / return with clientId: load client, fill search, suppress overlay.
    if (
      !state.selectedClient ||
      Number(state.selectedClient.id) !== Number(clientId)
    ) {
      try {
        const client = await deps.api(`/clients/${encodeURIComponent(clientId)}`);
        await selectClient(container, client, { suppressOverlay: true });
        return;
      } catch (err) {
        if (errorEl) {
          errorEl.textContent = err?.message || String(err);
          errorEl.hidden = false;
        }
        return;
      }
    }
    // Same client already selected — refresh invoices (NotifyViewActivated).
    await loadInvoices(container);
    return;
  }

  // No clientId in route: keep in-memory selection; refresh rail on return.
  if (state.selectedClient?.id) {
    await loadInvoices(container);
    return;
  }

  // Autoselect last-used MRU when empty (VI1 default on; config can disable).
  let autoselect = true;
  try {
    const cfg = await deps.api('/settings');
    if (cfg && typeof cfg.client_mru_autoselect === 'boolean') {
      autoselect = cfg.client_mru_autoselect;
    }
  } catch (_) {
    /* default on */
  }
  if (autoselect && (state.sessionRecent || []).length > 0) {
    await selectClient(container, state.sessionRecent[0], {
      suppressOverlay: true,
      touch: false,
    });
    return;
  }
  renderAll(container);
}

/**
 * @param {HTMLElement} container
 */
export function deactivateClientDashboard(container) {
  const abortRef = container._sysforgeClientDashAbort;
  if (abortRef?.controller) {
    try {
      abortRef.controller.abort();
    } catch (_) {
      /* ignore */
    }
    abortRef.controller = null;
  }
  container._sysforgeClassicSearcher?.cancel?.();
}

export {
  shouldOpenClassicOverlay,
  clearSearchQuery,
  pickClientFromSearch,
  trackRecentClient,
  MAX_RECENT_CLIENTS,
};

export default {
  mountClientDashboard,
  activateClientDashboard,
  deactivateClientDashboard,
};
