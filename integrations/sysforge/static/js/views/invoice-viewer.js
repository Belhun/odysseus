/**
 * Read-only invoice viewer.
 * View → #sysforge/invoice-view/:id
 * Edit CTA → invoice-calculator?invoiceId= (never invoice-edit; preserves return context).
 * Finalized: price-compare flags vs catalog BasePriceCents.
 * PDF download + email via host mail (invoice-ops slices A/B).
 * Payments panel: record / list / void / balance (slice C).
 */

import { buildInvoiceEditRoute } from '../routes-contract.js';
import { flagPriceMismatches } from '../invoice-price-compare.js';
import { buildEmailDefaults, downloadInvoicePdf } from '../invoice-pdf-email.js';
import {
  dollarsToCents,
  renderPaymentsPanelHtml,
} from '../invoice-payments.js';

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
 *   navigate: (routeKey: string, opts?: object) => void,
 *   navigateToInvoiceEdit?: (invoiceId: string|number) => void,
 * }} deps
 */
export function mountInvoiceViewer(container, deps) {
  if (container.dataset.mounted === '1') return;

  container.innerHTML = `
    <div class="sysforge-invoice-viewer">
      <div class="sysforge-viewer-toolbar">
        <div>
          <h3 class="sysforge-view-heading" tabindex="-1">Invoice</h3>
          <p class="sysforge-viewer-subtitle">Read-only view</p>
        </div>
        <div class="sysforge-viewer-toolbar-actions">
          <button type="button" class="btn-secondary" id="sysforge-viewer-pdf" disabled>Download PDF</button>
          <button type="button" class="btn-secondary" id="sysforge-viewer-email" disabled>Email…</button>
          <button type="button" class="btn-primary" id="sysforge-viewer-edit" disabled>Edit</button>
        </div>
      </div>
      <p class="sysforge-viewer-meta" id="sysforge-viewer-meta"></p>
      <p class="sysforge-clients-error" id="sysforge-viewer-error" hidden></p>
      <p class="sysforge-viewer-toast" id="sysforge-viewer-toast" hidden></p>
      <div id="sysforge-viewer-email-dialog" class="sysforge-email-dialog" hidden>
        <h4>Email invoice</h4>
        <label>To
          <input type="email" id="sysforge-email-to" autocomplete="email" />
        </label>
        <label>Subject
          <input type="text" id="sysforge-email-subject" />
        </label>
        <label>Message
          <textarea id="sysforge-email-body" rows="4"></textarea>
        </label>
        <p class="sysforge-clients-error" id="sysforge-email-error" hidden></p>
        <div class="sysforge-email-dialog-actions">
          <button type="button" class="btn-secondary" id="sysforge-email-cancel">Cancel</button>
          <button type="button" class="btn-primary" id="sysforge-email-send">Send</button>
        </div>
      </div>
      <div id="sysforge-viewer-body" class="sysforge-viewer-body">
        <p class="sysforge-placeholder-note">Select an invoice to view.</p>
      </div>
    </div>`;

  const abortRef = { controller: null };
  container.dataset.mounted = '1';
  container._sysforgeViewerAbort = abortRef;
  container._sysforgeViewerDeps = deps;
  container._sysforgeViewerInvoiceId = null;
  container._sysforgeViewerInvoice = null;

  const toast = (msg) => {
    const el = container.querySelector('#sysforge-viewer-toast');
    if (!el) return;
    el.textContent = msg;
    el.hidden = !msg;
  };

  container.querySelector('#sysforge-viewer-edit')?.addEventListener('click', () => {
    const id = container._sysforgeViewerInvoiceId;
    if (!id) return;
    if (typeof deps.navigateToInvoiceEdit === 'function') {
      deps.navigateToInvoiceEdit(id);
      return;
    }
    const target = buildInvoiceEditRoute(id);
    deps.navigate(target.routeKey, { params: target.params });
  });

  container.querySelector('#sysforge-viewer-pdf')?.addEventListener('click', async () => {
    const id = container._sysforgeViewerInvoiceId;
    if (!id) return;
    const btn = container.querySelector('#sysforge-viewer-pdf');
    if (btn) btn.disabled = true;
    toast('');
    try {
      await downloadInvoicePdf(id);
      toast('PDF downloaded.');
    } catch (err) {
      toast(err?.message || String(err));
    } finally {
      if (btn && container._sysforgeViewerInvoiceId) btn.disabled = false;
    }
  });

  const dialog = container.querySelector('#sysforge-viewer-email-dialog');
  const emailErr = container.querySelector('#sysforge-email-error');

  const closeEmail = () => {
    if (dialog) dialog.hidden = true;
    if (emailErr) {
      emailErr.hidden = true;
      emailErr.textContent = '';
    }
  };

  container.querySelector('#sysforge-viewer-email')?.addEventListener('click', () => {
    const inv = container._sysforgeViewerInvoice;
    if (!inv || !dialog) return;
    const defaults = buildEmailDefaults(inv);
    const toEl = container.querySelector('#sysforge-email-to');
    const subEl = container.querySelector('#sysforge-email-subject');
    const bodyEl = container.querySelector('#sysforge-email-body');
    if (toEl) toEl.value = defaults.to;
    if (subEl) subEl.value = defaults.subject;
    if (bodyEl) bodyEl.value = defaults.body;
    if (emailErr) {
      emailErr.hidden = true;
      emailErr.textContent = '';
    }
    dialog.hidden = false;
    toEl?.focus();
  });

  container.querySelector('#sysforge-email-cancel')?.addEventListener('click', closeEmail);

  const showPayError = (msg) => {
    const el = container.querySelector('#sysforge-payments-error');
    if (!el) return;
    el.textContent = msg || '';
    el.hidden = !msg;
  };

  const refreshPayments = async () => {
    const id = container._sysforgeViewerInvoiceId;
    const host = container.querySelector('#sysforge-viewer-payments');
    if (!id || !host) return;
    try {
      const summary = await deps.api(`/invoices/${encodeURIComponent(id)}/payments`);
      host.innerHTML = renderPaymentsPanelHtml(summary);
      container._sysforgePaymentsSummary = summary;
      if (container._sysforgeViewerInvoice && summary?.status) {
        container._sysforgeViewerInvoice.status = summary.status;
        const metaEl = container.querySelector('#sysforge-viewer-meta');
        const inv = container._sysforgeViewerInvoice;
        if (metaEl && inv) {
          const clientName = inv.client?.display_name || inv.client_info || 'No client';
          metaEl.textContent = `#${inv.id} · ${inv.status || 'Estimate'} · ${clientName} · ${formatMoney(
            inv.final_total_cents
          )}`;
        }
      }
    } catch (err) {
      host.innerHTML = `<p class="sysforge-clients-error">${escapeHtml(
        err?.message || String(err)
      )}</p>`;
    }
  };
  container._sysforgeRefreshPayments = refreshPayments;

  container.addEventListener('submit', async (e) => {
    const form = e.target?.closest?.('#sysforge-payments-form');
    if (!form || !container.contains(form)) return;
    e.preventDefault();
    const id = container._sysforgeViewerInvoiceId;
    if (!id) return;
    const amountCents = dollarsToCents(
      container.querySelector('#sysforge-pay-amount')?.value
    );
    if (amountCents == null) {
      showPayError('Enter a payment amount greater than zero.');
      return;
    }
    const method = container.querySelector('#sysforge-pay-method')?.value || 'Cash';
    const reference = container.querySelector('#sysforge-pay-ref')?.value?.trim() || null;
    const notes = container.querySelector('#sysforge-pay-notes')?.value?.trim() || null;
    const submitBtn = container.querySelector('#sysforge-pay-submit');
    if (submitBtn) submitBtn.disabled = true;
    showPayError('');
    try {
      const result = await deps.api(`/invoices/${encodeURIComponent(id)}/payments`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          amount_cents: amountCents,
          method,
          reference,
          notes,
        }),
      });
      if (result?.overpay_warning) {
        toast('Payment recorded. Balance is a credit (overpaid).');
      } else {
        toast('Payment recorded.');
      }
      await refreshPayments();
    } catch (err) {
      showPayError(err?.message || String(err));
    } finally {
      if (submitBtn) submitBtn.disabled = false;
    }
  });

  container.addEventListener('click', async (e) => {
    const voidBtn = e.target?.closest?.('.sysforge-payment-void');
    if (!voidBtn || !container.contains(voidBtn)) return;
    const paymentId = voidBtn.getAttribute('data-payment-id');
    if (!paymentId) return;
    const reason = window.prompt('Void reason (required):');
    if (reason == null) return;
    if (!String(reason).trim()) {
      showPayError('Void reason is required.');
      return;
    }
    showPayError('');
    voidBtn.disabled = true;
    try {
      await deps.api(`/payments/${encodeURIComponent(paymentId)}/void`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ reason: String(reason).trim() }),
      });
      toast('Payment voided.');
      await refreshPayments();
    } catch (err) {
      showPayError(err?.message || String(err));
      voidBtn.disabled = false;
    }
  });

  container.querySelector('#sysforge-email-send')?.addEventListener('click', async () => {
    const id = container._sysforgeViewerInvoiceId;
    if (!id) return;
    const to = container.querySelector('#sysforge-email-to')?.value?.trim() || '';
    const subject = container.querySelector('#sysforge-email-subject')?.value || '';
    const body = container.querySelector('#sysforge-email-body')?.value || '';
    if (!to) {
      if (emailErr) {
        emailErr.textContent = 'Enter a recipient email address.';
        emailErr.hidden = false;
      }
      return;
    }
    const sendBtn = container.querySelector('#sysforge-email-send');
    if (sendBtn) sendBtn.disabled = true;
    try {
      const result = await deps.api(`/invoices/${encodeURIComponent(id)}/email`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ to, subject, body }),
      });
      closeEmail();
      toast(`Email sent${result?.sent_at ? ` at ${result.sent_at}` : ''}.`);
      if (container._sysforgeViewerInvoice) {
        container._sysforgeViewerInvoice.sent_at = result?.sent_at || null;
        if (result?.status) container._sysforgeViewerInvoice.status = result.status;
      }
      const metaEl = container.querySelector('#sysforge-viewer-meta');
      const inv = container._sysforgeViewerInvoice;
      if (metaEl && inv) {
        const clientName = inv.client?.display_name || inv.client_info || 'No client';
        metaEl.textContent = `#${inv.id} · ${inv.status || 'Estimate'} · ${clientName} · ${formatMoney(
          inv.final_total_cents
        )}`;
      }
    } catch (err) {
      if (emailErr) {
        emailErr.textContent = err?.message || String(err);
        emailErr.hidden = false;
      }
    } finally {
      if (sendBtn) sendBtn.disabled = false;
    }
  });
}

/**
 * @param {HTMLElement} container
 * @param {Record<string, string>} [params]
 * @param {{ reason?: string }} [meta]
 */
export async function activateInvoiceViewer(container, params = {}, meta = {}) {
  const heading = container.querySelector('.sysforge-view-heading');
  heading?.focus?.({ preventScroll: true });

  const deps = container._sysforgeViewerDeps;
  const invoiceId = params.id || params.invoiceId;
  if (!deps || !invoiceId) return;

  const abortRef = container._sysforgeViewerAbort;
  if (abortRef?.controller) {
    try {
      abortRef.controller.abort();
    } catch (_) {
      /* ignore */
    }
  }
  const ac = typeof AbortController !== 'undefined' ? new AbortController() : null;
  if (abortRef) abortRef.controller = ac;

  const errorEl = container.querySelector('#sysforge-viewer-error');
  const bodyEl = container.querySelector('#sysforge-viewer-body');
  const metaEl = container.querySelector('#sysforge-viewer-meta');
  const editBtn = container.querySelector('#sysforge-viewer-edit');
  const pdfBtn = container.querySelector('#sysforge-viewer-pdf');
  const emailBtn = container.querySelector('#sysforge-viewer-email');
  const toastEl = container.querySelector('#sysforge-viewer-toast');
  const dialog = container.querySelector('#sysforge-viewer-email-dialog');

  if (editBtn) editBtn.disabled = true;
  if (pdfBtn) pdfBtn.disabled = true;
  if (emailBtn) emailBtn.disabled = true;
  if (toastEl) {
    toastEl.hidden = true;
    toastEl.textContent = '';
  }
  if (dialog) dialog.hidden = true;
  if (errorEl) {
    errorEl.hidden = true;
    errorEl.textContent = '';
  }
  if (bodyEl) {
    bodyEl.innerHTML = `<p class="sysforge-placeholder-note">Loading invoice #${escapeHtml(invoiceId)}…</p>`;
  }

  try {
    const invoice = await deps.api(`/invoices/${encodeURIComponent(invoiceId)}`, {
      signal: ac?.signal,
    });
    if (ac?.signal?.aborted) return;

    container._sysforgeViewerInvoiceId = invoice.id;
    container._sysforgeViewerInvoice = invoice;
    if (editBtn) editBtn.disabled = false;
    if (pdfBtn) pdfBtn.disabled = false;
    if (emailBtn) emailBtn.disabled = false;

    const clientName =
      invoice.client?.display_name || invoice.client_info || 'No client';
    if (metaEl) {
      metaEl.textContent = `#${invoice.id} · ${invoice.status || 'Estimate'} · ${clientName} · ${formatMoney(
        invoice.final_total_cents
      )}`;
    }
    if (heading) {
      heading.textContent = invoice.display_label || invoice.name || `Invoice #${invoice.id}`;
    }

    let items = invoice.items || [];
    if (invoice.is_finalized) {
      try {
        const cmp = await deps.api(
          `/invoices/${encodeURIComponent(invoiceId)}/price-compare`,
          { signal: ac?.signal }
        );
        if (ac?.signal?.aborted) return;
        const rows = Array.isArray(cmp) ? cmp : cmp?.items || [];
        if (rows.length) {
          const byItem = new Map(rows.map((r) => [Number(r.item_id), r]));
          items = items.map((it) => {
            const row = byItem.get(Number(it.id));
            if (!row) {
              return { ...it, has_price_mismatch: false, catalog_price_cents: null };
            }
            return {
              ...it,
              has_price_mismatch: Boolean(row.has_mismatch),
              catalog_price_cents: row.has_mismatch ? row.catalog_price_cents : null,
            };
          });
        } else {
          items = flagPriceMismatches(items, new Map());
        }
      } catch (_) {
        /* compare is best-effort; viewer still shows lines */
      }
    }

    const rows = items.length
      ? items
          .map((it) => {
            const mismatch = Boolean(it.has_price_mismatch);
            const catalogNote =
              mismatch && it.catalog_price_cents != null
                ? `<span class="sysforge-price-mismatch-note">Catalog ${formatMoney(
                    it.catalog_price_cents
                  )}</span>`
                : '';
            return `
          <tr class="${mismatch ? 'sysforge-price-mismatch' : ''}">
            <td>${escapeHtml(it.part_name)}${
              mismatch
                ? ' <span class="sysforge-price-mismatch-badge" title="Unit price differs from catalog">Price changed</span>'
                : ''
            }</td>
            <td>${escapeHtml(it.item_type)}</td>
            <td class="sysforge-num">${escapeHtml(String(it.quantity ?? ''))}</td>
            <td class="sysforge-num">${formatMoney(it.unit_price_cents)}${catalogNote}</td>
            <td class="sysforge-num">${formatMoney(it.line_total_cents)}</td>
          </tr>`;
          })
          .join('')
      : `<tr><td colspan="5">No line items</td></tr>`;

    if (bodyEl) {
      bodyEl.innerHTML = `
        <table class="sysforge-viewer-table" aria-label="Invoice line items (read-only)">
          <thead>
            <tr><th>Item</th><th>Type</th><th>Qty</th><th>Unit</th><th>Line</th></tr>
          </thead>
          <tbody>${rows}</tbody>
        </table>
        <dl class="sysforge-viewer-totals">
          <div><dt>Parts</dt><dd>${formatMoney(invoice.parts_subtotal_cents)}</dd></div>
          <div><dt>Labor</dt><dd>${formatMoney(invoice.labor_cost_cents)}</dd></div>
          <div><dt>Tax</dt><dd>${formatMoney(invoice.tax_amount_cents)}</dd></div>
          <div><dt>Shipping</dt><dd>${formatMoney(invoice.shipping_cost_cents)}</dd></div>
          <div class="sysforge-viewer-total"><dt>Total</dt><dd>${formatMoney(
            invoice.final_total_cents
          )}</dd></div>
        </dl>
        <div id="sysforge-viewer-payments" class="sysforge-viewer-payments">
          <p class="sysforge-placeholder-note">Loading payments…</p>
        </div>`;
    }
    if (typeof container._sysforgeRefreshPayments === 'function') {
      await container._sysforgeRefreshPayments();
    }
  } catch (err) {
    if (err?.name === 'AbortError') return;
    if (errorEl) {
      errorEl.textContent = err?.message || String(err);
      errorEl.hidden = false;
    }
    if (bodyEl) bodyEl.innerHTML = '';
    if (editBtn) editBtn.disabled = true;
    if (pdfBtn) pdfBtn.disabled = true;
    if (emailBtn) emailBtn.disabled = true;
    container._sysforgeViewerInvoiceId = null;
    container._sysforgeViewerInvoice = null;
  }

  void meta;
}

/**
 * @param {HTMLElement} container
 */
export function deactivateInvoiceViewer(container) {
  const abortRef = container._sysforgeViewerAbort;
  if (abortRef?.controller) {
    try {
      abortRef.controller.abort();
    } catch (_) {
      /* ignore */
    }
    abortRef.controller = null;
  }
}

export { flagPriceMismatches, compareLineToCatalog } from '../invoice-price-compare.js';
export { buildEmailDefaults, downloadInvoicePdf } from '../invoice-pdf-email.js';
