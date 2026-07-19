/**
 * Light people-dossier browse UI: list people, section slots, open archive cites, correct links.
 */
const API = () => window.location.origin;

let _open = false;
let _pane = null;
let _people = [];
let _selectedId = null;
let _dossier = null;

async function _fetch(path, opts = {}) {
  const res = await fetch(`${API()}${path}`, {
    credentials: 'same-origin',
    headers: { 'Content-Type': 'application/json', ...(opts.headers || {}) },
    ...opts,
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || res.statusText || 'request failed');
  }
  return res.json();
}

function _ensurePane() {
  if (_pane) return _pane;
  _pane = document.createElement('div');
  _pane.id = 'dossier-pane';
  _pane.className = 'dossier-pane';
  _pane.innerHTML = `
    <style>
      .dossier-pane { display:none; position:fixed; inset:auto 16px 16px auto; width:min(420px,94vw); max-height:80vh;
        overflow:auto; z-index:12000; background:var(--bg-elevated, #1a1a1a); color:var(--text, #eee);
        border:1px solid var(--border, #333); border-radius:12px; box-shadow:0 12px 40px rgba(0,0,0,.45); padding:12px 14px; }
      .dossier-pane.open { display:block; }
      .dossier-pane h2 { margin:0 0 8px; font-size:1.05rem; }
      .dossier-pane .row { display:flex; gap:8px; align-items:center; margin-bottom:8px; }
      .dossier-pane button, .dossier-pane select { font:inherit; }
      .dossier-pane .section { margin-top:12px; border-top:1px solid var(--border,#333); padding-top:8px; }
      .dossier-pane .section h3 { margin:0 0 6px; font-size:.85rem; opacity:.85; text-transform:uppercase; letter-spacing:.04em; }
      .dossier-pane .item { padding:6px 0; border-bottom:1px solid rgba(255,255,255,.06); font-size:.9rem; }
      .dossier-pane .muted { opacity:.7; font-size:.8rem; }
      .dossier-pane pre { white-space:pre-wrap; font-size:.8rem; background:rgba(0,0,0,.25); padding:8px; border-radius:8px; max-height:180px; overflow:auto; }
      .dossier-pane .close-btn { margin-left:auto; }
    </style>
    <div class="row">
      <h2>People dossier</h2>
      <button type="button" class="close-btn" id="dossier-close">Close</button>
    </div>
    <div class="row">
      <select id="dossier-people" style="flex:1"></select>
      <button type="button" id="dossier-refresh">Refresh</button>
    </div>
    <div id="dossier-body" class="muted">Select a person.</div>
  `;
  document.body.appendChild(_pane);
  _pane.querySelector('#dossier-close').onclick = () => closePanel();
  _pane.querySelector('#dossier-refresh').onclick = () => refresh();
  _pane.querySelector('#dossier-people').onchange = (e) => selectPerson(e.target.value);
  return _pane;
}

function _esc(s) {
  return String(s ?? '').replace(/[&<>"']/g, (c) => (
    { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]
  ));
}

function _renderSections() {
  const body = _pane.querySelector('#dossier-body');
  if (!_dossier) {
    body.innerHTML = '<span class="muted">Select a person.</span>';
    return;
  }
  const p = _dossier.person;
  const labels = (p.labels || []).join(', ') || 'none';
  const sections = [
    ['Identity', `<div class="item"><strong>${_esc(p.display_name)}</strong><div class="muted">Labels: ${_esc(labels)}</div></div>`],
    ['Situations', (_dossier.situations || []).map((s) =>
      `<div class="item">${_esc(s.title)} <span class="muted">(${_esc(s.status)})</span></div>`).join('') || '<div class="muted">Empty</div>'],
    ['Plans', (_dossier.plans || []).map((pl) =>
      `<div class="item"><strong>${_esc(pl.title)}</strong><div>${_esc(pl.summary)}</div>
       <div class="muted">${_esc(pl.how_we_got_here || '')}</div></div>`).join('') || '<div class="muted">Empty</div>'],
    ['Key facts', (_dossier.facts || []).map((f) =>
      `<div class="item"><strong>${_esc(f.label)}</strong>: ${_esc(f.value)}</div>`).join('') || '<div class="muted">Empty</div>'],
    ['Timeline', (_dossier.timeline || []).slice(0, 12).map((e) =>
      `<div class="item">${_esc(e.summary)} <span class="muted">${_esc(e.occurred_at || '')}</span></div>`).join('') || '<div class="muted">Empty</div>'],
    ['Raw archive', (_dossier.archive || []).map((a) =>
      `<div class="item">
        <button type="button" data-archive-id="${_esc(a.id)}">Open cite</button>
        ${_esc(a.source_tool)} · ${_esc(a.locator || '')}
        <div class="muted">${_esc((a.body || '').slice(0, 120))}</div>
        <div class="row" style="margin-top:4px">
          <label class="muted">Correct person</label>
          <select data-link-archive="${_esc(a.id)}">${_peopleOptions(a.person_id)}</select>
        </div>
      </div>`).join('') || '<div class="muted">Empty</div>'],
  ];
  body.innerHTML = sections.map(([title, html]) =>
    `<div class="section"><h3>${title}</h3>${html}</div>`).join('');

  body.querySelectorAll('[data-archive-id]').forEach((btn) => {
    btn.onclick = () => openArchive(btn.getAttribute('data-archive-id'));
  });
  body.querySelectorAll('[data-link-archive]').forEach((sel) => {
    sel.onchange = async () => {
      const id = sel.getAttribute('data-link-archive');
      await _fetch(`/api/dossier/archive/${id}/link`, {
        method: 'PATCH',
        body: JSON.stringify({ person_id: sel.value }),
      });
      await selectPerson(_selectedId);
    };
  });
}

function _peopleOptions(selected) {
  return _people.map((p) =>
    `<option value="${_esc(p.id)}" ${p.id === selected ? 'selected' : ''}>${_esc(p.display_name)}</option>`
  ).join('');
}

async function openArchive(id) {
  const data = await _fetch(`/api/dossier/archive/${id}`);
  const item = data.item;
  const body = _pane.querySelector('#dossier-body');
  const box = document.createElement('div');
  box.className = 'section';
  box.innerHTML = `<h3>Archive cite</h3>
    <div class="muted">${_esc(item.source_tool)} · ${_esc(item.locator || '')} · ${_esc(item.external_id || '')}</div>
    <pre>${_esc(item.body)}</pre>`;
  body.prepend(box);
}

async function refresh() {
  const data = await _fetch('/api/dossier/people');
  _people = data.people || [];
  const sel = _pane.querySelector('#dossier-people');
  sel.innerHTML = '<option value="">— people —</option>' + _people.map((p) =>
    `<option value="${_esc(p.id)}">${_esc(p.display_name)}</option>`).join('');
  if (_selectedId) {
    sel.value = _selectedId;
    await selectPerson(_selectedId);
  }
}

async function selectPerson(id) {
  _selectedId = id || null;
  if (!id) {
    _dossier = null;
    _renderSections();
    return;
  }
  _dossier = await _fetch(`/api/dossier/people/${id}`);
  _renderSections();
}

function openPanel() {
  _ensurePane();
  _pane.classList.add('open');
  _open = true;
  refresh().catch((e) => {
    _pane.querySelector('#dossier-body').textContent = e.message || String(e);
  });
}

function closePanel() {
  if (_pane) _pane.classList.remove('open');
  _open = false;
}

function togglePanel() {
  if (_open) closePanel();
  else openPanel();
}

export default { openPanel, closePanel, togglePanel };
