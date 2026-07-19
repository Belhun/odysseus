/**
 * Supplier detail — contacts, notes, linked parts.
 */

async function _toast(message, isError) {
  try {
    const ui = await import('/static/js/ui.js');
    if (typeof ui.showToast === 'function') {
      ui.showToast(message, isError ? 'error' : 'success');
      return;
    }
  } catch (_) {
    /* fall through */
  }
  console[isError ? 'error' : 'log'](message);
}

function _formatCents(cents) {
  const n = Number(cents || 0) / 100;
  return n.toLocaleString(undefined, { style: 'currency', currency: 'USD' });
}

function _esc(text) {
  return String(text || '').replace(/</g, '&lt;');
}

/**
 * @param {HTMLElement} container
 * @param {{ api: (path: string, opts?: object) => Promise<object>, navigate?: Function }} deps
 */
export function mountSupplierDetail(container, deps) {
  if (container.dataset.mounted === '1') return;

  container.innerHTML = `
    <div class="sysforge-supplier-detail">
      <h3 class="sysforge-view-heading" tabindex="-1">Supplier</h3>
      <p class="sysforge-dashboard-lead" id="sysforge-supplier-lead">Loading…</p>
      <p class="sysforge-parts-error" id="sysforge-supplier-error" hidden></p>
      <dl class="sysforge-supplier-meta" id="sysforge-supplier-meta"></dl>
      <h4>Linked parts</h4>
      <ul class="sysforge-hub-list" id="sysforge-supplier-parts"></ul>
      <div class="sysforge-settings-actions">
        <button type="button" class="btn-secondary" id="sysforge-supplier-back-parts">Back to parts</button>
      </div>
    </div>`;

  container.querySelector('#sysforge-supplier-back-parts')?.addEventListener('click', () => {
    if (typeof deps.navigate === 'function') deps.navigate('parts');
  });

  container.dataset.mounted = '1';
  container._sysforgeReloadSupplier = (params) => loadSupplier(container, deps, params);
}

async function loadSupplier(container, deps, params) {
  const id = Number(params?.id || 0);
  const errorEl = container.querySelector('#sysforge-supplier-error');
  const lead = container.querySelector('#sysforge-supplier-lead');
  const meta = container.querySelector('#sysforge-supplier-meta');
  const partsEl = container.querySelector('#sysforge-supplier-parts');
  if (errorEl) {
    errorEl.hidden = true;
    errorEl.textContent = '';
  }
  if (!id) {
    if (lead) lead.textContent = 'No supplier selected.';
    return;
  }
  try {
    const [supplier, partsData] = await Promise.all([
      deps.api(`/suppliers/${id}`),
      deps.api(`/suppliers/${id}/parts`),
    ]);
    if (lead) {
      lead.textContent = supplier.is_preferred
        ? `${supplier.name} (preferred)`
        : supplier.name;
    }
    if (meta) {
      meta.innerHTML = `
        <div><dt>Phone</dt><dd>${_esc(supplier.primary_phone) || '—'}</dd></div>
        <div><dt>Email</dt><dd>${_esc(supplier.primary_email) || '—'}</dd></div>
        <div><dt>Website</dt><dd>${_esc(supplier.website) || '—'}</dd></div>
        <div><dt>Shipping</dt><dd>${_formatCents(supplier.default_shipping_rate_cents)}</dd></div>
        <div><dt>Notes</dt><dd>${_esc(supplier.notes) || '—'}</dd></div>
      `;
    }
    const parts = partsData.items || [];
    if (partsEl) {
      partsEl.innerHTML = parts.length
        ? parts
            .map((p) => {
              const badge = p.is_placeholder
                ? ' <span class="sysforge-badge">placeholder</span>'
                : '';
              return `<li>${_esc(p.name)}${badge} · ${_formatCents(p.base_price_cents)}</li>`;
            })
            .join('')
        : '<li class="sysforge-classic-empty">No linked parts.</li>';
    }
  } catch (err) {
    const msg = err?.message || String(err);
    if (errorEl) {
      errorEl.textContent = msg;
      errorEl.hidden = false;
    }
    if (lead) lead.textContent = 'Could not load supplier.';
    await _toast(msg, true);
  }
}

/**
 * @param {HTMLElement} container
 * @param {object} deps
 * @param {Record<string, string>} params
 */
export async function activateSupplierDetail(container, deps, params) {
  const heading = container.querySelector('.sysforge-view-heading');
  heading?.focus?.({ preventScroll: true });
  if (typeof container._sysforgeReloadSupplier === 'function') {
    await container._sysforgeReloadSupplier(params || {});
  }
}

export function deactivateSupplierDetail(_container) {
  /* no-op */
}
