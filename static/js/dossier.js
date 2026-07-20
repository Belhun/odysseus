/**
 * People-dossier UI: browse, manual entry for core fields, archive cites, link correct.
 */
const API = () => window.location.origin;

let _open = false;
let _pane = null;
let _people = [];
let _selectedId = null;
let _dossier = null;
let _error = '';

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
      .dossier-pane .row { display:flex; gap:8px; align-items:center; margin-bottom:8px; flex-wrap:wrap; }
      .dossier-pane button, .dossier-pane select, .dossier-pane input, .dossier-pane textarea {
        font:inherit; color:inherit; background:var(--bg, #111); border:1px solid var(--border,#333); border-radius:6px;
      }
      .dossier-pane input, .dossier-pane textarea { padding:6px 8px; width:100%; box-sizing:border-box; }
      .dossier-pane textarea { min-height:56px; resize:vertical; }
      .dossier-pane button { padding:5px 10px; cursor:pointer; }
      .dossier-pane button.primary { border-color:var(--accent, #c44); }
      .dossier-pane .section { margin-top:12px; border-top:1px solid var(--border,#333); padding-top:8px; }
      .dossier-pane .section-head { display:flex; align-items:center; gap:8px; margin-bottom:6px; }
      .dossier-pane .section h3 { margin:0; font-size:.85rem; opacity:.85; text-transform:uppercase; letter-spacing:.04em; flex:1; }
      .dossier-pane .item { padding:6px 0; border-bottom:1px solid rgba(255,255,255,.06); font-size:.9rem; }
      .dossier-pane .muted { opacity:.7; font-size:.8rem; }
      .dossier-pane .error { color:#e06c75; font-size:.85rem; margin-bottom:8px; }
      .dossier-pane pre { white-space:pre-wrap; font-size:.8rem; background:rgba(0,0,0,.25); padding:8px; border-radius:8px; max-height:180px; overflow:auto; }
      .dossier-pane .close-btn { margin-left:auto; }
      .dossier-pane .mini-form { display:none; margin:8px 0; padding:8px; border:1px solid var(--border,#333); border-radius:8px; }
      .dossier-pane .mini-form.open { display:block; }
      .dossier-pane .mini-form label { display:block; font-size:.75rem; opacity:.8; margin:6px 0 2px; }
      .dossier-pane .mini-form .actions { display:flex; gap:8px; margin-top:8px; }
    </style>
    <div class="row">
      <h2>People dossier</h2>
      <button type="button" class="close-btn" id="dossier-close">Close</button>
    </div>
    <div id="dossier-error" class="error" hidden></div>
    <div class="row">
      <select id="dossier-people" style="flex:1"></select>
      <button type="button" id="dossier-refresh">Refresh</button>
      <button type="button" id="dossier-add-person">Add person</button>
    </div>
    <div id="dossier-add-person-form" class="mini-form">
      <label for="dossier-new-name">Name</label>
      <input id="dossier-new-name" type="text" placeholder="Display name">
      <label for="dossier-new-labels">Labels (comma-separated)</label>
      <input id="dossier-new-labels" type="text" placeholder="friend, client">
      <label for="dossier-new-notes">Notes</label>
      <textarea id="dossier-new-notes" placeholder="Optional notes"></textarea>
      <div class="actions">
        <button type="button" class="primary" id="dossier-save-person">Save person</button>
        <button type="button" id="dossier-cancel-person">Cancel</button>
      </div>
    </div>
    <div id="dossier-body" class="muted">Select a person.</div>
  `;
  document.body.appendChild(_pane);
  _pane.querySelector('#dossier-close').onclick = () => closePanel();
  _pane.querySelector('#dossier-refresh').onclick = () => refresh();
  _pane.querySelector('#dossier-people').onchange = (e) => selectPerson(e.target.value);
  _pane.querySelector('#dossier-add-person').onclick = () => _toggleForm('dossier-add-person-form');
  _pane.querySelector('#dossier-cancel-person').onclick = () => _toggleForm('dossier-add-person-form', false);
  _pane.querySelector('#dossier-save-person').onclick = () => savePerson();
  return _pane;
}

function _esc(s) {
  return String(s ?? '').replace(/[&<>"']/g, (c) => (
    { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]
  ));
}

function _setError(msg) {
  _error = msg || '';
  const el = _pane?.querySelector('#dossier-error');
  if (!el) return;
  if (_error) {
    el.textContent = _error;
    el.hidden = false;
  } else {
    el.textContent = '';
    el.hidden = true;
  }
}

function _toggleForm(id, open) {
  const form = _pane.querySelector(`#${id}`);
  if (!form) return;
  const next = open === undefined ? !form.classList.contains('open') : open;
  form.classList.toggle('open', next);
}

function _labelsFromInput(value) {
  return String(value || '')
    .split(',')
    .map((s) => s.trim().toLowerCase())
    .filter(Boolean);
}

function _miniForm(id, fieldsHtml, saveId) {
  return `<div id="${id}" class="mini-form">
    ${fieldsHtml}
    <div class="actions">
      <button type="button" class="primary" data-save="${saveId}">Save</button>
      <button type="button" data-cancel="${id}">Cancel</button>
    </div>
  </div>`;
}

function _sectionHead(title, formId) {
  return `<div class="section-head">
    <h3>${title}</h3>
    <button type="button" data-open-form="${formId}">Add</button>
  </div>`;
}

function _renderSections() {
  const body = _pane.querySelector('#dossier-body');
  if (!_dossier) {
    body.innerHTML = '<span class="muted">Select a person or add one.</span>';
    return;
  }
  const p = _dossier.person;
  const labels = (p.labels || []).join(', ') || 'none';
  const sections = [
    ['Identity', `
      ${_sectionHead('Identity', 'dossier-edit-person-form')}
      <div class="item"><strong>${_esc(p.display_name)}</strong>
        <div class="muted">Labels: ${_esc(labels)}</div>
        ${_esc(p.notes || '') ? `<div>${_esc(p.notes)}</div>` : ''}
      </div>
      ${_miniForm('dossier-edit-person-form', `
        <label>Name</label><input id="dossier-edit-name" type="text" value="${_esc(p.display_name)}">
        <label>Labels</label><input id="dossier-edit-labels" type="text" value="${_esc((p.labels || []).join(', '))}">
        <label>Notes</label><textarea id="dossier-edit-notes">${_esc(p.notes || '')}</textarea>
      `, 'edit-person')}
    `],
    ['Situations', `
      ${_sectionHead('Situations', 'dossier-add-situation-form')}
      ${(_dossier.situations || []).map((s) =>
        `<div class="item">${_esc(s.title)} <span class="muted">(${_esc(s.status)})</span>
         ${s.summary ? `<div>${_esc(s.summary)}</div>` : ''}</div>`).join('') || '<div class="muted">Empty</div>'}
      ${_miniForm('dossier-add-situation-form', `
        <label>Title</label><input id="dossier-sit-title" type="text">
        <label>Status</label><input id="dossier-sit-status" type="text" value="active">
        <label>Summary</label><textarea id="dossier-sit-summary"></textarea>
      `, 'add-situation')}
    `],
    ['Plans', `
      ${_sectionHead('Plans', 'dossier-add-plan-form')}
      ${(_dossier.plans || []).map((pl) =>
        `<div class="item"><strong>${_esc(pl.title)}</strong><div>${_esc(pl.summary)}</div>
         <div class="muted">${_esc(pl.how_we_got_here || '')}</div></div>`).join('') || '<div class="muted">Empty</div>'}
      ${_miniForm('dossier-add-plan-form', `
        <label>Title</label><input id="dossier-plan-title" type="text">
        <label>Summary</label><textarea id="dossier-plan-summary"></textarea>
        <label>How we got here</label><textarea id="dossier-plan-context"></textarea>
      `, 'add-plan')}
    `],
    ['Key facts', `
      ${_sectionHead('Key facts', 'dossier-add-fact-form')}
      ${(_dossier.facts || []).map((f) =>
        `<div class="item"><strong>${_esc(f.label)}</strong>: ${_esc(f.value)}</div>`).join('') || '<div class="muted">Empty</div>'}
      ${_miniForm('dossier-add-fact-form', `
        <label>Label</label><input id="dossier-fact-label" type="text">
        <label>Value</label><textarea id="dossier-fact-value"></textarea>
      `, 'add-fact')}
    `],
    ['Timeline', `
      ${_sectionHead('Timeline', 'dossier-add-timeline-form')}
      ${(_dossier.timeline || []).slice(0, 12).map((e) =>
        `<div class="item">${_esc(e.summary)} <span class="muted">${_esc(e.occurred_at || '')}</span></div>`).join('') || '<div class="muted">Empty</div>'}
      ${_miniForm('dossier-add-timeline-form', `
        <label>Note</label><textarea id="dossier-timeline-summary"></textarea>
      `, 'add-timeline')}
    `],
    ['Raw archive', `
      ${_sectionHead('Raw archive', 'dossier-add-archive-form')}
      ${(_dossier.archive || []).map((a) =>
        `<div class="item">
          <button type="button" data-archive-id="${_esc(a.id)}">Open cite</button>
          ${_esc(a.source_tool)} · ${_esc(a.locator || '')}
          <div class="muted">${_esc((a.body || '').slice(0, 120))}</div>
          <div class="row" style="margin-top:4px">
            <label class="muted">Correct person</label>
            <select data-link-archive="${_esc(a.id)}">${_peopleOptions(a.person_id)}</select>
          </div>
        </div>`).join('') || '<div class="muted">Empty</div>'}
      ${_miniForm('dossier-add-archive-form', `
        <label>Paste text</label><textarea id="dossier-archive-body" placeholder="Message, transcript, or plan text"></textarea>
        <label>Locator (optional)</label><input id="dossier-archive-locator" type="text" placeholder="line 12, chunk 3">
      `, 'add-archive')}
    `],
  ];
  body.innerHTML = sections.map(([title, html]) =>
    `<div class="section">${html}</div>`).join('');

  body.querySelectorAll('[data-open-form]').forEach((btn) => {
    btn.onclick = () => _toggleForm(btn.getAttribute('data-open-form'));
  });
  body.querySelectorAll('[data-cancel]').forEach((btn) => {
    btn.onclick = () => _toggleForm(btn.getAttribute('data-cancel'), false);
  });
  body.querySelectorAll('[data-save]').forEach((btn) => {
    btn.onclick = () => _saveSection(btn.getAttribute('data-save'));
  });
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

async function _saveSection(kind) {
  if (!_selectedId) return;
  _setError('');
  try {
    if (kind === 'edit-person') {
      await _fetch(`/api/dossier/people/${_selectedId}`, {
        method: 'PATCH',
        body: JSON.stringify({
          display_name: _pane.querySelector('#dossier-edit-name')?.value || '',
          labels: _labelsFromInput(_pane.querySelector('#dossier-edit-labels')?.value),
          notes: _pane.querySelector('#dossier-edit-notes')?.value || '',
        }),
      });
      _toggleForm('dossier-edit-person-form', false);
    } else if (kind === 'add-situation') {
      await _fetch(`/api/dossier/people/${_selectedId}/situations`, {
        method: 'POST',
        body: JSON.stringify({
          title: _pane.querySelector('#dossier-sit-title')?.value || '',
          status: _pane.querySelector('#dossier-sit-status')?.value || 'active',
          summary: _pane.querySelector('#dossier-sit-summary')?.value || '',
        }),
      });
      _toggleForm('dossier-add-situation-form', false);
    } else if (kind === 'add-plan') {
      await _fetch(`/api/dossier/people/${_selectedId}/plans`, {
        method: 'POST',
        body: JSON.stringify({
          title: _pane.querySelector('#dossier-plan-title')?.value || 'Plan',
          summary: _pane.querySelector('#dossier-plan-summary')?.value || '',
          how_we_got_here: _pane.querySelector('#dossier-plan-context')?.value || '',
        }),
      });
      _toggleForm('dossier-add-plan-form', false);
    } else if (kind === 'add-fact') {
      await _fetch(`/api/dossier/people/${_selectedId}/facts`, {
        method: 'POST',
        body: JSON.stringify({
          label: _pane.querySelector('#dossier-fact-label')?.value || '',
          value: _pane.querySelector('#dossier-fact-value')?.value || '',
        }),
      });
      _toggleForm('dossier-add-fact-form', false);
    } else if (kind === 'add-timeline') {
      await _fetch(`/api/dossier/people/${_selectedId}/timeline`, {
        method: 'POST',
        body: JSON.stringify({
          summary: _pane.querySelector('#dossier-timeline-summary')?.value || '',
        }),
      });
      _toggleForm('dossier-add-timeline-form', false);
    } else if (kind === 'add-archive') {
      await _fetch(`/api/dossier/people/${_selectedId}/archive`, {
        method: 'POST',
        body: JSON.stringify({
          body: _pane.querySelector('#dossier-archive-body')?.value || '',
          locator: _pane.querySelector('#dossier-archive-locator')?.value || '',
          source_tool: 'paste',
        }),
      });
      _toggleForm('dossier-add-archive-form', false);
    }
    await refresh();
    if (_selectedId) await selectPerson(_selectedId);
  } catch (e) {
    _setError(e.message || String(e));
  }
}

async function savePerson() {
  _setError('');
  try {
    const data = await _fetch('/api/dossier/people', {
      method: 'POST',
      body: JSON.stringify({
        display_name: _pane.querySelector('#dossier-new-name')?.value || '',
        labels: _labelsFromInput(_pane.querySelector('#dossier-new-labels')?.value),
        notes: _pane.querySelector('#dossier-new-notes')?.value || '',
      }),
    });
    _toggleForm('dossier-add-person-form', false);
    _pane.querySelector('#dossier-new-name').value = '';
    _pane.querySelector('#dossier-new-labels').value = '';
    _pane.querySelector('#dossier-new-notes').value = '';
    await refresh();
    if (data.person?.id) await selectPerson(data.person.id);
  } catch (e) {
    _setError(e.message || String(e));
  }
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
    _setError(e.message || String(e));
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
