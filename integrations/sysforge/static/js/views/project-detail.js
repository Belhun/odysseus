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

/** Lightweight markdown → safe HTML (bold, italic, code, links, paragraphs). */
function renderMarkdownLite(src) {
  let text = escapeHtml(src || '');
  text = text.replace(/\[([^\]]+)\]\((https?:\/\/[^)\s]+)\)/g, (_, label, href) => {
    return `<a href="${href}" target="_blank" rel="noopener noreferrer">${label}</a>`;
  });
  text = text.replace(/`([^`]+)`/g, '<code>$1</code>');
  text = text.replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>');
  text = text.replace(/(^|[^*])\*([^*]+)\*(?!\*)/g, '$1<em>$2</em>');
  text = text.replace(/\n/g, '<br>');
  return text || '<span class="sysforge-classic-empty">Empty.</span>';
}

function _noteSectionHtml(section, label) {
  return `
    <div class="sysforge-note-block" data-section="${section}">
      <div class="sysforge-note-toolbar" role="toolbar" aria-label="${escapeHtml(label)} formatting">
        <span class="sysforge-note-label">${escapeHtml(label)}</span>
        <button type="button" class="btn-secondary sysforge-md-btn" data-md="bold" data-section="${section}" title="Bold">B</button>
        <button type="button" class="btn-secondary sysforge-md-btn" data-md="italic" data-section="${section}" title="Italic">I</button>
        <button type="button" class="btn-secondary sysforge-md-btn" data-md="code" data-section="${section}" title="Code">\`\`</button>
        <button type="button" class="btn-secondary sysforge-md-btn" data-md="link" data-section="${section}" title="Link">Link</button>
      </div>
      <textarea id="sysforge-note-${section}" rows="4" class="sysforge-note-editor"></textarea>
      <div class="sysforge-note-preview" id="sysforge-note-preview-${section}" aria-live="polite"></div>
    </div>`;
}

function wrapSelection(textarea, before, after, placeholder) {
  if (!textarea) return;
  const start = textarea.selectionStart ?? 0;
  const end = textarea.selectionEnd ?? 0;
  const value = textarea.value || '';
  const selected = value.slice(start, end) || placeholder || '';
  const next = value.slice(0, start) + before + selected + after + value.slice(end);
  textarea.value = next;
  const cursor = start + before.length + selected.length;
  textarea.focus();
  textarea.setSelectionRange(start + before.length, cursor);
  textarea.dispatchEvent(new Event('input', { bubbles: true }));
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
          <span id="sysforge-project-display-code" class="sysforge-display-code"></span>
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
            <p class="sysforge-dashboard-lead">Markdown: **bold**, *italic*, \`code\`, [links](url).</p>
            ${_noteSectionHtml('FirstContact', 'First contact')}
            ${_noteSectionHtml('ClientIssue', 'Client issue')}
            ${_noteSectionHtml('Plan', 'Repair plan')}
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
              <div id="sysforge-companion-panel" class="sysforge-companion-panel" hidden>
                <h6>Phone upload</h6>
                <p class="sysforge-dashboard-lead">
                  Scan the QR on the same Wi-Fi, enter the 6-digit code, then take photos.
                </p>
                <div class="sysforge-companion-actions">
                  <button type="button" class="btn-primary" id="sysforge-companion-start">
                    Show QR / pair code
                  </button>
                  <button type="button" class="btn-secondary" id="sysforge-companion-regen" hidden>
                    Regenerate QR
                  </button>
                </div>
                <div id="sysforge-companion-pair-ui" class="sysforge-companion-pair-ui" hidden>
                  <img id="sysforge-companion-qr" alt="Phone pair QR code" width="180" height="180" />
                  <p class="sysforge-companion-code">
                    Code: <strong id="sysforge-companion-code-val"></strong>
                  </p>
                  <p class="sysforge-sm-preview-meta" id="sysforge-companion-url"></p>
                  <p class="sysforge-sm-preview-meta" id="sysforge-companion-lan"></p>
                </div>
                <div id="sysforge-companion-inbox" class="sysforge-companion-inbox" hidden>
                  <h6>Inbox fallback</h6>
                  <p class="sysforge-sm-preview-meta" id="sysforge-companion-inbox-meta"></p>
                  <button type="button" class="btn-secondary" id="sysforge-companion-inbox-scan">
                    Scan inbox
                  </button>
                  <button type="button" class="btn-primary" id="sysforge-companion-inbox-import" hidden>
                    Import pending
                  </button>
                  <ul id="sysforge-companion-inbox-list" class="sysforge-hub-list"></ul>
                </div>
              </div>
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

  container.querySelector('#sysforge-companion-start')?.addEventListener('click', () => {
    void startCompanionPair(container, deps);
  });
  container.querySelector('#sysforge-companion-regen')?.addEventListener('click', () => {
    void startCompanionPair(container, deps);
  });
  container.querySelector('#sysforge-companion-inbox-scan')?.addEventListener('click', () => {
    void scanCompanionInbox(container, deps);
  });
  container.querySelector('#sysforge-companion-inbox-import')?.addEventListener('click', () => {
    void importCompanionInbox(container, deps);
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

  container.addEventListener('click', (e) => {
    const btn = e.target.closest('.sysforge-md-btn');
    if (!btn) return;
    const section = btn.getAttribute('data-section');
    const kind = btn.getAttribute('data-md');
    const ta = container.querySelector(`#sysforge-note-${section}`);
    if (!ta) return;
    if (kind === 'bold') wrapSelection(ta, '**', '**', 'bold');
    else if (kind === 'italic') wrapSelection(ta, '*', '*', 'italic');
    else if (kind === 'code') wrapSelection(ta, '`', '`', 'code');
    else if (kind === 'link') wrapSelection(ta, '[', '](https://)', 'label');
  });

  for (const section of ['FirstContact', 'ClientIssue', 'Plan']) {
    const ta = container.querySelector(`#sysforge-note-${section}`);
    ta?.addEventListener('input', () => {
      const preview = container.querySelector(`#sysforge-note-preview-${section}`);
      if (preview) preview.innerHTML = renderMarkdownLite(ta.value);
    });
  }
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
              ${escapeHtml(p.display_code || p.device_id)} — ${escapeHtml(p.title || p.status || '')}
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

function _stockBadge(part) {
  const status = part.stock_status || 'untracked';
  if (status === 'untracked' || part.part_id == null) {
    return '<span class="sysforge-badge sysforge-stock-untracked">No stock</span>';
  }
  const avail = part.available ?? part.quantity_on_hand ?? 0;
  if (status === 'out') {
    return `<span class="sysforge-badge sysforge-stock-out">Out of stock</span>`;
  }
  if (status === 'low') {
    return `<span class="sysforge-badge sysforge-stock-low">Low (${avail} avail)</span>`;
  }
  return `<span class="sysforge-badge sysforge-stock-ok">In stock (${avail})</span>`;
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
  const codeEl = container.querySelector('#sysforge-project-display-code');
  const deviceEl = container.querySelector('#sysforge-project-device-id');
  if (titleEl) titleEl.textContent = p.title || 'Project';
  if (codeEl) codeEl.textContent = p.display_code || '';
  if (deviceEl) deviceEl.textContent = p.device_id || '';
  const statusSel = container.querySelector('#sysforge-project-status');
  if (statusSel) statusSel.value = p.status || 'Intake';

  const notes = state.detail.notes || {};
  for (const section of ['FirstContact', 'ClientIssue', 'Plan']) {
    const ta = container.querySelector(`#sysforge-note-${section}`);
    if (ta) ta.value = notes[section] || '';
    const preview = container.querySelector(`#sysforge-note-preview-${section}`);
    if (preview) preview.innerHTML = renderMarkdownLite(notes[section] || '');
  }

  const partsEl = container.querySelector('#sysforge-project-parts');
  const parts = state.detail.parts || [];
  if (partsEl) {
    partsEl.innerHTML = parts.length
      ? parts
          .map((part) => {
            const qty = (Number(part.quantity_milliunits) || 1000) / 1000;
            const badge = _stockBadge(part);
            return `<li>
              <span>${escapeHtml(part.part_name)} × ${qty}</span>
              ${badge}
            </li>`;
          })
          .join('')
      : `<li class="sysforge-classic-empty">No parts copied.</li>`;
  }

  const invBtn = container.querySelector('#sysforge-project-source-invoice');
  if (invBtn) {
    invBtn.hidden = !p.source_invoice_id;
  }

  const screw = container.querySelector('#sysforge-screw-map-slot');
  const preview = container.querySelector('#sysforge-screw-map-preview');
  const companionPanel = container.querySelector('#sysforge-companion-panel');
  if (screw) {
    const eligible = Boolean(state.detail.screw_map_eligible);
    screw.hidden = !eligible;
    if (companionPanel) companionPanel.hidden = !eligible;
    if (eligible && preview) {
      const map = state.detail.screw_map;
      const project = state.detail.project || {};
      if (!map) {
        preview.innerHTML = `
          <p class="sysforge-sm-preview-meta">No screw map yet.</p>
          <button type="button" class="btn-primary" id="sysforge-start-screw-map">
            Start screw map
          </button>
          <div class="sysforge-sm-library-reuse" id="sysforge-sm-library-reuse">
            <h6>Reuse from library</h6>
            <p class="sysforge-dashboard-lead">
              Matching sets for this device model (if any). Clones the full photo set into an empty map.
            </p>
            <button type="button" class="btn-secondary" id="sysforge-sm-browse-library">
              Browse library
            </button>
            <div id="sysforge-sm-library-picker" hidden>
              <label class="sysforge-field"><span>Library set</span>
                <select id="sysforge-sm-library-select"></select>
              </label>
              <button type="button" class="btn-primary" id="sysforge-sm-reuse-library" disabled>
                Reuse selected set
              </button>
              <p class="sysforge-sm-preview-meta" id="sysforge-sm-library-status"></p>
            </div>
          </div>`;
        preview.querySelector('#sysforge-start-screw-map')?.addEventListener('click', () => {
          void startScrewMap(container, deps);
        });
        preview.querySelector('#sysforge-sm-browse-library')?.addEventListener('click', () => {
          void browseLibrary(container, deps, project.device_model);
        });
        preview.querySelector('#sysforge-sm-reuse-library')?.addEventListener('click', () => {
          void reuseLibrarySet(container, deps);
        });
        preview.querySelector('#sysforge-sm-library-select')?.addEventListener('change', (ev) => {
          const btn = preview.querySelector('#sysforge-sm-reuse-library');
          if (btn) btn.disabled = !ev.target.value;
        });
      } else {
        const count = (map.images || []).length;
        const locked = map.is_locked ? ' · Locked' : '';
        const canPublish =
          map.is_locked && count > 0 && !map.has_library_set;
        const defaultTitle = escapeHtml(
          project.title || map.device_model || 'Screw map'
        );
        let publishBlock = '';
        if (map.has_library_set) {
          publishBlock = `<p class="sysforge-sm-preview-meta">Published to library.</p>`;
        } else if (canPublish) {
          publishBlock = `
            <div class="sysforge-sm-library-publish" id="sysforge-sm-library-publish">
              <h6>Publish to library</h6>
              <label class="sysforge-field"><span>Title</span>
                <input type="text" id="sysforge-sm-publish-title" value="${defaultTitle}" /></label>
              <label class="sysforge-field"><span>Tags (comma-separated)</span>
                <input type="text" id="sysforge-sm-publish-tags" placeholder="iphone, bottom" /></label>
              <label class="sysforge-field"><span>Notes (optional)</span>
                <textarea id="sysforge-sm-publish-notes" rows="2"></textarea></label>
              <button type="button" class="btn-primary" id="sysforge-sm-publish">
                Publish set
              </button>
            </div>`;
        } else if (map.is_locked && count === 0) {
          publishBlock = `<p class="sysforge-sm-preview-meta">Add photos before publishing.</p>`;
        }

        preview.innerHTML = `
          <p class="sysforge-sm-preview-meta">${count} photo${count === 1 ? '' : 's'}${locked}</p>
          <button type="button" class="btn-secondary" id="sysforge-open-screw-map">
            Open screw map
          </button>
          ${publishBlock}`;
        preview.querySelector('#sysforge-open-screw-map')?.addEventListener('click', () => {
          deps.navigate('screw-map', { params: { projectId: state.projectId } });
        });
        preview.querySelector('#sysforge-sm-publish')?.addEventListener('click', () => {
          void publishScrewMap(container, deps);
        });
      }
      void syncCompanionContext(container, deps, state.projectId);
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

async function browseLibrary(container, deps, deviceModel) {
  const preview = container.querySelector('#sysforge-screw-map-preview');
  const picker = preview?.querySelector('#sysforge-sm-library-picker');
  const select = preview?.querySelector('#sysforge-sm-library-select');
  const status = preview?.querySelector('#sysforge-sm-library-status');
  const reuseBtn = preview?.querySelector('#sysforge-sm-reuse-library');
  if (!picker || !select) return;
  picker.hidden = false;
  if (status) status.textContent = 'Loading…';
  if (reuseBtn) reuseBtn.disabled = true;
  try {
    const q = deviceModel
      ? `?device_model=${encodeURIComponent(deviceModel)}`
      : '';
    const data = await deps.api(`/screw-map-library${q}`);
    const sets = data.sets || [];
    if (!sets.length) {
      select.innerHTML = '';
      if (status) {
        status.textContent = deviceModel
          ? `No library sets for “${deviceModel}”.`
          : 'No library sets yet.';
      }
      return;
    }
    select.innerHTML = sets
      .map((s) => {
        const tags = (s.tags || []).length ? ` · ${(s.tags || []).join(', ')}` : '';
        const label = `${s.title}${tags}`;
        return `<option value="${s.id}">${escapeHtml(label)}</option>`;
      })
      .join('');
    if (status) status.textContent = `${sets.length} set(s) available.`;
    if (reuseBtn) reuseBtn.disabled = !select.value;
  } catch (err) {
    if (status) status.textContent = err.message || String(err);
    void _toast(err.message || String(err), 'error');
  }
}

async function reuseLibrarySet(container, deps) {
  const state = container._sysforgeProject;
  const projectId = state?.projectId;
  const select = container.querySelector('#sysforge-sm-library-select');
  const setId = Number(select?.value || 0);
  if (!projectId || setId < 1) return;
  try {
    await deps.api(`/projects/${projectId}/screw-map/clone-from-library`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ set_id: setId }),
    });
    void _toast('Library set reused');
    deps.navigate('screw-map', { params: { projectId } });
  } catch (err) {
    void _toast(err.message || String(err), 'error');
  }
}

async function publishScrewMap(container, deps) {
  const state = container._sysforgeProject;
  const map = state?.detail?.screw_map;
  if (!map?.id) return;
  const titleEl = container.querySelector('#sysforge-sm-publish-title');
  const tagsEl = container.querySelector('#sysforge-sm-publish-tags');
  const notesEl = container.querySelector('#sysforge-sm-publish-notes');
  const title = (titleEl?.value || '').trim();
  if (!title) {
    void _toast('Title is required.', 'error');
    return;
  }
  try {
    await deps.api(`/screw-maps/${map.id}/publish`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        title,
        tags: tagsEl?.value || '',
        notes: (notesEl?.value || '').trim() || null,
      }),
    });
    void _toast('Published to library');
    await loadProject(container, deps, state.projectId);
  } catch (err) {
    void _toast(err.message || String(err), 'error');
  }
}

async function syncCompanionContext(container, deps, projectId) {
  if (!projectId) return;
  try {
    await deps.api('/companion/context', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ project_id: projectId, mode: 'screw_map' }),
    });
  } catch (_) {
    /* companion optional; settings may disable */
  }
}

async function startCompanionPair(container, deps) {
  const pairUi = container.querySelector('#sysforge-companion-pair-ui');
  const regen = container.querySelector('#sysforge-companion-regen');
  const qr = container.querySelector('#sysforge-companion-qr');
  const codeVal = container.querySelector('#sysforge-companion-code-val');
  const urlEl = container.querySelector('#sysforge-companion-url');
  const lanEl = container.querySelector('#sysforge-companion-lan');
  try {
    const data = await deps.api('/companion/pair/start', { method: 'POST' });
    if (pairUi) pairUi.hidden = false;
    if (regen) regen.hidden = false;
    if (codeVal) codeVal.textContent = data.pair_code || '';
    if (urlEl) urlEl.textContent = data.url || '';
    if (lanEl) {
      const ips = (data.lan_ips || []).join(', ');
      lanEl.textContent = ips
        ? `LAN IP(s): ${ips}. If scan fails, open the URL on the phone or try laptop hotspot.`
        : 'If scan fails, connect phone to the same Wi-Fi (or laptop hotspot) and open the URL.';
    }
    if (qr && data.qr_png_base64) {
      qr.src = `data:image/png;base64,${data.qr_png_base64}`;
      qr.hidden = false;
    } else if (qr) {
      qr.hidden = true;
    }
    const inbox = container.querySelector('#sysforge-companion-inbox');
    if (inbox) inbox.hidden = false;
    void _toast('Pairing ready — scan QR on phone');
  } catch (err) {
    void _toast(err.message || String(err), 'error');
  }
}

async function scanCompanionInbox(container, deps) {
  const list = container.querySelector('#sysforge-companion-inbox-list');
  const meta = container.querySelector('#sysforge-companion-inbox-meta');
  const importBtn = container.querySelector('#sysforge-companion-inbox-import');
  try {
    const data = await deps.api('/companion/inbox/scan', { method: 'POST' });
    if (meta) {
      meta.textContent = data.enabled
        ? `${data.inbox_path} · ${data.pending_count || 0} pending`
        : 'Inbox disabled — enable in Settings.';
    }
    const pending = data.pending || [];
    if (list) {
      list.innerHTML = pending.length
        ? pending
            .map(
              (p) =>
                `<li>${escapeHtml(p.file_name)} <span class="sysforge-sm-preview-meta">(${p.file_size || 0} B)</span></li>`
            )
            .join('')
        : `<li class="sysforge-classic-empty">No pending photos.</li>`;
    }
    if (importBtn) importBtn.hidden = pending.length === 0;
    if (data.auto_import_result?.imported_count) {
      void _toast(`Imported ${data.auto_import_result.imported_count} from inbox`);
      const state = container._sysforgeProject;
      if (state?.projectId) await loadProject(container, deps, state.projectId);
    }
  } catch (err) {
    void _toast(err.message || String(err), 'error');
  }
}

async function importCompanionInbox(container, deps) {
  try {
    const data = await deps.api('/companion/inbox/import', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ ids: [] }),
    });
    const n = data.imported_count || 0;
    void _toast(n ? `Imported ${n} photo(s)` : 'Nothing to import');
    const state = container._sysforgeProject;
    if (state?.projectId) await loadProject(container, deps, state.projectId);
    await scanCompanionInbox(container, deps);
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
