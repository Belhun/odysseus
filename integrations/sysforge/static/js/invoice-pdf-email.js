/**
 * Invoice viewer PDF download + email dialog helpers.
 */

/**
 * Download invoice PDF via same-origin fetch (blob).
 * @param {number|string} invoiceId
 * @param {{ apiBase?: string }} [opts]
 */
export async function downloadInvoicePdf(invoiceId, opts = {}) {
  const base = opts.apiBase || `${window.location.origin}/api/sysforge`;
  const res = await fetch(
    `${base}/invoices/${encodeURIComponent(invoiceId)}/pdf`,
    { credentials: 'same-origin' }
  );
  if (!res.ok) {
    let detail = `Download failed (${res.status})`;
    try {
      const data = await res.json();
      if (data?.detail) detail = typeof data.detail === 'string' ? data.detail : detail;
    } catch (_) {
      /* ignore */
    }
    throw new Error(detail);
  }
  const blob = await res.blob();
  const cd = res.headers.get('Content-Disposition') || '';
  const match = /filename="([^"]+)"/i.exec(cd);
  const filename = match?.[1] || `invoice-${invoiceId}.pdf`;
  const url = URL.createObjectURL(blob);
  try {
    const a = document.createElement('a');
    a.href = url;
    a.download = filename;
    a.rel = 'noopener';
    document.body.appendChild(a);
    a.click();
    a.remove();
  } finally {
    URL.revokeObjectURL(url);
  }
}

/**
 * @param {object} invoice
 * @returns {{ to: string, subject: string, body: string }}
 */
export function buildEmailDefaults(invoice) {
  const label =
    invoice?.display_label || invoice?.name || `Invoice #${invoice?.id || ''}`;
  const clientEmail = invoice?.client?.email || '';
  const totalCents = Number(invoice?.final_total_cents || 0);
  const total = (totalCents / 100).toLocaleString(undefined, {
    style: 'currency',
    currency: 'USD',
  });
  return {
    to: clientEmail,
    subject: `Invoice: ${label}`,
    body: `Please find attached invoice ${label}.\n\nTotal: ${total}\n`,
  };
}
