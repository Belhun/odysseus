/**
 * SysForge Business Management — optional plugin shell.
 * Full client/invoice/parts UI ports land incrementally; this opens the panel
 * only when the plugin is installed via Integrations.
 */

import { makeWindowDraggable } from '/static/js/windowDrag.js';

const API = `${window.location.origin}/api/sysforge`;
let _open = false;
let _modal = null;

function _el(id) {
  return document.getElementById(id);
}

async function _api(path, opts = {}) {
  const res = await fetch(`${API}${path}`, { credentials: 'same-origin', ...opts });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.detail || data.message || `Request failed (${res.status})`);
  return data;
}

function _getModal() {
  if (_modal) return _modal;
  _modal = document.createElement('div');
  _modal.id = 'sysforge-modal';
  _modal.className = 'modal';
  _modal.innerHTML = `
    <div class="modal-content" style="width:min(920px,94vw);height:min(640px,88vh);display:flex;flex-direction:column;">
      <div class="modal-header">
        <h2 style="margin:0;font-size:1.1rem;">Business Management</h2>
        <button type="button" class="modal-close" id="sysforge-close-btn" aria-label="Close">&times;</button>
      </div>
      <div id="sysforge-panel" style="flex:1;overflow:auto;padding:16px;">
        <p style="opacity:0.85;margin-top:0;">SysForge systems for repair-shop operations.</p>
        <p style="opacity:0.65;font-size:0.9rem;">Clients, invoices, parts, and projects load here as each module is ported. This plugin is optional — uninstall anytime from Settings → Integrations.</p>
        <div id="sysforge-status" style="margin-top:12px;font-size:0.85rem;opacity:0.7;">Loading status…</div>
      </div>
    </div>`;
  document.body.appendChild(_modal);
  const content = _modal.querySelector('.modal-content');
  const header = _modal.querySelector('.modal-header');
  if (content && header) {
    makeWindowDraggable(_modal, {
      content,
      header,
      skipSelector: 'button, input, select, textarea, label',
    });
  }
  _el('sysforge-close-btn')?.addEventListener('click', closeSysforge);
  _modal.addEventListener('click', (e) => { if (e.target === _modal) closeSysforge(); });
  return _modal;
}

async function _loadStatus() {
  const statusEl = _el('sysforge-status');
  try {
    const data = await _api('/status');
    if (statusEl) {
      statusEl.textContent = data.version
        ? `Installed v${data.version}`
        : 'Installed and active';
    }
  } catch (err) {
    if (statusEl) statusEl.textContent = err.message || String(err);
  }
}

export function isSysforgeOpen() {
  return _open;
}

export async function openSysforge() {
  _getModal();
  _open = true;
  _modal.style.display = 'flex';
  await _loadStatus();
  const Modals = await import('/static/js/modalManager.js');
  Modals.register('sysforge-modal', {
    railBtnId: 'rail-sysforge',
    sidebarBtnId: 'tool-sysforge-btn',
    closeFn: () => closeSysforge(),
    restoreFn: () => {},
  });
}

export function closeSysforge() {
  _open = false;
  if (_modal) _modal.style.display = 'none';
}

export default { openSysforge, closeSysforge, isSysforgeOpen };
