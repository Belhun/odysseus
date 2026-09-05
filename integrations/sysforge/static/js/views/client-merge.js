/**
 * Client merge tool — soft-merge duplicates (survivor keeps; loser deleted + MergedIntoClientId).
 * Detection reuses phone/email/name duplicate signals; merge is always intentional.
 * Route: #sysforge/client-merge
 */

function escapeHtml(s) {
  return String(s ?? '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

function clientCardHtml(client, role) {
  if (!client) {
    return `<div class="sysforge-client-merge-card"><p class="sysforge-parts-empty">Not selected</p></div>`;
  }
  const cls =
    role === 'survivor'
      ? 'sysforge-client-merge-card sysforge-merge-survivor'
      : 'sysforge-client-merge-card';
  return `<div class="${cls}">
    <h4>${role === 'survivor' ? 'Survivor (keep)' : 'Loser (merge away)'}</h4>
    <p><strong>${escapeHtml(client.display_name || `#${client.id}`)}</strong></p>
    <p>Phone: ${escapeHtml(client.phone_number || '—')}</p>
    <p>Email: ${escapeHtml(client.email || '—')}</p>
    <p>Company: ${escapeHtml(client.company || '—')}</p>
    <p>Id: ${escapeHtml(String(client.id))}</p>
  </div>`;
}

/**
 * @param {HTMLElement} container
 * @param {{
 *   api: (path: string, opts?: object) => Promise<object>,
 *   navigate?: (routeKey: string, opts?: object) => void,
 * }} deps
 */
export function mountClientMerge(container, deps) {
  if (container.dataset.mounted === '1') return;

  container.innerHTML = `
    <div class="sysforge-client-merge">
      <h3 class="sysforge-view-heading" tabindex="-1">Client merge</h3>
      <p class="sysforge-dashboard-lead">
        Soft-merge a duplicate into a survivor. Invoices, work orders, and projects move.
        Merge is permanent; the loser stays soft-deleted with a link to the survivor.
        Duplicate warnings on create stay advisory — this tool never auto-merges.
      </p>
      <div class="sysforge-parts-toolbar">
        <label>Search
          <input type="search" id="sysforge-merge-q" placeholder="Name, phone, or email" />
        </label>
        <button type="button" class="btn-secondary" id="sysforge-merge-find">Find candidates</button>
      </div>
      <p class="sysforge-parts-error" id="sysforge-merge-error" hidden></p>
      <p class="sysforge-viewer-toast" id="sysforge-merge-toast" hidden></p>
      <div id="sysforge-merge-candidates" class="sysforge-merge-groups"></div>
      <div class="sysforge-client-merge-pair" id="sysforge-merge-pair">
        ${clientCardHtml(null, 'survivor')}
        ${clientCardHtml(null, 'loser')}
      </div>
      <label class="sysforge-merge-confirm">
        <input type="checkbox" id="sysforge-merge-confirm-check" />
        I understand merge is permanent and will move related invoices / projects.
      </label>
      <button type="button" class="btn-primary" id="sysforge-merge-go" disabled>Merge clients</button>
    </div>`;

  container.dataset.mounted = '1';
  container._sysforgeMergeDeps = deps;
  container._sysforgeMergeSurvivor = null;
  container._sysforgeMergeLoser = null;

  const errorEl = container.querySelector('#sysforge-merge-error');
  const toastEl = container.querySelector('#sysforge-merge-toast');
  const goBtn = container.querySelector('#sysforge-merge-go');
  const confirmEl = container.querySelector('#sysforge-merge-confirm-check');

  const setError = (msg) => {
    if (!errorEl) return;
    errorEl.textContent = msg || '';
    errorEl.hidden = !msg;
  };

  const setToast = (msg) => {
    if (!toastEl) return;
    toastEl.textContent = msg || '';
    toastEl.hidden = !msg;
  };

  const syncPair = () => {
    const pair = container.querySelector('#sysforge-merge-pair');
    if (pair) {
      pair.innerHTML =
        clientCardHtml(container._sysforgeMergeSurvivor, 'survivor') +
        clientCardHtml(container._sysforgeMergeLoser, 'loser');
    }
    const ready =
      container._sysforgeMergeSurvivor &&
      container._sysforgeMergeLoser &&
      container._sysforgeMergeSurvivor.id !== container._sysforgeMergeLoser.id &&
      confirmEl?.checked;
    if (goBtn) goBtn.disabled = !ready;
  };

  confirmEl?.addEventListener('change', syncPair);

  const findCandidates = async () => {
    setError('');
    setToast('');
    const q = container.querySelector('#sysforge-merge-q')?.value?.trim() || '';
    const host = container.querySelector('#sysforge-merge-candidates');
    if (!host) return;
    try {
      let data;
      if (/^\d+$/.test(q)) {
        data = await deps.api(
          `/clients/merge/candidates?client_id=${encodeURIComponent(q)}`
        );
      } else if (q.includes('@')) {
        data = await deps.api(
          `/clients/merge/candidates?email=${encodeURIComponent(q)}`
        );
      } else if (/\d{7,}/.test(q.replace(/\D/g, ''))) {
        data = await deps.api(
          `/clients/merge/candidates?phone=${encodeURIComponent(q)}`
        );
      } else if (q) {
        data = await deps.api(
          `/clients/merge/candidates?name=${encodeURIComponent(q)}`
        );
      } else {
        host.innerHTML =
          '<p class="sysforge-parts-empty">Enter a name, phone, email, or client id.</p>';
        return;
      }
      const rows = Array.isArray(data?.candidates) ? data.candidates : [];
      if (!rows.length) {
        host.innerHTML =
          '<p class="sysforge-parts-empty">No candidates. Create-anyway duplicates still need a manual pick.</p>';
        return;
      }
      host.innerHTML = `<ul class="sysforge-merge-members">${rows
        .map(
          (c) => `<li>
            <span>${escapeHtml(c.display_name || `#${c.id}`)} · ${escapeHtml(
            c.phone_number || ''
          )} · ${escapeHtml(c.email || '')}</span>
            <button type="button" class="btn-secondary sysforge-merge-pick-survivor"
              data-id="${escapeHtml(String(c.id))}">Survivor</button>
            <button type="button" class="btn-secondary sysforge-merge-pick-loser"
              data-id="${escapeHtml(String(c.id))}">Loser</button>
          </li>`
        )
        .join('')}</ul>`;
      container._sysforgeMergeCandidateMap = new Map(rows.map((c) => [String(c.id), c]));
    } catch (err) {
      setError(err?.message || String(err));
      host.innerHTML = '';
    }
  };

  container.querySelector('#sysforge-merge-find')?.addEventListener('click', () => {
    void findCandidates();
  });
  container.querySelector('#sysforge-merge-q')?.addEventListener('keydown', (e) => {
    if (e.key === 'Enter') {
      e.preventDefault();
      void findCandidates();
    }
  });

  container.addEventListener('click', (e) => {
    const survBtn = e.target?.closest?.('.sysforge-merge-pick-survivor');
    const loseBtn = e.target?.closest?.('.sysforge-merge-pick-loser');
    const map = container._sysforgeMergeCandidateMap;
    if (survBtn && map) {
      const c = map.get(survBtn.getAttribute('data-id'));
      if (c) {
        container._sysforgeMergeSurvivor = c;
        syncPair();
      }
    }
    if (loseBtn && map) {
      const c = map.get(loseBtn.getAttribute('data-id'));
      if (c) {
        container._sysforgeMergeLoser = c;
        syncPair();
      }
    }
  });

  goBtn?.addEventListener('click', async () => {
    const survivor = container._sysforgeMergeSurvivor;
    const loser = container._sysforgeMergeLoser;
    if (!survivor || !loser || !confirmEl?.checked) return;
    if (survivor.id === loser.id) {
      setError('Pick two different clients.');
      return;
    }
    const ok = window.confirm(
      `Merge «${loser.display_name || loser.id}» into «${
        survivor.display_name || survivor.id
      }»?\n\nThis is permanent. Invoices, work orders, and projects move to the survivor.`
    );
    if (!ok) return;
    goBtn.disabled = true;
    setError('');
    try {
      const result = await deps.api('/clients/merge', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          survivor_id: survivor.id,
          loser_id: loser.id,
        }),
      });
      setToast(
        `Merged. Moved ${result.invoices_moved} invoice(s), ` +
          `${result.work_orders_moved} work order(s), ` +
          `${result.projects_moved} project(s).`
      );
      container._sysforgeMergeLoser = null;
      if (confirmEl) confirmEl.checked = false;
      syncPair();
      await findCandidates();
    } catch (err) {
      setError(err?.message || String(err));
      syncPair();
    }
  });

  container._sysforgeReloadClientMerge = findCandidates;
}

/**
 * @param {HTMLElement} container
 */
export async function activateClientMerge(container) {
  container.querySelector('.sysforge-view-heading')?.focus?.({ preventScroll: true });
}
