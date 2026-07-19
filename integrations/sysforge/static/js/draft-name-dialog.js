/**
 * Save Draft name dialog — title “Save Draft”, Cancel / Save.
 */

/**
 * @param {{
 *   prefill?: string,
 *   onSave: (name: string) => void | Promise<void>,
 *   onCancel?: () => void,
 * }} opts
 * @returns {() => void} close
 */
export function openDraftNameDialog(opts) {
  const existing = document.getElementById('sysforge-draft-name-dialog');
  existing?.remove();

  const overlay = document.createElement('div');
  overlay.id = 'sysforge-draft-name-dialog';
  overlay.className = 'sysforge-draft-dialog-overlay';
  overlay.innerHTML = `
    <div class="sysforge-draft-dialog" role="dialog" aria-labelledby="sysforge-draft-dialog-title">
      <h4 id="sysforge-draft-dialog-title">Save Draft</h4>
      <label class="sysforge-field">
        <span class="visually-hidden">Draft name</span>
        <input type="text" id="sysforge-draft-name-input" placeholder="Draft name…" autocomplete="off" />
      </label>
      <div class="sysforge-settings-actions">
        <button type="button" class="btn-secondary" id="sysforge-draft-name-cancel">Cancel</button>
        <button type="button" class="btn-primary" id="sysforge-draft-name-save">Save</button>
      </div>
    </div>`;

  document.body.appendChild(overlay);

  const input = overlay.querySelector('#sysforge-draft-name-input');
  if (input && opts.prefill) input.value = opts.prefill;
  input?.focus();
  input?.select?.();

  function close() {
    overlay.remove();
  }

  overlay.querySelector('#sysforge-draft-name-cancel')?.addEventListener('click', () => {
    opts.onCancel?.();
    close();
  });

  overlay.querySelector('#sysforge-draft-name-save')?.addEventListener('click', async () => {
    const name = (input?.value || '').trim();
    try {
      await opts.onSave(name);
      close();
    } catch (_) {
      /* keep dialog open; caller toasts */
    }
  });

  overlay.addEventListener('click', (e) => {
    if (e.target === overlay) {
      opts.onCancel?.();
      close();
    }
  });

  input?.addEventListener('keydown', (e) => {
    if (e.key === 'Enter') {
      e.preventDefault();
      overlay.querySelector('#sysforge-draft-name-save')?.click();
    }
    if (e.key === 'Escape') {
      opts.onCancel?.();
      close();
    }
  });

  return close;
}

/**
 * Default prefill: current name or Unknown Client / client + local date time (DRAFT-07).
 * @param {{ name?: string, clientName?: string, createdAt?: string }} draft
 */
export function defaultDraftNamePrefill(draft) {
  const name = (draft?.name || '').trim();
  if (name && name !== 'AUTOSAVE') return name;
  const d = draft?.createdAt ? new Date(draft.createdAt) : new Date();
  const mm = String(d.getMonth() + 1).padStart(2, '0');
  const dd = String(d.getDate()).padStart(2, '0');
  const yyyy = d.getFullYear();
  const hh = String(d.getHours()).padStart(2, '0');
  const mi = String(d.getMinutes()).padStart(2, '0');
  const client = (draft?.clientName || '').trim() || 'Unknown Client';
  return `${client} - ${mm}/${dd}/${yyyy} ${hh}:${mi}`;
}

export default { openDraftNameDialog, defaultDraftNamePrefill };
