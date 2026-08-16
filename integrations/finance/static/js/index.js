/**
 * Finance — manual bank import, accounts, budgets, spending reports.
 */

import { makeWindowDraggable } from '/static/js/windowDrag.js';
// bindMenuDismiss reserved for future esc-menu wiring

const API = `${window.location.origin}/api/finance`;
let _open = false;

function _escHtml(text) {
  return String(text ?? '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}
let _modal = null;
let _accounts = [];
let _categories = [];
let _activeAccountId = null;
let _activeTab = 'transactions';
let _preview = null;
let _setupConvert = null;
let _showCategoryForm = false;
let _renderSeq = 0;
let _txSearch = '';
let _txPage = 0;
let _txListAccountId = null;
let _txSearchTimer = null;
let _txShellBuiltForForm = null;
let _txUnclassified = false;
let _txUncategorized = false;
let _selectedTxIds = new Set();
let _showAccountForm = false;
let _editingAccountId = null;
let _includeBusiness = true;
const TX_PAGE_SIZE = 50;
const CLASS_OPTIONS = [
  { value: '', label: '—' },
  { value: 'spend', label: 'Spend' },
  { value: 'income', label: 'Income' },
  { value: 'transfer', label: 'Transfer' },
  { value: 'reimbursement', label: 'Reimbursement' },
];

const PANEL_FADE_MS = 150;

function _el(id) {
  return document.getElementById(id);
}

/**
 * Smooth panel refresh: keep current content visible but dimmed while the
 * next view loads, then fade the new content in. Avoids the blank
 * "Loading…" flash that made account/tab switches look like a full reopen.
 * Returns a seq token; callers bail if a newer render started meanwhile.
 */
function _panelLoading(panel) {
  const seq = ++_renderSeq;
  panel.style.transition = `opacity ${PANEL_FADE_MS}ms ease`;
  if (panel.innerHTML.trim()) {
    panel.style.opacity = '0.45';
    panel.style.pointerEvents = 'none';
  } else {
    panel.innerHTML = '<p style="opacity:0.7;">Loading…</p>';
  }
  return seq;
}

function _panelSwap(panel, html) {
  panel.innerHTML = html;
  panel.scrollTop = 0;
  panel.style.opacity = '0';
  panel.style.pointerEvents = '';
  requestAnimationFrame(() => { panel.style.opacity = '1'; });
}

function _fmtMoney(cents) {
  const n = (Number(cents) || 0) / 100;
  const sign = n < 0 ? '-' : '';
  return `${sign}$${Math.abs(n).toFixed(2)}`;
}

async function _api(path, opts = {}) {
  const res = await fetch(`${API}${path}`, { credentials: 'same-origin', ...opts });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.detail || data.message || `Request failed (${res.status})`);
  return data;
}

function _getModal() {
  if (_modal) return _modal;
  _modal = document.createElement('div');
  _modal.id = 'finance-modal';
  _modal.className = 'modal';
  _modal.innerHTML = `
    <div class="modal-content finance-modal-content">
      <div class="modal-header">
        <h2 style="margin:0;font-size:1.1rem;">Finance</h2>
        <button type="button" class="modal-close" id="finance-close-btn" aria-label="Close">&times;</button>
      </div>
      <div class="finance-toolbar" style="display:flex;gap:8px;padding:8px 12px;border-bottom:1px solid var(--border-color,#333);flex-wrap:wrap;align-items:center;">
        <select id="finance-account-select" style="min-width:220px;"></select>
        <button type="button" id="finance-add-account-btn" class="btn-secondary">+ Account</button>
        <button type="button" id="finance-edit-account-btn" class="btn-secondary">Edit account</button>
        <div style="flex:1"></div>
        <button type="button" class="finance-tab-btn" data-tab="transactions">Transactions</button>
        <button type="button" class="finance-tab-btn" data-tab="import">Import</button>
        <button type="button" class="finance-tab-btn" data-tab="budget">Budget</button>
        <button type="button" class="finance-tab-btn" data-tab="recurring">Recurring</button>
        <button type="button" class="finance-tab-btn" data-tab="reports">Reports</button>
      </div>
      <div id="finance-panel" style="flex:1;overflow:auto;padding:12px;"></div>
    </div>`;
  document.body.appendChild(_modal);
  const content = _modal.querySelector('.finance-modal-content');
  const header = _modal.querySelector('.modal-header');
  if (content && header) {
    makeWindowDraggable(_modal, {
      content,
      header,
      skipSelector: 'button, input, select, textarea, label',
    });
  }
  _el('finance-close-btn')?.addEventListener('click', closeFinance);
  _modal.addEventListener('click', (e) => { if (e.target === _modal) closeFinance(); });
  _el('finance-add-account-btn')?.addEventListener('click', () => _openAccountForm(null));
  _el('finance-edit-account-btn')?.addEventListener('click', () => {
    if (_activeAccountId) _openAccountForm(_activeAccountId);
  });
  _el('finance-account-select')?.addEventListener('change', (e) => {
    _activeAccountId = e.target.value || null;
    _renderPanel();
  });
  _modal.querySelectorAll('.finance-tab-btn').forEach((btn) => {
    btn.addEventListener('click', () => {
      _activeTab = btn.dataset.tab || 'transactions';
      _renderPanel();
    });
  });
  return _modal;
}

async function _loadAccounts() {
  const data = await _api('/accounts');
  _accounts = data.accounts || [];
  if (!_activeAccountId && _accounts.length) _activeAccountId = _accounts[0].id;
  const sel = _el('finance-account-select');
  if (!sel) return;
  sel.innerHTML = _accounts.map((a) =>
    `<option value="${a.id}" ${a.id === _activeAccountId ? 'selected' : ''}>${_escHtml(a.name)} (${_fmtMoney(a.posted_cents ?? a.balance_cents)})</option>`
  ).join('') || '<option value="">No accounts</option>';
  _renderAccountMeta();
}

function _fmtShortDate(iso) {
  if (!iso) return '';
  const d = new Date(`${iso}T00:00:00`);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleDateString(undefined, { month: 'short', day: 'numeric' });
}

function _ageLabel(days) {
  if (days == null) return '';
  if (days <= 0) return 'as of today';
  if (days === 1) return 'as of 1 day ago';
  return `as of ${days} days ago`;
}

function _pinDeltaText(a) {
  if (a.posted_pin_cents == null) return '';
  const asOf = a.posted_pin_as_of ? ` as of ${_fmtShortDate(a.posted_pin_as_of)}` : '';
  if (!a.posted_pin_delta_cents) return `Books match your pin${asOf}.`;
  const amt = _fmtMoney(Math.abs(a.posted_pin_delta_cents));
  if (a.posted_pin_delta_cents < 0) return `Books are ${amt} below your pin${asOf}.`;
  return `Books are ${amt} above your pin${asOf}.`;
}

function _renderAccountMeta() {
  let meta = _el('finance-account-meta');
  const toolbar = _modal?.querySelector('.finance-toolbar');
  if (!toolbar) return;
  if (!meta) {
    meta = document.createElement('div');
    meta.id = 'finance-account-meta';
    meta.style.cssText = 'width:100%;font-size:0.8rem;opacity:0.9;padding:0 0 4px;';
    toolbar.appendChild(meta);
  }
  const a = _accounts.find((x) => x.id === _activeAccountId);
  if (!a) {
    meta.textContent = '';
    return;
  }
  const availAge = _ageLabel(a.available_age_days);
  const stale = (a.available_age_days ?? 0) > 3;
  const avail = a.available_cents == null
    ? 'Available not pinned'
    : `Available ${_fmtMoney(a.available_cents)}${availAge ? ` (${availAge})` : ''}`;
  meta.innerHTML = `
    <span>Posted ${_fmtMoney(a.posted_cents ?? a.balance_cents)}</span>
    <span style="margin-left:10px;${stale ? 'opacity:0.55;' : ''}">${_escHtml(avail)}</span>
    ${a.posted_pin_cents != null ? `<span style="margin-left:10px;">${_escHtml(_pinDeltaText(a))}</span>` : ''}
    ${stale && a.available_cents != null ? '<button type="button" id="finance-repin-btn" class="btn-secondary" style="margin-left:8px;font-size:0.75rem;">Re-pin available</button>' : ''}
  `;
  _el('finance-repin-btn')?.addEventListener('click', () => _openAccountForm(a.id));
}

async function _loadCategories() {
  const data = await _api('/categories');
  _categories = data.categories || [];
}

function _orderedCategories() {
  const tops = _categories.filter((c) => !c.parent_id).sort((a, b) => a.name.localeCompare(b.name));
  const out = [];
  for (const top of tops) {
    out.push(top);
    _categories
      .filter((c) => c.parent_id === top.id)
      .sort((a, b) => a.name.localeCompare(b.name))
      .forEach((child) => out.push(child));
  }
  const seen = new Set(out.map((c) => c.id));
  _categories.filter((c) => !seen.has(c.id)).forEach((c) => out.push(c));
  return out;
}

function _categoryOptionLabel(cat) {
  return cat.parent_id ? `  ↳ ${cat.name}` : (cat.display_name || cat.name);
}

function _categoryOptionsHtml(selectedId) {
  return _orderedCategories().map((c) =>
    `<option value="${c.id}" ${c.id === selectedId ? 'selected' : ''}>${_escHtml(_categoryOptionLabel(c))}</option>`
  ).join('');
}

function _topLevelCategoryOptionsHtml(selectedId = '') {
  const tops = _categories
    .filter((c) => !c.parent_id)
    .sort((a, b) => a.name.localeCompare(b.name));
  return `<option value="">Top level</option>${tops.map((c) =>
    `<option value="${c.id}" ${c.id === selectedId ? 'selected' : ''}>${_escHtml(c.name)}</option>`
  ).join('')}`;
}

function _categoryFormHtml() {
  return `
    <div id="finance-category-form" style="margin-bottom:12px;padding:10px;border:1px solid var(--border-color,#333);border-radius:6px;">
      <div style="font-weight:600;margin-bottom:8px;">New category</div>
      <div style="display:flex;gap:8px;flex-wrap:wrap;align-items:flex-end;">
        <label style="display:flex;flex-direction:column;gap:4px;flex:1;min-width:140px;">
          <span style="font-size:0.8rem;opacity:0.85;">Name</span>
          <input id="finance-cat-name" type="text" placeholder="e.g. Fast Food" />
        </label>
        <label style="display:flex;flex-direction:column;gap:4px;min-width:160px;">
          <span style="font-size:0.8rem;opacity:0.85;">Parent (subcategory)</span>
          <select id="finance-cat-parent">${_topLevelCategoryOptionsHtml()}</select>
        </label>
        <label id="finance-cat-income-wrap" style="display:flex;align-items:center;gap:6px;font-size:0.85rem;padding-bottom:6px;">
          <input id="finance-cat-income" type="checkbox" /> Income
        </label>
        <button type="button" id="finance-cat-save" class="btn-primary">Save</button>
        <button type="button" id="finance-cat-cancel" class="btn-secondary">Cancel</button>
      </div>
      <p id="finance-cat-error" style="color:var(--danger,#e74c3c);font-size:0.85rem;margin:8px 0 0;"></p>
    </div>`;
}

function _bindCategoryForm() {
  const parentSel = _el('finance-cat-parent');
  const incomeWrap = _el('finance-cat-income-wrap');
  const syncIncome = () => {
    if (incomeWrap) incomeWrap.style.display = parentSel?.value ? 'none' : 'flex';
  };
  parentSel?.addEventListener('change', syncIncome);
  syncIncome();

  _el('finance-cat-cancel')?.addEventListener('click', () => {
    _showCategoryForm = false;
    _renderTransactions();
  });
  _el('finance-cat-save')?.addEventListener('click', async () => {
    const name = _el('finance-cat-name')?.value?.trim();
    const errEl = _el('finance-cat-error');
    if (!name) {
      if (errEl) errEl.textContent = 'Enter a category name.';
      return;
    }
    const parentId = parentSel?.value || null;
    const body = { name };
    if (parentId) body.parent_id = parentId;
    else if (_el('finance-cat-income')?.checked) body.is_income = true;
    try {
      await _api('/categories', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      });
      _showCategoryForm = false;
      await _loadCategories();
      _renderTransactions();
    } catch (err) {
      if (errEl) errEl.textContent = err.message || String(err);
    }
  });
}

function _dollarsToCents(raw) {
  if (raw === '' || raw == null) return null;
  const n = Number(raw);
  if (Number.isNaN(n)) return null;
  return Math.round(n * 100);
}

function _centsToDollars(cents) {
  if (cents == null) return '';
  return (Number(cents) / 100).toFixed(2);
}

function _openAccountForm(accountId) {
  _editingAccountId = accountId;
  _showAccountForm = true;
  _renderAccountForm();
}

function _closeAccountForm() {
  _showAccountForm = false;
  _editingAccountId = null;
  _el('finance-account-form')?.remove();
}

function _renderAccountForm() {
  if (!_showAccountForm || !_modal) return;
  _el('finance-account-form')?.remove();
  const existing = _accounts.find((a) => a.id === _editingAccountId) || {};
  const wrap = document.createElement('div');
  wrap.id = 'finance-account-form';
  wrap.style.cssText = 'padding:12px;border-bottom:1px solid var(--border-color,#333);background:var(--surface,#1c1c1c);';
  wrap.innerHTML = `
    <div style="font-weight:600;margin-bottom:8px;">${_editingAccountId ? 'Edit account' : 'New account'}</div>
    <div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(160px,1fr));gap:8px;">
      <label>Name<input id="fin-acct-name" type="text" value="${_escHtml(existing.name || '')}" /></label>
      <label>Institution<input id="fin-acct-inst" type="text" value="${_escHtml(existing.institution || '')}" /></label>
      <label>Type
        <select id="fin-acct-type">
          ${['checking','savings','credit_card','loan','cash','other'].map((t) =>
            `<option value="${t}" ${existing.account_type === t ? 'selected' : ''}>${t}</option>`).join('')}
        </select>
      </label>
      <label>Purpose
        <select id="fin-acct-purpose">
          ${['operating','trip','processor'].map((t) =>
            `<option value="${t}" ${(existing.purpose || 'operating') === t ? 'selected' : ''}>${t}</option>`).join('')}
        </select>
      </label>
      <label id="fin-acct-rail-wrap">Rail
        <select id="fin-acct-rail">
          <option value="">—</option>
          ${['paypal','venmo','google'].map((t) =>
            `<option value="${t}" ${existing.rail === t ? 'selected' : ''}>${t}</option>`).join('')}
        </select>
      </label>
      <label>Opening posted ($)
        <input id="fin-acct-opening" type="number" step="0.01" value="${_centsToDollars(existing.opening_balance_cents || 0)}" />
      </label>
      <label>Balance as of
        <input id="fin-acct-opening-date" type="date" value="${existing.opening_balance_date || ''}" />
      </label>
      <label>Available ($)
        <input id="fin-acct-avail" type="number" step="0.01" value="${_centsToDollars(existing.available_cents)}" />
      </label>
      <label>Available as of
        <input id="fin-acct-avail-date" type="date" value="${existing.available_as_of || ''}" />
      </label>
      <label>Posted pin ($)
        <input id="fin-acct-pin" type="number" step="0.01" value="${_centsToDollars(existing.posted_pin_cents)}" />
      </label>
      <label>Pin as of
        <input id="fin-acct-pin-date" type="date" value="${existing.posted_pin_as_of || ''}" />
      </label>
    </div>
    <p style="font-size:0.8rem;opacity:0.8;margin:8px 0;">
      Opening posted is the balance shown the morning before your first imported row; use 0 if you imported from account opening.
    </p>
    <p id="fin-acct-error" style="color:var(--danger,#e74c3c);font-size:0.85rem;"></p>
    <div style="display:flex;gap:8px;align-items:center;">
      <button type="button" id="fin-acct-save" class="btn-primary">Save account</button>
      <button type="button" id="fin-acct-cancel" class="btn-secondary">Cancel</button>
      ${_editingAccountId ? `
        <div style="flex:1"></div>
        <button type="button" id="fin-acct-delete" class="btn-secondary" style="color:var(--danger,#e74c3c);">Delete account</button>
      ` : ''}
    </div>
    ${_editingAccountId ? '<div id="fin-acct-delete-confirm"></div>' : ''}`;
  const header = _modal.querySelector('.finance-toolbar');
  header?.after(wrap);
  const syncRail = () => {
    const proc = _el('fin-acct-purpose')?.value === 'processor';
    const railWrap = _el('fin-acct-rail-wrap');
    if (railWrap) railWrap.style.display = proc ? '' : 'none';
  };
  _el('fin-acct-purpose')?.addEventListener('change', syncRail);
  syncRail();
  _el('fin-acct-cancel')?.addEventListener('click', _closeAccountForm);
  _el('fin-acct-save')?.addEventListener('click', _saveAccountForm);
  _el('fin-acct-delete')?.addEventListener('click', () => _askDeleteAccount(existing));
}

async function _askDeleteAccount(account) {
  const box = _el('fin-acct-delete-confirm');
  if (!box) return;
  const name = account.name || 'this account';
  let txTotal = 0;
  try {
    const listed = await _api(
      `/transactions?account_id=${encodeURIComponent(account.id)}&limit=1&include_void=true`
    );
    txTotal = listed.total || 0;
  } catch {
    txTotal = 0;
  }
  const rowsLine = txTotal
    ? `This also deletes <strong>${txTotal}</strong> transaction${txTotal === 1 ? '' : 's'} and their import history. Linked transfers in other accounts go back to unlinked.`
    : 'This account has no transactions.';
  box.innerHTML = `
    <div style="margin-top:10px;padding:10px;border:1px solid var(--danger,#e74c3c);border-radius:6px;">
      <div style="font-weight:600;margin-bottom:4px;">Delete ${_escHtml(name)}?</div>
      <p style="font-size:0.85rem;margin:0 0 8px;">${rowsLine} You cannot undo this.</p>
      <div style="display:flex;gap:8px;">
        <button type="button" id="fin-acct-delete-step2" class="btn-secondary" style="color:var(--danger,#e74c3c);">Continue</button>
        <button type="button" id="fin-acct-delete-abort" class="btn-secondary">Keep account</button>
      </div>
    </div>`;
  _el('fin-acct-delete-abort')?.addEventListener('click', () => { box.innerHTML = ''; });
  _el('fin-acct-delete-step2')?.addEventListener('click', () => _confirmDeleteAccount(account, txTotal));
}

function _confirmDeleteAccount(account, txTotal) {
  const box = _el('fin-acct-delete-confirm');
  if (!box) return;
  const name = account.name || '';
  box.innerHTML = `
    <div style="margin-top:10px;padding:10px;border:1px solid var(--danger,#e74c3c);border-radius:6px;">
      <div style="font-weight:600;margin-bottom:4px;">Last check</div>
      <p style="font-size:0.85rem;margin:0 0 8px;">Type <strong>${_escHtml(name)}</strong> to delete it for good.</p>
      <input id="fin-acct-delete-name" type="text" autocomplete="off" placeholder="Account name" style="width:100%;margin-bottom:8px;" />
      <p id="fin-acct-delete-error" style="color:var(--danger,#e74c3c);font-size:0.85rem;margin:0 0 8px;"></p>
      <div style="display:flex;gap:8px;">
        <button type="button" id="fin-acct-delete-final" class="btn-secondary" style="color:var(--danger,#e74c3c);" disabled>Delete forever</button>
        <button type="button" id="fin-acct-delete-abort2" class="btn-secondary">Keep account</button>
      </div>
    </div>`;
  const input = _el('fin-acct-delete-name');
  const finalBtn = _el('fin-acct-delete-final');
  const matches = () => (input?.value || '').trim() === name.trim();
  input?.addEventListener('input', () => {
    if (finalBtn) finalBtn.disabled = !matches();
  });
  input?.focus();
  _el('fin-acct-delete-abort2')?.addEventListener('click', () => { box.innerHTML = ''; });
  finalBtn?.addEventListener('click', async () => {
    if (!matches()) return;
    const errEl = _el('fin-acct-delete-error');
    finalBtn.disabled = true;
    try {
      await _api(
        `/accounts/${account.id}?purge_transactions=${txTotal ? 'true' : 'false'}`,
        { method: 'DELETE' }
      );
      if (_activeAccountId === account.id) _activeAccountId = null;
      _closeAccountForm();
      await _loadAccounts();
      await _renderPanel();
    } catch (err) {
      finalBtn.disabled = false;
      if (errEl) errEl.textContent = err.message || String(err);
    }
  });
}

async function _saveAccountForm() {
  const err = _el('fin-acct-error');
  const name = _el('fin-acct-name')?.value?.trim();
  if (!name) {
    if (err) err.textContent = 'Name is required.';
    return;
  }
  const purpose = _el('fin-acct-purpose')?.value || 'operating';
  const body = {
    name,
    institution: _el('fin-acct-inst')?.value || '',
    account_type: _el('fin-acct-type')?.value || 'checking',
    purpose,
    rail: purpose === 'processor' ? (_el('fin-acct-rail')?.value || null) : null,
    opening_balance_cents: _dollarsToCents(_el('fin-acct-opening')?.value) || 0,
    opening_balance_date: _el('fin-acct-opening-date')?.value || null,
    available_cents: _dollarsToCents(_el('fin-acct-avail')?.value),
    available_as_of: _el('fin-acct-avail-date')?.value || null,
    posted_pin_cents: _dollarsToCents(_el('fin-acct-pin')?.value),
    posted_pin_as_of: _el('fin-acct-pin-date')?.value || null,
  };
  try {
    if (_editingAccountId) {
      await _api(`/accounts/${_editingAccountId}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      });
    } else {
      const created = await _api('/accounts', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      });
      _activeAccountId = created.id;
    }
    _closeAccountForm();
    await _loadAccounts();
    _renderPanel();
  } catch (e) {
    if (err) err.textContent = e.message || String(e);
  }
}

function _tabStyle(tab) {
  return _activeTab === tab ? 'font-weight:600;text-decoration:underline;' : '';
}

function _uiClassValue(cls) {
  return cls === 'pass_through' ? 'transfer' : (cls || '');
}

function _classOptionsHtml(selected) {
  const value = _uiClassValue(selected);
  return CLASS_OPTIONS.map((o) =>
    `<option value="${o.value}" ${value === o.value ? 'selected' : ''}>${o.label}</option>`
  ).join('');
}

function _txRowHtml(tx) {
  const amtClass = tx.amount_cents < 0 ? 'color:var(--danger,#e74c3c)' : 'color:var(--success,#2ecc71)';
  const catOpts = _categoryOptionsHtml(tx.category_id);
  const checked = _selectedTxIds.has(tx.id) ? 'checked' : '';
  const linked = tx.is_linked ? ' <span title="Linked movement" style="opacity:0.7;">↔</span>' : '';
  return `<tr>
    <td><input type="checkbox" class="finance-tx-check" data-tx-id="${tx.id}" ${checked} /></td>
    <td>${tx.date || ''}</td>
    <td style="max-width:280px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;" title="${_escHtml(tx.payee)}">${_escHtml(tx.payee)}${linked}</td>
    <td style="${amtClass};text-align:right;">${_fmtMoney(tx.amount_cents)}</td>
    <td><select data-tx-cat="${tx.id}" class="finance-cat-select"><option value="">—</option>${catOpts}</select></td>
    <td><select data-tx-class="${tx.id}" class="finance-class-select">${_classOptionsHtml(tx.movement_class)}</select></td>
    <td><button type="button" class="btn-secondary finance-apply-payee" data-tx-id="${tx.id}" data-payee="${_escHtml(tx.payee)}" style="font-size:0.75rem;">Apply to payee</button></td>
  </tr>`;
}

function _wireCategorySelects(root) {
  root?.querySelectorAll('.finance-cat-select').forEach((sel) => {
    sel.addEventListener('change', async () => {
      await _api(`/transactions/${sel.dataset.txCat}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ category_id: sel.value || null }),
      });
    });
  });
  root?.querySelectorAll('.finance-class-select').forEach((sel) => {
    sel.addEventListener('change', async () => {
      if (!sel.value) return;
      await _api(`/transactions/${sel.dataset.txClass}/classify`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ movement_class: sel.value }),
      });
    });
  });
  root?.querySelectorAll('.finance-tx-check').forEach((box) => {
    box.addEventListener('change', () => {
      if (box.checked) _selectedTxIds.add(box.dataset.txId);
      else _selectedTxIds.delete(box.dataset.txId);
      _updateBulkCount();
    });
  });
  root?.querySelectorAll('.finance-apply-payee').forEach((btn) => {
    btn.addEventListener('click', async () => {
      const row = btn.closest('tr');
      const cls = row?.querySelector('.finance-class-select')?.value;
      const cat = row?.querySelector('.finance-cat-select')?.value;
      if (!cls && !cat) return;
      await _api('/transactions/bulk', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          transaction_ids: [btn.dataset.txId],
          movement_class: cls || null,
          category_id: cat || null,
          apply_to_payee: true,
        }),
      });
      _fetchTransactionPage();
    });
  });
}

function _updateBulkCount() {
  const el = _el('finance-bulk-count');
  if (el) el.textContent = `${_selectedTxIds.size} selected`;
}

async function _applyBulk() {
  const ids = [..._selectedTxIds];
  if (!ids.length) return;
  const cls = _el('finance-bulk-class')?.value || null;
  const cat = _el('finance-bulk-cat')?.value || null;
  if (!cls && !cat) return;
  await _api('/transactions/bulk', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      transaction_ids: ids,
      movement_class: cls,
      category_id: cat,
      apply_to_payee: !!_el('finance-bulk-payee')?.checked,
    }),
  });
  _selectedTxIds.clear();
  _fetchTransactionPage();
}

function _txPagerHtml(total, { border = 'top' } = {}) {
  const pageCount = Math.max(1, Math.ceil(total / TX_PAGE_SIZE));
  if (_txPage >= pageCount) _txPage = Math.max(0, pageCount - 1);
  const start = total ? _txPage * TX_PAGE_SIZE + 1 : 0;
  const end = Math.min(total, (_txPage + 1) * TX_PAGE_SIZE);
  const edge = border === 'bottom'
    ? 'margin-bottom:10px;padding-bottom:10px;border-bottom:1px solid var(--border-color,#333);'
    : 'margin-top:12px;padding-top:12px;border-top:1px solid var(--border-color,#333);';
  return `
    <div style="display:flex;gap:12px;align-items:center;justify-content:space-between;flex-wrap:wrap;${edge}">
      <span style="font-size:0.85rem;opacity:0.85;">
        ${total ? `Showing ${start}–${end} of ${total.toLocaleString()}` : 'No transactions'}
      </span>
      <div style="display:flex;gap:8px;align-items:center;">
        <button type="button" class="btn-secondary finance-tx-prev" ${_txPage <= 0 ? 'disabled' : ''}>Previous</button>
        <span style="font-size:0.85rem;min-width:7rem;text-align:center;">Page ${_txPage + 1} of ${pageCount}</span>
        <button type="button" class="btn-secondary finance-tx-next" ${_txPage >= pageCount - 1 ? 'disabled' : ''}>Next</button>
      </div>
    </div>`;
}

function _wireTxPagerButtons(root, pageCount) {
  root?.querySelectorAll('.finance-tx-prev').forEach((btn) => {
    btn.addEventListener('click', () => {
      if (_txPage > 0) {
        _txPage -= 1;
        _fetchTransactionPage();
      }
    });
  });
  root?.querySelectorAll('.finance-tx-next').forEach((btn) => {
    btn.addEventListener('click', () => {
      if (_txPage < pageCount - 1) {
        _txPage += 1;
        _fetchTransactionPage();
      }
    });
  });
}

function _renderTxPager(total) {
  const pageCount = Math.max(1, Math.ceil(total / TX_PAGE_SIZE));
  if (_txPage >= pageCount) _txPage = Math.max(0, pageCount - 1);

  const top = _el('finance-tx-pager-top');
  const bottom = _el('finance-tx-pager');
  if (top) top.innerHTML = _txPagerHtml(total, { border: 'bottom' });
  if (bottom) bottom.innerHTML = _txPagerHtml(total, { border: 'top' });

  const root = _el('finance-tx-root');
  _wireTxPagerButtons(root, pageCount);
}

async function _fetchTransactionPage() {
  const tbody = _el('finance-tx-tbody');
  const status = _el('finance-tx-status');
  const searchInput = _el('finance-tx-search');
  const hadFocus = document.activeElement === searchInput;
  const selStart = searchInput?.selectionStart ?? null;
  const selEnd = searchInput?.selectionEnd ?? null;

  if (status) status.textContent = 'Loading…';
    if (tbody) {
    tbody.innerHTML = '<tr><td colspan="7" style="opacity:0.7;">Loading transactions…</td></tr>';
  }

  try {
    const offset = _txPage * TX_PAGE_SIZE;
    const data = await _api(
      `/transactions?account_id=${encodeURIComponent(_activeAccountId)}`
      + `&limit=${TX_PAGE_SIZE}&offset=${offset}&search=${encodeURIComponent(_txSearch)}`
      + `${_txUnclassified ? '&unclassified=true' : ''}`
      + `${_txUncategorized ? '&uncategorized=true' : ''}`,
    );
    const txs = data.transactions || [];
    const total = Number(data.total) || 0;
    if (status) status.textContent = _txSearch ? `Filtered by “${_txSearch}”` : '';
    if (tbody) {
      tbody.innerHTML = txs.length
        ? txs.map(_txRowHtml).join('')
        : '<tr><td colspan="7">No matching transactions.</td></tr>';
      _wireCategorySelects(tbody);
    }
    _renderTxPager(total);
  } catch (err) {
    if (status) status.textContent = '';
    if (tbody) {
      tbody.innerHTML = `<tr><td colspan="7" style="color:var(--danger,#e74c3c);">${_escHtml(err.message || String(err))}</td></tr>`;
    }
    _renderTxPager(0);
  }

  if (hadFocus && searchInput) {
    searchInput.focus();
    if (selStart != null && selEnd != null) {
      searchInput.setSelectionRange(selStart, selEnd);
    }
  }
}

function _ensureTransactionsShell() {
  const panel = _el('finance-panel');
  if (!panel) return;
  const needRebuild = !panel.querySelector('#finance-tx-root')
    || _txShellBuiltForForm !== _showCategoryForm;
  if (!needRebuild) return;

  _txShellBuiltForForm = _showCategoryForm;
  _panelSwap(panel, `
    <div id="finance-tx-root">
      <div style="margin-bottom:8px;display:flex;gap:8px;flex-wrap:wrap;align-items:center;">
        <input id="finance-tx-search" type="search" placeholder="Search payee…" autocomplete="off" style="flex:1;min-width:160px;" />
        <label style="font-size:0.85rem;"><input type="checkbox" id="finance-filter-unclassified" ${_txUnclassified ? 'checked' : ''} /> Unclassified</label>
        <label style="font-size:0.85rem;"><input type="checkbox" id="finance-filter-uncategorized" ${_txUncategorized ? 'checked' : ''} /> Uncategorized</label>
        <button type="button" id="finance-add-category-btn" class="btn-secondary">+ Category</button>
      </div>
      <div id="finance-bulk-bar" style="margin-bottom:8px;display:flex;gap:8px;flex-wrap:wrap;align-items:center;font-size:0.85rem;">
        <span id="finance-bulk-count">0 selected</span>
        <select id="finance-bulk-class">${_classOptionsHtml('')}</select>
        <select id="finance-bulk-cat"><option value="">Set category</option>${_categoryOptionsHtml('')}</select>
        <label><input type="checkbox" id="finance-bulk-payee" /> Apply to this payee</label>
        <button type="button" id="finance-bulk-apply" class="btn-primary">Apply to selection</button>
      </div>
      ${_showCategoryForm ? _categoryFormHtml() : ''}
      <div id="finance-tx-pager-top"></div>
      <div id="finance-tx-status" style="font-size:0.85rem;opacity:0.8;min-height:1.2em;margin-bottom:4px;"></div>
      <table class="finance-table" style="width:100%;border-collapse:collapse;font-size:0.9rem;">
        <thead><tr><th></th><th>Date</th><th>Payee</th><th style="text-align:right;">Amount</th><th>Category</th><th>Class</th><th></th></tr></thead>
        <tbody id="finance-tx-tbody"></tbody>
      </table>
      <div id="finance-tx-pager"></div>
    </div>`);

  const searchInput = _el('finance-tx-search');
  if (searchInput) {
    searchInput.value = _txSearch;
    searchInput.addEventListener('input', (e) => {
      _txSearch = e.target.value;
      _txPage = 0;
      clearTimeout(_txSearchTimer);
      _txSearchTimer = setTimeout(() => _fetchTransactionPage(), 300);
    });
  }
  _el('finance-add-category-btn')?.addEventListener('click', () => {
    _showCategoryForm = true;
    _renderTransactions();
  });
  _el('finance-filter-unclassified')?.addEventListener('change', (e) => {
    _txUnclassified = !!e.target.checked;
    _txPage = 0;
    _fetchTransactionPage();
  });
  _el('finance-filter-uncategorized')?.addEventListener('change', (e) => {
    _txUncategorized = !!e.target.checked;
    _txPage = 0;
    _fetchTransactionPage();
  });
  _el('finance-bulk-apply')?.addEventListener('click', _applyBulk);
  if (_showCategoryForm) _bindCategoryForm();
}

async function _renderTransactions() {
  const panel = _el('finance-panel');
  if (!panel) return;
  if (!_activeAccountId) {
    _txShellBuiltForForm = null;
    _panelSwap(panel, '<p>Create an account to get started.</p>');
    return;
  }
  if (_txListAccountId !== _activeAccountId) {
    _txListAccountId = _activeAccountId;
    _txPage = 0;
    _txSearch = '';
    _selectedTxIds.clear();
    _txShellBuiltForForm = null;
  }
  _ensureTransactionsShell();
  const searchInput = _el('finance-tx-search');
  if (searchInput && searchInput.value !== _txSearch) {
    searchInput.value = _txSearch;
  }
  await _fetchTransactionPage();
}

async function _renderImport() {
  const panel = _el('finance-panel');
  if (!panel) return;
  _renderSeq += 1;
  const mappings = _activeAccountId
    ? await _api('/import/mappings').catch(() => ({ mappings: [] }))
    : { mappings: [] };
  const saved = mappings.mappings || [];
  const bankBlock = _activeAccountId ? `
    <h3 style="margin:24px 0 8px;">Bank export</h3>
    <p style="opacity:0.85;margin-top:0;">After the setup file is in, upload a CSV or QFX/OFX from Wells Fargo, Navy Federal, or another bank. Matching rows are skipped. Missing statement fields are filled in. New rows are added.</p>
    <div style="display:flex;gap:8px;flex-wrap:wrap;align-items:center;margin-bottom:12px;">
      <input type="file" id="finance-import-file" accept=".csv,.qfx,.ofx,text/csv" />
      <select id="finance-import-preset">
        <option value="">Auto-detect</option>
        <option value="csv_wells_fargo">Wells Fargo CSV</option>
        <option value="csv_navy_federal">Navy Federal CSV</option>
        <option value="csv_generic">Generic CSV</option>
      </select>
      <select id="finance-import-mapping">
        <option value="">Saved mapping…</option>
        ${saved.map((m) => `<option value="${m.id}">${_escHtml(m.name)}</option>`).join('')}
      </select>
      <button type="button" id="finance-import-preview-btn" class="btn-primary">Preview import</button>
    </div>
  ` : `
    <h3 style="margin:24px 0 8px;">Bank export</h3>
    <p>Create an account first, then import the setup file or a bank CSV.</p>
  `;
  _panelSwap(panel, `
    <h3 style="margin-top:0;">Statement setup file</h3>
    <p style="opacity:0.85;margin-top:0;">No account needed yet. Upload Wells Fargo monthly statement PDFs and optionally the latest checking CSV. Odysseus builds one setup file. Then create a new account from it, or import into an account you already have.</p>
    <div style="display:flex;gap:8px;flex-wrap:wrap;align-items:center;margin-bottom:12px;">
      <label style="display:flex;flex-direction:column;gap:4px;font-size:0.85rem;">Statement PDFs
        <input type="file" id="finance-stmt-files" accept=".pdf,application/pdf" multiple />
      </label>
      <label style="display:flex;flex-direction:column;gap:4px;font-size:0.85rem;">Checking CSV (optional)
        <input type="file" id="finance-stmt-csv" accept=".csv,text/csv" multiple />
      </label>
      <button type="button" id="finance-stmt-convert-btn" class="btn-primary">Convert statements</button>
    </div>
    <div id="finance-stmt-status"></div>
    <div id="finance-stmt-result"></div>
    ${bankBlock}
    <div id="finance-import-status"></div>
    <div id="finance-import-preview"></div>`);
  _el('finance-stmt-convert-btn')?.addEventListener('click', _runStatementConvert);
  _el('finance-import-preview-btn')?.addEventListener('click', _runImportPreview);
  if (_setupConvert) _renderSetupConvertResult();
}

function _downloadText(filename, text, mime) {
  const blob = new Blob([text], { type: mime || 'text/csv;charset=utf-8' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}

function _renderSetupConvertResult() {
  const resultEl = _el('finance-stmt-result');
  const status = _el('finance-stmt-status');
  if (!resultEl || !_setupConvert) return;
  if (status) {
    status.textContent = `${_setupConvert.statement_count} statements, ${_setupConvert.transaction_count} transactions. Opening posted ${_setupConvert.opening_posted} as of ${_setupConvert.opening_as_of}.`;
    if (_setupConvert.bank_appended_count) {
      status.textContent += ` Added ${_setupConvert.bank_appended_count} newer posted rows from the checking CSV.`;
    }
  }
  const warn = (_setupConvert.warnings || []).map((w) => `<li>${_escHtml(w)}</li>`).join('');
  const acctOpts = (_accounts || []).map((a) =>
    `<option value="${a.id}" ${a.id === _activeAccountId ? 'selected' : ''}>${_escHtml(a.name)}</option>`
  ).join('');
  resultEl.innerHTML = `
    ${warn ? `<ul>${warn}</ul>` : ''}
    <pre style="max-height:180px;overflow:auto;white-space:pre-wrap;font-size:0.8rem;opacity:0.9;">${_escHtml(_setupConvert.report || '')}</pre>
    <div style="display:flex;gap:8px;flex-wrap:wrap;align-items:center;margin-top:8px;">
      <button type="button" id="finance-stmt-download-btn" class="btn-primary">Download setup file</button>
      <button type="button" id="finance-stmt-new-acct-btn">Create a new account from this file</button>
      ${acctOpts ? `
        <label style="display:flex;gap:6px;align-items:center;">Import into
          <select id="finance-stmt-import-account">${acctOpts}</select>
        </label>
        <button type="button" id="finance-stmt-import-btn">Preview import</button>
      ` : ''}
    </div>
    <div id="finance-stmt-new-acct"></div>`;
  _el('finance-stmt-download-btn')?.addEventListener('click', () => {
    _downloadText(_setupConvert.filename || 'wells-from-statements.csv', _setupConvert.csv);
  });
  _el('finance-stmt-import-btn')?.addEventListener('click', () => {
    _previewSetupFile(_el('finance-stmt-import-account')?.value);
  });
  _el('finance-stmt-new-acct-btn')?.addEventListener('click', _renderSetupNewAccountForm);
}

function _suggestedSetupAccount() {
  const s = _setupConvert?.suggested_account || {};
  return {
    name: s.name || 'Wells Fargo Checking',
    institution: s.institution || 'Wells Fargo',
    account_type: s.account_type || 'checking',
    purpose: s.purpose || 'operating',
    opening_balance_cents: s.opening_balance_cents ?? _setupConvert?.opening_posted_cents ?? 0,
    opening_balance_date: s.opening_balance_date || _setupConvert?.opening_as_of || '',
    mask_last4: s.mask_last4 || '',
  };
}

function _renderSetupNewAccountForm() {
  const host = _el('finance-stmt-new-acct');
  if (!host) return;
  const s = _suggestedSetupAccount();
  const types = ['checking', 'savings', 'credit_card', 'loan', 'cash', 'other'];
  host.innerHTML = `
    <div style="margin-top:12px;padding:12px;border:1px solid var(--border-color,#333);border-radius:8px;">
      <p style="margin-top:0;">Edit anything that looks wrong, then create the account. Opening posted comes from the oldest statement. Import runs next.</p>
      <div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(160px,1fr));gap:8px;">
        <label>Name<input id="stmt-acct-name" type="text" value="${_escHtml(s.name)}" /></label>
        <label>Institution<input id="stmt-acct-inst" type="text" value="${_escHtml(s.institution)}" /></label>
        <label>Type
          <select id="stmt-acct-type">
            ${types.map((t) => `<option value="${t}" ${s.account_type === t ? 'selected' : ''}>${t}</option>`).join('')}
          </select>
        </label>
        <label>Purpose
          <select id="stmt-acct-purpose">
            ${['operating','trip','processor'].map((t) =>
              `<option value="${t}" ${s.purpose === t ? 'selected' : ''}>${t}</option>`).join('')}
          </select>
        </label>
        <label>Last 4<input id="stmt-acct-last4" type="text" maxlength="4" value="${_escHtml(s.mask_last4)}" /></label>
        <label>Opening posted ($)
          <input id="stmt-acct-opening" type="number" step="0.01" value="${_centsToDollars(s.opening_balance_cents)}" />
        </label>
        <label>Balance as of
          <input id="stmt-acct-opening-date" type="date" value="${_escHtml(s.opening_balance_date)}" />
        </label>
      </div>
      <p id="stmt-acct-error" style="color:var(--danger,#e74c3c);font-size:0.85rem;"></p>
      <div style="display:flex;gap:8px;margin-top:8px;">
        <button type="button" id="stmt-acct-save" class="btn-primary">Create account and preview import</button>
        <button type="button" id="stmt-acct-cancel" class="btn-secondary">Cancel</button>
      </div>
    </div>`;
  _el('stmt-acct-cancel')?.addEventListener('click', () => { host.innerHTML = ''; });
  _el('stmt-acct-save')?.addEventListener('click', _createSetupAccountAndImport);
}

async function _createSetupAccountAndImport() {
  const err = _el('stmt-acct-error');
  const name = _el('stmt-acct-name')?.value?.trim();
  if (!name) {
    if (err) err.textContent = 'Name is required.';
    return;
  }
  const body = {
    name,
    institution: _el('stmt-acct-inst')?.value || '',
    account_type: _el('stmt-acct-type')?.value || 'checking',
    purpose: _el('stmt-acct-purpose')?.value || 'operating',
    mask_last4: _el('stmt-acct-last4')?.value?.trim() || null,
    opening_balance_cents: _dollarsToCents(_el('stmt-acct-opening')?.value) || 0,
    opening_balance_date: _el('stmt-acct-opening-date')?.value || null,
  };
  try {
    const created = await _api('/accounts', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });
    _activeAccountId = created.id;
    await _loadAccounts();
    await _previewSetupFile(created.id);
  } catch (e) {
    if (err) err.textContent = e.message || String(e);
  }
}

async function _runStatementConvert() {
  const fileInput = _el('finance-stmt-files');
  const status = _el('finance-stmt-status');
  const resultEl = _el('finance-stmt-result');
  const files = Array.from(fileInput?.files || []);
  const csvFiles = Array.from(_el('finance-stmt-csv')?.files || []);
  if (!files.length) {
    if (status) status.textContent = 'Choose one or more Wells Fargo statement PDFs.';
    return;
  }
  if (status) {
    const extra = csvFiles.length ? ` plus ${csvFiles.length} checking CSV${csvFiles.length === 1 ? '' : 's'}` : '';
    status.textContent = `Converting ${files.length} PDF${files.length === 1 ? '' : 's'}${extra}… this can take a minute for a full history.`;
  }
  if (resultEl) resultEl.innerHTML = '';
  const fd = new FormData();
  files.forEach((f) => fd.append('files', f));
  csvFiles.forEach((f) => fd.append('csv_files', f));
  try {
    const data = await fetch(`${API}/statements/convert`, { method: 'POST', body: fd, credentials: 'same-origin' })
      .then(async (r) => {
        const d = await r.json();
        if (!r.ok) {
          const detail = d.detail;
          throw new Error(typeof detail === 'string' ? detail : (detail && JSON.stringify(detail)) || 'Convert failed');
        }
        return d;
      });
    _setupConvert = data;
    _renderSetupConvertResult();
  } catch (err) {
    if (status) status.textContent = err.message || String(err);
    if (resultEl) resultEl.innerHTML = '';
  }
}

async function _previewSetupFile(accountId) {
  const id = accountId || _el('finance-stmt-import-account')?.value || _activeAccountId;
  if (!_setupConvert?.csv || !id) return;
  const file = new File(
    [_setupConvert.csv],
    _setupConvert.filename || 'wells-from-statements.csv',
    { type: 'text/csv' },
  );
  await _postImportPreview(file, 'csv_wells_fargo', id);
}

async function _runImportPreview() {
  const fileInput = _el('finance-import-file');
  const status = _el('finance-import-status');
  const file = fileInput?.files?.[0];
  if (!file) {
    if (status) status.textContent = 'Choose a file first.';
    return;
  }
  const preset = _el('finance-import-preset')?.value || '';
  await _postImportPreview(file, preset);
}

async function _postImportPreview(file, preset, accountId) {
  const status = _el('finance-import-status');
  const previewEl = _el('finance-import-preview');
  const acct = accountId || _activeAccountId;
  if (!acct) {
    if (status) status.textContent = 'Pick an account, or create one from the setup file.';
    return;
  }
  if (status) status.textContent = 'Parsing…';
  const fd = new FormData();
  fd.append('file', file);
  fd.append('account_id', acct);
  if (preset) fd.append('preset', preset);
  const mappingId = _el('finance-import-mapping')?.value || '';
  if (mappingId) fd.append('mapping_id', mappingId);
  if (_preview?.pending_mapping) {
    fd.append('mapping', JSON.stringify(_preview.pending_mapping));
    fd.append('preset', 'csv_generic');
  }
  try {
    _preview = await fetch(`${API}/import/preview`, { method: 'POST', body: fd, credentials: 'same-origin' })
      .then(async (r) => {
        const d = await r.json();
        if (!r.ok) throw new Error(d.detail || 'Preview failed');
        return d;
      });
    if (_preview.needs_mapping) {
      if (status) status.textContent = 'This file needs a column mapping before counts are trustworthy.';
      _renderMappingForm(_preview, previewEl);
      return;
    }
    const enrich = _preview.enrich_count || 0;
    if (status) {
      status.textContent = `${_preview.new_count} new, ${enrich} filled from this file, ${_preview.duplicate_count} already in the books (${_preview.format})`;
    }
    const rows = (_preview.rows || []).slice(0, 100).map((r) =>
      `<tr style="${r.status === 'duplicate' ? 'opacity:0.5' : ''}${r.status === 'enrich' ? ';background:rgba(46,204,113,0.12)' : ''}${r.status === 'possible_manual_duplicate' ? ';outline:1px solid var(--warn,#f1c40f)' : ''}">
        <td>${r.date}</td><td>${_escHtml(r.payee)}</td><td style="text-align:right;">${_fmtMoney(r.amount_cents)}</td><td>${_escHtml(r.status)}</td>
      </tr>`
    ).join('');
    const importLabel = enrich
      ? `Import ${_preview.new_count} new and fill ${enrich}`
      : `Import ${_preview.new_count} transactions`;
    previewEl.innerHTML = `
      ${_preview.warning ? `<p style="color:var(--warn,#f1c40f);">${_escHtml(_preview.warning)}</p>` : ''}
      ${_preview.opening ? `<p>This file includes opening posted <strong>${_fmtMoney(_preview.opening.opening_posted_cents)}</strong> as of ${_escHtml(_preview.opening.opening_as_of)}.</p>
        <label style="display:flex;gap:8px;align-items:center;margin:8px 0;">
          <input type="checkbox" id="finance-import-apply-opening" ${_preview.opening.account_has_opening ? '' : 'checked'} />
          Apply opening posted to this account
        </label>
        ${_preview.opening.account_has_opening ? '<p style="font-size:0.85rem;opacity:0.8;">This account already has an opening posted. Check the box only if you want to replace it.</p>' : ''}
      ` : ''}
      <table style="width:100%;border-collapse:collapse;font-size:0.85rem;margin-top:8px;">
        <thead><tr><th>Date</th><th>Payee</th><th>Amount</th><th>Status</th></tr></thead>
        <tbody>${rows}</tbody>
      </table>
      ${(_preview.rows || []).length > 100 ? '<p>Showing first 100 rows…</p>' : ''}
      <button type="button" id="finance-import-commit-btn" class="btn-primary" style="margin-top:12px;">${importLabel}</button>`;
    _el('finance-import-commit-btn')?.addEventListener('click', _commitImport);
  } catch (err) {
    if (status) status.textContent = err.message || String(err);
    if (previewEl) previewEl.innerHTML = '';
  }
}

function _renderMappingForm(preview, previewEl) {
  const cols = preview.columns || [];
  const suggested = preview.suggested_mapping || {};
  const fields = [
    ['date', 'Date'],
    ['amount', 'Amount'],
    ['debit', 'Debit'],
    ['credit', 'Credit'],
    ['payee', 'Payee'],
    ['memo', 'Memo'],
    ['fitid', 'FITID (optional)'],
    ['check_number', 'Check #'],
    ['bank_category', 'Bank category'],
  ];
  const colOpts = (selected) =>
    `<option value="">—</option>${cols.map((c) =>
      `<option value="${_escHtml(c)}" ${c === selected ? 'selected' : ''}>${_escHtml(c)}</option>`
    ).join('')}`;
  previewEl.innerHTML = `
    <p>Map columns, then preview again. Counts stay hidden until mapping is set.</p>
    <div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(160px,1fr));gap:8px;">
      ${fields.map(([key, label]) =>
        `<label>${label}<select data-map-field="${key}">${colOpts(suggested[key] || '')}</select></label>`
      ).join('')}
    </div>
    <label style="display:block;margin-top:8px;">Save as
      <input id="finance-map-name" type="text" placeholder="PayPal export" />
    </label>
    <button type="button" id="finance-map-apply" class="btn-primary" style="margin-top:8px;">Apply mapping and preview</button>`;
  _el('finance-map-apply')?.addEventListener('click', async () => {
    const mapping = {};
    previewEl.querySelectorAll('[data-map-field]').forEach((sel) => {
      if (sel.value) mapping[sel.dataset.mapField] = sel.value;
    });
    const name = _el('finance-map-name')?.value?.trim();
    if (name && preview.fingerprint) {
      await _api('/import/mappings', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name, fingerprint: preview.fingerprint, mapping }),
      });
    }
    _preview = { pending_mapping: mapping };
    _runImportPreview();
  });
}

async function _commitImport() {
  if (!_preview?.preview_id) return;
  const status = _el('finance-import-status');
  try {
    const applyOpening = !!_el('finance-import-apply-opening')?.checked;
    const result = await _api('/import/commit', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        preview_id: _preview.preview_id,
        skip_duplicates: true,
        apply_opening: applyOpening,
      }),
    });
    if (status) {
      status.textContent = `Imported ${result.imported_count} transactions (${result.duplicate_count} skipped as duplicates).`;
      if (result.enriched_count) status.textContent += ` Filled ${result.enriched_count} existing rows.`;
      if (result.opening_applied) status.textContent += ' Opening posted applied from the file.';
      if (result.warning) status.textContent += ` ${result.warning}`;
    }
    _preview = null;
    await _loadAccounts();
    _activeTab = 'transactions';
    _renderPanel();
  } catch (err) {
    if (status) status.textContent = err.message || String(err);
  }
}

async function _renderBudget() {
  const panel = _el('finance-panel');
  if (!panel) return;
  const seq = _panelLoading(panel);
  const month = _el('finance-budget-month')?.value || new Date().toISOString().slice(0, 7);
  const data = await _api(`/budgets?month=${month}`);
  if (seq !== _renderSeq) return;
  const rows = (data.categories || []).map((c) => `
    <tr>
      <td><span style="display:inline-block;width:10px;height:10px;background:${c.color};border-radius:2px;margin-right:6px;"></span>${c.category_name}</td>
      <td style="text-align:right;">${_fmtMoney(c.spent_cents)}</td>
      <td style="text-align:right;">${c.limit_cents != null ? _fmtMoney(c.limit_cents) : '—'}</td>
      <td style="text-align:right;">${c.remaining_cents != null ? _fmtMoney(c.remaining_cents) : '—'}</td>
      <td><input type="number" min="0" step="1" data-budget-cat="${c.category_id}" placeholder="Set $" value="${c.limit_cents != null ? (c.limit_cents / 100).toFixed(0) : ''}" style="width:80px;" /></td>
    </tr>`).join('');
  _panelSwap(panel, `
    <h3 style="margin-top:0;">Budget — ${data.month}</h3>
    <div style="display:flex;gap:8px;flex-wrap:wrap;align-items:center;margin-bottom:8px;">
      <input id="finance-budget-month" type="month" value="${data.month}" />
      <button type="button" id="finance-budget-reload" class="btn-secondary">Load month</button>
      <button type="button" id="finance-budget-copy" class="btn-secondary">Copy previous month</button>
      <label>Income target $
        <input id="finance-income-target" type="number" step="1" value="${data.income_target_cents != null ? (data.income_target_cents / 100).toFixed(0) : ''}" style="width:90px;" />
      </label>
    </div>
    <p style="opacity:0.8;font-size:0.85rem;">${_escHtml(_classifiedStat(data))} Category rows are gross; reimbursements offset below the table. Planned lines are not posted spend.</p>
    <table style="width:100%;border-collapse:collapse;">
      <thead><tr><th>Category</th><th style="text-align:right;">Spent</th><th style="text-align:right;">Limit</th><th style="text-align:right;">Remaining</th><th>Set limit</th></tr></thead>
      <tbody>${rows || '<tr><td colspan="5">No spending this month yet.</td></tr>'}</tbody>
    </table>
    <button type="button" id="finance-save-budgets" class="btn-secondary" style="margin-top:12px;">Save limits</button>`);
  _el('finance-save-budgets')?.addEventListener('click', async () => {
    const inputs = panel.querySelectorAll('[data-budget-cat]');
    for (const inp of inputs) {
      const dollars = parseFloat(inp.value);
      if (!inp.value || Number.isNaN(dollars)) continue;
      await _api('/budgets', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          category_id: inp.dataset.budgetCat,
          month: data.month,
          limit_cents: Math.round(dollars * 100),
        }),
      });
    }
    const target = parseFloat(_el('finance-income-target')?.value);
    if (!Number.isNaN(target)) {
      await _api('/budgets/income-target', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ month: data.month, income_target_cents: Math.round(target * 100) }),
      });
    }
    _renderBudget();
  });
  _el('finance-budget-reload')?.addEventListener('click', _renderBudget);
  _el('finance-budget-copy')?.addEventListener('click', async () => {
    const [y, m] = data.month.split('-').map(Number);
    const prev = m === 1 ? `${y - 1}-12` : `${y}-${String(m - 1).padStart(2, '0')}`;
    await _api('/budgets/copy', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ from_month: prev, to_month: data.month }),
    });
    _renderBudget();
  });
  await _renderPlannedAndJob(panel, data.month);
}

function _spendTitle(cf) {
  const n = Number(cf.unclassified_count || 0);
  if (n > 0) return `Spend (${n} rows counted by sign)`;
  return 'True spend';
}

function _classifiedStat(cf) {
  const unclassified = Number(cf.unclassified_count || 0);
  const outflow = Number(cf.unclassified_outflow_cents || 0);
  const gross = Number(cf.gross_spend_cents || cf.spending_cents || 0);
  if (!unclassified) return '100% of this month classified.';
  const classifiedPct = gross > 0 ? Math.max(0, Math.round(100 * (gross - outflow) / gross)) : 0;
  return `${classifiedPct}% of ${cf.month || 'this month'} spend classified; ${unclassified} rows worth ${_fmtMoney(outflow)} are not.`;
}

async function _renderReports() {
  const panel = _el('finance-panel');
  if (!panel) return;
  const seq = _panelLoading(panel);
  const month = new Date().toISOString().slice(0, 7);
  const [spending, trends, worth, byAcct] = await Promise.all([
    _api(`/reports/spending?month=${month}`),
    _api('/reports/trends?months=6'),
    _api('/reports/net-worth'),
    _api(`/reports/spend-by-account?month=${month}`),
  ]);
  if (seq !== _renderSeq) return;
  const catRows = (spending.categories || []).map((c) =>
    `<tr><td>${_escHtml(c.category_name)}</td><td style="text-align:right;">${_fmtMoney(c.gross_spent_cents ?? c.spent_cents)}</td><td style="text-align:right;">${c.transaction_count}</td></tr>`
  ).join('');
  const trendRows = (trends.trends || []).map((t) =>
    `<tr><td>${t.month}</td><td style="text-align:right;color:var(--success,#2ecc71);">${_fmtMoney(t.income_cents)}</td><td style="text-align:right;color:var(--danger,#e74c3c);">${_fmtMoney(t.spending_cents)}</td></tr>`
  ).join('');
  const reimbRows = (spending.reimbursements || []).map((r) => {
    const share = r.billed_cents
      ? `${_escHtml(r.payee)}: ${_fmtMoney(r.billed_cents)} billed, ${_fmtMoney(r.reimbursed_cents)} reimbursed, ${_fmtMoney(r.you_bear_cents)} you bear`
      : `${_escHtml(r.payee)} ${_fmtMoney(r.amount_cents)}`;
    return `<tr><td>${r.date || ''}</td><td>${_escHtml(share)}</td><td>${_escHtml(r.memo || '')}</td></tr>`;
  }).join('');
  const funding = spending.unmatched_funding || [];
  const fundingCents = spending.unmatched_funding_cents || 0;
  const unclassifiedNote = spending.unclassified_count
    ? `<p>Up to ${_fmtMoney(spending.unclassified_outflow_cents)} of this may be transfers or reimbursements.</p>`
    : '';
  _panelSwap(panel, `
    <h3 style="margin-top:0;">${_spendTitle(spending)} — ${spending.month}</h3>
    <p style="font-size:0.85rem;opacity:0.85;">${_escHtml(_classifiedStat(spending))}</p>
    ${unclassifiedNote}
    <p>Income ${_fmtMoney(spending.income_cents)} · Gross spend ${_fmtMoney(spending.gross_spend_cents)} · Less reimbursements ${_fmtMoney(spending.reimbursement_in_cents)} · Net ${_fmtMoney(spending.net_spend_cents)}</p>
    <table style="width:100%;border-collapse:collapse;margin-bottom:12px;">
      <thead><tr><th>Category</th><th style="text-align:right;">Spent (gross)</th><th style="text-align:right;">Txns</th></tr></thead>
      <tbody>${catRows || '<tr><td colspan="3">No data</td></tr>'}</tbody>
    </table>
    <p style="font-size:0.85rem;">Less reimbursements received: ${_fmtMoney(spending.reimbursement_in_cents)}</p>
    <h3>Reimbursements</h3>
    <table style="width:100%;border-collapse:collapse;margin-bottom:16px;">
      <thead><tr><th>Date</th><th>Share</th><th>Memo</th></tr></thead>
      <tbody>${reimbRows || '<tr><td colspan="3">None this month</td></tr>'}</tbody>
    </table>
    <p>${funding.length} funding legs with no matching bill, ${_fmtMoney(fundingCents)} total; merchant spend may be missing.</p>
    <h3>Spend by account</h3>
    <table style="width:100%;border-collapse:collapse;margin-bottom:16px;">
      <thead><tr><th>Account</th><th>Purpose</th><th style="text-align:right;">Spend</th></tr></thead>
      <tbody>${(byAcct.accounts || []).map((a) =>
        `<tr><td>${_escHtml(a.name)}</td><td>${_escHtml(a.purpose)}</td><td style="text-align:right;">${_fmtMoney(a.personal_spend_cents)}</td></tr>`
      ).join('') || '<tr><td colspan="3">No data</td></tr>'}</tbody>
    </table>
    <h3>Net worth</h3>
    <p>Assets ${_fmtMoney(worth.assets_cents)} · Liabilities ${_fmtMoney(worth.liabilities_cents)} · Net ${_fmtMoney(worth.net_worth_cents)}</p>
    <h3>6-month trends</h3>
    <table style="width:100%;border-collapse:collapse;">
      <thead><tr><th>Month</th><th style="text-align:right;">Income</th><th style="text-align:right;">Spending</th></tr></thead>
      <tbody>${trendRows}</tbody>
    </table>`);
}

async function _renderPanel() {
  _modal?.querySelectorAll('.finance-tab-btn').forEach((btn) => {
    btn.style.cssText = _tabStyle(btn.dataset.tab);
  });
  if (_activeTab === 'transactions') await _renderTransactions();
  else if (_activeTab === 'import') await _renderImport();
  else if (_activeTab === 'budget') await _renderBudget();
  else if (_activeTab === 'recurring') await _renderRecurring();
  else if (_activeTab === 'reports') await _renderReports();
}

async function _renderPlannedAndJob(panel, month) {
  const [planned, job] = await Promise.all([
    _api('/planned'),
    _api(`/job-scenario?month=${month}&include_business=${_includeBusiness ? 'true' : 'false'}`),
  ]);
  const plannedRows = (planned.planned || []).map((p) =>
    `<tr><td>${_escHtml(p.name)}</td><td>${p.kind}</td><td style="text-align:right;">${_fmtMoney(p.amount_cents)}</td><td>${p.is_funding ? 'funding' : 'need'}</td><td><button type="button" class="btn-secondary" data-del-planned="${p.id}">Remove</button></td></tr>`
  ).join('');
  const surplus = job.surplus_cents == null
    ? (job.partial_data ? 'partial data — surplus withheld' : 'surplus withheld (unclassified outflows)')
    : _fmtMoney(job.surplus_cents);
  const chipRows = (job.chip_in_rows || []).map((r) =>
    `<li>${r.date} ${_escHtml(r.payee)} ${_fmtMoney(r.amount_cents)}</li>`
  ).join('');
  const block = document.createElement('div');
  block.innerHTML = `
    <h3>Planned — not posted spend</h3>
    <p style="font-size:0.8rem;opacity:0.8;">Monthly amount (annual bill divided by 12). starts_on is a note only.</p>
    <table style="width:100%;border-collapse:collapse;">
      <thead><tr><th>Name</th><th>Kind</th><th style="text-align:right;">Monthly</th><th></th><th></th></tr></thead>
      <tbody>${plannedRows || '<tr><td colspan="5">No planned lines</td></tr>'}</tbody>
    </table>
    <div style="display:flex;gap:8px;flex-wrap:wrap;margin:8px 0;">
      <input id="fin-plan-name" placeholder="Rent" />
      <select id="fin-plan-kind">${['rent','utilities','insurance','telecom','reimbursement_swap','savings_funding','other'].map((k) => `<option value="${k}">${k}</option>`).join('')}</select>
      <input id="fin-plan-amt" type="number" step="1" placeholder="$" style="width:80px;" />
      <label><input type="checkbox" id="fin-plan-fund" /> Savings funding</label>
      <button type="button" id="fin-plan-add" class="btn-secondary">Add planned</button>
    </div>
    <h3>Hypothetical job</h3>
    <p>${_escHtml(job.label || 'Hypothetical job scenario — not income on the books')}</p>
    ${job.rent_support_warning ? '<p>Warning: a rent line and another line mentioning rent or support are both included.</p>' : ''}
    <p>Observed ${job.observed_month}${(job.candidate_months || []).length ? ` (also ${(job.candidate_months || []).join(', ')})` : ''}. Survival need ${_fmtMoney(job.survival_need_cents)}. Surplus ${surplus}.</p>
    <p>Largest spend rows:</p>
    <ul>${(job.largest_rows || []).map((r) => `<li>${r.date || ''} ${_escHtml(r.payee || '')} ${_fmtMoney(r.amount_cents)}</li>`).join('') || '<li>None</li>'}</ul>
    <p>With savings target ${_fmtMoney(job.needed_cents)}; surplus ${job.surplus_with_savings_cents == null ? 'withheld' : _fmtMoney(job.surplus_with_savings_cents)}.</p>
    <p>Trip spend excluded ${_fmtMoney(job.trip_spend_excluded_cents)}. Navy Fed business ${_fmtMoney(job.business_spend_cents)}. ${_escHtml(job.business_income_note || '')}</p>
    <label><input type="checkbox" id="fin-job-business" ${_includeBusiness ? 'checked' : ''} /> Include Navy Fed business spend in the floor</label>
    <p>Unclassified ${job.unclassified_count} rows / ${_fmtMoney(job.unclassified_outflow_cents)}.</p>
    <p>Excluded chip-in:</p>
    <ul>${chipRows || '<li>None</li>'}</ul>
    <label>Take-home $<input id="fin-job-takehome" type="number" step="1" value="${job.take_home_cents ? (job.take_home_cents / 100).toFixed(0) : ''}" style="width:100px;" /></label>
    <button type="button" id="fin-job-save" class="btn-primary">Save hypothetical take-home</button>`;
  panel.appendChild(block);
  block.querySelectorAll('[data-del-planned]').forEach((btn) => {
    btn.addEventListener('click', async () => {
      await _api(`/planned/${btn.dataset.delPlanned}`, { method: 'DELETE' });
      _renderBudget();
    });
  });
  _el('fin-plan-add')?.addEventListener('click', async () => {
    const dollars = parseFloat(_el('fin-plan-amt')?.value);
    if (Number.isNaN(dollars)) return;
    await _api('/planned', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        name: _el('fin-plan-name')?.value || 'Planned',
        kind: _el('fin-plan-kind')?.value || 'other',
        amount_cents: Math.round(dollars * 100),
        is_funding: !!_el('fin-plan-fund')?.checked,
      }),
    });
    _renderBudget();
  });
  _el('fin-job-business')?.addEventListener('change', (e) => {
    _includeBusiness = !!e.target.checked;
    _renderBudget();
  });
  _el('fin-job-save')?.addEventListener('click', async () => {
    const dollars = parseFloat(_el('fin-job-takehome')?.value);
    if (Number.isNaN(dollars)) return;
    await _api('/job-scenario', {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ take_home_cents: Math.round(dollars * 100), label: 'Hypothetical job' }),
    });
    _renderBudget();
  });
}

async function _renderRecurring() {
  const panel = _el('finance-panel');
  if (!panel) return;
  const seq = _panelLoading(panel);
  const data = await _api('/recurring');
  if (seq !== _renderSeq) return;
  const rows = (data.series || []).map((s) => `
    <tr>
      <td>${_escHtml(s.display_payee)}</td>
      <td>${s.cadence}</td>
      <td style="text-align:right;">${_fmtMoney(s.median_amount_cents)}</td>
      <td>${s.status === 'automatic' ? 'Automatic' : (s.status === 'dismissed' ? 'Dismissed' : 'Detected')}</td>
      <td>${s.skip_reason ? _escHtml(s.skip_reason) : ''}</td>
      <td>
        <button type="button" class="btn-secondary" data-rec-auto="${s.id}" ${s.skip_reason ? 'disabled' : ''}>Mark automatic</button>
        <button type="button" class="btn-secondary" data-rec-dismiss="${s.id}">Dismiss</button>
      </td>
    </tr>`).join('');
  _panelSwap(panel, `
    <h3 style="margin-top:0;">Recurring</h3>
    <p style="font-size:0.85rem;opacity:0.8;">Detected means the series was inferred. Automatic is a label, not a bill poster.</p>
    <table style="width:100%;border-collapse:collapse;">
      <thead><tr><th>Payee</th><th>Cadence</th><th style="text-align:right;">Median</th><th>Status</th><th></th><th></th></tr></thead>
      <tbody>${rows || '<tr><td colspan="6">No recurring series yet.</td></tr>'}</tbody>
    </table>`);
  panel.querySelectorAll('[data-rec-auto]').forEach((btn) => {
    btn.addEventListener('click', async () => {
      const spend = CLASS_OPTIONS.find((o) => o.value === 'spend');
      const cat = _categories.find((c) => !c.parent_id && c.name === 'Subscriptions') || _categories[0];
      try {
        await _api(`/recurring/${btn.dataset.recAuto}`, {
          method: 'PATCH',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ status: 'automatic', category_id: cat?.id, movement_class: spend?.value || 'spend' }),
        });
      } catch (err) {
        alert(err.message || String(err));
      }
      _renderRecurring();
    });
  });
  panel.querySelectorAll('[data-rec-dismiss]').forEach((btn) => {
    btn.addEventListener('click', async () => {
      await _api(`/recurring/${btn.dataset.recDismiss}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ status: 'dismissed' }),
      });
      _renderRecurring();
    });
  });
}

export function isFinanceOpen() {
  return _open;
}

export async function openFinance() {
  _getModal();
  _open = true;
  _modal.style.display = 'flex';
  try {
    await Promise.all([_loadAccounts(), _loadCategories()]);
    await _renderPanel();
  } catch (err) {
    const panel = _el('finance-panel');
    if (panel) _panelSwap(panel, `<p style="color:var(--danger,#e74c3c);">${_escHtml(err.message || err)}</p>`);
  }
  const Modals = await import('/static/js/modalManager.js');
  Modals.register('finance-modal', {
    railBtnId: 'rail-finance',
    sidebarBtnId: 'tool-finance-btn',
    closeFn: () => closeFinance(),
    restoreFn: () => {},
  });
}

export function closeFinance() {
  _open = false;
  if (_modal) _modal.style.display = 'none';
}

export default { openFinance, closeFinance, isFinanceOpen };
