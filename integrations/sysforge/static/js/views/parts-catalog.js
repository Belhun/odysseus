/**
 * Parts catalog — list, search, create/edit, delete, promote placeholders.
 */

let _abort = null;
let _searchTimer = null;

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

function _emptyForm() {
  return {
    id: null,
    name: '',
    sku: '',
    base_price_cents: 0,
    description: '',
    compatible_devices: '',
    tags: '',
    has_warranty: false,
    supplier_id: '',
    preferred_supplier_id: '',
    supplier_label: '',
    preferred_supplier_label: '',
    is_placeholder: false,
  };
}

/**
 * @param {HTMLElement} container
 * @param {{ api: (path: string, opts?: object) => Promise<object> }} deps
 */
export function mountPartsCatalog(container, deps) {
  if (container.dataset.mounted === '1') return;

  container.innerHTML = `
    <div class="sysforge-parts">
      <h3 class="sysforge-view-heading" tabindex="-1">Parts catalog</h3>
      <p class="sysforge-dashboard-lead">Full-text parts search. Placeholders show a badge.</p>
      <div class="sysforge-parts-toolbar">
        <input type="search" id="sysforge-parts-q" class="sysforge-parts-search"
          placeholder="Search parts…" autocomplete="off" />
        <button type="button" class="btn-primary" id="sysforge-parts-new">Add part</button>
        <button type="button" class="btn-secondary" id="sysforge-parts-triage">Triage queue</button>
        <button type="button" class="btn-secondary" id="sysforge-parts-refresh">Refresh</button>
        <button type="button" class="btn-secondary" id="sysforge-parts-rebuild">Rebuild search index</button>
      </div>
      <p class="sysforge-parts-error" id="sysforge-parts-error" hidden></p>
      <div class="sysforge-parts-layout">
        <div class="sysforge-parts-list-wrap">
          <table class="sysforge-parts-table" id="sysforge-parts-table">
            <thead>
              <tr>
                <th>Name</th>
                <th>SKU</th>
                <th>Price</th>
                <th>Stock</th>
                <th></th>
              </tr>
            </thead>
            <tbody id="sysforge-parts-tbody"></tbody>
          </table>
          <p class="sysforge-parts-empty" id="sysforge-parts-empty" hidden>No parts match.</p>
        </div>
        <form id="sysforge-parts-form" class="sysforge-parts-form" hidden>
          <h4 id="sysforge-parts-form-title">Edit part</h4>
          <label class="sysforge-field">
            <span>Name</span>
            <input type="text" id="sysforge-part-name" required />
          </label>
          <label class="sysforge-field">
            <span>SKU</span>
            <input type="text" id="sysforge-part-sku" />
          </label>
          <label class="sysforge-field">
            <span>Base price (USD)</span>
            <input type="number" id="sysforge-part-price" min="0" step="0.01" required />
          </label>
          <label class="sysforge-field">
            <span>Description</span>
            <textarea id="sysforge-part-desc" rows="2"></textarea>
          </label>
          <label class="sysforge-field">
            <span>Compatible devices</span>
            <input type="text" id="sysforge-part-devices" />
          </label>
          <label class="sysforge-field">
            <span>Tags</span>
            <input type="text" id="sysforge-part-tags" />
          </label>
          <label class="sysforge-field">
            <span>Supplier</span>
            <input type="search" id="sysforge-part-supplier-q" placeholder="Type to search suppliers…" autocomplete="off" />
            <input type="hidden" id="sysforge-part-supplier" />
            <button type="button" class="btn-secondary" id="sysforge-part-supplier-clear" hidden>Clear</button>
            <ul class="sysforge-parts-suggest" id="sysforge-part-supplier-suggest" hidden></ul>
          </label>
          <label class="sysforge-field">
            <span>Preferred supplier (buy-from)</span>
            <input type="search" id="sysforge-part-preferred-q" placeholder="Type to search…" autocomplete="off" />
            <input type="hidden" id="sysforge-part-preferred" />
            <button type="button" class="btn-secondary" id="sysforge-part-preferred-clear" hidden>Clear</button>
            <ul class="sysforge-parts-suggest" id="sysforge-part-preferred-suggest" hidden></ul>
          </label>
          <label class="sysforge-field">
            <span>On hand (stock)</span>
            <input type="number" id="sysforge-part-stock" min="0" step="1" value="0" />
          </label>
          <label class="sysforge-field sysforge-field-check">
            <input type="checkbox" id="sysforge-part-warranty" />
            <span>Has warranty</span>
          </label>
          <p class="sysforge-parts-badge-note" id="sysforge-part-ph-note" hidden>This row is a placeholder.</p>
          <div class="sysforge-settings-actions">
            <button type="submit" class="btn-primary" id="sysforge-part-save">Save</button>
            <button type="button" class="btn-secondary" id="sysforge-part-convert" hidden>Promote to catalog</button>
            <button type="button" class="btn-secondary" id="sysforge-part-cancel">Cancel</button>
            <button type="button" class="btn-secondary" id="sysforge-part-delete" hidden>Delete</button>
          </div>
        </form>
      </div>
    </div>`;

  const state = { form: _emptyForm(), items: [] };
  const errorEl = container.querySelector('#sysforge-parts-error');
  const tbody = container.querySelector('#sysforge-parts-tbody');
  const emptyEl = container.querySelector('#sysforge-parts-empty');
  const formEl = container.querySelector('#sysforge-parts-form');
  const qInput = container.querySelector('#sysforge-parts-q');

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

  function fillForm(data) {
    state.form = { ..._emptyForm(), ...data };
    const f = state.form;
    container.querySelector('#sysforge-part-name').value = f.name || '';
    container.querySelector('#sysforge-part-sku').value = f.sku || '';
    container.querySelector('#sysforge-part-price').value = (
      Number(f.base_price_cents || 0) / 100
    ).toFixed(2);
    container.querySelector('#sysforge-part-desc').value = f.description || '';
    container.querySelector('#sysforge-part-devices').value = f.compatible_devices || '';
    container.querySelector('#sysforge-part-tags').value = f.tags || '';
    _setSupplierField('supplier', f.supplier_id, f.supplier_label);
    _setSupplierField('preferred', f.preferred_supplier_id, f.preferred_supplier_label);
    container.querySelector('#sysforge-part-warranty').checked = Boolean(f.has_warranty);
    const stockEl = container.querySelector('#sysforge-part-stock');
    if (stockEl) {
      stockEl.value = String(
        f.quantity_on_hand != null ? f.quantity_on_hand : 0
      );
      stockEl.disabled = false;
    }
    const phNote = container.querySelector('#sysforge-part-ph-note');
    const convertBtn = container.querySelector('#sysforge-part-convert');
    const deleteBtn = container.querySelector('#sysforge-part-delete');
    const title = container.querySelector('#sysforge-parts-form-title');
    if (phNote) phNote.hidden = !f.is_placeholder;
    if (convertBtn) convertBtn.hidden = !f.is_placeholder || !f.id;
    if (deleteBtn) deleteBtn.hidden = !f.id;
    if (title) title.textContent = f.id ? 'Edit part' : 'Add part';
    if (formEl) formEl.hidden = false;
    if (f.supplier_id && !f.supplier_label) {
      _loadSupplierLabel(f.supplier_id, 'supplier');
    }
    if (f.preferred_supplier_id && !f.preferred_supplier_label) {
      _loadSupplierLabel(f.preferred_supplier_id, 'preferred');
    }
  }

  function _setSupplierField(kind, id, label) {
    const hidden = container.querySelector(
      kind === 'preferred' ? '#sysforge-part-preferred' : '#sysforge-part-supplier'
    );
    const q = container.querySelector(
      kind === 'preferred' ? '#sysforge-part-preferred-q' : '#sysforge-part-supplier-q'
    );
    const clearBtn = container.querySelector(
      kind === 'preferred'
        ? '#sysforge-part-preferred-clear'
        : '#sysforge-part-supplier-clear'
    );
    const sid = id != null && id !== '' ? Number(id) : null;
    if (hidden) hidden.value = sid != null ? String(sid) : '';
    if (q) q.value = label || (sid != null ? `Supplier #${sid}` : '');
    if (clearBtn) clearBtn.hidden = sid == null;
  }

  async function _loadSupplierLabel(id, kind) {
    try {
      const s = await deps.api(`/suppliers/${id}`);
      _setSupplierField(kind, s.id, s.name + (s.is_preferred ? ' ★' : ''));
    } catch (_) {
      /* keep id fallback label */
    }
  }

  function readForm() {
    const supplierRaw = container.querySelector('#sysforge-part-supplier').value;
    const preferredRaw = container.querySelector('#sysforge-part-preferred').value;
    const dollars = Number(container.querySelector('#sysforge-part-price').value || 0);
    return {
      name: container.querySelector('#sysforge-part-name').value,
      sku: container.querySelector('#sysforge-part-sku').value || null,
      base_price_cents: Math.round(dollars * 100),
      description: container.querySelector('#sysforge-part-desc').value || null,
      compatible_devices: container.querySelector('#sysforge-part-devices').value || null,
      tags: container.querySelector('#sysforge-part-tags').value || null,
      supplier_id: supplierRaw ? Number(supplierRaw) : null,
      preferred_supplier_id: preferredRaw ? Number(preferredRaw) : null,
      has_warranty: Boolean(container.querySelector('#sysforge-part-warranty').checked),
      is_placeholder: Boolean(state.form.is_placeholder),
    };
  }

  function renderList(items) {
    state.items = items || [];
    if (!tbody) return;
    tbody.innerHTML = state.items
      .map((p) => {
        const badge = p.is_placeholder
          ? '<span class="sysforge-badge">placeholder</span>'
          : '';
        const name = String(p.name || '').replace(/</g, '&lt;');
        const sku = String(p.sku || '—').replace(/</g, '&lt;');
        const onHand = p.quantity_on_hand != null ? p.quantity_on_hand : 0;
        const avail = p.available != null ? p.available : onHand;
        const stockLabel =
          p.stock_status === 'out'
            ? `<span class="sysforge-badge sysforge-stock-out">0</span>`
            : String(avail);
        return `<tr data-id="${p.id}">
          <td>${name} ${badge}</td>
          <td>${sku}</td>
          <td>${_formatCents(p.base_price_cents)}</td>
          <td>${stockLabel}</td>
          <td><button type="button" class="btn-secondary sysforge-parts-edit" data-id="${p.id}">Edit</button></td>
        </tr>`;
      })
      .join('');
    if (emptyEl) emptyEl.hidden = state.items.length > 0;
  }

  async function loadList(q) {
    showError('');
    if (_abort) _abort.abort();
    _abort = new AbortController();
    try {
      let data;
      if (q && q.trim()) {
        data = await deps.api(
          `/parts/search?q=${encodeURIComponent(q.trim())}&include_placeholders=true`,
          { signal: _abort.signal },
        );
      } else {
        data = await deps.api('/parts?placeholders=all', { signal: _abort.signal });
      }
      renderList(data.items || []);
    } catch (err) {
      if (err?.name === 'AbortError') return;
      showError(err?.message || String(err));
      await _toast(err?.message || String(err), true);
    }
  }

  tbody?.addEventListener('click', (e) => {
    const btn = e.target.closest('.sysforge-parts-edit');
    if (!btn) return;
    const id = Number(btn.getAttribute('data-id'));
    const part = state.items.find((p) => p.id === id);
    if (part) fillForm(part);
  });

  container.querySelector('#sysforge-parts-new')?.addEventListener('click', () => {
    fillForm(_emptyForm());
  });

  container.querySelector('#sysforge-parts-triage')?.addEventListener('click', () => {
    deps.navigate?.('parts-triage');
  });

  container.querySelector('#sysforge-parts-refresh')?.addEventListener('click', () => {
    loadList(qInput?.value || '');
  });

  container.querySelector('#sysforge-parts-rebuild')?.addEventListener('click', async () => {
    try {
      const counts = await deps.api('/parts/search/rebuild', { method: 'POST' });
      await _toast(
        `Search index rebuilt (${counts.fts_count || 0} of ${counts.parts_count || 0})`,
        false,
      );
      await loadList(qInput?.value || '');
    } catch (err) {
      await _toast(err?.message || String(err), true);
    }
  });

  function _wireSupplierTypeahead(kind) {
    const qEl = container.querySelector(
      kind === 'preferred' ? '#sysforge-part-preferred-q' : '#sysforge-part-supplier-q'
    );
    const suggestEl = container.querySelector(
      kind === 'preferred'
        ? '#sysforge-part-preferred-suggest'
        : '#sysforge-part-supplier-suggest'
    );
    const clearBtn = container.querySelector(
      kind === 'preferred'
        ? '#sysforge-part-preferred-clear'
        : '#sysforge-part-supplier-clear'
    );
    let timer = null;
    let abort = null;

    qEl?.addEventListener('input', () => {
      clearTimeout(timer);
      timer = setTimeout(async () => {
        const q = (qEl.value || '').trim();
        if (!q) {
          if (suggestEl) suggestEl.hidden = true;
          return;
        }
        if (abort) abort.abort();
        abort = new AbortController();
        try {
          const data = await deps.api(
            `/suppliers/search?q=${encodeURIComponent(q)}&limit=8`,
            { signal: abort.signal },
          );
          const items = data.items || [];
          if (!suggestEl) return;
          if (!items.length) {
            suggestEl.hidden = true;
            return;
          }
          suggestEl.innerHTML = items
            .map((s) => {
              const name = String(s.name || '').replace(/</g, '&lt;');
              const star = s.is_preferred ? ' ★' : '';
              return `<li><button type="button" data-id="${s.id}" data-name="${name}${star}">${name}${star}</button></li>`;
            })
            .join('');
          suggestEl.hidden = false;
        } catch (err) {
          if (err?.name === 'AbortError') return;
        }
      }, 200);
    });

    suggestEl?.addEventListener('click', (e) => {
      const btn = e.target.closest('button[data-id]');
      if (!btn) return;
      _setSupplierField(kind, Number(btn.getAttribute('data-id')), btn.getAttribute('data-name'));
      suggestEl.hidden = true;
    });

    clearBtn?.addEventListener('click', () => {
      _setSupplierField(kind, null, '');
      if (suggestEl) suggestEl.hidden = true;
    });
  }

  _wireSupplierTypeahead('supplier');
  _wireSupplierTypeahead('preferred');

  qInput?.addEventListener('input', () => {
    clearTimeout(_searchTimer);
    _searchTimer = setTimeout(() => loadList(qInput.value), 250);
  });

  formEl?.addEventListener('submit', async (e) => {
    e.preventDefault();
    showError('');
    const body = readForm();
    const stockRaw = container.querySelector('#sysforge-part-stock')?.value;
    const onHand = Math.max(0, Math.floor(Number(stockRaw || 0)));
    try {
      if (state.form.id) {
        await deps.api(`/parts/${state.form.id}`, {
          method: 'PUT',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(body),
        });
        await deps.api(`/parts/${state.form.id}/stock`, {
          method: 'PUT',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ quantity_on_hand: onHand }),
        });
        await _toast('Part saved', false);
      } else {
        const created = await deps.api('/parts', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(body),
        });
        if (created?.id != null && onHand > 0) {
          await deps.api(`/parts/${created.id}/stock`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ quantity_on_hand: onHand }),
          });
        }
        await _toast('Part created', false);
      }
      if (formEl) formEl.hidden = true;
      await loadList(qInput?.value || '');
    } catch (err) {
      const msg = err?.message || String(err);
      showError(msg);
      await _toast(msg, true);
    }
  });

  container.querySelector('#sysforge-part-cancel')?.addEventListener('click', () => {
    if (formEl) formEl.hidden = true;
  });

  container.querySelector('#sysforge-part-convert')?.addEventListener('click', async () => {
    if (!state.form.id) return;
    const body = readForm();
    body.is_placeholder = false;
    try {
      await deps.api(`/parts/${state.form.id}/convert`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      });
      await _toast('Promoted to catalog part', false);
      if (formEl) formEl.hidden = true;
      await loadList(qInput?.value || '');
    } catch (err) {
      const msg = err?.message || String(err);
      showError(msg);
      await _toast(msg, true);
    }
  });

  container.querySelector('#sysforge-part-delete')?.addEventListener('click', async () => {
    if (!state.form.id) return;
    let usage = 0;
    try {
      const u = await deps.api(`/parts/${state.form.id}/usage`);
      usage = Number(u.count || 0);
    } catch (_) {
      /* proceed with confirm */
    }
    const msg =
      usage > 0
        ? `Delete this part? It is used on ${usage} invoice line(s). Those lines will be unlinked from the catalog.`
        : 'Delete this part from the catalog?';
    if (!window.confirm(msg)) return;
    try {
      await deps.api(`/parts/${state.form.id}`, { method: 'DELETE' });
      await _toast(
        usage > 0
          ? 'Removed from catalog; invoice lines unlinked'
          : 'Part deleted',
        false,
      );
      if (formEl) formEl.hidden = true;
      await loadList(qInput?.value || '');
    } catch (err) {
      const m = err?.message || String(err);
      showError(m);
      await _toast(m, true);
    }
  });

  container.dataset.mounted = '1';
  container._sysforgeReloadParts = () => loadList(qInput?.value || '');
}

/**
 * @param {HTMLElement} container
 */
export async function activatePartsCatalog(container) {
  const heading = container.querySelector('.sysforge-view-heading');
  heading?.focus?.({ preventScroll: true });
  if (typeof container._sysforgeReloadParts === 'function') {
    await container._sysforgeReloadParts();
  }
}
