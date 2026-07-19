/**
 * Four-column project detail — sole production project surface.
 * Notes | Parts | Photos (screw map above Before/After) | Device (Done-editing autosave).
 */

import { startCreateProjectFromInvoice } from '../create-project-wizard.js';

const STATUSES = [
  'Intake',
  'WaitingOnPartsPayment',
  'WaitingForParts',
  'WaitingOnDevice',
  'ReadyToStart',
  'InProgress',
  'FinishedWaitingDropOff',
  'WaitingOnPayment',
];

async function _toast(message, kind) {
  try {
    const ui = await import('/static/js/ui.js');
    if (typeof ui.showToast === 'function') {
      ui.showToast(message, kind === 'error' ? 'error' : 'success');
      return;
    }
  } catch (_) {
    /* fall through */
  }
  console.log(message);
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
 *   api: Function,
 *   navigate: Function,
 *   navigateToInvoiceViewer?: Function,
 * }} deps
 */
export function mountProjectDetail(container, deps) {
  if (container.dataset.mounted === '1') return;

  container.innerHTML = `
    <div class="sysforge-project-detail">
      <div class="sysforge-project-header">
        <div class="sysforge-project-picker">
          <input type="search" id="sysforge-project-picker-q"
            class="sysforge-clients-q" placeholder="Recent / search projects…" />
          <ul id="sysforge-project-picker-list" class="sysforge-project-picker-list"></ul>
        </div>
        <button type="button" class="btn-secondary" id="sysforge-project-create-from-invoice">
          Create project from invoice
        </button>
      </div>
      <div id="sysforge-project-empty" class="sysforge-classic-empty">
        Select a project from the picker, or create one from an invoice.
      </div>
      <div id="sysforge-project-body" hidden>
        <div class="sysforge-project-status-strip">
          <strong id="sysforge-project-title"></strong>
          <span id="sysforge-project-device-id"></span>
          <label class="sysforge-field">
            <span>Status</span>
            <select id="sysforge-project-status">
              ${STATUSES.map((s) => `<option value="${s}">${s}</option>`).join('')}
            </select>
          </label>
        </div>
        <div class="sysforge-project-columns">
          <section class="sysforge-project-col" aria-label="Notes">
            <h4>Notes</h4>
            <label class="sysforge-field"><span>First contact</span>
              <textarea id="sysforge-note-FirstContact" rows="4"></textarea></label>
            <label class="sysforge-field"><span>Client issue</span>
              <textarea id="sysforge-note-ClientIssue" rows="4"></textarea></label>
            <label class="sysforge-field"><span>Repair plan</span>
              <textarea id="sysforge-note-Plan" rows="4"></textarea></label>
            <button type="button" class="btn-primary" id="sysforge-save-notes">Save notes</button>
          </section>
          <section class="sysforge-project-col" aria-label="Parts">
            <h4>Parts and invoicing</h4>
            <p class="sysforge-dashboard-lead">Order parts before starting work when needed.</p>
            <ul id="sysforge-project-parts" class="sysforge-hub-list"></ul>
            <button type="button" class="btn-secondary" id="sysforge-project-source-invoice" hidden>
              Open source invoice
            </button>
          </section>
          <section class="sysforge-project-col" aria-label="Photos">
            <h4>Photos</h4>
            <div id="sysforge-screw-map-slot" class="sysforge-screw-map-slot" hidden>
              <h5>Screw map</h5>
              <div id="sysforge-screw-map-preview" class="sysforge-screw-map-preview"></div>
            </div>
            <div class="sysforge-photo-block">
              <h5>Before</h5>
              <ul id="sysforge-photos-before" class="sysforge-hub-list"></ul>
              <input type="file" id="sysforge-photo-before" accept="image/*" />
            </div>
            <div class="sysforge-photo-block">
              <h5>After</h5>
              <ul id="sysforge-photos-after" class="sysforge-hub-list"></ul>
              <input type="file" id="sysforge-photo-after" accept="image/*" />
            </div>
          </section>
          <section class="sysforge-project-col" aria-label="Device">
            <h4>Device details</h4>
            <dl id="sysforge-device-readonly" class="sysforge-device-readonly">
              <div><dt>Device ID</dt><dd id="sysforge-dev-id-ro"></dd></div>
              <div><dt>Model</dt><dd id="sysforge-dev-model-ro"></dd></div>
              <div><dt>Serial</dt><dd id="sysforge-dev-serial-ro"></dd></div>
              <div><dt>Color</dt><dd id="sysforge-dev-color-ro"></dd></div>
            </dl>
            <div id="sysforge-device-edit" hidden>
              <label class="sysforge-field"><span>Model</span>
                <input type="text" id="sysforge-dev-model" /></label>
              <label class="sysforge-field"><span>Serial</span>
                <input type="text" id="sysforge-dev-serial" /></label>
              <label class="sysforge-field"><span>Color</span>
                <input type="text" id="sysforge-dev-color" /></label>
            </div>
            <button type="button" class="btn-secondary" id="sysforge-toggle-device-edit">
              Edit device details
            </button>
          </section>
        </div>
      </div>
      <p class="sysforge-settings-error" id="sysforge-project-error" hidden></p>
    </div>`;

  container._sysforgeProject = {
    projectId: null,
    detail: null,
    isEditingDevice: false,
    pickerTimer: null,
  };
  container.dataset.mounted = '1';

  const pickerQ = container.querySelector('#sysforge-project-picker-q');
  pickerQ?.addEventListener('focus', () => {
    void refreshPicker(container, deps, '');
  });
  pickerQ?.addEventListener('input', () => {
    clearTimeout(container._sysforgeProject.pickerTimer);
    container._sysforgeProject.pickerTimer = setTimeout(() => {
      void refreshPicker(container, deps, pickerQ.value);
    }, 200);
  });

  container.querySelector('#sysforge-project-picker-list')?.addEventListener('click', (e) => {
    const btn = e.target.closest('[data-project-id]');
    if (!btn) return;
    // Exit edit mode when selecting another project (no orphaned dirty state).
    container._sysforgeProject.isEditingDevice = false;
    void loadProject(container, deps, Number(btn.getAttribute('data-project-id')));
  });

  container
    .querySelector('#sysforge-project-create-from-invoice')
    ?.addEventListener('click', () => {
      void startCreateProjectFromInvoice({
        api: deps.api,
        navigate: deps.navigate,
        invoiceId: null,
      });
    });

  container.querySelector('#sysforge-project-status')?.addEventListener('change', async (e) => {
    const state = container._sysforgeProject;
    if (!state.projectId) return;
    try {
      const project = await deps.api(`/projects/${state.projectId}/status`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ status: e.target.value }),
      });
      if (state.detail) state.detail.project = project;
      await _toast('Status updated', 'success');
    } catch (err) {
      await _toast(err.message || String(err), 'error');
      await loadProject(container, deps, state.projectId);
    }
  });

  container.querySelector('#sysforge-save-notes')?.addEventListener('click', async () => {
    const state = container._sysforgeProject;
    if (!state.projectId) return;
    const notes = {
      FirstContact: container.querySelector('#sysforge-note-FirstContact')?.value || '',
      ClientIssue: container.querySelector('#sysforge-note-ClientIssue')?.value || '',
      Plan: container.querySelector('#sysforge-note-Plan')?.value || '',
    };
    try {
      const res = await deps.api(`/projects/${state.projectId}/notes`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(notes),
      });
      if (state.detail) state.detail.notes = res.notes;
      await _toast('Notes saved', 'success');
    } catch (err) {
      await _toast(err.message || String(err), 'error');
    }
  });

  container.querySelector('#sysforge-toggle-device-edit')?.addEventListener('click', async () => {
    const state = container._sysforgeProject;
    if (!state.projectId || !state.detail) return;
    if (state.isEditingDevice) {
      // Done editing → autosave model/serial/color, then flip off.
      try {
        const project = await deps.api(`/projects/${state.projectId}`, {
          method: 'PATCH',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            device_model: container.querySelector('#sysforge-dev-model')?.value || '',
            device_serial: container.querySelector('#sysforge-dev-serial')?.value || '',
            device_color: container.querySelector('#sysforge-dev-color')?.value || '',
          }),
        });
        state.detail.project = project;
        state.isEditingDevice = false;
        renderDevice(container);
        await _toast('Device details saved', 'success');
      } catch (err) {
        await _toast(err.message || String(err), 'error');
      }
      return;
    }
    state.isEditingDevice = true;
    renderDevice(container);
  });

  container.querySelector('#sysforge-project-source-invoice')?.addEventListener('click', () => {
    const invId = container._sysforgeProject?.detail?.project?.source_invoice_id;
    if (!invId) return;
    if (typeof deps.navigateToInvoiceViewer === 'function') {
      deps.navigateToInvoiceViewer(invId);
    } else {
      deps.navigate('invoice-view', { params: { id: invId } });
    }
  });

  wirePhotoUpload(container, deps, 'before', '#sysforge-photo-before');
  wirePhotoUpload(container, deps, 'after', '#sysforge-photo-after');
}

function wirePhotoUpload(container, deps, phase, selector) {
  container.querySelector(selector)?.addEventListener('change', async (e) => {
    const file = e.target.files?.[0];
    const state = container._sysforgeProject;
    if (!file || !state.projectId) return;
    const form = new FormData();
    form.append('phase', phase === 'before' ? 'Before' : 'After');
    form.append('file', file);
    try {
      await fetch(`${window.location.origin}/api/sysforge/projects/${state.projectId}/photos`, {
        method: 'POST',
        credentials: 'same-origin',
        body: form,
      }).then(async (res) => {
        if (!res.ok) {
          const data = await res.json().catch(() => ({}));
          throw new Error(data.detail || data.message || `Upload failed (${res.status})`);
        }
      });
      await loadProject(container, deps, state.projectId);
      await _toast('Photo uploaded', 'success');
    } catch (err) {
      await _toast(err.message || String(err), 'error');
    }
    e.target.value = '';
  });
}

async function refreshPicker(container, deps, query) {
  const list = container.querySelector('#sysforge-project-picker-list');
  if (!list) return;
  const q = (query || '').trim();
  try {
    const path = q
      ? `/projects?q=${encodeURIComponent(q)}`
      : '/projects?recent=3';
    const data = await deps.api(path);
    const projects = (data.projects || []).slice(0, 3);
    list.innerHTML = projects.length
      ? projects
          .map(
            (p) => `<li>
            <button type="button" data-project-id="${p.id}">
              ${escapeHtml(p.device_id)} — ${escapeHtml(p.title || p.status || '')}
            </button>
          </li>`
          )
          .join('')
      : `<li class="sysforge-classic-empty">No projects.</li>`;
  } catch (err) {
    list.innerHTML = `<li class="sysforge-classic-empty">${escapeHtml(err.message)}</li>`;
  }
}

function renderDevice(container) {
  const state = container._sysforgeProject;
  const p = state.detail?.project;
  if (!p) return;
  const editing = state.isEditingDevice;
  const ro = container.querySelector('#sysforge-device-readonly');
  const ed = container.querySelector('#sysforge-device-edit');
  const btn = container.querySelector('#sysforge-toggle-device-edit');
  if (ro) ro.hidden = editing;
  if (ed) ed.hidden = !editing;
  if (btn) btn.textContent = editing ? 'Done editing' : 'Edit device details';

  const setText = (id, val) => {
    const el = container.querySelector(id);
    if (el) el.textContent = val || '—';
  };
  setText('#sysforge-dev-id-ro', p.device_id);
  setText('#sysforge-dev-model-ro', p.device_model);
  setText('#sysforge-dev-serial-ro', p.device_serial);
  setText('#sysforge-dev-color-ro', p.device_color);

  if (editing) {
    const model = container.querySelector('#sysforge-dev-model');
    const serial = container.querySelector('#sysforge-dev-serial');
    const color = container.querySelector('#sysforge-dev-color');
    if (model) model.value = p.device_model || '';
    if (serial) serial.value = p.device_serial || '';
    if (color) color.value = p.device_color || '';
  }
}

function renderDetail(container, deps) {
  const state = container._sysforgeProject;
  const empty = container.querySelector('#sysforge-project-empty');
  const body = container.querySelector('#sysforge-project-body');
  if (!state.detail) {
    if (empty) empty.hidden = false;
    if (body) body.hidden = true;
    return;
  }
  if (empty) empty.hidden = true;
  if (body) body.hidden = false;

  const p = state.detail.project;
  const titleEl = container.querySelector('#sysforge-project-title');
  const deviceEl = container.querySelector('#sysforge-project-device-id');
  if (titleEl) titleEl.textContent = p.title || 'Project';
  if (deviceEl) deviceEl.textContent = p.device_id || '';
  const statusSel = container.querySelector('#sysforge-project-status');
  if (statusSel) statusSel.value = p.status || 'Intake';

  const notes = state.detail.notes || {};
  for (const section of ['FirstContact', 'ClientIssue', 'Plan']) {
    const ta = container.querySelector(`#sysforge-note-${section}`);
    if (ta) ta.value = notes[section] || '';
  }

  const partsEl = container.querySelector('#sysforge-project-parts');
  const parts = state.detail.parts || [];
  if (partsEl) {
    partsEl.innerHTML = parts.length
      ? parts
          .map(
            (part) =>
              `<li>${escapeHtml(part.part_name)} × ${(Number(part.quantity_milliunits) || 1000) / 1000}</li>`
          )
          .join('')
      : `<li class="sysforge-classic-empty">No parts copied.</li>`;
  }

  const invBtn = container.querySelector('#sysforge-project-source-invoice');
  if (invBtn) {
    invBtn.hidden = !p.source_invoice_id;
  }

  const screw = container.querySelector('#sysforge-screw-map-slot');
  const preview = container.querySelector('#sysforge-screw-map-preview');
  if (screw) {
    const eligible = Boolean(state.detail.screw_map_eligible);
    screw.hidden = !eligible;
    if (eligible && preview) {
      const map = state.detail.screw_map;
      if (!map) {
        preview.innerHTML = `
          <p class="sysforge-sm-preview-meta">No screw map yet.</p>
          <button type="button" class="btn-primary" id="sysforge-start-screw-map">
            Start screw map
          </button>`;
        preview.querySelector('#sysforge-start-screw-map')?.addEventListener('click', () => {
          void startScrewMap(container, deps);
        });
      } else {
        const count = (map.images || []).length;
        const locked = map.is_locked ? ' · Locked' : '';
        preview.innerHTML = `
          <p class="sysforge-sm-preview-meta">${count} photo${count === 1 ? '' : 's'}${locked}</p>
          <button type="button" class="btn-secondary" id="sysforge-open-screw-map">
            Open screw map
          </button>`;
        preview.querySelector('#sysforge-open-screw-map')?.addEventListener('click', () => {
          deps.navigate('screw-map', { params: { projectId: state.projectId } });
        });
      }
    }
  }

  const photos = state.detail.photos || { before: [], after: [] };
  renderPhotos(container.querySelector('#sysforge-photos-before'), photos.before);
  renderPhotos(container.querySelector('#sysforge-photos-after'), photos.after);

  renderDevice(container);
}

async function startScrewMap(container, deps) {
  const state = container._sysforgeProject;
  const projectId = state?.projectId;
  if (!projectId) return;
  try {
    await deps.api(`/projects/${projectId}/screw-map`, { method: 'POST' });
    deps.navigate('screw-map', { params: { projectId } });
  } catch (err) {
    void _toast(err.message || String(err), 'error');
  }
}

function renderPhotos(el, items) {
  if (!el) return;
  el.innerHTML = (items || []).length
    ? items.map((ph) => `<li>${escapeHtml(ph.file_name)}</li>`).join('')
    : `<li class="sysforge-classic-empty">None.</li>`;
}

async function loadProject(container, deps, projectId) {
  const errEl = container.querySelector('#sysforge-project-error');
  if (errEl) {
    errEl.hidden = true;
    errEl.textContent = '';
  }
  try {
    const detail = await deps.api(`/projects/${projectId}`);
    container._sysforgeProject.projectId = projectId;
    container._sysforgeProject.detail = detail;
    container._sysforgeProject.isEditingDevice = false;
    renderDetail(container, deps);
  } catch (err) {
    container._sysforgeProject.projectId = null;
    container._sysforgeProject.detail = null;
    renderDetail(container, deps);
    if (errEl) {
      errEl.hidden = false;
      errEl.textContent = err.message || String(err);
    }
  }
}

/**
 * @param {HTMLElement} container
 * @param {{ api: Function, navigate: Function }} deps
 * @param {Record<string, string>} params
 */
export async function activateProjectDetail(container, deps, params = {}) {
  // PrepareForReturnNavigation: clear edit mode on re-activate.
  if (container._sysforgeProject) {
    container._sysforgeProject.isEditingDevice = false;
  }
  const id = params.id || params.projectId;
  if (id) {
    await loadProject(container, deps, Number(id));
  } else {
    container._sysforgeProject.projectId = null;
    container._sysforgeProject.detail = null;
    renderDetail(container, deps);
    await refreshPicker(container, deps, '');
  }
}

export function deactivateProjectDetail(container) {
  if (container?._sysforgeProject) {
    container._sysforgeProject.isEditingDevice = false;
  }
}
