/**
 * Shared create-from-invoice wizard (header, Classic preview, calculator).
 * Blank Device ID refused; all entry points call the same POST.
 */

async function _toast(message, kind) {
  try {
    const ui = await import('/static/js/ui.js');
    if (typeof ui.showToast === 'function') {
      ui.showToast(message, kind === 'error' ? 'error' : kind === 'info' ? 'info' : 'success');
      return;
    }
  } catch (_) {
    /* fall through */
  }
  console.log(message);
}

function _escape(s) {
  return String(s ?? '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

/**
 * @param {{
 *   api: (path: string, opts?: object) => Promise<object>,
 *   navigate: (routeId: string, opts?: object) => void,
 *   invoiceId?: number|null,
 *   invoiceDeviceId?: number|null,
 * }} opts
 * @returns {Promise<number|null>} project id or null if cancelled
 */
export async function startCreateProjectFromInvoice(opts) {
  const api = opts.api;
  let invoiceId = opts.invoiceId != null ? Number(opts.invoiceId) : null;
  let deviceId = opts.invoiceDeviceId != null ? Number(opts.invoiceDeviceId) : null;

  if (!invoiceId) {
    const picked = await _pickInvoice(api);
    if (!picked) return null;
    invoiceId = picked;
  }

  let preflight;
  try {
    preflight = await api(`/projects/from-invoice/preflight?invoice_id=${invoiceId}`);
  } catch (err) {
    await _toast(err.message || String(err), 'error');
    return null;
  }

  if (preflight.accept_first) {
    await _toast('Accept estimate first', 'error');
    return null;
  }
  if (preflight.no_devices) {
    await _toast('Add a device on the estimate before creating a project', 'error');
    return null;
  }
  if (preflight.all_have_projects) {
    await _toast('Every device on this invoice already has a project', 'error');
    return null;
  }

  const eligible = preflight.eligible || [];
  if (!deviceId) {
    if (eligible.length === 1) {
      deviceId = eligible[0].id;
    } else {
      const pickedDevice = await _pickDevice(eligible);
      if (!pickedDevice) return null;
      deviceId = pickedDevice;
    }
  } else {
    const match = eligible.find((d) => Number(d.id) === Number(deviceId));
    if (!match) {
      await _toast('That device already has a project or is missing', 'error');
      return null;
    }
  }

  const target = (preflight.devices || []).find((d) => Number(d.id) === Number(deviceId));
  const inv = await api(`/invoices/${invoiceId}`);
  const items = inv.items || [];

  let suggested = `DEV-${new Date().toISOString().slice(2, 10).replace(/-/g, '')}-XXXXXX`;
  try {
    const sug = await api('/projects/suggest-device-id');
    if (sug.device_id) suggested = sug.device_id;
  } catch (_) {
    /* keep fallback */
  }

  const setup = await _setupDialog({
    label: target?.label || 'Device',
    suggestedDeviceId: suggested,
    items,
  });
  if (!setup) return null;

  try {
    const result = await api('/projects/from-invoice', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        invoice_id: invoiceId,
        invoice_device_id: deviceId,
        device_id: setup.deviceId,
        category: setup.category,
        invoice_item_ids: setup.itemIds,
      }),
    });
    const projectId = result.project_id;
    await _toast(`Project ${result.device_id} created`, 'success');
    opts.navigate('project', { params: { id: projectId } });
    return projectId;
  } catch (err) {
    await _toast(err.message || String(err), 'error');
    return null;
  }
}

async function _pickInvoice(api) {
  // Recent-ish: hub estimates + accepted missing invoice ids from active list is heavy;
  // use client invoices via a simple prompt of recent estimates from hub.
  let hub;
  try {
    hub = await api('/projects/hub');
  } catch (err) {
    await _toast(err.message || String(err), 'error');
    return null;
  }
  const rows = [
    ...(hub.estimates_not_accepted || []).map((r) => ({
      id: r.invoice_id,
      label: r.invoice_name || r.client_info || `Invoice #${r.invoice_id}`,
      hint: 'Estimate (not accepted)',
    })),
    ...(hub.accepted_missing || []).map((r) => ({
      id: r.invoice_id,
      label: `${r.device_label} — invoice #${r.invoice_id}`,
      hint: 'Accepted — missing project',
    })),
  ];
  // Dedupe by invoice id
  const seen = new Set();
  const unique = [];
  for (const r of rows) {
    if (seen.has(r.id)) continue;
    seen.add(r.id);
    unique.push(r);
  }
  if (!unique.length) {
    await _toast('No invoices available for create-from-invoice', 'info');
    return null;
  }
  return _listPickDialog('Select invoice', unique);
}

function _pickDevice(eligible) {
  const rows = eligible.map((d) => ({
    id: d.id,
    label: d.label || `Device #${d.id}`,
    hint: '',
  }));
  return _listPickDialog('Select device', rows);
}

function _listPickDialog(title, rows) {
  return new Promise((resolve) => {
    const overlay = document.createElement('div');
    overlay.className = 'sysforge-wizard-overlay';
    overlay.innerHTML = `
      <div class="sysforge-wizard" role="dialog" aria-modal="true">
        <h3>${_escape(title)}</h3>
        <ul class="sysforge-wizard-list">
          ${rows
            .map(
              (r) => `<li>
              <button type="button" data-id="${r.id}">
                <span>${_escape(r.label)}</span>
                ${r.hint ? `<small>${_escape(r.hint)}</small>` : ''}
              </button>
            </li>`
            )
            .join('')}
        </ul>
        <div class="sysforge-wizard-actions">
          <button type="button" class="btn-secondary" data-cancel>Cancel</button>
        </div>
      </div>`;
    document.body.appendChild(overlay);
    const close = (val) => {
      overlay.remove();
      resolve(val);
    };
    overlay.querySelector('[data-cancel]')?.addEventListener('click', () => close(null));
    overlay.querySelectorAll('[data-id]').forEach((btn) => {
      btn.addEventListener('click', () => close(Number(btn.getAttribute('data-id'))));
    });
  });
}

function _setupDialog({ label, suggestedDeviceId, items }) {
  return new Promise((resolve) => {
    const overlay = document.createElement('div');
    overlay.className = 'sysforge-wizard-overlay';
    const itemRows = (items || [])
      .map(
        (it, idx) => `<label class="sysforge-wizard-check">
          <input type="checkbox" data-item-id="${it.id}" checked />
          <span>${_escape(it.part_name || `Item ${idx + 1}`)}</span>
        </label>`
      )
      .join('');
    overlay.innerHTML = `
      <div class="sysforge-wizard" role="dialog" aria-modal="true">
        <h3>Create project</h3>
        <p class="sysforge-dashboard-lead">${_escape(label)}</p>
        <label class="sysforge-field">
          <span>Device ID</span>
          <input type="text" id="sysforge-wizard-device-id" value="${_escape(suggestedDeviceId)}" />
        </label>
        <label class="sysforge-field">
          <span>Category</span>
          <select id="sysforge-wizard-category">
            <option value="HW" selected>HW</option>
            <option value="SW">SW</option>
            <option value="Other">Other</option>
          </select>
        </label>
        <fieldset class="sysforge-wizard-parts">
          <legend>Parts to copy</legend>
          ${itemRows || '<p>No line items.</p>'}
        </fieldset>
        <p class="sysforge-settings-error" id="sysforge-wizard-err" hidden></p>
        <div class="sysforge-wizard-actions">
          <button type="button" class="btn-secondary" data-cancel>Cancel</button>
          <button type="button" class="btn-primary" data-create>Create</button>
        </div>
      </div>`;
    document.body.appendChild(overlay);
    const errEl = overlay.querySelector('#sysforge-wizard-err');
    const close = (val) => {
      overlay.remove();
      resolve(val);
    };
    overlay.querySelector('[data-cancel]')?.addEventListener('click', () => close(null));
    overlay.querySelector('[data-create]')?.addEventListener('click', () => {
      const deviceId = String(
        overlay.querySelector('#sysforge-wizard-device-id')?.value || ''
      ).trim();
      if (!deviceId) {
        if (errEl) {
          errEl.hidden = false;
          errEl.textContent = 'Device ID is required';
        }
        return; // refuse blank — dialog stays open
      }
      const category =
        overlay.querySelector('#sysforge-wizard-category')?.value || 'HW';
      const itemIds = Array.from(
        overlay.querySelectorAll('[data-item-id]:checked')
      ).map((el) => Number(el.getAttribute('data-item-id')));
      close({ deviceId, category, itemIds });
    });
  });
}

export default { startCreateProjectFromInvoice };
