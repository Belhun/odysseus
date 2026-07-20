/**
 * Thin sales / tax report — date range + CSV download.
 * Route: #sysforge/reports/sales
 */

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

function defaultRange() {
  const to = new Date();
  const from = new Date(to.getFullYear(), to.getMonth(), 1);
  const iso = (d) => d.toISOString().slice(0, 10);
  return { from: iso(from), to: iso(to) };
}

/**
 * @param {HTMLElement} container
 * @param {{
 *   api: (path: string, opts?: object) => Promise<object>,
 *   apiBase?: string,
 * }} deps
 */
export function mountSalesReport(container, deps) {
  if (container.dataset.mounted === '1') return;

  const range = defaultRange();
  container.innerHTML = `
    <div class="sysforge-sales-report">
      <h3 class="sysforge-view-heading" tabindex="-1">Sales report</h3>
      <p class="sysforge-dashboard-lead">
        Date-range totals for parts, labor, tax, collected payments, and outstanding.
      </p>
      <div class="sysforge-parts-toolbar sysforge-sales-toolbar">
        <label>From
          <input type="date" id="sysforge-sales-from" value="${escapeHtml(range.from)}" />
        </label>
        <label>To
          <input type="date" id="sysforge-sales-to" value="${escapeHtml(range.to)}" />
        </label>
        <button type="button" class="btn-secondary" id="sysforge-sales-run">Run</button>
        <button type="button" class="btn-secondary" id="sysforge-sales-csv">Download CSV</button>
      </div>
      <p class="sysforge-parts-error" id="sysforge-sales-error" hidden></p>
      <dl class="sysforge-sales-summary" id="sysforge-sales-summary"></dl>
      <ul class="sysforge-outstanding-list" id="sysforge-sales-list"></ul>
      <p class="sysforge-parts-empty" id="sysforge-sales-empty" hidden>
        No invoices in this date range.
      </p>
    </div>`;

  container.dataset.mounted = '1';
  container._sysforgeSalesDeps = deps;

  const showError = (msg) => {
    const errorEl = container.querySelector('#sysforge-sales-error');
    if (!errorEl) return;
    if (msg) {
      errorEl.textContent = msg;
      errorEl.hidden = false;
    } else {
      errorEl.textContent = '';
      errorEl.hidden = true;
    }
  };

  const reload = async () => {
    const from = container.querySelector('#sysforge-sales-from')?.value || '';
    const to = container.querySelector('#sysforge-sales-to')?.value || '';
    const summaryEl = container.querySelector('#sysforge-sales-summary');
    const listEl = container.querySelector('#sysforge-sales-list');
    const emptyEl = container.querySelector('#sysforge-sales-empty');
    showError('');
    try {
      const q = new URLSearchParams();
      if (from) q.set('from', from);
      if (to) q.set('to', to);
      const data = await deps.api(`/reports/sales?${q.toString()}`);
      const s = data?.summary || {};
      if (summaryEl) {
        summaryEl.innerHTML = `
          <div><dt>Invoices</dt><dd>${escapeHtml(String(s.invoice_count ?? 0))}</dd></div>
          <div><dt>Parts</dt><dd>${escapeHtml(formatMoney(s.parts_subtotal_cents))}</dd></div>
          <div><dt>Labor</dt><dd>${escapeHtml(formatMoney(s.labor_cost_cents))}</dd></div>
          <div><dt>Tax</dt><dd>${escapeHtml(formatMoney(s.tax_amount_cents))}</dd></div>
          <div><dt>Final total</dt><dd>${escapeHtml(formatMoney(s.final_total_cents))}</dd></div>
          <div><dt>Collected</dt><dd>${escapeHtml(formatMoney(s.collected_payments_cents))}</dd></div>
          <div><dt>Outstanding</dt><dd>${escapeHtml(formatMoney(s.outstanding_cents))}</dd></div>`;
      }
      const rows = Array.isArray(data?.invoices) ? data.invoices : [];
      if (listEl) {
        listEl.innerHTML = rows
          .map(
            (r) => `<li>
              <span>${escapeHtml(r.name || `Invoice #${r.invoice_id}`)}</span>
              <span>${escapeHtml(r.status || '')} · ${formatMoney(r.final_total_cents)}
                · tax ${formatMoney(r.tax_amount_cents)}
                · bal ${formatMoney(r.balance_cents)}</span>
            </li>`
          )
          .join('');
      }
      if (emptyEl) emptyEl.hidden = rows.length > 0;
    } catch (err) {
      showError(err?.message || String(err));
      if (summaryEl) summaryEl.innerHTML = '';
      if (listEl) listEl.innerHTML = '';
      if (emptyEl) emptyEl.hidden = true;
    }
  };
  container._sysforgeReloadSales = reload;

  container.querySelector('#sysforge-sales-run')?.addEventListener('click', () => {
    void reload();
  });

  container.querySelector('#sysforge-sales-csv')?.addEventListener('click', () => {
    const from = container.querySelector('#sysforge-sales-from')?.value || '';
    const to = container.querySelector('#sysforge-sales-to')?.value || '';
    const q = new URLSearchParams({ format: 'csv' });
    if (from) q.set('from', from);
    if (to) q.set('to', to);
    const base = deps.apiBase || '/api/sysforge';
    window.open(`${base}/reports/sales?${q.toString()}`, '_blank');
  });
}

/**
 * @param {HTMLElement} container
 */
export async function activateSalesReport(container) {
  container.querySelector('.sysforge-view-heading')?.focus?.({ preventScroll: true });
  if (typeof container._sysforgeReloadSales === 'function') {
    await container._sysforgeReloadSales();
  }
}
