/**
 * Outstanding invoices — balance > 0 after non-voided payments.
 * Route: #sysforge/invoices-outstanding
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

/**
 * @param {HTMLElement} container
 * @param {{
 *   api: (path: string, opts?: object) => Promise<object>,
 *   navigate?: (routeKey: string, opts?: object) => void,
 *   navigateToInvoiceViewer?: (invoiceId: string|number) => void,
 * }} deps
 */
export function mountOutstandingInvoices(container, deps) {
  if (container.dataset.mounted === '1') return;

  container.innerHTML = `
    <div class="sysforge-outstanding">
      <h3 class="sysforge-view-heading" tabindex="-1">Outstanding invoices</h3>
      <p class="sysforge-dashboard-lead">Invoices with a balance due after recorded payments.</p>
      <div class="sysforge-parts-toolbar">
        <button type="button" class="btn-secondary" id="sysforge-outstanding-refresh">Refresh</button>
      </div>
      <p class="sysforge-parts-error" id="sysforge-outstanding-error" hidden></p>
      <ul class="sysforge-outstanding-list" id="sysforge-outstanding-list"></ul>
      <p class="sysforge-parts-empty" id="sysforge-outstanding-empty" hidden>
        All caught up — no unpaid balances.
      </p>
    </div>`;

  container.dataset.mounted = '1';
  container._sysforgeOutstandingDeps = deps;

  const reload = async () => {
    const listEl = container.querySelector('#sysforge-outstanding-list');
    const emptyEl = container.querySelector('#sysforge-outstanding-empty');
    const errorEl = container.querySelector('#sysforge-outstanding-error');
    if (errorEl) {
      errorEl.hidden = true;
      errorEl.textContent = '';
    }
    try {
      const data = await deps.api('/invoices/outstanding');
      const rows = Array.isArray(data?.invoices) ? data.invoices : [];
      if (listEl) {
        listEl.innerHTML = rows
          .map(
            (r) => `<li>
              <button type="button" class="btn-secondary sysforge-outstanding-open"
                data-invoice-id="${escapeHtml(String(r.invoice_id))}">
                ${escapeHtml(r.name || `Invoice #${r.invoice_id}`)}
              </button>
              <span>${escapeHtml(r.status || '')} · ${formatMoney(r.balance_cents)}</span>
            </li>`
          )
          .join('');
      }
      if (emptyEl) emptyEl.hidden = rows.length > 0;
    } catch (err) {
      if (errorEl) {
        errorEl.textContent = err?.message || String(err);
        errorEl.hidden = false;
      }
      if (listEl) listEl.innerHTML = '';
      if (emptyEl) emptyEl.hidden = true;
    }
  };
  container._sysforgeReloadOutstanding = reload;

  container.querySelector('#sysforge-outstanding-refresh')?.addEventListener('click', () => {
    void reload();
  });

  container.addEventListener('click', (e) => {
    const btn = e.target?.closest?.('.sysforge-outstanding-open');
    if (!btn || !container.contains(btn)) return;
    const id = btn.getAttribute('data-invoice-id');
    if (!id) return;
    if (typeof deps.navigateToInvoiceViewer === 'function') {
      deps.navigateToInvoiceViewer(id);
      return;
    }
    deps.navigate?.('invoice-view', { params: { id } });
  });
}

/**
 * @param {HTMLElement} container
 */
export async function activateOutstandingInvoices(container) {
  container.querySelector('.sysforge-view-heading')?.focus?.({ preventScroll: true });
  if (typeof container._sysforgeReloadOutstanding === 'function') {
    await container._sysforgeReloadOutstanding();
  }
}
