/**
 * Placeholder Merge — name-grouped duplicates, confirm, merge, delete unused.
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

/**
 * @param {HTMLElement} container
 * @param {{ api: (path: string, opts?: object) => Promise<object> }} deps
 */
export function mountPlaceholderMerge(container, deps) {
  if (container.dataset.mounted === '1') return;

  container.innerHTML = `
    <div class="sysforge-merge">
      <h3 class="sysforge-view-heading" tabindex="-1">Placeholder Merge</h3>
      <p class="sysforge-dashboard-lead">
        Merge duplicate placeholders that share the same name. Line prices stay unchanged.
      </p>
      <div class="sysforge-parts-toolbar">
        <button type="button" class="btn-secondary" id="sysforge-merge-refresh">Refresh</button>
      </div>
      <p class="sysforge-parts-error" id="sysforge-merge-error" hidden></p>
      <div id="sysforge-merge-groups" class="sysforge-merge-groups"></div>
      <p class="sysforge-parts-empty" id="sysforge-merge-empty" hidden>No merge groups. Need two or more placeholders with the same name.</p>
    </div>`;

  const groupsEl = container.querySelector('#sysforge-merge-groups');
  const emptyEl = container.querySelector('#sysforge-merge-empty');
  const errorEl = container.querySelector('#sysforge-merge-error');
  const refreshBtn = container.querySelector('#sysforge-merge-refresh');

  function setBusy(busy) {
    _busy = busy;
    container.querySelectorAll('button').forEach((btn) => {
      btn.disabled = busy;
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

  function renderGroups(groups) {
    if (!groupsEl) return;
    if (!groups || groups.length === 0) {
      groupsEl.innerHTML = '';
      if (emptyEl) emptyEl.hidden = false;
      return;
    }
    if (emptyEl) emptyEl.hidden = true;
    groupsEl.innerHTML = groups
      .map((g, idx) => {
        const name = String(g.suggested_name || '').replace(/</g, '&lt;');
        const sku = g.suggested_sku
          ? String(g.suggested_sku).replace(/</g, '&lt;')
          : '—';
        const members = (g.parts || [])
          .map((p) => {
            const usage = (g.part_usage_counts || {})[String(p.id)] ?? 0;
            const pname = String(p.name || '').replace(/</g, '&lt;');
            return `<li data-part-id="${p.id}">
              <span>${pname} · ${_formatCents(p.base_price_cents)} · used ${usage}</span>
              <button type="button" class="btn-secondary sysforge-merge-del"
                data-part-id="${p.id}" data-usage="${usage}">Delete unused</button>
            </li>`;
          })
          .join('');
        return `<article class="sysforge-merge-group" data-group="${idx}">
          <header>
            <strong>${name}</strong>
            <span>SKU ${sku} · ${_formatCents(g.most_recent_price_cents)} · ${g.invoice_count} line(s) · ${g.parts.length} parts</span>
          </header>
          <ul class="sysforge-merge-members">${members}</ul>
          <button type="button" class="btn-primary sysforge-merge-go" data-group="${idx}">
            Merge into first
          </button>
        </article>`;
      })
      .join('');
    groupsEl._groups = groups;
  }

  async function reload() {
    showError('');
    setBusy(true);
    try {
      const data = await deps.api('/placeholders/groups');
      renderGroups(data.groups || []);
    } catch (err) {
      showError(err?.message || String(err));
      await _toast(err?.message || String(err), true);
    } finally {
      setBusy(false);
    }
  }

  groupsEl?.addEventListener('click', async (e) => {
    if (_busy) return;
    const mergeBtn = e.target.closest('.sysforge-merge-go');
    if (mergeBtn) {
      const idx = Number(mergeBtn.getAttribute('data-group'));
      const groups = groupsEl._groups || [];
      const group = groups[idx];
      if (!group || !group.parts || group.parts.length < 2) return;
      const target = group.parts[0];
      const sources = group.parts.slice(1).map((p) => p.id);
      const label = group.suggested_name || target.name || 'part';
      const ok = window.confirm(
        `Merge ${sources.length} placeholder(s) into «${label}»? This cannot be undone.`,
      );
      if (!ok) return;
      setBusy(true);
      showError('');
      try {
        await deps.api('/placeholders/merge', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            target_part_id: target.id,
            source_part_ids: sources,
          }),
        });
        await _toast(`Merged ${sources.length} placeholder(s)`, false);
        await reload();
      } catch (err) {
        showError(err?.message || String(err));
        await _toast(err?.message || String(err), true);
        setBusy(false);
      }
      return;
    }

    const delBtn = e.target.closest('.sysforge-merge-del');
    if (delBtn) {
      const usage = Number(delBtn.getAttribute('data-usage') || 0);
      const partId = Number(delBtn.getAttribute('data-part-id'));
      if (usage > 0) {
        await _toast(`Cannot delete: used on ${usage} invoice line(s)`, true);
        return;
      }
      if (!window.confirm('Delete this unused placeholder?')) return;
      setBusy(true);
      try {
        await deps.api(`/parts/${partId}`, { method: 'DELETE' });
        await _toast('Placeholder deleted', false);
        await reload();
      } catch (err) {
        showError(err?.message || String(err));
        await _toast(err?.message || String(err), true);
        setBusy(false);
      }
    }
  });

  refreshBtn?.addEventListener('click', () => {
    if (!_busy) reload();
  });

  container.dataset.mounted = '1';
  container._sysforgeReloadMerge = reload;
}

/**
 * @param {HTMLElement} container
 */
export async function activatePlaceholderMerge(container) {
  const heading = container.querySelector('.sysforge-view-heading');
  heading?.focus?.({ preventScroll: true });
  if (typeof container._sysforgeReloadMerge === 'function') {
    await container._sysforgeReloadMerge();
  }
}
