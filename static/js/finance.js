/**
 * Finance — manual bank import, accounts, budgets, spending reports.
 */

import { makeWindowDraggable } from './windowDrag.js';
import { bindMenuDismiss } from './escMenuStack.js';

const API = `${window.location.origin}/api/finance`;
let _open = false;
let _modal = null;
let _accounts = [];
let _categories = [];
let _activeAccountId = null;
let _activeTab = 'transactions';
let _preview = null;

function _el(id) {
  return document.getElementById(id);
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
    <div class="modal-content finance-modal-content" style="width:min(1100px,96vw);max-height:90vh;display:flex;flex-direction:column;">
      <div class="modal-header finance-modal-header" style="cursor:move;">
        <h2 style="margin:0;font-size:1.1rem;">Finance</h2>
        <button type="button" class="modal-close" id="finance-close-btn" aria-label="Close">&times;</button>
      </div>
      <div class="finance-toolbar" style="display:flex;gap:8px;padding:8px 12px;border-bottom:1px solid var(--border-color,#333);flex-wrap:wrap;align-items:center;">
        <select id="finance-account-select" style="min-width:180px;"></select>
        <button type="button" id="finance-add-account-btn" class="btn-secondary">+ Account</button>
        <div style="flex:1"></div>
        <button type="button" class="finance-tab-btn" data-tab="transactions">Transactions</button>
        <button type="button" class="finance-tab-btn" data-tab="import">Import</button>
        <button type="button" class="finance-tab-btn" data-tab="budget">Budget</button>
        <button type="button" class="finance-tab-btn" data-tab="reports">Reports</button>
      </div>
      <div id="finance-panel" style="flex:1;overflow:auto;padding:12px;"></div>
    </div>`;
  document.body.appendChild(_modal);
  makeWindowDraggable(_modal.querySelector('.finance-modal-content'), _modal.querySelector('.finance-modal-header'));
  _el('finance-close-btn')?.addEventListener('click', closeFinance);
  _modal.addEventListener('click', (e) => { if (e.target === _modal) closeFinance(); });
  _el('finance-add-account-btn')?.addEventListener('click', _promptNewAccount);
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
    `<option value="${a.id}" ${a.id === _activeAccountId ? 'selected' : ''}>${a.name} (${_fmtMoney(a.balance_cents)})</option>`
  ).join('') || '<option value="">No accounts</option>';
}

async function _loadCategories() {
  const data = await _api('/categories');
  _categories = data.categories || [];
}

async function _promptNewAccount() {
  const name = prompt('Account name (e.g. Wells Fargo Checking):');
  if (!name?.trim()) return;
  const institution = prompt('Institution (optional):') || '';
  const type = prompt('Type: checking, savings, credit_card, loan, cash, other', 'checking') || 'checking';
  await _api('/accounts', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ name: name.trim(), institution, account_type: type }),
  });
  await _loadAccounts();
  _renderPanel();
}

function _tabStyle(tab) {
  return _activeTab === tab ? 'font-weight:600;text-decoration:underline;' : '';
}

async function _renderTransactions() {
  const panel = _el('finance-panel');
  if (!panel) return;
  if (!_activeAccountId) {
    panel.innerHTML = '<p>Create an account to get started.</p>';
    return;
  }
  panel.innerHTML = '<p>Loading transactions…</p>';
  const search = panel.dataset.search || '';
  const data = await _api(`/transactions?account_id=${encodeURIComponent(_activeAccountId)}&limit=200&search=${encodeURIComponent(search)}`);
  const rows = (data.transactions || []).map((tx) => {
    const amtClass = tx.amount_cents < 0 ? 'color:var(--danger,#e74c3c)' : 'color:var(--success,#2ecc71)';
    const catOpts = _categories.map((c) =>
      `<option value="${c.id}" ${c.id === tx.category_id ? 'selected' : ''}>${c.name}</option>`
    ).join('');
    return `<tr>
      <td>${tx.date || ''}</td>
      <td style="max-width:320px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;" title="${(tx.payee || '').replace(/"/g, '&quot;')}">${tx.payee || ''}</td>
      <td style="${amtClass};text-align:right;">${_fmtMoney(tx.amount_cents)}</td>
      <td><select data-tx-cat="${tx.id}" class="finance-cat-select"><option value="">—</option>${catOpts}</select></td>
    </tr>`;
  }).join('');
  panel.innerHTML = `
    <div style="margin-bottom:8px;display:flex;gap:8px;">
      <input id="finance-tx-search" placeholder="Search payee…" value="${search.replace(/"/g, '&quot;')}" style="flex:1;" />
    </div>
    <table class="finance-table" style="width:100%;border-collapse:collapse;font-size:0.9rem;">
      <thead><tr><th>Date</th><th>Payee</th><th style="text-align:right;">Amount</th><th>Category</th></tr></thead>
      <tbody>${rows || '<tr><td colspan="4">No transactions yet. Import a CSV from your bank.</td></tr>'}</tbody>
    </table>`;
  _el('finance-tx-search')?.addEventListener('input', (e) => {
    panel.dataset.search = e.target.value;
    clearTimeout(panel._searchTimer);
    panel._searchTimer = setTimeout(() => _renderTransactions(), 300);
  });
  panel.querySelectorAll('.finance-cat-select').forEach((sel) => {
    sel.addEventListener('change', async () => {
      await _api(`/transactions/${sel.dataset.txCat}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ category_id: sel.value || null }),
      });
    });
  });
}

async function _renderImport() {
  const panel = _el('finance-panel');
  if (!panel) return;
  if (!_activeAccountId) {
    panel.innerHTML = '<p>Create an account first, then import a CSV or QFX export from your bank.</p>';
    return;
  }
  panel.innerHTML = `
    <p style="opacity:0.85;margin-top:0;">Upload a CSV or QFX/OFX export from Wells Fargo, Navy Federal, or another bank. Data stays on this server.</p>
    <div style="display:flex;gap:8px;flex-wrap:wrap;align-items:center;margin-bottom:12px;">
      <input type="file" id="finance-import-file" accept=".csv,.qfx,.ofx,text/csv" />
      <select id="finance-import-preset">
        <option value="">Auto-detect</option>
        <option value="csv_wells_fargo">Wells Fargo CSV</option>
        <option value="csv_navy_federal">Navy Federal CSV</option>
        <option value="csv_generic">Generic CSV</option>
      </select>
      <button type="button" id="finance-import-preview-btn" class="btn-primary">Preview import</button>
    </div>
    <div id="finance-import-status"></div>
    <div id="finance-import-preview"></div>`;
  _el('finance-import-preview-btn')?.addEventListener('click', _runImportPreview);
}

async function _runImportPreview() {
  const fileInput = _el('finance-import-file');
  const status = _el('finance-import-status');
  const previewEl = _el('finance-import-preview');
  const file = fileInput?.files?.[0];
  if (!file) {
    if (status) status.textContent = 'Choose a file first.';
    return;
  }
  if (status) status.textContent = 'Parsing…';
  const fd = new FormData();
  fd.append('file', file);
  fd.append('account_id', _activeAccountId);
  const preset = _el('finance-import-preset')?.value || '';
  if (preset) fd.append('preset', preset);
  try {
    _preview = await fetch(`${API}/import/preview`, { method: 'POST', body: fd, credentials: 'same-origin' })
      .then(async (r) => {
        const d = await r.json();
        if (!r.ok) throw new Error(d.detail || 'Preview failed');
        return d;
      });
    if (status) status.textContent = `${_preview.new_count} new, ${_preview.duplicate_count} duplicates (${_preview.format})`;
    const rows = (_preview.rows || []).slice(0, 100).map((r) =>
      `<tr style="${r.status === 'duplicate' ? 'opacity:0.5' : ''}">
        <td>${r.date}</td><td>${r.payee}</td><td style="text-align:right;">${_fmtMoney(r.amount_cents)}</td><td>${r.status}</td>
      </tr>`
    ).join('');
    previewEl.innerHTML = `
      <table style="width:100%;border-collapse:collapse;font-size:0.85rem;margin-top:8px;">
        <thead><tr><th>Date</th><th>Payee</th><th>Amount</th><th>Status</th></tr></thead>
        <tbody>${rows}</tbody>
      </table>
      ${(_preview.rows || []).length > 100 ? '<p>Showing first 100 rows…</p>' : ''}
      <button type="button" id="finance-import-commit-btn" class="btn-primary" style="margin-top:12px;">Import ${_preview.new_count} transactions</button>`;
    _el('finance-import-commit-btn')?.addEventListener('click', _commitImport);
  } catch (err) {
    if (status) status.textContent = err.message || String(err);
    if (previewEl) previewEl.innerHTML = '';
  }
}

async function _commitImport() {
  if (!_preview?.preview_id) return;
  const status = _el('finance-import-status');
  try {
    const result = await _api('/import/commit', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ preview_id: _preview.preview_id, skip_duplicates: true }),
    });
    if (status) status.textContent = `Imported ${result.imported_count} transactions (${result.duplicate_count} skipped as duplicates).`;
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
  const month = new Date().toISOString().slice(0, 7);
  const data = await _api(`/budgets?month=${month}`);
  const rows = (data.categories || []).map((c) => `
    <tr>
      <td><span style="display:inline-block;width:10px;height:10px;background:${c.color};border-radius:2px;margin-right:6px;"></span>${c.category_name}</td>
      <td style="text-align:right;">${_fmtMoney(c.spent_cents)}</td>
      <td style="text-align:right;">${c.limit_cents != null ? _fmtMoney(c.limit_cents) : '—'}</td>
      <td style="text-align:right;">${c.remaining_cents != null ? _fmtMoney(c.remaining_cents) : '—'}</td>
      <td><input type="number" min="0" step="1" data-budget-cat="${c.category_id}" placeholder="Set $" value="${c.limit_cents != null ? (c.limit_cents / 100).toFixed(0) : ''}" style="width:80px;" /></td>
    </tr>`).join('');
  panel.innerHTML = `
    <h3 style="margin-top:0;">Budget — ${data.month}</h3>
    <p style="opacity:0.8;font-size:0.85rem;">Set monthly limits (whole dollars). Spending is based on categorized outflows.</p>
    <table style="width:100%;border-collapse:collapse;">
      <thead><tr><th>Category</th><th style="text-align:right;">Spent</th><th style="text-align:right;">Limit</th><th style="text-align:right;">Remaining</th><th>Set limit</th></tr></thead>
      <tbody>${rows || '<tr><td colspan="5">No spending this month yet.</td></tr>'}</tbody>
    </table>
    <button type="button" id="finance-save-budgets" class="btn-secondary" style="margin-top:12px;">Save limits</button>`;
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
    _renderBudget();
  });
}

async function _renderReports() {
  const panel = _el('finance-panel');
  if (!panel) return;
  const month = new Date().toISOString().slice(0, 7);
  const [spending, trends] = await Promise.all([
    _api(`/reports/spending?month=${month}`),
    _api('/reports/trends?months=6'),
  ]);
  const catRows = (spending.categories || []).map((c) =>
    `<tr><td>${c.category_name}</td><td style="text-align:right;">${_fmtMoney(c.spent_cents)}</td><td style="text-align:right;">${c.transaction_count}</td></tr>`
  ).join('');
  const trendRows = (trends.trends || []).map((t) =>
    `<tr><td>${t.month}</td><td style="text-align:right;color:var(--success,#2ecc71);">${_fmtMoney(t.income_cents)}</td><td style="text-align:right;color:var(--danger,#e74c3c);">${_fmtMoney(t.spending_cents)}</td></tr>`
  ).join('');
  panel.innerHTML = `
    <h3 style="margin-top:0;">Spending by category — ${spending.month}</h3>
    <table style="width:100%;border-collapse:collapse;margin-bottom:20px;">
      <thead><tr><th>Category</th><th style="text-align:right;">Spent</th><th style="text-align:right;">Txns</th></tr></thead>
      <tbody>${catRows || '<tr><td colspan="3">No data</td></tr>'}</tbody>
    </table>
    <h3>6-month trends</h3>
    <table style="width:100%;border-collapse:collapse;">
      <thead><tr><th>Month</th><th style="text-align:right;">Income</th><th style="text-align:right;">Spending</th></tr></thead>
      <tbody>${trendRows}</tbody>
    </table>`;
}

async function _renderPanel() {
  _modal?.querySelectorAll('.finance-tab-btn').forEach((btn) => {
    btn.style.cssText = _tabStyle(btn.dataset.tab);
  });
  if (_activeTab === 'transactions') await _renderTransactions();
  else if (_activeTab === 'import') await _renderImport();
  else if (_activeTab === 'budget') await _renderBudget();
  else if (_activeTab === 'reports') await _renderReports();
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
    if (panel) panel.innerHTML = `<p style="color:var(--danger,#e74c3c);">${err.message || err}</p>`;
  }
  const Modals = await import('./modalManager.js');
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
