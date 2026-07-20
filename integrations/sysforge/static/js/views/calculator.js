/**
 * Invoice calculator: create / edit same-id / save-as-new.
 * UX: keyboard-first, matches-before-Add-New, edit-load client dropdown guard.
 * Autosave: reuses drafts-autosave controller (flush on leave, clear on save).
 */

import { createClientSearch } from '../clientSearch.js';
import { createDraftAutosaveController } from '../drafts-autosave.js';
import { openDraftNameDialog, defaultDraftNamePrefill } from '../draft-name-dialog.js';
import { startCreateProjectFromInvoice } from '../create-project-wizard.js';

const PART_MATCH_CAP = 8;
const CLIENT_MATCH_CAP = 5;

async function _toast(message, kind) {
  try {
    const ui = await import('/static/js/ui.js');
    if (typeof ui.showToast === 'function') {
      const map = kind === 'error' ? 'error' : kind === 'info' ? 'info' : 'success';
      ui.showToast(message, map);
      return;
    }
  } catch (_) {
    /* fall through */
  }
  console.log(message);
}

/** Edit-load guard: hide overlay when query equals selected display_name. */
export function shouldShowClientDropdown(query, selectedClient) {
  if (!selectedClient) return true;
  const q = (query || '').trim().toLowerCase();
  const name = String(selectedClient.display_name || selectedClient.displayName || '')
    .trim()
    .toLowerCase();
  if (!q || !name) return true;
  return q !== name;
}

function _defaultInvoiceName(clientName) {
  const d = new Date();
  const mm = String(d.getUTCMonth() + 1).padStart(2, '0');
  const dd = String(d.getUTCDate()).padStart(2, '0');
  const yyyy = d.getUTCFullYear();
  const client = (clientName || '').trim() || 'No Client';
  return `${client} - ${mm}/${dd}/${yyyy}`;
}

function _emptyDraft(taxBps) {
  const taxPercent = (Number(taxBps) || 775) / 100;
  return {
    id: '',
    name: '',
    clientId: null,
    clientName: null,
    clientPhone: null,
    clientEmail: null,
    items: [],
    includeTax: true,
    includeShipping: false,
    taxRate: taxPercent,
    taxRateBps: Number(taxBps) || 775,
    shippingRate: 0,
    shippingRateCents: 0,
    partsSubtotal: 0,
    laborCost: 0,
    shippingCost: 0,
    taxAmount: 0,
    finalTotal: 0,
    invoiceWasSaved: false,
  };
}

function _lineFromApi(it) {
  return {
    partId: it.part_id ?? null,
    partName: it.part_name || '',
    sku: it.sku || null,
    quantity: (Number(it.quantity_milliunits) || 1000) / 1000,
    unitPrice: (Number(it.unit_price_cents) || 0) / 100,
    discountType: it.discount_type || 'None',
    discountValue: it.discount_value || 0,
    isTaxable: it.is_taxable !== false,
    itemType: it.item_type || 'Part',
    sortOrder: it.sort_order || 0,
    supplierId: it.supplier_id ?? null,
  };
}

function _itemsForApi(items) {
  return (items || []).map((it, idx) => ({
    part_id: it.partId ?? null,
    part_name: String(it.partName || '').trim(),
    sku: it.sku || null,
    quantity_milliunits: Math.max(1, Math.round(Number(it.quantity) * 1000) || 1000),
    unit_price_cents: Math.max(0, Math.round(Number(it.unitPrice) * 100) || 0),
    discount_type: it.discountType || 'None',
    discount_value: Number(it.discountValue) || 0,
    is_taxable: it.isTaxable !== false,
    sort_order: idx,
    item_type: it.itemType || 'Part',
    supplier_id: it.supplierId ?? null,
  }));
}

function _money(cents) {
  return `$${(Number(cents) / 100).toFixed(2)}`;
}

function _openInvoiceNameDialog(opts) {
  return openDraftNameDialog({
    ...opts,
    prefill: opts.prefill,
    onSave: async (name) => {
      const title = document.getElementById('sysforge-draft-dialog-title');
      if (title) title.textContent = 'Save Invoice';
      await opts.onSave(name);
    },
  });
}

/**
 * @param {HTMLElement} container
 * @param {{
 *   api: (path: string, opts?: object) => Promise<object>,
 *   navigate?: (routeId: string, opts?: object) => void,
 * }} deps
 */
export function mountCalculator(container, deps) {
  if (container.dataset.mounted === '1') return;

  const apiBase = `${window.location.origin}/api/sysforge`;
  const clientSearch = createClientSearch(apiBase, {
    debounceMs: 250,
    limit: CLIENT_MATCH_CAP,
  });

  let _draft = _emptyDraft(775);
  let _editingInvoiceId = null;
  let _selectedClient = null;
  let _isSaving = false;
  let _isLoading = false;
  let _loadAbort = null;
  let _clientItems = [];
  let _clientIndex = -1;
  let _partItems = [];
  let _partIndex = -1;
  let _partTimer = null;
  let _partAbort = null;
  let _settingsLoaded = false;
  let _devices = [];
  let _hasWorkOrder = false;
  let _invoiceStatus = 'Estimate';
  let _invoiceFinalized = false;
  let _pricePreview = [];

  const controller = createDraftAutosaveController({
    api: deps.api,
    getSnapshot: () => ({
      ..._draft,
      items: [...(_draft.items || [])],
      clientId: _selectedClient?.id ?? _draft.clientId,
      clientName:
        _selectedClient?.display_name ||
        _selectedClient?.displayName ||
        _draft.clientName,
    }),
    hasItems: () => Array.isArray(_draft.items) && _draft.items.length > 0,
    onRecover: (draft) => {
      applyDraftSnapshot(draft);
      render();
    },
    toast: _toast,
  });

  container.innerHTML = `
    <div class="sysforge-calculator">
      <h3 class="sysforge-view-heading" tabindex="-1">Quick Invoice Calculator</h3>
      <p class="sysforge-dashboard-lead" id="sysforge-calc-mode">New estimate</p>

      <div class="sysforge-calc-client-row">
        <label class="sysforge-field sysforge-calc-client-wrap">
          <span>Client</span>
          <input type="search" id="sysforge-calc-client" class="sysforge-clients-q"
            placeholder="Search client…" autocomplete="off" />
          <ul id="sysforge-calc-client-suggest" class="sysforge-clients-suggest" hidden role="listbox"></ul>
        </label>
      </div>

      <div class="sysforge-calc-quick">
        <label class="sysforge-field">
          <span>Quick add part</span>
          <input type="text" id="sysforge-calc-quick" placeholder="Part name…" autocomplete="off" />
          <ul id="sysforge-calc-part-suggest" class="sysforge-clients-suggest" hidden role="listbox"></ul>
        </label>
      </div>

      <div class="sysforge-calc-lines-wrap">
        <table class="sysforge-calc-lines" id="sysforge-calc-lines">
          <thead>
            <tr>
              <th>Name</th>
              <th>Type</th>
              <th>Qty</th>
              <th>Price</th>
              <th></th>
            </tr>
          </thead>
          <tbody id="sysforge-calc-tbody"></tbody>
        </table>
        <p class="sysforge-clients-empty" id="sysforge-calc-empty" hidden>No line items yet.</p>
      </div>

      <div class="sysforge-calc-devices">
        <h4>Devices</h4>
        <div class="sysforge-calc-device-add">
          <input type="text" id="sysforge-calc-device-label" placeholder="Device label (e.g. iPhone 14)" />
          <button type="button" class="btn-secondary" id="sysforge-calc-add-device">Add device</button>
        </div>
        <ul id="sysforge-calc-device-list" class="sysforge-hub-list"></ul>
      </div>

      <div class="sysforge-calc-toggles">
        <label class="sysforge-field-check">
          <input type="checkbox" id="sysforge-calc-tax" checked />
          <span>Include tax</span>
        </label>
        <label class="sysforge-field-check">
          <input type="checkbox" id="sysforge-calc-ship" />
          <span>Include shipping</span>
        </label>
        <label class="sysforge-field">
          <span>Shipping $</span>
          <input type="number" id="sysforge-calc-ship-rate" min="0" step="0.01" value="0" />
        </label>
      </div>

      <div class="sysforge-calc-totals" id="sysforge-calc-totals"></div>

      <div class="sysforge-calc-toolbar">
        <button type="button" class="btn-primary" id="sysforge-calc-save">Save</button>
        <button type="button" class="btn-secondary" id="sysforge-calc-save-as-new" hidden>Save as new</button>
        <button type="button" class="btn-secondary" id="sysforge-calc-update-prices" hidden>Update prices</button>
        <button type="button" class="btn-secondary" id="sysforge-calc-accept" hidden>Mark client accepted</button>
        <button type="button" class="btn-secondary" id="sysforge-calc-save-draft">Save draft</button>
        <button type="button" class="btn-secondary" id="sysforge-calc-clear">Clear</button>
      </div>
      <dialog id="sysforge-calc-price-dialog" class="sysforge-calc-price-dialog">
        <form method="dialog" class="sysforge-parts-form">
          <h4>Update line prices</h4>
          <p class="sysforge-dashboard-lead">
            Preview catalog (or history) prices before applying. Cancel leaves the invoice unchanged.
          </p>
          <div id="sysforge-calc-price-table-wrap"></div>
          <p class="sysforge-parts-error" id="sysforge-calc-price-error" hidden></p>
          <div class="sysforge-parts-form-actions">
            <button type="submit" value="cancel" class="btn-secondary">Cancel</button>
            <button type="button" class="btn-primary" id="sysforge-calc-price-apply">Confirm apply</button>
          </div>
        </form>
      </dialog>
      <p class="sysforge-calc-state" id="sysforge-calc-state"></p>
    </div>`;

  const clientInput = container.querySelector('#sysforge-calc-client');
  const clientSuggest = container.querySelector('#sysforge-calc-client-suggest');
  const quickInput = container.querySelector('#sysforge-calc-quick');
  const partSuggest = container.querySelector('#sysforge-calc-part-suggest');
  const tbody = container.querySelector('#sysforge-calc-tbody');
  const emptyEl = container.querySelector('#sysforge-calc-empty');
  const taxCb = container.querySelector('#sysforge-calc-tax');
  const shipCb = container.querySelector('#sysforge-calc-ship');
  const shipRate = container.querySelector('#sysforge-calc-ship-rate');
  const totalsEl = container.querySelector('#sysforge-calc-totals');
  const modeEl = container.querySelector('#sysforge-calc-mode');
  const saveBtn = container.querySelector('#sysforge-calc-save');
  const saveAsNewBtn = container.querySelector('#sysforge-calc-save-as-new');
  const updatePricesBtn = container.querySelector('#sysforge-calc-update-prices');
  const acceptBtn = container.querySelector('#sysforge-calc-accept');
  const stateEl = container.querySelector('#sysforge-calc-state');
  const deviceList = container.querySelector('#sysforge-calc-device-list');
  const deviceLabelInput = container.querySelector('#sysforge-calc-device-label');
  const priceDialog = container.querySelector('#sysforge-calc-price-dialog');
  const priceTableWrap = container.querySelector('#sysforge-calc-price-table-wrap');
  const priceErrorEl = container.querySelector('#sysforge-calc-price-error');
  const priceApplyBtn = container.querySelector('#sysforge-calc-price-apply');

  function markDirty() {
    controller.markDirty();
    recomputeLocalTotals();
    renderTotals();
    renderState();
  }

  function recomputeLocalTotals() {
    const items = _draft.items || [];
    let parts = 0;
    let labor = 0;
    let misc = 0;
    let taxable = 0;
    for (const it of items) {
      const line = Math.round(Number(it.quantity) * Number(it.unitPrice) * 100) || 0;
      const type = it.itemType || 'Part';
      if (type === 'Part') parts += line;
      else if (type === 'Labor') labor += line;
      else misc += line;
      if (it.isTaxable !== false || type === 'Part') taxable += line;
    }
    const taxBps = _draft.taxRateBps || 775;
    const tax = taxCb?.checked
      ? Math.round((taxable * taxBps) / 10000)
      : 0;
    const shipCents = shipCb?.checked
      ? Math.round(Number(shipRate?.value || 0) * 100) || 0
      : 0;
    _draft.partsSubtotal = parts / 100;
    _draft.laborCost = labor / 100;
    _draft.taxAmount = tax / 100;
    _draft.shippingCost = shipCents / 100;
    _draft.finalTotal = (parts + labor + misc + tax + shipCents) / 100;
    _draft.includeTax = Boolean(taxCb?.checked);
    _draft.includeShipping = Boolean(shipCb?.checked);
    _draft.shippingRateCents = Math.round(Number(shipRate?.value || 0) * 100) || 0;
  }

  function applyDraftSnapshot(draft) {
    _draft = { ..._emptyDraft(_draft.taxRateBps), ...draft };
    _editingInvoiceId = null;
    _invoiceStatus = 'Estimate';
    _invoiceFinalized = false;
    if (draft.clientId) {
      _selectedClient = {
        id: draft.clientId,
        display_name: draft.clientName || '',
      };
      if (clientInput) clientInput.value = draft.clientName || '';
    }
    if (taxCb) taxCb.checked = draft.includeTax !== false;
    if (shipCb) shipCb.checked = Boolean(draft.includeShipping);
    if (shipRate) {
      shipRate.value = String(
        draft.shippingRateCents != null
          ? Number(draft.shippingRateCents) / 100
          : draft.shippingRate || 0
      );
    }
  }

  function hideClientSuggest() {
    if (clientSuggest) clientSuggest.hidden = true;
    _clientItems = [];
    _clientIndex = -1;
  }

  function renderClientSuggest(items) {
    _clientItems = items || [];
    _clientIndex = _clientItems.length ? 0 : -1;
    if (!clientSuggest) return;
    if (!_clientItems.length) {
      clientSuggest.hidden = true;
      clientSuggest.innerHTML = '';
      return;
    }
    clientSuggest.innerHTML = _clientItems
      .map((item, i) => {
        if (item.kind === 'add_new') {
          return `<li role="option" data-idx="${i}" class="${i === _clientIndex ? 'is-active' : ''}">
            Add New: <strong>${escapeHtml(item.query)}</strong></li>`;
        }
        const c = item.client;
        const label = c.display_name || c.displayName || `${c.first_name || ''} ${c.last_name || ''}`.trim();
        return `<li role="option" data-idx="${i}" class="${i === _clientIndex ? 'is-active' : ''}">${escapeHtml(label)}</li>`;
      })
      .join('');
    clientSuggest.hidden = false;
  }

  function escapeHtml(s) {
    return String(s || '')
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');
  }

  function selectClientItem(item) {
    if (!item) return;
    if (item.kind === 'add_new') {
      createIncompleteClient(item.query);
      return;
    }
    const c = item.client;
    _selectedClient = c;
    _draft.clientId = c.id;
    _draft.clientName = c.display_name || c.displayName || '';
    if (clientInput) clientInput.value = _draft.clientName;
    hideClientSuggest();
    markDirty();
    if (c?.id != null) {
      void deps.api(`/clients/${encodeURIComponent(c.id)}/touch`, { method: 'POST' }).catch(
        () => {}
      );
    }
  }

  async function createIncompleteClient(query) {
    const parts = String(query || '').trim().split(/\s+/);
    const first = parts[0] || query;
    const last = parts.slice(1).join(' ') || null;
    try {
      const created = await deps.api('/clients', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          first_name: first,
          last_name: last,
          is_incomplete: true,
        }),
      });
      _selectedClient = created;
      _draft.clientId = created.id;
      _draft.clientName = created.display_name || query;
      if (clientInput) clientInput.value = _draft.clientName;
      hideClientSuggest();
      markDirty();
      await _toast('Client created', 'success');
    } catch (err) {
      await _toast(err?.message || String(err), 'error');
    }
  }

  function runClientSearch(query) {
    // Dropdown guard: selected client + query == display_name → stay closed.
    if (!shouldShowClientDropdown(query, _selectedClient)) {
      clientSearch.cancel();
      hideClientSuggest();
      return;
    }
    clientSearch.search(query, (payload, err) => {
      if (err) {
        hideClientSuggest();
        return;
      }
      if (!payload || !payload.query) {
        hideClientSuggest();
        return;
      }
      // Cap matches at 5, then Add New (buildItems already appends Add New).
      const matches = (payload.results || []).slice(0, CLIENT_MATCH_CAP);
      const items = clientSearch.buildItems(matches, payload.query);
      renderClientSuggest(items);
    });
  }

  function hidePartSuggest() {
    if (partSuggest) partSuggest.hidden = true;
    _partItems = [];
    _partIndex = -1;
  }

  function renderPartSuggest(items) {
    _partItems = items || [];
    _partIndex = _partItems.length ? 0 : -1;
    if (!partSuggest) return;
    if (!_partItems.length) {
      partSuggest.hidden = true;
      return;
    }
    partSuggest.innerHTML = _partItems
      .map((p, i) => {
        const price = _money(p.base_price_cents || 0);
        const ph = p.is_placeholder ? ' (placeholder)' : '';
        return `<li role="option" data-idx="${i}" class="${i === _partIndex ? 'is-active' : ''}">
          ${escapeHtml(p.name)} · ${price}${ph}</li>`;
      })
      .join('');
    partSuggest.hidden = false;
  }

  function searchParts(query) {
    if (_partTimer) clearTimeout(_partTimer);
    if (_partAbort) _partAbort.abort();
    const q = (query || '').trim();
    if (!q) {
      hidePartSuggest();
      return;
    }
    _partTimer = setTimeout(async () => {
      _partAbort = new AbortController();
      try {
        const res = await fetch(
          `${apiBase}/parts/search?q=${encodeURIComponent(q)}&mode=autocomplete&limit=${PART_MATCH_CAP}`,
          { credentials: 'same-origin', signal: _partAbort.signal }
        );
        const data = await res.json().catch(() => ({}));
        if (!res.ok) throw new Error(data.detail || 'Part search failed');
        renderPartSuggest(data.items || []);
      } catch (err) {
        if (err?.name === 'AbortError') return;
        hidePartSuggest();
      }
    }, 200);
  }

  function addLine(partial) {
    const items = [...(_draft.items || [])];
    items.push({
      partId: partial.partId ?? null,
      partName: partial.partName || '',
      sku: partial.sku || null,
      quantity: partial.quantity != null ? partial.quantity : 1,
      unitPrice: partial.unitPrice != null ? partial.unitPrice : 0,
      discountType: 'None',
      discountValue: 0,
      isTaxable: true,
      itemType: partial.itemType || 'Part',
      sortOrder: items.length,
      supplierId: null,
    });
    _draft.items = items;
    hidePartSuggest();
    if (quickInput) quickInput.value = '';
    markDirty();
    renderLines();
    // Focus new line name (keyboard-first).
    const rows = tbody?.querySelectorAll('tr');
    const last = rows?.[rows.length - 1];
    last?.querySelector('.sf-line-name')?.focus();
  }

  function selectPart(part) {
    addLine({
      partId: part.id,
      partName: part.name,
      sku: part.sku,
      unitPrice: (Number(part.base_price_cents) || 0) / 100,
      itemType: 'Part',
    });
  }

  function renderLines() {
    const items = _draft.items || [];
    if (emptyEl) emptyEl.hidden = items.length > 0;
    if (!tbody) return;
    tbody.innerHTML = items
      .map(
        (it, i) => `
      <tr data-idx="${i}">
        <td><input type="text" class="sf-line-name" data-idx="${i}" value="${escapeHtml(it.partName)}" /></td>
        <td>
          <select class="sf-line-type" data-idx="${i}">
            ${['Part', 'Labor', 'Misc']
              .map(
                (t) =>
                  `<option value="${t}" ${it.itemType === t ? 'selected' : ''}>${t}</option>`
              )
              .join('')}
          </select>
        </td>
        <td><input type="number" class="sf-line-qty" data-idx="${i}" min="0.001" step="0.001" value="${it.quantity}" /></td>
        <td><input type="number" class="sf-line-price" data-idx="${i}" min="0" step="0.01" value="${it.unitPrice}" /></td>
        <td><button type="button" class="btn-secondary sf-line-del" data-idx="${i}" aria-label="Remove">×</button></td>
      </tr>`
      )
      .join('');
  }

  function renderTotals() {
    if (!totalsEl) return;
    recomputeLocalTotals();
    totalsEl.innerHTML = `
      <div>Parts: ${_money(_draft.partsSubtotal * 100)}</div>
      <div>Labor: ${_money(_draft.laborCost * 100)}</div>
      <div>Tax: ${_money(_draft.taxAmount * 100)}</div>
      <div>Shipping: ${_money(_draft.shippingCost * 100)}</div>
      <div class="sysforge-calc-final"><strong>Total: ${_money(_draft.finalTotal * 100)}</strong></div>`;
  }

  function renderState() {
    if (!stateEl) return;
    const n = _draft.items?.length || 0;
    const mode = _editingInvoiceId ? `Editing #${_editingInvoiceId}` : 'Create';
    const busy = _isSaving || _isLoading ? ' · busy' : '';
    stateEl.textContent = `${mode} · ${n} line(s)${busy}`;
    if (modeEl) {
      modeEl.textContent = _editingInvoiceId
        ? `Editing invoice #${_editingInvoiceId}`
        : 'New estimate';
    }
    if (saveAsNewBtn) saveAsNewBtn.hidden = !_editingInvoiceId;
    if (updatePricesBtn) {
      const blocked =
        _invoiceFinalized || String(_invoiceStatus) === 'Invoiced';
      updatePricesBtn.hidden = !_editingInvoiceId;
      updatePricesBtn.disabled = !_editingInvoiceId || blocked || _isSaving || _isLoading;
      updatePricesBtn.title = blocked
        ? 'Unavailable on finalized or invoiced invoices'
        : 'Update line prices from catalog or history';
    }
    if (acceptBtn) {
      acceptBtn.hidden = !_editingInvoiceId || _hasWorkOrder;
      acceptBtn.disabled = _isSaving || _isLoading;
    }
    if (saveBtn) saveBtn.disabled = _isSaving || _isLoading;
    if (saveAsNewBtn) saveAsNewBtn.disabled = _isSaving || _isLoading;
  }

  function renderDevices() {
    if (!deviceList) return;
    if (!_devices.length) {
      deviceList.innerHTML = `<li class="sysforge-classic-empty">No devices yet.</li>`;
      return;
    }
    deviceList.innerHTML = _devices
      .map((d, i) => {
        const hasProj = Boolean(d.has_project || d.project_id);
        return `<li class="sysforge-calc-device-row">
          <span>${escapeHtml(d.label)}</span>
          ${hasProj ? '<span class="sysforge-hub-status">Has project</span>' : ''}
          ${
            _editingInvoiceId && _hasWorkOrder && !hasProj
              ? `<button type="button" class="btn-secondary" data-create-device="${d.id ?? i}">Create project</button>`
              : ''
          }
          ${
            !hasProj
              ? `<button type="button" class="btn-secondary" data-remove-device="${i}" aria-label="Remove">×</button>`
              : ''
          }
        </li>`;
      })
      .join('');
  }

  function render() {
    renderLines();
    renderTotals();
    renderDevices();
    renderState();
  }

  function clearForm() {
    _editingInvoiceId = null;
    _invoiceStatus = 'Estimate';
    _invoiceFinalized = false;
    _selectedClient = null;
    _devices = [];
    _hasWorkOrder = false;
    _draft = _emptyDraft(_draft.taxRateBps);
    if (clientInput) clientInput.value = '';
    if (quickInput) quickInput.value = '';
    if (taxCb) taxCb.checked = true;
    if (shipCb) shipCb.checked = false;
    if (shipRate) shipRate.value = '0';
    hideClientSuggest();
    hidePartSuggest();
    render();
  }

  function buildPayload(name) {
    const clientInfo =
      _selectedClient?.display_name ||
      _selectedClient?.displayName ||
      _draft.clientName ||
      null;
    return {
      client_id: _selectedClient?.id ?? _draft.clientId ?? null,
      client_info: clientInfo,
      name: name ?? _draft.name ?? null,
      include_tax: Boolean(taxCb?.checked),
      include_shipping: Boolean(shipCb?.checked),
      tax_rate_bps: _draft.taxRateBps || 775,
      shipping_rate_cents: Math.round(Number(shipRate?.value || 0) * 100) || 0,
      items: _itemsForApi(_draft.items),
    };
  }

  async function doSave() {
    if (_isSaving || _isLoading) return;
    const isEdit = _editingInvoiceId != null;
    if (!isEdit && (!_draft.items || _draft.items.length === 0)) {
      await _toast('Add at least one line item', 'error');
      return;
    }

    const run = async (name) => {
      _isSaving = true;
      renderState();
      try {
        let result;
        if (isEdit) {
          // Omit status/finalized/sent so server preserves DB values.
          const body = buildPayload(_draft.name);
          result = await deps.api(`/invoices/${_editingInvoiceId}`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(body),
          });
          await persistDevices(result.id);
        } else {
          result = await deps.api('/invoices', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(buildPayload(name)),
          });
          await persistDevices(result.id);
        }
        const savedClientId =
          result.client_id ?? _selectedClient?.id ?? _draft.clientId ?? null;
        await controller.onInvoiceSavedOrDiscard();
        clearForm();
        await _toast(
          isEdit ? `Invoice #${result.id} saved` : `Invoice #${result.id} created`,
          'success'
        );
        // Edit/create save → restore origin (Classic + client), not stay on viewer.
        if (typeof deps.navigateAfterInvoiceSave === 'function') {
          deps.navigateAfterInvoiceSave(savedClientId);
        } else if (typeof deps.navigate === 'function') {
          deps.navigate('client-dashboard', {
            params: savedClientId != null ? { clientId: savedClientId } : {},
          });
        }
      } catch (err) {
        await _toast(err?.message || String(err), 'error');
        throw err;
      } finally {
        _isSaving = false;
        renderState();
      }
    };

    if (isEdit) {
      await run(_draft.name);
    } else {
      _openInvoiceNameDialog({
        prefill: _defaultInvoiceName(
          _selectedClient?.display_name || _draft.clientName
        ),
        onSave: run,
      });
      // Fix dialog title after open
      requestAnimationFrame(() => {
        const title = document.getElementById('sysforge-draft-dialog-title');
        if (title) title.textContent = 'Save Invoice';
      });
    }
  }

  async function doSaveAsNew() {
    if (!_editingInvoiceId || _isSaving || _isLoading) return;
    if (!_draft.items || _draft.items.length === 0) {
      await _toast('Add at least one line item', 'error');
      return;
    }
    _openInvoiceNameDialog({
      prefill: _defaultInvoiceName(
        _selectedClient?.display_name || _draft.clientName
      ),
      onSave: async (name) => {
        _isSaving = true;
        renderState();
        try {
          const result = await deps.api(
            `/invoices/${_editingInvoiceId}/save-as-new`,
            {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify(buildPayload(name)),
            }
          );
          const savedClientId =
            result.client_id ?? _selectedClient?.id ?? _draft.clientId ?? null;
          await controller.onInvoiceSavedOrDiscard();
          // Clear edit state before leave (chat 21972123) so cache reuse is clean.
          clearForm();
          await _toast(`Saved as new invoice #${result.id}`, 'success');
          // Trim calculator off stack, then viewer for new id (BUG-008).
          if (typeof deps.navigateToViewerAfterSaveAsNew === 'function') {
            deps.navigateToViewerAfterSaveAsNew(result.id, savedClientId);
          } else if (typeof deps.navigate === 'function') {
            deps.navigate('invoice-view', { params: { id: result.id } });
          }
        } catch (err) {
          await _toast(err?.message || String(err), 'error');
          throw err;
        } finally {
          _isSaving = false;
          renderState();
        }
      },
    });
    requestAnimationFrame(() => {
      const title = document.getElementById('sysforge-draft-dialog-title');
      if (title) title.textContent = 'Save as New Invoice';
    });
  }

  async function persistDevices(invoiceId) {
    if (!invoiceId) return;
    const payload = {
      devices: (_devices || [])
        .filter((d) => String(d.label || '').trim())
        .map((d, i) => ({
          id: d.id && Number(d.id) > 0 ? Number(d.id) : null,
          label: String(d.label).trim(),
          sort_order: i,
        })),
    };
    const res = await deps.api(`/invoices/${invoiceId}/devices`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    _devices = res.devices || [];
  }

  async function refreshWorkOrderFlag(invoiceId) {
    if (!invoiceId) {
      _hasWorkOrder = false;
      return;
    }
    try {
      const pre = await deps.api(
        `/projects/from-invoice/preflight?invoice_id=${invoiceId}`
      );
      _hasWorkOrder = Boolean(pre.work_order_id);
    } catch (_) {
      _hasWorkOrder = false;
    }
  }

  async function loadInvoice(invoiceId) {
    if (!invoiceId) return;
    if (_loadAbort) _loadAbort.abort();
    _loadAbort = new AbortController();
    _isLoading = true;
    renderState();
    try {
      const inv = await deps.api(`/invoices/${invoiceId}`);
      _editingInvoiceId = inv.id;
      _invoiceStatus = inv.status || 'Estimate';
      _invoiceFinalized = Boolean(inv.is_finalized);
      _draft.name = inv.name || '';
      _draft.clientId = inv.client_id;
      _draft.clientName = inv.client_info || '';
      _draft.taxRateBps = inv.tax_rate_bps || 775;
      _draft.items = (inv.items || []).map(_lineFromApi);
      if (taxCb) taxCb.checked = inv.include_tax !== false;
      if (shipCb) shipCb.checked = Boolean(inv.include_shipping);
      if (shipRate) {
        shipRate.value = String((inv.shipping_rate_cents || 0) / 100);
      }
      if (inv.client_id) {
        try {
          const client = await deps.api(`/clients/${inv.client_id}`);
          _selectedClient = client;
          _draft.clientName = client.display_name || inv.client_info || '';
        } catch (_) {
          _selectedClient = {
            id: inv.client_id,
            display_name: inv.client_info || '',
          };
        }
      } else {
        _selectedClient = null;
      }
      if (clientInput) {
        clientInput.value = _draft.clientName || '';
      }
      try {
        const devRes = await deps.api(`/invoices/${invoiceId}/devices`);
        _devices = devRes.devices || [];
      } catch (_) {
        _devices = [];
      }
      await refreshWorkOrderFlag(invoiceId);
      // Edit-load guard: show display_name, dropdown stays closed.
      hideClientSuggest();
      controller.setCurrentDraftId(null);
      render();
    } catch (err) {
      if (err?.name === 'AbortError') return;
      await _toast(err?.message || String(err), 'error');
    } finally {
      _isLoading = false;
      renderState();
    }
  }

  async function loadClient(clientId) {
    if (!clientId) return;
    try {
      const client = await deps.api(`/clients/${clientId}`);
      _selectedClient = client;
      _draft.clientId = client.id;
      _draft.clientName = client.display_name || '';
      if (clientInput) clientInput.value = _draft.clientName;
      hideClientSuggest();
      markDirty();
    } catch (err) {
      await _toast(err?.message || String(err), 'error');
    }
  }

  // --- Events (bind once) ---

  clientInput?.addEventListener('input', () => {
    const q = clientInput.value;
    if (
      _selectedClient &&
      q.trim().toLowerCase() !==
        String(_selectedClient.display_name || '').trim().toLowerCase()
    ) {
      // Query diverged from selected — clear selection so search runs.
      // Keep typing; selection clears when they pick again.
    }
    runClientSearch(q);
  });

  clientInput?.addEventListener('keydown', (e) => {
    if (clientSuggest && !clientSuggest.hidden) {
      const handled = clientSearch.handleKeydown(e, {
        items: _clientItems,
        index: _clientIndex,
        onIndex: (n) => {
          _clientIndex = n;
          clientSuggest.querySelectorAll('li').forEach((li, i) => {
            li.classList.toggle('is-active', i === n);
          });
        },
        onSelect: selectClientItem,
      });
      if (handled) return;
    }
  });

  clientSuggest?.addEventListener('click', (e) => {
    const li = e.target.closest('li[data-idx]');
    if (!li) return;
    const idx = Number(li.getAttribute('data-idx'));
    selectClientItem(_clientItems[idx]);
  });

  quickInput?.addEventListener('input', () => searchParts(quickInput.value));

  quickInput?.addEventListener('keydown', (e) => {
    if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
      if (!partSuggest || partSuggest.hidden || !_partItems.length) return;
      e.preventDefault();
      if (e.key === 'ArrowDown') {
        _partIndex = Math.min(_partItems.length - 1, _partIndex + 1);
      } else {
        _partIndex = Math.max(0, _partIndex - 1);
      }
      partSuggest.querySelectorAll('li').forEach((li, i) => {
        li.classList.toggle('is-active', i === _partIndex);
      });
      return;
    }
    if (e.key === 'Enter') {
      e.preventDefault();
      if (!partSuggest?.hidden && _partIndex >= 0 && _partItems[_partIndex]) {
        selectPart(_partItems[_partIndex]);
        return;
      }
      const name = (quickInput.value || '').trim();
      if (!name) return;
      addLine({ partName: name, unitPrice: 0, itemType: 'Part' });
    }
  });

  partSuggest?.addEventListener('click', (e) => {
    const li = e.target.closest('li[data-idx]');
    if (!li) return;
    selectPart(_partItems[Number(li.getAttribute('data-idx'))]);
  });

  tbody?.addEventListener('input', (e) => {
    const t = e.target;
    const idx = Number(t.getAttribute('data-idx'));
    if (!Number.isFinite(idx) || !_draft.items[idx]) return;
    if (t.classList.contains('sf-line-name')) {
      _draft.items[idx].partName = t.value;
      // Clear catalog link when name edited freely
      if (_draft.items[idx].partId != null) {
        /* keep partId unless name diverges — keep for placeholder survival */
      }
    } else if (t.classList.contains('sf-line-qty')) {
      let q = Number(t.value);
      if (!Number.isFinite(q) || q <= 0) q = 1;
      _draft.items[idx].quantity = q;
    } else if (t.classList.contains('sf-line-price')) {
      let p = Number(t.value);
      if (!Number.isFinite(p) || p < 0) p = 0;
      _draft.items[idx].unitPrice = p;
    }
    markDirty();
  });

  tbody?.addEventListener('change', (e) => {
    const t = e.target;
    if (!t.classList.contains('sf-line-type')) return;
    const idx = Number(t.getAttribute('data-idx'));
    if (_draft.items[idx]) {
      _draft.items[idx].itemType = t.value;
      markDirty();
    }
  });

  tbody?.addEventListener('keydown', (e) => {
    if (e.key !== 'Enter') return;
    const t = e.target;
    e.preventDefault();
    if (t.classList.contains('sf-line-name')) {
      t.closest('tr')?.querySelector('.sf-line-price')?.focus();
    } else if (t.classList.contains('sf-line-price')) {
      const price = Number(t.value);
      if (!Number.isFinite(price) || price < 0) {
        t.value = '0';
        return;
      }
      t.closest('tr')?.querySelector('.sf-line-qty')?.focus();
    } else if (t.classList.contains('sf-line-qty')) {
      let q = Number(t.value);
      if (!Number.isFinite(q) || q <= 0) {
        t.value = '1';
        _draft.items[Number(t.getAttribute('data-idx'))].quantity = 1;
      }
      quickInput?.focus();
    }
  });

  tbody?.addEventListener('click', (e) => {
    const btn = e.target.closest('.sf-line-del');
    if (!btn) return;
    const idx = Number(btn.getAttribute('data-idx'));
    _draft.items = (_draft.items || []).filter((_, i) => i !== idx);
    markDirty();
    renderLines();
  });

  taxCb?.addEventListener('change', () => markDirty());
  shipCb?.addEventListener('change', () => markDirty());
  shipRate?.addEventListener('input', () => markDirty());

  saveBtn?.addEventListener('click', () => doSave());
  saveAsNewBtn?.addEventListener('click', () => doSaveAsNew());

  function _formatDelta(cents) {
    const n = Number(cents) || 0;
    const sign = n > 0 ? '+' : '';
    return `${sign}${_money(n)}`;
  }

  function renderPricePreview(rows) {
    _pricePreview = rows || [];
    if (!priceTableWrap) return;
    if (!_pricePreview.length) {
      priceTableWrap.innerHTML =
        '<p class="sysforge-clients-empty">No linked parts to update.</p>';
      return;
    }
    priceTableWrap.innerHTML = `
      <table class="sysforge-calc-lines">
        <thead>
          <tr>
            <th>Part</th>
            <th>Current</th>
            <th>Proposed</th>
            <th>Delta</th>
            <th>Source</th>
          </tr>
        </thead>
        <tbody>
          ${_pricePreview
            .map((r) => {
              const histOpts = (r.history_options || [])
                .map(
                  (h) =>
                    `<option value="history:${h.id}" ${
                      r.source === 'history' && r.history_id === h.id
                        ? 'selected'
                        : ''
                    }>History ${_money(h.price_cents)}</option>`
                )
                .join('');
              return `<tr data-item-id="${r.item_id}">
                <td>${escapeHtml(r.part_name || '')}</td>
                <td>${_money(r.current_unit_cents)}</td>
                <td>${_money(r.proposed_cents)}</td>
                <td>${_formatDelta(r.delta_cents)}</td>
                <td>
                  <select class="sysforge-calc-price-source" data-item-id="${r.item_id}">
                    <option value="base" ${r.source === 'base' ? 'selected' : ''}>
                      Catalog ${_money(r.base_price_cents)}
                    </option>
                    ${histOpts}
                  </select>
                </td>
              </tr>`;
            })
            .join('')}
        </tbody>
      </table>`;
  }

  async function openUpdatePrices() {
    if (!_editingInvoiceId) return;
    if (priceErrorEl) {
      priceErrorEl.hidden = true;
      priceErrorEl.textContent = '';
    }
    try {
      const preview = await deps.api(
        `/invoices/${_editingInvoiceId}/update-prices/preview`,
        {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ choices: [] }),
        }
      );
      const rows = preview.items || [];
      for (const row of rows) {
        try {
          const hist = await deps.api(
            `/parts/${row.part_id}/price-history?limit=5`
          );
          row.history_options = hist.items || [];
        } catch (_) {
          row.history_options = [];
        }
      }
      renderPricePreview(rows);
      if (typeof priceDialog?.showModal === 'function') {
        priceDialog.showModal();
      }
    } catch (err) {
      await _toast(err?.message || String(err), 'error');
    }
  }

  updatePricesBtn?.addEventListener('click', () => {
    void openUpdatePrices();
  });

  priceTableWrap?.addEventListener('change', async (e) => {
    const sel = e.target.closest('.sysforge-calc-price-source');
    if (!sel || !_editingInvoiceId) return;
    const itemId = Number(sel.getAttribute('data-item-id'));
    const val = String(sel.value || 'base');
    const choices = _pricePreview.map((r) => {
      if (Number(r.item_id) !== itemId) {
        return {
          item_id: r.item_id,
          source: r.source || 'base',
          history_id: r.history_id ?? null,
        };
      }
      if (val.startsWith('history:')) {
        return {
          item_id: itemId,
          source: 'history',
          history_id: Number(val.slice('history:'.length)),
        };
      }
      return { item_id: itemId, source: 'base', history_id: null };
    });
    try {
      const preview = await deps.api(
        `/invoices/${_editingInvoiceId}/update-prices/preview`,
        {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ choices }),
        }
      );
      const next = preview.items || [];
      for (const row of next) {
        const prev = _pricePreview.find((p) => p.item_id === row.item_id);
        row.history_options = prev?.history_options || [];
      }
      renderPricePreview(next);
    } catch (err) {
      if (priceErrorEl) {
        priceErrorEl.textContent = err?.message || String(err);
        priceErrorEl.hidden = false;
      }
    }
  });

  priceApplyBtn?.addEventListener('click', async (e) => {
    e.preventDefault();
    if (!_editingInvoiceId || !_pricePreview.length) return;
    if (priceErrorEl) {
      priceErrorEl.hidden = true;
      priceErrorEl.textContent = '';
    }
    try {
      const inv = await deps.api(
        `/invoices/${_editingInvoiceId}/update-prices/apply`,
        {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            items: _pricePreview.map((r) => ({
              item_id: r.item_id,
              proposed_cents: r.proposed_cents,
            })),
          }),
        }
      );
      if (typeof priceDialog?.close === 'function') priceDialog.close();
      _draft.items = (inv.items || []).map(_lineFromApi);
      recomputeLocalTotals();
      render();
      await _toast('Line prices updated', 'success');
    } catch (err) {
      if (priceErrorEl) {
        priceErrorEl.textContent = err?.message || String(err);
        priceErrorEl.hidden = false;
      }
      await _toast(err?.message || String(err), 'error');
    }
  });

  container.querySelector('#sysforge-calc-add-device')?.addEventListener('click', () => {
    const label = String(deviceLabelInput?.value || '').trim();
    if (!label) return;
    _devices.push({ id: 0, label, has_project: false });
    if (deviceLabelInput) deviceLabelInput.value = '';
    markDirty();
    renderDevices();
  });

  deviceList?.addEventListener('click', (e) => {
    const removeBtn = e.target.closest('[data-remove-device]');
    if (removeBtn) {
      const idx = Number(removeBtn.getAttribute('data-remove-device'));
      const d = _devices[idx];
      if (d?.has_project || d?.project_id) return;
      _devices = _devices.filter((_, i) => i !== idx);
      markDirty();
      renderDevices();
      return;
    }
    const createBtn = e.target.closest('[data-create-device]');
    if (createBtn && _editingInvoiceId) {
      const deviceId = Number(createBtn.getAttribute('data-create-device'));
      void (async () => {
        try {
          await persistDevices(_editingInvoiceId);
        } catch (err) {
          await _toast(err?.message || String(err), 'error');
          return;
        }
        await startCreateProjectFromInvoice({
          api: deps.api,
          navigate: deps.navigate,
          invoiceId: _editingInvoiceId,
          invoiceDeviceId: deviceId,
        });
      })();
    }
  });

  acceptBtn?.addEventListener('click', async () => {
    if (!_editingInvoiceId || _hasWorkOrder) return;
    const ok = window.confirm(
      'Mark this estimate as client-accepted and create a work order? Invoice status will be set to Invoiced.'
    );
    if (!ok) return;
    try {
      await persistDevices(_editingInvoiceId);
      const res = await deps.api('/work-orders/from-accepted-estimate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          invoice_id: _editingInvoiceId,
          bump_status_to_invoiced: true,
        }),
      });
      _hasWorkOrder = true;
      renderState();
      renderDevices();
      await _toast(`Work order #${res.work_order_id} created`, 'success');
    } catch (err) {
      await _toast(err?.message || String(err), 'error');
    }
  });

  container.querySelector('#sysforge-calc-save-draft')?.addEventListener('click', () => {
    openDraftNameDialog({
      prefill: defaultDraftNamePrefill(_draft),
      onSave: async (name) => {
        if (!_draft.items?.length) {
          await _toast('Add at least one line item', 'error');
          throw new Error('empty');
        }
        const body = {
          ..._draft,
          name,
          clientId: _selectedClient?.id ?? _draft.clientId,
          clientName:
            _selectedClient?.display_name || _draft.clientName,
          id: _draft.id || undefined,
        };
        const res = await deps.api('/drafts', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(body),
        });
        if (res?.draft) {
          _draft = { ..._draft, ...res.draft };
          controller.setCurrentDraftId(res.draft.id);
        }
        await controller.clearAutosaves();
        await _toast('Draft saved', 'success');
        renderState();
      },
    });
  });

  container.querySelector('#sysforge-calc-clear')?.addEventListener('click', async () => {
    await controller.onInvoiceSavedOrDiscard();
    clearForm();
    await _toast('Calculator cleared', 'info');
  });

  container.dataset.mounted = '1';
  container._sysforgeCalcController = controller;
  container._sysforgeCalcLoadInvoice = loadInvoice;
  container._sysforgeCalcLoadClient = loadClient;
  container._sysforgeLoadDraft = async (draftId) => {
    if (!draftId) return;
    try {
      const res = await deps.api(`/drafts/${encodeURIComponent(draftId)}`);
      if (res?.draft) {
        applyDraftSnapshot(res.draft);
        controller.setCurrentDraftId(res.draft.id);
        render();
      }
    } catch (err) {
      await _toast(err?.message || String(err), 'error');
    }
  };

  // Load default tax from settings once
  deps.api('/settings')
    .then((s) => {
      if (_settingsLoaded) return;
      _settingsLoaded = true;
      if (s?.tax_rate_bps != null && !_editingInvoiceId) {
        _draft.taxRateBps = s.tax_rate_bps;
        _draft.taxRate = s.tax_rate_bps / 100;
      }
    })
    .catch(() => {});

  render();
}

/**
 * @param {HTMLElement} container
 * @param {object} [params]
 */
export async function activateCalculator(container, params = {}) {
  const heading = container.querySelector('.sysforge-view-heading');
  heading?.focus?.({ preventScroll: true });
  const controller = container._sysforgeCalcController;
  if (controller) {
    await controller.start();
  }
  // Edit: invoiceId; New-for-client: clientId; Drafts: draftId (routes-contract).
  const invoiceId = params?.invoiceId ?? params?.id;
  const clientId = params?.clientId;
  const draftId = params?.draftId;
  if (invoiceId && typeof container._sysforgeCalcLoadInvoice === 'function') {
    await container._sysforgeCalcLoadInvoice(Number(invoiceId));
  } else if (clientId && typeof container._sysforgeCalcLoadClient === 'function') {
    await container._sysforgeCalcLoadClient(Number(clientId));
  } else if (draftId && typeof container._sysforgeLoadDraft === 'function') {
    await container._sysforgeLoadDraft(draftId);
  }
}

/**
 * @param {HTMLElement} container
 */
export async function deactivateCalculator(container) {
  const controller = container._sysforgeCalcController;
  if (controller) {
    await controller.stop({ flushOnStop: true });
  }
}

export default { mountCalculator, activateCalculator, deactivateCalculator, shouldShowClientDropdown };
