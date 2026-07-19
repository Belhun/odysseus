/**
 * Placeholder triage queue — convert placeholders to full catalog parts.
 * Route: #sysforge/parts/triage (ROUTE.PARTS_TRIAGE).
 */

let _busy = false;

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

function escapeHtml(s) {
  return String(s ?? '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

/**
 * @param {HTMLElement} container
 * @param {{
 *   api: (path: string, opts?: object) => Promise<object>,
 *   navigate?: (routeId: string, opts?: object) => void,
 * }} deps
 */
export function mountPartsTriage(container, deps) {
  if (container.dataset.mounted === '1') return;

  container.innerHTML = `
    <div class="sysforge-triage">
      <h3 class="sysforge-view-heading" tabindex="-1">Placeholder triage</h3>
      <p class="sysforge-dashboard-lead">
        Convert placeholders into full catalog parts. Line prices on invoices stay unchanged.
      </p>
      <div class="sysforge-parts-toolbar">
        <button type="button" class="btn-secondary" id="sysforge-triage-refresh">Refresh</button>
        <button type="button" class="btn-secondary" id="sysforge-triage-merge">Open merge</button>
      </div>
      <p class="sysforge-parts-error" id="sysforge-triage-error" hidden></p>
      <div class="sysforge-parts-layout">
        <div class="sysforge-parts-list-wrap">
          <table class="sysforge-parts-table" id="sysforge-triage-table">
            <thead>
              <tr>
                <th>Name</th>
                <th>Price</th>
                <th>Used</th>
                <th>Supplier</th>
                <th></th>
              </tr>
            </thead>
            <tbody id="sysforge-triage-tbody"></tbody>
          </table>
          <p class="sysforge-parts-empty" id="sysforge-triage-empty" hidden>No open placeholders.</p>
        </div>
        <form id="sysforge-triage-form" class="sysforge-parts-form" hidden>
          <h4>Convert to catalog part</h4>
          <input type="hidden" id="sysforge-triage-id" />
          <label class="sysforge-field">
            <span>Name</span>
            <input type="text" id="sysforge-triage-name" required />
          </label>
          <label class="sysforge-field">
            <span>SKU</span>
            <input type="text" id="sysforge-triage-sku" />
          </label>
          <label class="sysforge-field">
            <span>Base price (USD)</span>
            <input type="number" id="sysforge-triage-price" min="0" step="0.01" value="0" />
          </label>
          <label class="sysforge-field">
            <span>Description</span>
            <textarea id="sysforge-triage-desc" rows="2"></textarea>
          </label>
          <label class="sysforge-field">
            <span>Tags</span>
            <input type="text" id="sysforge-triage-tags" />
          </label>
          <label class="sysforge-field">
            <span>Supplier id (optional)</span>
            <input type="number" id="sysforge-triage-supplier" min="1" step="1" />
          </label>
          <label class="sysforge-field">
            <span>Preferred supplier id (optional)</span>
            <input type="number" id="sysforge-triage-preferred" min="1" step="1" />
          </label>
          <p class="sysforge-parts-error" id="sysforge-triage-sku-conflict" hidden></p>
          <div class="sysforge-parts-form-actions">
            <button type="submit" class="btn-primary">Convert</button>
            <button type="button" class="btn-secondary" id="sysforge-triage-cancel">Cancel</button>
          </div>
        </form>
      </div>
    </div>`;

  const tbody = container.querySelector('#sysforge-triage-tbody');
  const emptyEl = container.querySelector('#sysforge-triage-empty');
  const errorEl = container.querySelector('#sysforge-triage-error');
  const form = container.querySelector('#sysforge-triage-form');
  const conflictEl = container.querySelector('#sysforge-triage-sku-conflict');

  function setBusy(busy) {
    _busy = busy;
    container.querySelectorAll('button, input, textarea').forEach((el) => {
      if (el.id === 'sysforge-triage-cancel') return;
      el.disabled = busy;
    });
  }

  function showError(msg) {
    if (!errorEl) return;
    if (!msg) {
      errorEl.hidden = true;
      errorEl.textContent = '';
      return;
    }
    errorEl.textContent = msg;
    errorEl.hidden = false;
  }

  function showConflict(payload) {
    if (!conflictEl) return;
    if (!payload) {
      conflictEl.hidden = true;
      conflictEl.textContent = '';
      return;
    }
    const other = payload.conflicting_part || {};
    conflictEl.innerHTML = `
      SKU conflict with «${escapeHtml(other.name || 'existing part')}»
      (id ${escapeHtml(other.id)}). Change the SKU, or use merge for duplicates.
      <button type="button" class="btn-secondary" id="sysforge-triage-use-merge">Open merge</button>
    `;
    conflictEl.hidden = false;
    conflictEl.querySelector('#sysforge-triage-use-merge')?.addEventListener('click', () => {
      deps.navigate?.('placeholder-merge');
    });
  }

  function hideForm() {
    if (form) form.hidden = true;
    showConflict(null);
  }

  function openConvert(part) {
    if (!form) return;
    form.hidden = false;
    container.querySelector('#sysforge-triage-id').value = String(part.id);
    container.querySelector('#sysforge-triage-name').value = part.name || '';
    container.querySelector('#sysforge-triage-sku').value = part.sku || '';
    container.querySelector('#sysforge-triage-price').value = String(
      (Number(part.base_price_cents) || 0) / 100
    );
    container.querySelector('#sysforge-triage-desc').value = part.description || '';
    container.querySelector('#sysforge-triage-tags').value = part.tags || '';
    container.querySelector('#sysforge-triage-supplier').value =
      part.supplier_id != null ? String(part.supplier_id) : '';
    container.querySelector('#sysforge-triage-preferred').value =
      part.preferred_supplier_id != null ? String(part.preferred_supplier_id) : '';
    showConflict(null);
    container.querySelector('#sysforge-triage-name')?.focus();
  }

  function renderRows(items) {
    if (!tbody) return;
    if (!items || items.length === 0) {
      tbody.innerHTML = '';
      if (emptyEl) emptyEl.hidden = false;
      return;
    }
    if (emptyEl) emptyEl.hidden = true;
    tbody.innerHTML = items
      .map((p) => {
        const supplier = p.supplier_name
          ? escapeHtml(p.supplier_name)
          : p.supplier_id != null
            ? `#${p.supplier_id}`
            : '—';
        return `<tr data-part-id="${p.id}">
          <td>${escapeHtml(p.name)}</td>
          <td>${_formatCents(p.base_price_cents)}</td>
          <td>${Number(p.usage_count) || 0}</td>
          <td>${supplier}</td>
          <td>
            <button type="button" class="btn-primary sysforge-triage-convert" data-part-id="${p.id}">
              Convert
            </button>
          </td>
        </tr>`;
      })
      .join('');
    tbody._items = items;
  }

  async function reload() {
    showError('');
    setBusy(true);
    try {
      const data = await deps.api('/parts/placeholders');
      renderRows(data.items || []);
    } catch (err) {
      showError(err?.message || String(err));
      await _toast(err?.message || String(err), true);
    } finally {
      setBusy(false);
    }
  }

  container.querySelector('#sysforge-triage-refresh')?.addEventListener('click', () => {
    if (!_busy) void reload();
  });
  container.querySelector('#sysforge-triage-merge')?.addEventListener('click', () => {
    deps.navigate?.('placeholder-merge');
  });
  container.querySelector('#sysforge-triage-cancel')?.addEventListener('click', () => {
    hideForm();
  });

  tbody?.addEventListener('click', (e) => {
    if (_busy) return;
    const btn = e.target.closest('.sysforge-triage-convert');
    if (!btn) return;
    const id = Number(btn.getAttribute('data-part-id'));
    const items = tbody._items || [];
    const part = items.find((p) => Number(p.id) === id);
    if (part) openConvert(part);
  });

  form?.addEventListener('submit', async (e) => {
    e.preventDefault();
    if (_busy) return;
    const partId = Number(container.querySelector('#sysforge-triage-id')?.value);
    if (!partId) return;
    const dollars = Number(container.querySelector('#sysforge-triage-price')?.value || 0);
    const supplierRaw = container.querySelector('#sysforge-triage-supplier')?.value;
    const preferredRaw = container.querySelector('#sysforge-triage-preferred')?.value;
    const body = {
      name: container.querySelector('#sysforge-triage-name')?.value?.trim() || '',
      sku: container.querySelector('#sysforge-triage-sku')?.value?.trim() || null,
      base_price_cents: Math.round(dollars * 100),
      description: container.querySelector('#sysforge-triage-desc')?.value || null,
      tags: container.querySelector('#sysforge-triage-tags')?.value || null,
      supplier_id: supplierRaw ? Number(supplierRaw) : null,
      preferred_supplier_id: preferredRaw ? Number(preferredRaw) : null,
      is_placeholder: false,
    };
    setBusy(true);
    showError('');
    showConflict(null);
    try {
      await deps.api(`/parts/placeholders/${partId}/convert`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      });
      await _toast('Converted to catalog part', false);
      hideForm();
      await reload();
    } catch (err) {
      const payload = err?.payload || err?.body || null;
      if (payload?.code === 'sku_conflict' || err?.status === 409) {
        showConflict(payload || err);
      } else {
        showError(err?.message || String(err));
        await _toast(err?.message || String(err), true);
      }
      setBusy(false);
    }
  });

  container._sysforgeTriageReload = reload;
  container.dataset.mounted = '1';
  void reload();
}

/**
 * @param {HTMLElement} container
 */
export async function activatePartsTriage(container) {
  const heading = container.querySelector('.sysforge-view-heading');
  heading?.focus?.({ preventScroll: true });
  if (typeof container._sysforgeTriageReload === 'function') {
    await container._sysforgeTriageReload();
  }
}

export default {
  mountPartsTriage,
  activatePartsTriage,
};
