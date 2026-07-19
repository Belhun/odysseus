/**
 * Invoice payments panel helpers (integer cents; soft-void).
 */

export const PAYMENT_METHODS = Object.freeze([
  'Cash',
  'Card',
  'Check',
  'Transfer',
  'Other',
]);

/**
 * @param {number|string|null|undefined} cents
 * @returns {string}
 */
export function formatMoney(cents) {
  const n = Number(cents || 0) / 100;
  return n.toLocaleString(undefined, { style: 'currency', currency: 'USD' });
}

/**
 * Parse a dollars string ("12.50") to integer cents. Returns null if invalid.
 * @param {string} dollars
 * @returns {number|null}
 */
export function dollarsToCents(dollars) {
  const raw = String(dollars ?? '').trim();
  if (!raw) return null;
  const n = Number(raw);
  if (!Number.isFinite(n) || n <= 0) return null;
  return Math.round(n * 100);
}

/**
 * @param {object} summary
 * @returns {string}
 */
export function balanceLabel(summary) {
  const balance = Number(summary?.balance_cents ?? 0);
  const total = Number(summary?.final_total_cents ?? 0);
  if (balance < 0) {
    return `Credit ${formatMoney(-balance)} (overpaid)`;
  }
  if (balance === 0 && total > 0) {
    return 'Paid in full';
  }
  return `Balance due ${formatMoney(balance)}`;
}

/**
 * Escape for HTML text/attrs.
 * @param {unknown} s
 */
function escapeHtml(s) {
  return String(s ?? '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

/**
 * @param {object} summary — list_payments payload
 * @returns {string} HTML
 */
export function renderPaymentsPanelHtml(summary) {
  const payments = Array.isArray(summary?.payments) ? summary.payments : [];
  const balance = Number(summary?.balance_cents ?? 0);
  const overpayNote =
    balance < 0
      ? `<p class="sysforge-payments-warn">Balance will be a credit (${formatMoney(
          -balance
        )}).</p>`
      : '';

  const rows = payments.length
    ? payments
        .map((p) => {
          const voided = Boolean(p.is_voided);
          const voidNote = voided
            ? ` <span class="sysforge-payment-void-reason">(${escapeHtml(
                p.void_reason || 'voided'
              )})</span>`
            : '';
          const voidBtn = voided
            ? ''
            : `<button type="button" class="btn-secondary sysforge-payment-void" data-payment-id="${escapeHtml(
                String(p.id)
              )}">Void</button>`;
          return `<tr class="${voided ? 'sysforge-payment-voided' : ''}">
            <td>${escapeHtml(p.received_at || '')}</td>
            <td>${escapeHtml(p.method)}</td>
            <td class="sysforge-num">${formatMoney(p.amount_cents)}${voidNote}</td>
            <td>${escapeHtml(p.reference || '')}</td>
            <td>${voidBtn}</td>
          </tr>`;
        })
        .join('')
    : `<tr><td colspan="5">No payments recorded.</td></tr>`;

  const methodOpts = PAYMENT_METHODS.map(
    (m) => `<option value="${m}">${m}</option>`
  ).join('');

  return `
    <section class="sysforge-payments" aria-label="Payments">
      <h4 class="sysforge-payments-heading">Payments</h4>
      <p class="sysforge-payments-balance" id="sysforge-payments-balance">${escapeHtml(
        balanceLabel(summary)
      )} · Status ${escapeHtml(summary?.status || 'Estimate')}</p>
      ${overpayNote}
      <table class="sysforge-viewer-table sysforge-payments-table" aria-label="Payment history">
        <thead>
          <tr><th>Received</th><th>Method</th><th>Amount</th><th>Ref</th><th></th></tr>
        </thead>
        <tbody id="sysforge-payments-tbody">${rows}</tbody>
      </table>
      <form class="sysforge-payments-form" id="sysforge-payments-form">
        <label>Amount ($)
          <input type="number" id="sysforge-pay-amount" min="0.01" step="0.01" required />
        </label>
        <label>Method
          <select id="sysforge-pay-method">${methodOpts}</select>
        </label>
        <label>Reference
          <input type="text" id="sysforge-pay-ref" />
        </label>
        <label>Notes
          <input type="text" id="sysforge-pay-notes" />
        </label>
        <button type="submit" class="btn-primary" id="sysforge-pay-submit">Record payment</button>
      </form>
      <p class="sysforge-clients-error" id="sysforge-payments-error" hidden></p>
    </section>`;
}
