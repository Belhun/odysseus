/**
 * ScrewMapView workspace — thumbnails, canvas, list/detail, autosave + undo.
 * Port of desktop ScrewMapView (single-click place; numbered dots; no Save button).
 */

import { createScrewMapCanvas } from '../screw-map-canvas.js';

const DEBOUNCE_MS = 2000;
const INTERVAL_MS = 3000;

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

function parseOptionalFloat(text) {
  const t = String(text ?? '').trim();
  if (!t) return null;
  const n = Number(t);
  return Number.isFinite(n) ? n : null;
}

function snapshotsEqual(a, b) {
  if (!a || !b) return false;
  return (
    a.label === b.label &&
    a.notes === b.notes &&
    a.warning_flag === b.warning_flag &&
    a.length_mm === b.length_mm &&
    a.shaft_diameter_mm === b.shaft_diameter_mm &&
    a.head_diameter_mm === b.head_diameter_mm
  );
}

/**
 * @param {HTMLElement} container
 * @param {{ api: Function, apiBase?: string, navigate: Function }} deps
 */
export function mountScrewMapView(container, deps) {
  if (container.dataset.mounted === '1') return;

  const apiBase = deps.apiBase || `${window.location.origin}/api/sysforge`;

  container.innerHTML = `
    <div class="sysforge-sm-view">
      <div class="sysforge-sm-thumbs" id="sysforge-sm-thumbs"></div>
      <div class="sysforge-sm-main">
        <div class="sysforge-sm-center">
          <div class="sysforge-sm-title-row">
            <h4 id="sysforge-sm-image-title">No photo selected</h4>
            <span id="sysforge-sm-locked" class="sysforge-sm-locked" hidden>Locked (read-only)</span>
          </div>
          <p class="sysforge-dashboard-lead">
            Click the image to place the next screw. Details autosave as you type.
            Ctrl+Z undoes edits for this screw. Escape shows the full screw list.
          </p>
          <div id="sysforge-sm-canvas-host" class="sysforge-sm-canvas-host"></div>
        </div>
        <aside class="sysforge-sm-side" aria-label="Screw details">
          <div id="sysforge-sm-list-panel">
            <h5>Screws</h5>
            <ul id="sysforge-sm-screw-list" class="sysforge-hub-list"></ul>
          </div>
          <div id="sysforge-sm-detail-panel" hidden>
            <h5>Screw <span id="sysforge-sm-detail-num"></span></h5>
            <label class="sysforge-field"><span>Label</span>
              <input type="text" id="sysforge-sm-label" /></label>
            <label class="sysforge-field"><span>Notes</span>
              <textarea id="sysforge-sm-notes" rows="3"></textarea></label>
            <label class="sysforge-field sysforge-sm-check">
              <input type="checkbox" id="sysforge-sm-warning" />
              <span>Warning flag</span>
            </label>
            <label class="sysforge-field"><span>Length (mm)</span>
              <input type="number" step="0.01" id="sysforge-sm-length" /></label>
            <label class="sysforge-field"><span>Shaft Ø (mm)</span>
              <input type="number" step="0.01" id="sysforge-sm-shaft" /></label>
            <label class="sysforge-field"><span>Head Ø (mm)</span>
              <input type="number" step="0.01" id="sysforge-sm-head" /></label>
            <p class="sysforge-sm-save-status" id="sysforge-sm-save-status"></p>
            <button type="button" class="btn-secondary" id="sysforge-sm-clear-sel">
              Show screw list
            </button>
          </div>
        </aside>
      </div>
      <div class="sysforge-sm-footer">
        <label class="btn-secondary sysforge-sm-add-photo">
          Add new photo
          <input type="file" id="sysforge-sm-file" accept="image/*" hidden />
        </label>
        <button type="button" class="btn-secondary" id="sysforge-sm-prev">Back</button>
        <button type="button" class="btn-secondary" id="sysforge-sm-next">Next</button>
        <button type="button" class="btn-secondary" id="sysforge-sm-lock">Lock map</button>
        <button type="button" class="btn-secondary" id="sysforge-sm-to-project">Back to project</button>
      </div>
      <p class="sysforge-settings-error" id="sysforge-sm-error" hidden></p>
    </div>`;

  /** @type {any} */
  const st = {
    projectId: null,
    map: null,
    screws: [],
    imageIndex: 0,
    selectedId: null,
    dirty: false,
    debounceTimer: null,
    intervalTimer: null,
    saving: false,
    undoStack: [],
    sessionBaseline: null,
    lastAnchor: null,
    applyingForm: false,
    canvas: null,
  };
  container._sysforgeScrewMap = st;
  container.dataset.mounted = '1';

  const el = (id) => container.querySelector(id);
  const formEls = () => ({
    label: /** @type {HTMLInputElement} */ (el('#sysforge-sm-label')),
    notes: /** @type {HTMLTextAreaElement} */ (el('#sysforge-sm-notes')),
    warning: /** @type {HTMLInputElement} */ (el('#sysforge-sm-warning')),
    length: /** @type {HTMLInputElement} */ (el('#sysforge-sm-length')),
    shaft: /** @type {HTMLInputElement} */ (el('#sysforge-sm-shaft')),
    head: /** @type {HTMLInputElement} */ (el('#sysforge-sm-head')),
  });

  function captureSnap() {
    const f = formEls();
    return {
      label: f.label?.value || '',
      notes: f.notes?.value || '',
      warning_flag: Boolean(f.warning?.checked),
      length_mm: f.length?.value || '',
      shaft_diameter_mm: f.shaft?.value || '',
      head_diameter_mm: f.head?.value || '',
    };
  }

  function setError(msg) {
    const node = el('#sysforge-sm-error');
    if (!node) return;
    node.hidden = !msg;
    node.textContent = msg || '';
  }

  function setSaveStatus(text) {
    const node = el('#sysforge-sm-save-status');
    if (node) node.textContent = text || '';
  }

  function isLocked() {
    return Boolean(st.map?.is_locked);
  }

  function currentImage() {
    return (st.map?.images || [])[st.imageIndex] || null;
  }

  function imageUrl(img) {
    return img ? `${apiBase}/screw-maps/images/${img.id}/file` : null;
  }

  function markersForCurrent() {
    const img = currentImage();
    if (!img) return [];
    return st.screws.filter((s) => s.screw_map_image_id === img.id);
  }

  function showList(show) {
    const list = el('#sysforge-sm-list-panel');
    const detail = el('#sysforge-sm-detail-panel');
    if (list) list.hidden = !show;
    if (detail) detail.hidden = show;
  }

  function fillDetail(screw) {
    st.applyingForm = true;
    const num = el('#sysforge-sm-detail-num');
    if (num) num.textContent = String(screw.screw_number);
    const f = formEls();
    if (f.label) f.label.value = screw.label || '';
    if (f.notes) f.notes.value = screw.notes || '';
    if (f.warning) f.warning.checked = Boolean(screw.warning_flag);
    if (f.length) f.length.value = screw.length_mm != null ? String(screw.length_mm) : '';
    if (f.shaft) {
      f.shaft.value = screw.shaft_diameter_mm != null ? String(screw.shaft_diameter_mm) : '';
    }
    if (f.head) {
      f.head.value = screw.head_diameter_mm != null ? String(screw.head_diameter_mm) : '';
    }
    const disabled = isLocked();
    Object.values(f).forEach((input) => {
      if (input) input.disabled = disabled;
    });
    st.applyingForm = false;
  }

  function resetUndo() {
    st.undoStack = [];
    const snap = captureSnap();
    st.sessionBaseline = snap;
    st.lastAnchor = snap;
    st.dirty = false;
    setSaveStatus(isLocked() ? 'Locked' : '');
  }

  function pushUndo(snap) {
    if (st.undoStack.length && snapshotsEqual(st.undoStack[st.undoStack.length - 1], snap)) {
      return;
    }
    st.undoStack.push(snap);
  }

  function applySnap(snap) {
    st.applyingForm = true;
    const f = formEls();
    if (f.label) f.label.value = snap.label;
    if (f.notes) f.notes.value = snap.notes;
    if (f.warning) f.warning.checked = snap.warning_flag;
    if (f.length) f.length.value = snap.length_mm;
    if (f.shaft) f.shaft.value = snap.shaft_diameter_mm;
    if (f.head) f.head.value = snap.head_diameter_mm;
    st.applyingForm = false;
  }

  function onDetailChanged() {
    if (st.applyingForm || isLocked() || st.selectedId == null) return;
    if (st.lastAnchor) pushUndo(st.lastAnchor);
    st.lastAnchor = captureSnap();
    st.dirty = !snapshotsEqual(st.lastAnchor, st.sessionBaseline);
    setSaveStatus(st.dirty ? 'Unsaved changes' : '');
    clearTimeout(st.debounceTimer);
    st.debounceTimer = setTimeout(() => {
      void flushAutosave();
    }, DEBOUNCE_MS);
  }

  async function flushAutosave() {
    clearTimeout(st.debounceTimer);
    st.debounceTimer = null;
    if (!st.dirty || st.saving || st.selectedId == null || isLocked()) return;
    st.saving = true;
    setSaveStatus('Saving…');
    const id = st.selectedId;
    const snap = captureSnap();
    try {
      const updated = await deps.api(`/screw-maps/screws/${id}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          label: snap.label || null,
          notes: snap.notes,
          warning_flag: snap.warning_flag,
          length_mm: parseOptionalFloat(snap.length_mm),
          shaft_diameter_mm: parseOptionalFloat(snap.shaft_diameter_mm),
          head_diameter_mm: parseOptionalFloat(snap.head_diameter_mm),
        }),
      });
      const idx = st.screws.findIndex((s) => s.id === id);
      if (idx >= 0) st.screws[idx] = updated;
      st.sessionBaseline = snap;
      st.lastAnchor = snap;
      st.dirty = false;
      setSaveStatus('Saved');
      renderList();
    } catch (err) {
      setSaveStatus('Save failed');
      setError(err.message || String(err));
      void _toast(err.message || String(err), 'error');
    } finally {
      st.saving = false;
    }
  }

  function tryUndo() {
    if (isLocked() || st.selectedId == null) return;
    if (st.undoStack.length) {
      const prev = st.undoStack.pop();
      applySnap(prev);
      st.lastAnchor = captureSnap();
      st.dirty = !snapshotsEqual(st.lastAnchor, st.sessionBaseline);
      setSaveStatus(st.dirty ? 'Unsaved changes' : '');
      clearTimeout(st.debounceTimer);
      st.debounceTimer = setTimeout(() => {
        void flushAutosave();
      }, DEBOUNCE_MS);
      return;
    }
    if (
      st.sessionBaseline &&
      st.lastAnchor &&
      !snapshotsEqual(st.lastAnchor, st.sessionBaseline)
    ) {
      applySnap(st.sessionBaseline);
      st.lastAnchor = st.sessionBaseline;
      st.dirty = false;
      setSaveStatus('');
    }
  }

  function renderThumbs() {
    const node = el('#sysforge-sm-thumbs');
    if (!node) return;
    const images = st.map?.images || [];
    if (!images.length) {
      node.innerHTML = `<p class="sysforge-classic-empty">No photos yet.</p>`;
      return;
    }
    node.innerHTML = images
      .map((img, i) => {
        const sel = i === st.imageIndex ? ' is-selected' : '';
        return `<button type="button" class="sysforge-sm-thumb${sel}" data-index="${i}">
          <img src="${escapeHtml(imageUrl(img))}" alt="" />
          <span>Photo ${i + 1}</span>
        </button>`;
      })
      .join('');
    node.querySelectorAll('.sysforge-sm-thumb').forEach((btn) => {
      btn.addEventListener('click', () => {
        void switchImage(Number(btn.getAttribute('data-index')));
      });
    });
  }

  function renderList() {
    const node = el('#sysforge-sm-screw-list');
    if (!node) return;
    node.innerHTML = st.screws.length
      ? st.screws
          .map(
            (s) =>
              `<li><button type="button" class="sysforge-sm-list-btn" data-id="${s.id}">
                #${s.screw_number}${s.warning_flag ? ' ⚠' : ''}
              </button></li>`
          )
          .join('')
      : `<li class="sysforge-classic-empty">No screws yet.</li>`;
    node.querySelectorAll('.sysforge-sm-list-btn').forEach((btn) => {
      btn.addEventListener('click', () => {
        void selectScrew(Number(btn.getAttribute('data-id')));
      });
    });
  }

  function updateChrome() {
    const img = currentImage();
    const title = el('#sysforge-sm-image-title');
    if (title) title.textContent = img ? `Photo ${st.imageIndex + 1}` : 'No photo selected';
    const locked = el('#sysforge-sm-locked');
    if (locked) locked.hidden = !isLocked();
    const file = /** @type {HTMLInputElement|null} */ (el('#sysforge-sm-file'));
    const lockBtn = /** @type {HTMLButtonElement|null} */ (el('#sysforge-sm-lock'));
    if (file) file.disabled = isLocked();
    if (lockBtn) lockBtn.disabled = isLocked();
  }

  function ensureCanvas() {
    const host = el('#sysforge-sm-canvas-host');
    if (!host || st.canvas) return;
    st.canvas = createScrewMapCanvas(host, {
      getImageUrl: () => imageUrl(currentImage()),
      getMarkers: () => markersForCurrent(),
      getSelectedId: () => st.selectedId,
      isReadOnly: () => isLocked(),
      onPlace: (x, y) => void placeScrew(x, y),
      onSelect: (id) => void selectScrew(id),
      onMove: (id, x, y) => void moveScrew(id, x, y),
    });
  }

  async function selectScrew(id) {
    if (st.selectedId != null && st.selectedId !== id) await flushAutosave();
    st.selectedId = id;
    if (id == null) {
      showList(true);
      st.canvas?.refresh();
      return;
    }
    const screw = st.screws.find((s) => s.id === id);
    if (!screw) {
      showList(true);
      return;
    }
    const images = st.map?.images || [];
    const idx = images.findIndex((img) => img.id === screw.screw_map_image_id);
    if (idx >= 0 && idx !== st.imageIndex) {
      st.imageIndex = idx;
      renderThumbs();
      updateChrome();
    }
    showList(false);
    fillDetail(screw);
    resetUndo();
    st.canvas?.refresh();
  }

  async function switchImage(index) {
    await flushAutosave();
    const images = st.map?.images || [];
    if (index < 0 || index >= images.length) return;
    st.imageIndex = index;
    st.selectedId = null;
    showList(true);
    renderThumbs();
    updateChrome();
    st.canvas?.refresh();
  }

  async function placeScrew(x, y) {
    if (isLocked()) return;
    const img = currentImage();
    if (!img) return;
    await flushAutosave();
    try {
      const screw = await deps.api(`/screw-maps/images/${img.id}/screws`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ position_x: x, position_y: y }),
      });
      st.screws.push(screw);
      st.screws.sort((a, b) => a.screw_number - b.screw_number);
      renderList();
      await selectScrew(screw.id);
    } catch (err) {
      setError(err.message || String(err));
      void _toast(err.message || String(err), 'error');
    }
  }

  async function moveScrew(id, x, y) {
    if (isLocked()) return;
    try {
      const updated = await deps.api(`/screw-maps/screws/${id}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ position_x: x, position_y: y }),
      });
      const idx = st.screws.findIndex((s) => s.id === id);
      if (idx >= 0) st.screws[idx] = { ...st.screws[idx], ...updated };
      st.canvas?.refresh();
    } catch (err) {
      setError(err.message || String(err));
      void _toast(err.message || String(err), 'error');
      await reloadScrews();
    }
  }

  async function reloadScrews() {
    if (!st.map) return;
    const data = await deps.api(`/screw-maps/${st.map.id}/screws`);
    st.screws = data.screws || [];
    renderList();
    st.canvas?.refresh();
  }

  async function loadWorkspace(projectId, imageId) {
    st.projectId = projectId;
    st.selectedId = null;
    st.dirty = false;
    setError('');
    let map;
    try {
      map = await deps.api(`/projects/${projectId}/screw-map`);
    } catch (_) {
      map = await deps.api(`/projects/${projectId}/screw-map`, { method: 'POST' });
    }
    st.map = map;
    if (imageId) {
      const idx = (map.images || []).findIndex((img) => String(img.id) === String(imageId));
      st.imageIndex = idx >= 0 ? idx : 0;
    } else {
      st.imageIndex = 0;
    }
    const data = await deps.api(`/screw-maps/${map.id}/screws`);
    st.screws = data.screws || [];
    showList(true);
    renderThumbs();
    renderList();
    updateChrome();
    ensureCanvas();
    st.canvas?.refresh();
  }

  // Wire controls once
  ['label', 'notes', 'warning', 'length', 'shaft', 'head'].forEach((key) => {
    const input = formEls()[key];
    if (!input) return;
    input.addEventListener(key === 'warning' ? 'change' : 'input', () => onDetailChanged());
  });

  el('#sysforge-sm-clear-sel')?.addEventListener('click', () => void selectScrew(null));
  el('#sysforge-sm-prev')?.addEventListener('click', () => void switchImage(st.imageIndex - 1));
  el('#sysforge-sm-next')?.addEventListener('click', () => void switchImage(st.imageIndex + 1));

  el('#sysforge-sm-file')?.addEventListener('change', async (e) => {
    const input = /** @type {HTMLInputElement} */ (e.target);
    const file = input.files?.[0];
    input.value = '';
    if (!file || !st.map || isLocked()) return;
    await flushAutosave();
    const fd = new FormData();
    fd.append('file', file);
    try {
      const img = await deps.api(`/screw-maps/${st.map.id}/images`, {
        method: 'POST',
        body: fd,
      });
      st.map.images = [...(st.map.images || []), img];
      st.imageIndex = st.map.images.length - 1;
      st.selectedId = null;
      showList(true);
      renderThumbs();
      updateChrome();
      st.canvas?.refresh();
      void _toast('Photo added');
    } catch (err) {
      setError(err.message || String(err));
      void _toast(err.message || String(err), 'error');
    }
  });

  el('#sysforge-sm-lock')?.addEventListener('click', async () => {
    if (!st.map || isLocked()) return;
    await flushAutosave();
    if (!window.confirm('Lock this screw map? It becomes read-only.')) return;
    try {
      st.map = await deps.api(`/screw-maps/${st.map.id}/lock`, { method: 'POST' });
      updateChrome();
      if (st.selectedId != null) {
        const screw = st.screws.find((s) => s.id === st.selectedId);
        if (screw) fillDetail(screw);
      }
      st.canvas?.refresh();
      void _toast('Screw map locked');
    } catch (err) {
      setError(err.message || String(err));
      void _toast(err.message || String(err), 'error');
    }
  });

  el('#sysforge-sm-to-project')?.addEventListener('click', async () => {
    await flushAutosave();
    deps.navigate('project', { params: { id: st.projectId } });
  });

  const keyHandler = (e) => {
    if (!container.isConnected) return;
    if (e.key === 'Escape') {
      void selectScrew(null);
      return;
    }
    if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'z') {
      if (st.selectedId != null) {
        e.preventDefault();
        tryUndo();
      }
    }
  };
  document.addEventListener('keydown', keyHandler);
  st._keyHandler = keyHandler;
  st.intervalTimer = setInterval(() => {
    if (st.dirty && !st.saving) void flushAutosave();
  }, INTERVAL_MS);

  st.loadWorkspace = loadWorkspace;
  st.flushAutosave = flushAutosave;
}

/**
 * @param {HTMLElement} container
 * @param {{ api: Function, apiBase?: string, navigate: Function }} deps
 * @param {Record<string, string>} params
 */
export async function activateScrewMapView(container, deps, params = {}) {
  const projectId = Number(params.projectId || params.id);
  if (!Number.isFinite(projectId) || projectId < 1) {
    const err = container.querySelector('#sysforge-sm-error');
    if (err) {
      err.hidden = false;
      err.textContent = 'Missing project id.';
    }
    return;
  }
  const st = container._sysforgeScrewMap;
  if (!st?.loadWorkspace) return;
  try {
    await st.loadWorkspace(projectId, params.imageId);
  } catch (err) {
    const node = container.querySelector('#sysforge-sm-error');
    if (node) {
      node.hidden = false;
      node.textContent = err.message || String(err);
    }
    void _toast(err.message || String(err), 'error');
  }
}

/**
 * @param {HTMLElement} container
 */
export async function deactivateScrewMapView(container) {
  const st = container?._sysforgeScrewMap;
  if (!st) return;
  if (typeof st.flushAutosave === 'function') {
    await st.flushAutosave();
  }
}
