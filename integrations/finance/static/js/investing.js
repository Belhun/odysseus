/**
 * Finance investing panel. Manual holdings; Odysseus does not fetch quotes.
 * Orchestrator wires window.renderFinanceInvesting from index.js.
 */

const EMPTY_COPY =
  'No holdings yet. Add an asset and type its current value. Odysseus does not fetch quotes.';

const KINDS = [
  { value: 'stock', label: 'Stock' },
  { value: 'etf', label: 'ETF' },
  { value: 'fund', label: 'Fund' },
  { value: 'crypto', label: 'Crypto' },
  { value: 'cash', label: 'Cash' },
  { value: 'other', label: 'Other' },
];

function _kindLabel(kind) {
  return KINDS.find((k) => k.value === kind)?.label || kind || 'Other';
}

function _centsFromDollars(raw) {
  const s = String(raw ?? '').trim().replace(/\$/g, '').replace(/,/g, '');
  if (!s) return 0;
  const n = Number(s);
  if (!Number.isFinite(n) || n < 0) return null;
  return Math.round(n * 100);
}

function _dollarsFromCents(cents) {
  return ((Number(cents) || 0) / 100).toFixed(2);
}

function _gainClass(cents) {
  const n = Number(cents) || 0;
  if (n > 0) return 'color:var(--success,#50fa7b);';
  if (n < 0) return 'color:var(--danger,#e06c75);';
  return '';
}

export async function renderFinanceInvesting(ctx) {
  const panel = ctx?.panel;
  if (!panel) return;
  const api = ctx.api;
  const esc = ctx.escHtml || ((t) => String(t ?? '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;'));
  const moneyHtml = ctx.moneyHtml || ((cents) => {
    const n = (Number(cents) || 0) / 100;
    const sign = n < 0 ? '-' : '';
    return `<span class="finance-money">${sign}$${Math.abs(n).toFixed(2)}</span>`;
  });
  let accounts = ctx.accounts || [];

  panel.style.pointerEvents = '';
  panel.style.opacity = '1';

  const state = { form: null, valueAsset: null };

  async function reload() {
    try {
      if (!accounts.length) {
        try {
          const acctData = await api('/accounts');
          accounts = acctData.accounts || [];
        } catch (_) { /* optional label */ }
      }
      const [summary, listed] = await Promise.all([
        api('/invest/summary'),
        api('/invest/assets'),
      ]);
      paint(summary, listed.assets || [], null);
    } catch (err) {
      paint(null, [], err.message || String(err));
    }
  }

  function kindOptions(selected) {
    return KINDS.map((k) => (
      `<option value="${k.value}" ${k.value === selected ? 'selected' : ''}>${k.label}</option>`
    )).join('');
  }

  function accountOptions(selected) {
    const opts = [`<option value="">(none — label only)</option>`];
    for (const acct of accounts) {
      opts.push(
        `<option value="${esc(acct.id)}" ${acct.id === selected ? 'selected' : ''}>${esc(acct.name)}</option>`
      );
    }
    return opts.join('');
  }

  function formHtml(asset) {
    const a = asset || {};
    return `
      <div class="finance-card" id="invest-form-card" style="margin-bottom:12px;">
        <h3 style="margin:0 0 8px;">${asset ? 'Edit holding' : 'Add holding'}</h3>
        <p style="opacity:0.75;margin:0 0 10px;">Type the value from your broker. Odysseus does not fetch quotes. Optional account is a label, not a cash move.</p>
        <div style="display:grid;gap:8px;grid-template-columns:1fr 1fr;">
          <label>Name<input id="inv-name" value="${esc(a.name || '')}" /></label>
          <label>Symbol<input id="inv-symbol" value="${esc(a.symbol || '')}" /></label>
          <label>Kind<select id="inv-kind">${kindOptions(a.asset_kind || 'other')}</select></label>
          <label>Account<select id="inv-account">${accountOptions(a.account_id || '')}</select></label>
          <label>Shares<input id="inv-shares" value="${esc(a.shares || '')}" /></label>
          <label>Cost basis<input id="inv-cost" value="${asset ? _dollarsFromCents(a.cost_basis_cents) : ''}" /></label>
          <label>Current value<input id="inv-value" value="${asset ? _dollarsFromCents(a.current_value_cents) : ''}" /></label>
          <label>Notes<input id="inv-notes" value="${esc(a.notes || '')}" /></label>
        </div>
        <div style="margin-top:10px;display:flex;gap:8px;">
          <button type="button" class="btn-primary" id="inv-save">Save</button>
          <button type="button" class="btn-secondary" id="inv-cancel">Cancel</button>
          ${asset ? '<button type="button" class="btn-secondary" id="inv-archive">Archive</button>' : ''}
        </div>
      </div>`;
  }

  function valueFormHtml(asset) {
    return `
      <div class="finance-card" id="invest-value-card" style="margin-bottom:12px;">
        <h3 style="margin:0 0 8px;">Update value · ${esc(asset.name)}</h3>
        <p style="opacity:0.75;margin:0 0 10px;">Type the value from your broker. Odysseus does not fetch quotes.</p>
        <label>Current value<input id="inv-new-value" value="${_dollarsFromCents(asset.current_value_cents)}" /></label>
        <label>As of<input id="inv-as-of" type="date" /></label>
        <div style="margin-top:10px;display:flex;gap:8px;">
          <button type="button" class="btn-primary" id="inv-value-save">Save</button>
          <button type="button" class="btn-secondary" id="inv-value-cancel">Cancel</button>
        </div>
      </div>`;
  }

  function paint(summary, assets, error) {
    if (error) {
      panel.innerHTML = `
        <p style="color:var(--danger,#e74c3c);">${esc(error)}</p>
        <button type="button" class="btn-secondary" id="inv-retry">Retry</button>`;
      panel.querySelector('#inv-retry')?.addEventListener('click', reload);
      return;
    }
    const cards = summary
      ? `
        <div class="finance-report-cards" style="display:flex;gap:10px;flex-wrap:wrap;margin-bottom:12px;">
          <div class="finance-card"><div style="opacity:0.7;">Current value</div><div>${moneyHtml(summary.total_current_value_cents)}</div></div>
          <div class="finance-card"><div style="opacity:0.7;">Cost basis</div><div>${moneyHtml(summary.total_cost_basis_cents)}</div></div>
          <div class="finance-card"><div style="opacity:0.7;">Unrealized gain</div><div style="${_gainClass(summary.unrealized_gain_cents)}">${moneyHtml(summary.unrealized_gain_cents)}${summary.unrealized_gain_pct == null ? '' : ` (${esc(summary.unrealized_gain_pct)}%)`}</div></div>
        </div>
        <div style="margin-bottom:10px;opacity:0.8;">${(summary.allocation || []).map((row) =>
          `${esc(_kindLabel(row.asset_kind))} ${esc(row.pct)}%`).join(' · ') || ''}</div>`
      : '';
    const rows = (assets || []).map((a) => `
      <tr data-id="${esc(a.id)}">
        <td>${esc(a.name)}${a.symbol ? ` <span style="opacity:0.7;">${esc(a.symbol)}</span>` : ''}</td>
        <td>${esc(_kindLabel(a.asset_kind))}</td>
        <td>${esc(a.shares)}</td>
        <td class="finance-money">${moneyHtml(a.current_value_cents)}</td>
        <td style="${_gainClass(a.unrealized_gain_cents)}">${moneyHtml(a.unrealized_gain_cents)}</td>
        <td>
          <button type="button" class="btn-secondary" data-edit="${esc(a.id)}">Edit</button>
          <button type="button" class="btn-secondary" data-value="${esc(a.id)}">Value</button>
        </td>
      </tr>`).join('');
    const table = assets.length
      ? `<table class="finance-table"><thead><tr><th>Holding</th><th>Kind</th><th>Shares</th><th>Value</th><th>Gain</th><th></th></tr></thead><tbody>${rows}</tbody></table>`
      : `<p>${EMPTY_COPY}</p>`;
    const extra = state.form === 'add'
      ? formHtml(null)
      : state.form?.id
        ? formHtml(assets.find((a) => a.id === state.form.id))
        : state.valueAsset
          ? valueFormHtml(state.valueAsset)
          : '';
    panel.innerHTML = `
      ${cards}
      <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px;">
        <h3 style="margin:0;">Holdings</h3>
        <button type="button" class="btn-primary" id="inv-add">Add holding</button>
      </div>
      ${extra}
      ${table}`;
    bind(assets);
  }

  function bind(assets) {
    const byId = Object.fromEntries((assets || []).map((a) => [a.id, a]));
    panel.querySelector('#inv-add')?.addEventListener('click', () => {
      state.form = 'add';
      state.valueAsset = null;
      reload();
    });
    panel.querySelectorAll('[data-edit]').forEach((btn) => {
      btn.addEventListener('click', () => {
        state.form = byId[btn.dataset.edit] || { id: btn.dataset.edit };
        state.valueAsset = null;
        reload();
      });
    });
    panel.querySelectorAll('[data-value]').forEach((btn) => {
      btn.addEventListener('click', () => {
        state.valueAsset = byId[btn.dataset.value];
        state.form = null;
        reload();
      });
    });
    panel.querySelector('#inv-cancel')?.addEventListener('click', () => {
      state.form = null;
      reload();
    });
    panel.querySelector('#inv-value-cancel')?.addEventListener('click', () => {
      state.valueAsset = null;
      reload();
    });
    panel.querySelector('#inv-save')?.addEventListener('click', async () => {
      const cost = _centsFromDollars(panel.querySelector('#inv-cost')?.value);
      const value = _centsFromDollars(panel.querySelector('#inv-value')?.value);
      if (cost === null || value === null) {
        window.alert('Cost basis and current value must be amounts 0 or more.');
        return;
      }
      const body = {
        name: panel.querySelector('#inv-name')?.value || '',
        symbol: panel.querySelector('#inv-symbol')?.value || '',
        asset_kind: panel.querySelector('#inv-kind')?.value || 'other',
        account_id: panel.querySelector('#inv-account')?.value || null,
        shares: panel.querySelector('#inv-shares')?.value || '0',
        cost_basis_cents: cost,
        current_value_cents: value,
        notes: panel.querySelector('#inv-notes')?.value || '',
      };
      try {
        if (state.form && state.form !== 'add' && state.form.id) {
          await api(`/invest/assets/${state.form.id}`, {
            method: 'PATCH',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(body),
          });
        } else {
          await api('/invest/assets', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(body),
          });
        }
        state.form = null;
        await reload();
      } catch (err) {
        window.alert(err.message || err);
      }
    });
    panel.querySelector('#inv-archive')?.addEventListener('click', async () => {
      if (!state.form?.id) return;
      try {
        await api(`/invest/assets/${state.form.id}`, {
          method: 'PATCH',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ archived: true }),
        });
        state.form = null;
        await reload();
      } catch (err) {
        window.alert(err.message || err);
      }
    });
    panel.querySelector('#inv-value-save')?.addEventListener('click', async () => {
      if (!state.valueAsset) return;
      const value = _centsFromDollars(panel.querySelector('#inv-new-value')?.value);
      if (value === null) {
        window.alert('Current value must be an amount 0 or more.');
        return;
      }
      const asOf = panel.querySelector('#inv-as-of')?.value || undefined;
      try {
        await api(`/invest/assets/${state.valueAsset.id}/value`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ current_value_cents: value, as_of: asOf }),
        });
        state.valueAsset = null;
        await reload();
      } catch (err) {
        window.alert(err.message || err);
      }
    });
  }

  await reload();
}

window.renderFinanceInvesting = renderFinanceInvesting;
