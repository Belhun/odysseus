/**
 * Clients list / create / edit — CRUD + FTS typeahead + soft duplicate warnings.
 */

import { createClientSearch } from '../clientSearch.js';

/**
 * @param {HTMLElement} container
 * @param {{
 *   api: (path: string, opts?: object) => Promise<object>,
 *   navigate?: (routeKey: string, opts?: object) => void,
 * }} deps
 */
export function mountClients(container, deps) {
  if (container.dataset.mounted === '1') return;

  const apiBase = `${window.location.origin}/api/sysforge`;
  const searcher = createClientSearch(apiBase, { debounceMs: 250 });

  container.innerHTML = `
    <div class="sysforge-clients">
      <h3 class="sysforge-view-heading" tabindex="-1">Clients</h3>
      <p class="sysforge-dashboard-lead">Search, create, and edit shop clients. Soft-delete keeps invoice history.</p>

      <div class="sysforge-clients-toolbar">
        <div class="sysforge-clients-search-wrap">
          <input type="search" id="sysforge-clients-q" class="sysforge-clients-q"
            placeholder="Search name, phone, or email…" autocomplete="off" />
          <ul id="sysforge-clients-suggest" class="sysforge-clients-suggest" hidden role="listbox"></ul>
        </div>
        <button type="button" class="btn-primary" id="sysforge-clients-new">Add New</button>
      </div>

      <div id="sysforge-clients-dup" class="sysforge-clients-dup" hidden></div>
      <p class="sysforge-clients-error" id="sysforge-clients-error" hidden></p>

      <div id="sysforge-clients-main" class="sysforge-clients-main">
        <div id="sysforge-clients-list" class="sysforge-clients-list"></div>
        <form id="sysforge-clients-form" class="sysforge-clients-form" hidden>
          <h4 id="sysforge-clients-form-title">New client</h4>
          <input type="hidden" id="sf-client-id" value="" />
          <label class="sysforge-field"><span>First name</span>
            <input type="text" id="sf-first" maxlength="100" /></label>
          <label class="sysforge-field"><span>Last name</span>
            <input type="text" id="sf-last" maxlength="100" /></label>
          <label class="sysforge-field"><span>Nickname</span>
            <input type="text" id="sf-nick" maxlength="200" /></label>
          <label class="sysforge-field"><span>Phone</span>
            <input type="tel" id="sf-phone" /></label>
          <label class="sysforge-field"><span>Email</span>
            <input type="email" id="sf-email" /></label>
          <label class="sysforge-field"><span>Company</span>
            <input type="text" id="sf-company" maxlength="200" /></label>
          <label class="sysforge-field"><span>Address</span>
            <input type="text" id="sf-address" /></label>
          <label class="sysforge-field"><span>Notes</span>
            <textarea id="sf-notes" rows="2"></textarea></label>
          <label class="sysforge-field sysforge-field-check">
            <input type="checkbox" id="sf-incomplete" />
            <span>Incomplete record</span>
          </label>
          <div class="sysforge-settings-actions">
            <button type="submit" class="btn-primary" id="sf-save">Save</button>
            <button type="button" class="btn-secondary" id="sf-cancel">Cancel</button>
            <button type="button" class="btn-secondary" id="sf-delete" hidden>Soft-delete</button>
          </div>
        </form>
      </div>
    </div>`;

  const qInput = container.querySelector('#sysforge-clients-q');
  const suggestEl = container.querySelector('#sysforge-clients-suggest');
  const listEl = container.querySelector('#sysforge-clients-list');
  const form = container.querySelector('#sysforge-clients-form');
  const formTitle = container.querySelector('#sysforge-clients-form-title');
  const errorEl = container.querySelector('#sysforge-clients-error');
  const dupEl = container.querySelector('#sysforge-clients-dup');
  const deleteBtn = container.querySelector('#sf-delete');
  const idInput = container.querySelector('#sf-client-id');

  let _suggestItems = [];
  let _suggestIndex = -1;
  let _clients = [];
  let _dupOverride = false;
  let _pendingSave = null;

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

  function clearDup() {
    _dupOverride = false;
    if (dupEl) {
      dupEl.hidden = true;
      dupEl.innerHTML = '';
    }
  }

  function renderDup(duplicates) {
    if (!dupEl) return;
    const n = duplicates.length;
    dupEl.innerHTML = `
      <p class="sysforge-clients-dup-msg">
        ${n} existing client(s) share this phone or email. Select one or create a new client anyway.
      </p>
      <ul class="sysforge-clients-dup-list">
        ${duplicates
          .map(
            (c) => `
          <li>
            <button type="button" class="btn-secondary sysforge-dup-use" data-id="${c.id}">
              Use this client — ${escapeHtml(c.display_name || 'Unknown')}
            </button>
          </li>`
          )
          .join('')}
      </ul>
      <button type="button" class="btn-primary" id="sysforge-dup-anyway">Create new client anyway</button>`;
    dupEl.hidden = false;
    dupEl.querySelectorAll('.sysforge-dup-use').forEach((btn) => {
      btn.addEventListener('click', () => {
        const id = Number(btn.getAttribute('data-id'));
        clearDup();
        openEdit(id);
      });
    });
    dupEl.querySelector('#sysforge-dup-anyway')?.addEventListener('click', async () => {
      _dupOverride = true;
      dupEl.hidden = true;
      if (_pendingSave) {
        await doSave(_pendingSave);
        _pendingSave = null;
      }
    });
  }

  function escapeHtml(s) {
    return String(s)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');
  }

  function renderSuggest(items) {
    _suggestItems = items || [];
    _suggestIndex = -1;
    if (!suggestEl) return;
    if (!_suggestItems.length) {
      suggestEl.hidden = true;
      suggestEl.innerHTML = '';
      return;
    }
    suggestEl.innerHTML = _suggestItems
      .map((item, i) => {
        if (item.kind === 'add_new') {
          return `<li role="option" data-i="${i}" class="sysforge-suggest-add">Add New — ${escapeHtml(item.query)}</li>`;
        }
        const c = item.client;
        const sub = [c.phone_number, c.email].filter(Boolean).join(' · ');
        return `<li role="option" data-i="${i}">${escapeHtml(c.display_name || 'Unknown')}${
          sub ? `<span class="sysforge-suggest-sub">${escapeHtml(sub)}</span>` : ''
        }</li>`;
      })
      .join('');
    suggestEl.hidden = false;
  }

  function highlightSuggest() {
    suggestEl?.querySelectorAll('li').forEach((li, i) => {
      li.classList.toggle('is-active', i === _suggestIndex);
    });
  }

  function selectSuggestItem(item) {
    suggestEl.hidden = true;
    if (!item) return;
    if (item.kind === 'add_new') {
      openCreate({ first_name: item.query });
      return;
    }
    openEdit(item.client.id);
  }

  function renderList(clients) {
    _clients = clients || [];
    if (!listEl) return;
    if (!_clients.length) {
      listEl.innerHTML = `<p class="sysforge-clients-empty">No clients yet. Search or Add New.</p>`;
      return;
    }
    listEl.innerHTML = `
      <table class="sysforge-clients-table">
        <thead><tr><th>Name</th><th>Phone</th><th>Email</th><th></th></tr></thead>
        <tbody>
          ${_clients
            .map(
              (c) => `
            <tr data-id="${c.id}">
              <td>${escapeHtml(c.display_name || '')}${c.is_incomplete ? ' <em>(incomplete)</em>' : ''}</td>
              <td>${escapeHtml(c.phone_number || '')}</td>
              <td>${escapeHtml(c.email || '')}</td>
              <td>
                <button type="button" class="btn-secondary sysforge-client-hub" data-id="${c.id}">Invoices</button>
                <button type="button" class="btn-secondary sysforge-client-open" data-id="${c.id}">Edit</button>
              </td>
            </tr>`
            )
            .join('')}
        </tbody>
      </table>`;
    listEl.querySelectorAll('.sysforge-client-open').forEach((btn) => {
      btn.addEventListener('click', () => openEdit(Number(btn.getAttribute('data-id'))));
    });
    listEl.querySelectorAll('.sysforge-client-hub').forEach((btn) => {
      btn.addEventListener('click', () => {
        const id = Number(btn.getAttribute('data-id'));
        if (!id || typeof deps.navigate !== 'function') return;
        deps.navigate('client-dashboard', { params: { clientId: id } });
      });
    });
  }

  function readForm() {
    return {
      first_name: container.querySelector('#sf-first')?.value || null,
      last_name: container.querySelector('#sf-last')?.value || null,
      nickname: container.querySelector('#sf-nick')?.value || null,
      phone_number: container.querySelector('#sf-phone')?.value || null,
      email: container.querySelector('#sf-email')?.value || null,
      company: container.querySelector('#sf-company')?.value || null,
      address: container.querySelector('#sf-address')?.value || null,
      notes: container.querySelector('#sf-notes')?.value || null,
      is_incomplete: Boolean(container.querySelector('#sf-incomplete')?.checked),
    };
  }

  function fillForm(c) {
    idInput.value = c?.id != null ? String(c.id) : '';
    container.querySelector('#sf-first').value = c?.first_name || '';
    container.querySelector('#sf-last').value = c?.last_name || '';
    container.querySelector('#sf-nick').value = c?.nickname || '';
    container.querySelector('#sf-phone').value = c?.phone_number || '';
    container.querySelector('#sf-email').value = c?.email || '';
    container.querySelector('#sf-company').value = c?.company || '';
    container.querySelector('#sf-address').value = c?.address || '';
    container.querySelector('#sf-notes').value = c?.notes || '';
    container.querySelector('#sf-incomplete').checked = Boolean(c?.is_incomplete);
  }

  function openCreate(seed = {}) {
    clearDup();
    showError('');
    formTitle.textContent = 'New client';
    fillForm({ is_incomplete: Boolean(seed.first_name && !seed.last_name), ...seed });
    if (seed.first_name && !seed.last_name) {
      container.querySelector('#sf-incomplete').checked = true;
    }
    deleteBtn.hidden = true;
    form.hidden = false;
    listEl.hidden = true;
    container.querySelector('#sf-first')?.focus();
  }

  async function openEdit(id) {
    clearDup();
    showError('');
    try {
      const c = await deps.api(`/clients/${id}`);
      formTitle.textContent = 'Edit client';
      fillForm(c);
      deleteBtn.hidden = false;
      form.hidden = false;
      listEl.hidden = true;
    } catch (err) {
      showError(err?.message || String(err));
    }
  }

  function closeForm() {
    form.hidden = true;
    listEl.hidden = false;
    clearDup();
    showError('');
  }

  async function reloadList() {
    const data = await deps.api('/clients');
    renderList(data.clients || []);
  }

  async function doSave(body) {
    showError('');
    const id = idInput.value ? Number(idInput.value) : null;
    try {
      if (id) {
        await deps.api(`/clients/${id}`, {
          method: 'PUT',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(body),
        });
      } else {
        await deps.api('/clients', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(body),
        });
      }
      closeForm();
      await reloadList();
    } catch (err) {
      showError(err?.message || String(err));
    }
  }

  form?.addEventListener('submit', async (e) => {
    e.preventDefault();
    const body = readForm();
    const id = idInput.value ? Number(idInput.value) : null;

    if (!id && !_dupOverride) {
      try {
        const dup = await deps.api('/clients/duplicates', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            phone: body.phone_number,
            email: body.email,
            name: [body.first_name, body.last_name].filter(Boolean).join(' ') || null,
          }),
        });
        if ((dup.duplicates || []).length) {
          _pendingSave = body;
          renderDup(dup.duplicates);
          return;
        }
      } catch (_) {
        /* non-blocking: proceed to save */
      }
    }
    await doSave(body);
    _dupOverride = false;
  });

  container.querySelector('#sf-cancel')?.addEventListener('click', () => {
    closeForm();
    reloadList().catch(() => {});
  });

  deleteBtn?.addEventListener('click', async () => {
    const id = idInput.value ? Number(idInput.value) : null;
    if (!id) return;
    if (!window.confirm('Soft-delete this client? They will leave search but stay on past invoices.')) {
      return;
    }
    try {
      await deps.api(`/clients/${id}`, { method: 'DELETE' });
      closeForm();
      await reloadList();
    } catch (err) {
      showError(err?.message || String(err));
    }
  });

  container.querySelector('#sysforge-clients-new')?.addEventListener('click', () => {
    openCreate();
  });

  qInput?.addEventListener('input', () => {
    searcher.search(qInput.value, (payload, err) => {
      if (err) {
        showError(err.message);
        renderSuggest([]);
        return;
      }
      showError('');
      renderSuggest(payload?.items || []);
    });
  });

  qInput?.addEventListener('keydown', (e) => {
    searcher.handleKeydown(e, {
      items: _suggestItems,
      index: _suggestIndex,
      onIndex: (n) => {
        _suggestIndex = n;
        highlightSuggest();
      },
      onSelect: (item) => selectSuggestItem(item),
    });
  });

  suggestEl?.addEventListener('mousedown', (e) => {
    const li = e.target.closest('li[data-i]');
    if (!li) return;
    e.preventDefault();
    const i = Number(li.getAttribute('data-i'));
    selectSuggestItem(_suggestItems[i]);
  });

  qInput?.addEventListener('blur', () => {
    setTimeout(() => {
      if (suggestEl) suggestEl.hidden = true;
    }, 150);
  });

  container.dataset.mounted = '1';
  container._sysforgeReloadClients = reloadList;
  container._sysforgeAbortClients = () => searcher.cancel();
}

/**
 * @param {HTMLElement} container
 */
export async function activateClients(container) {
  const heading = container.querySelector('.sysforge-view-heading');
  heading?.focus?.({ preventScroll: true });
  if (typeof container._sysforgeReloadClients === 'function') {
    try {
      await container._sysforgeReloadClients();
    } catch (err) {
      const errorEl = container.querySelector('#sysforge-clients-error');
      if (errorEl) {
        errorEl.textContent = err?.message || String(err);
        errorEl.hidden = false;
      }
    }
  }
}

/**
 * @param {HTMLElement} container
 */
export function deactivateClients(container) {
  if (typeof container._sysforgeAbortClients === 'function') {
    container._sysforgeAbortClients();
  }
}
