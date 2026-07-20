/**
 * Business Settings — tax / currency / autosave + Backup & restore.
 *
 * Business backup is plugin-scoped (sysforge.db). Odysseus /api/export is separate.
 */

let _loaded = null;
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

function _setBusy(on) {
  _busy = Boolean(on);
  const root = document.querySelector('.sysforge-settings');
  if (!root) return;
  root.querySelectorAll('[data-backup-action]').forEach((el) => {
    el.disabled = _busy;
  });
}

/**
 * @param {HTMLElement} container
 * @param {{ api: (path: string, opts?: object) => Promise<object> }} deps
 */
export function mountSettings(container, deps) {
  if (container.dataset.mounted === '1') return;

  container.innerHTML = `
    <div class="sysforge-settings">
      <h3 class="sysforge-view-heading" tabindex="-1">Settings</h3>
      <p class="sysforge-dashboard-lead">Tax, currency, drafts, and Business backup for Business Management.</p>
      <form id="sysforge-settings-form" class="sysforge-settings-form">
        <label class="sysforge-field">
          <span>Tax rate (%)</span>
          <input type="number" id="sysforge-settings-tax" name="tax_rate_percent"
            min="0" max="100" step="0.01" placeholder="7.75" required />
          <span class="sysforge-field-hint">Stored as basis points on disk</span>
        </label>
        <label class="sysforge-field">
          <span>Currency</span>
          <select id="sysforge-settings-currency" name="currency">
            <option value="USD">USD</option>
            <option value="CAD">CAD</option>
            <option value="EUR">EUR</option>
            <option value="GBP">GBP</option>
          </select>
        </label>
        <label class="sysforge-field sysforge-field-check">
          <input type="checkbox" id="sysforge-settings-autosave" name="autosave_drafts" />
          <span>Automatically save invoice calculator drafts</span>
        </label>
        <label class="sysforge-field sysforge-field-check">
          <input type="checkbox" id="sysforge-settings-archived" name="include_archived_in_search" />
          <span>Include archived projects in search</span>
        </label>
        <div class="sysforge-settings-actions">
          <button type="submit" class="btn-primary" id="sysforge-settings-save">Save</button>
          <button type="button" class="btn-secondary" id="sysforge-settings-cancel">Cancel</button>
        </div>
        <p class="sysforge-settings-error" id="sysforge-settings-error" hidden></p>
      </form>

      <section class="sysforge-retention-panel" aria-labelledby="sysforge-retention-heading">
        <h4 id="sysforge-retention-heading" class="sysforge-backup-heading">Draft retention</h4>
        <p class="sysforge-field-hint">
          Off by default. Never runs when the plugin starts.
          Autosaves and pinned drafts are kept.
        </p>
        <label class="sysforge-field sysforge-field-check">
          <input type="checkbox" id="sysforge-retention-auto" />
          <span>Automatically delete old drafts</span>
        </label>
        <label class="sysforge-field">
          <span>Keep drafts for (months)</span>
          <input type="number" id="sysforge-retention-months" min="1" max="60" step="1" />
        </label>
        <label class="sysforge-field sysforge-field-check">
          <input type="checkbox" id="sysforge-retention-schedule" />
          <span>Enable weekly cleanup when automatic deletion is on</span>
        </label>
        <p class="sysforge-field-hint" id="sysforge-retention-preview">Loading preview…</p>
        <div class="sysforge-settings-actions">
          <button type="button" class="btn-secondary" id="sysforge-retention-save">Save retention</button>
          <button type="button" class="btn-secondary" id="sysforge-retention-cleanup" disabled>Clean up now…</button>
        </div>
        <p class="sysforge-settings-error" id="sysforge-retention-error" hidden></p>
      </section>

      <section class="sysforge-backup-panel" aria-labelledby="sysforge-backup-heading">
        <h4 id="sysforge-backup-heading" class="sysforge-backup-heading">Backup &amp; restore</h4>
        <p class="sysforge-field-hint">
          Business data only (clients, invoices, parts, plugin settings).
          Odysseus app export is separate (host Settings / docs/backup-restore.md).
        </p>
        <div class="sysforge-backup-actions">
          <button type="button" class="btn-primary" data-backup-action="create">Create Business backup</button>
          <label class="sysforge-field-check sysforge-backup-inline">
            <input type="checkbox" id="sysforge-backup-include-drafts" />
            <span>Include drafts</span>
          </label>
        </div>
        <div class="sysforge-backup-actions">
          <button type="button" class="btn-secondary" data-backup-action="export-json">Export JSON</button>
          <label class="btn-secondary sysforge-file-btn">
            Import JSON
            <input type="file" id="sysforge-backup-import-json" accept=".json,application/json" hidden />
          </label>
          <button type="button" class="btn-secondary" data-backup-action="rebuild">Rebuild search</button>
        </div>
        <p class="sysforge-backup-result" id="sysforge-backup-result" hidden></p>
        <h5 class="sysforge-backup-sub">Saved backups</h5>
        <ul class="sysforge-backup-list" id="sysforge-backup-list"></ul>
        <form id="sysforge-backup-schedule" class="sysforge-backup-schedule">
          <h5 class="sysforge-backup-sub">Schedule</h5>
          <label class="sysforge-field sysforge-field-check">
            <input type="checkbox" id="sysforge-backup-sched-enabled" />
            <span>Enable scheduled Business backups</span>
          </label>
          <label class="sysforge-field">
            <span>Interval (days)</span>
            <input type="number" id="sysforge-backup-sched-interval" min="1" max="365" step="1" />
          </label>
          <label class="sysforge-field">
            <span>Retention (days)</span>
            <input type="number" id="sysforge-backup-sched-retention" min="1" max="3650" step="1" />
          </label>
          <button type="submit" class="btn-secondary" data-backup-action="schedule-save">Save schedule</button>
        </form>
      </section>

      <section class="sysforge-companion-settings" aria-labelledby="sysforge-companion-heading">
        <h4 id="sysforge-companion-heading" class="sysforge-backup-heading">Phone companion (S5)</h4>
        <p class="sysforge-field-hint">
          LAN browser upload (Method A). Inbox folder is the Wi-Fi fallback (Method B).
          Optional public URL for Tailscale / HTTPS (Method C docs).
        </p>
        <label class="sysforge-field sysforge-field-check">
          <input type="checkbox" id="sysforge-companion-enabled" />
          <span>Enable phone companion</span>
        </label>
        <label class="sysforge-field">
          <span>Pair code lifetime (minutes)</span>
          <input type="number" id="sysforge-companion-pair-mins" min="1" max="120" step="1" />
        </label>
        <label class="sysforge-field">
          <span>Session lifetime (hours)</span>
          <input type="number" id="sysforge-companion-session-hrs" min="1" max="168" step="1" />
        </label>
        <label class="sysforge-field sysforge-field-check">
          <input type="checkbox" id="sysforge-companion-inbox-enabled" />
          <span>Enable inbox folder import</span>
        </label>
        <label class="sysforge-field">
          <span>Inbox folder path</span>
          <input type="text" id="sysforge-companion-inbox-path"
            placeholder="Default: plugin data / Inbox" />
        </label>
        <label class="sysforge-field sysforge-field-check">
          <input type="checkbox" id="sysforge-companion-inbox-auto" />
          <span>Auto-import inbox photos into active screw map</span>
        </label>
        <label class="sysforge-field">
          <span>Public base URL (optional)</span>
          <input type="url" id="sysforge-companion-public-url"
            placeholder="https://sysforge-pc.tailnet.ts.net:7000" />
          <span class="sysforge-field-hint">
            Tailscale MagicDNS or reverse-proxy HTTPS origin for QR links.
            Leave empty for LAN-only.
          </span>
        </label>
        <div class="sysforge-settings-actions">
          <button type="button" class="btn-secondary" id="sysforge-companion-save">
            Save companion settings
          </button>
          <button type="button" class="btn-secondary" id="sysforge-companion-revoke">
            Revoke all paired phones
          </button>
        </div>
        <ul id="sysforge-companion-sessions" class="sysforge-hub-list"></ul>
        <p class="sysforge-settings-error" id="sysforge-companion-error" hidden></p>
        <p class="sysforge-field-hint">
          Docs: <code>integrations/sysforge/docs/companion-remote-access.md</code>
        </p>
      </section>
    </div>`;

  const form = container.querySelector('#sysforge-settings-form');
  const taxInput = container.querySelector('#sysforge-settings-tax');
  const currencySelect = container.querySelector('#sysforge-settings-currency');
  const autosaveInput = container.querySelector('#sysforge-settings-autosave');
  const archivedInput = container.querySelector('#sysforge-settings-archived');
  const errorEl = container.querySelector('#sysforge-settings-error');
  const cancelBtn = container.querySelector('#sysforge-settings-cancel');
  const resultEl = container.querySelector('#sysforge-backup-result');
  const listEl = container.querySelector('#sysforge-backup-list');
  const includeDrafts = container.querySelector('#sysforge-backup-include-drafts');
  const importInput = container.querySelector('#sysforge-backup-import-json');
  const schedForm = container.querySelector('#sysforge-backup-schedule');
  const schedEnabled = container.querySelector('#sysforge-backup-sched-enabled');
  const schedInterval = container.querySelector('#sysforge-backup-sched-interval');
  const schedRetention = container.querySelector('#sysforge-backup-sched-retention');
  const retentionAuto = container.querySelector('#sysforge-retention-auto');
  const retentionMonths = container.querySelector('#sysforge-retention-months');
  const retentionSchedule = container.querySelector('#sysforge-retention-schedule');
  const retentionPreview = container.querySelector('#sysforge-retention-preview');
  const retentionSave = container.querySelector('#sysforge-retention-save');
  const retentionCleanup = container.querySelector('#sysforge-retention-cleanup');
  const retentionError = container.querySelector('#sysforge-retention-error');
  const companionEnabled = container.querySelector('#sysforge-companion-enabled');
  const companionPairMins = container.querySelector('#sysforge-companion-pair-mins');
  const companionSessionHrs = container.querySelector('#sysforge-companion-session-hrs');
  const companionInboxEnabled = container.querySelector('#sysforge-companion-inbox-enabled');
  const companionInboxPath = container.querySelector('#sysforge-companion-inbox-path');
  const companionInboxAuto = container.querySelector('#sysforge-companion-inbox-auto');
  const companionPublicUrl = container.querySelector('#sysforge-companion-public-url');
  const companionSave = container.querySelector('#sysforge-companion-save');
  const companionRevoke = container.querySelector('#sysforge-companion-revoke');
  const companionSessions = container.querySelector('#sysforge-companion-sessions');
  const companionError = container.querySelector('#sysforge-companion-error');

  let _retentionWarned = false;
  let _previewWouldDelete = 0;

  function showBackupResult(message, isError) {
    if (!resultEl) return;
    resultEl.hidden = false;
    resultEl.textContent = message;
    resultEl.classList.toggle('sysforge-backup-result-error', Boolean(isError));
  }

  function applyLoaded(data) {
    _loaded = data;
    if (taxInput) taxInput.value = String(data.tax_rate_percent ?? '');
    if (currencySelect) currencySelect.value = data.currency || 'USD';
    if (autosaveInput) autosaveInput.checked = Boolean(data.autosave_drafts);
    if (archivedInput) {
      archivedInput.checked = Boolean(
        data.include_archived_in_search ??
          data.projects?.include_archived_in_search
      );
    }
    const c = data.companion || {};
    if (companionEnabled) companionEnabled.checked = Boolean(c.enabled ?? true);
    if (companionPairMins) companionPairMins.value = String(c.pair_code_minutes ?? 15);
    if (companionSessionHrs) companionSessionHrs.value = String(c.session_hours ?? 48);
    if (companionInboxEnabled) companionInboxEnabled.checked = Boolean(c.inbox_enabled);
    if (companionInboxPath) companionInboxPath.value = c.inbox_path || '';
    if (companionInboxAuto) companionInboxAuto.checked = Boolean(c.inbox_auto_import);
    if (companionPublicUrl) companionPublicUrl.value = c.public_base_url || '';
    if (errorEl) {
      errorEl.hidden = true;
      errorEl.textContent = '';
    }
  }

  async function reloadCompanionSessions() {
    if (!companionSessions) return;
    try {
      const data = await deps.api('/companion/sessions');
      const sessions = data.sessions || [];
      if (!sessions.length) {
        companionSessions.innerHTML =
          '<li class="sysforge-classic-empty">No paired phones.</li>';
        return;
      }
      companionSessions.innerHTML = sessions
        .map((s) => {
          const label = s.device_label || `Session ${s.id}`;
          const state = s.active ? 'active' : s.revoked ? 'revoked' : 'expired';
          return `<li>${label} · ${state} · expires ${s.expires_at || ''}</li>`;
        })
        .join('');
    } catch (_) {
      companionSessions.innerHTML =
        '<li class="sysforge-classic-empty">Could not load sessions.</li>';
    }
  }

  function syncRetentionControls() {
    const on = Boolean(retentionAuto?.checked);
    if (retentionCleanup) {
      retentionCleanup.disabled = !on;
      retentionCleanup.title = on
        ? ''
        : 'Turn on automatic deletion first';
    }
  }

  function applyRetention(data) {
    if (retentionAuto) retentionAuto.checked = Boolean(data.auto_delete_old);
    if (retentionMonths) {
      retentionMonths.value = String(data.retention_months ?? 6);
    }
    if (retentionSchedule) {
      retentionSchedule.checked = Boolean(data.schedule_enabled);
    }
    if (data.scheduled_notice) {
      _toast(data.scheduled_notice, false);
    }
    syncRetentionControls();
  }

  async function reloadRetentionPreview() {
    try {
      const m = Number(retentionMonths?.value || 6);
      const qs = Number.isFinite(m) ? `?months=${encodeURIComponent(m)}` : '';
      const preview = await deps.api(`/drafts/retention/preview${qs}`);
      _previewWouldDelete = Number(preview.would_delete || 0);
      const months = preview.retention_months ?? m;
      if (retentionPreview) {
        retentionPreview.textContent =
          `${_previewWouldDelete} draft(s) older than ${months} months` +
          (preview.skipped_pinned
            ? ` · ${preview.skipped_pinned} pinned kept`
            : '');
      }
    } catch (err) {
      if (retentionPreview) {
        retentionPreview.textContent = err?.message || String(err);
      }
    }
  }

  async function reloadRetention() {
    const data = await deps.api('/drafts/retention');
    applyRetention(data);
    await reloadRetentionPreview();
  }

  function showRetentionError(msg) {
    if (!retentionError) return;
    if (!msg) {
      retentionError.hidden = true;
      retentionError.textContent = '';
      return;
    }
    retentionError.textContent = msg;
    retentionError.hidden = false;
  }

  async function reload() {
    const data = await deps.api('/settings');
    applyLoaded(data);
  }

  async function reloadSchedule() {
    const data = await deps.api('/backup/schedule');
    if (schedEnabled) schedEnabled.checked = Boolean(data.schedule_enabled);
    if (schedInterval) schedInterval.value = String(data.schedule_interval_days ?? 7);
    if (schedRetention) schedRetention.value = String(data.retention_days ?? 30);
    if (includeDrafts) includeDrafts.checked = Boolean(data.include_drafts);
  }

  async function reloadBackups() {
    const data = await deps.api('/backup/list');
    const backups = data.backups || [];
    if (!listEl) return;
    if (!backups.length) {
      listEl.innerHTML = '<li class="sysforge-backup-empty">No Business backups yet.</li>';
      return;
    }
    listEl.innerHTML = backups
      .map(
        (b) => `
      <li class="sysforge-backup-item" data-id="${b.id}">
        <div class="sysforge-backup-item-meta">
          <strong>${b.filename}</strong>
          <span>${b.created_at || ''} · ${Math.round((b.size_bytes || 0) / 1024)} KB</span>
        </div>
        <div class="sysforge-backup-item-actions">
          <a class="btn-secondary" href="/api/sysforge/backup/download/${encodeURIComponent(b.id)}"
             download>Download</a>
          <button type="button" class="btn-secondary" data-restore-id="${b.id}" data-backup-action="restore">
            Restore
          </button>
        </div>
      </li>`
      )
      .join('');
  }

  form?.addEventListener('submit', async (e) => {
    e.preventDefault();
    if (errorEl) {
      errorEl.hidden = true;
      errorEl.textContent = '';
    }
    const body = {
      tax_rate_percent: Number(taxInput?.value),
      currency: currencySelect?.value || 'USD',
      autosave_drafts: Boolean(autosaveInput?.checked),
      include_archived_in_search: Boolean(archivedInput?.checked),
    };
    try {
      const data = await deps.api('/settings', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      });
      applyLoaded(data);
      await _toast('Business settings saved', false);
    } catch (err) {
      const msg = err?.message || String(err);
      if (errorEl) {
        errorEl.textContent = msg;
        errorEl.hidden = false;
      }
      await _toast(msg, true);
    }
  });

  cancelBtn?.addEventListener('click', () => {
    if (_loaded) applyLoaded(_loaded);
    else reload().catch(() => {});
  });

  container.querySelector('[data-backup-action="create"]')?.addEventListener('click', async () => {
    if (_busy) return;
    _setBusy(true);
    try {
      const data = await deps.api('/backup/create', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ include_drafts: Boolean(includeDrafts?.checked) }),
      });
      showBackupResult(data.message || 'Business backup created', false);
      await _toast(data.message || 'Business backup created', false);
      await reloadBackups();
    } catch (err) {
      const msg = err?.message || String(err);
      showBackupResult(msg, true);
      await _toast(msg, true);
    } finally {
      _setBusy(false);
    }
  });

  container.querySelector('[data-backup-action="export-json"]')?.addEventListener('click', () => {
    window.location.href = '/api/sysforge/backup/export.json';
  });

  container.querySelector('[data-backup-action="rebuild"]')?.addEventListener('click', async () => {
    if (_busy) return;
    _setBusy(true);
    try {
      const data = await deps.api('/backup/search/rebuild', { method: 'POST' });
      showBackupResult(`Client search rebuilt (${data.rows ?? 0} rows)`, false);
      await _toast('Client search rebuilt', false);
    } catch (err) {
      const msg = err?.message || String(err);
      showBackupResult(msg, true);
      await _toast(msg, true);
    } finally {
      _setBusy(false);
    }
  });

  importInput?.addEventListener('change', async () => {
    const file = importInput.files?.[0];
    if (!file || _busy) return;
    if (String(file.name).toLowerCase().endsWith('.sql')) {
      showBackupResult(
        'SQL dump import is not supported. Use portable JSON or a Business .db / ZIP backup.',
        true
      );
      importInput.value = '';
      return;
    }
    _setBusy(true);
    try {
      const fd = new FormData();
      fd.append('file', file);
      fd.append('import_clients', 'true');
      fd.append('import_invoices', 'true');
      fd.append('import_invoice_items', 'true');
      fd.append('import_parts', 'true');
      fd.append('import_settings', 'true');
      fd.append('conflict', 'skip');
      const data = await deps.api('/backup/import.json', { method: 'POST', body: fd });
      const ok = data.ok !== false && data.success !== false;
      const msg =
        data.message ||
        `Imported clients ${data.clients_imported ?? 0} (skipped ${data.clients_skipped ?? 0}); ` +
          `search_rebuilt=${Boolean(data.search_rebuilt)}`;
      showBackupResult(msg, !ok);
      await _toast(msg, !ok);
    } catch (err) {
      const msg = err?.message || String(err);
      showBackupResult(msg, true);
      await _toast(msg, true);
    } finally {
      importInput.value = '';
      _setBusy(false);
    }
  });

  listEl?.addEventListener('click', async (e) => {
    const btn = e.target?.closest?.('[data-restore-id]');
    if (!btn || _busy) return;
    const id = btn.getAttribute('data-restore-id');
    if (!id) return;
    const confirmed = window.confirm(
      'Replaces Business database. A safety backup is created first. Continue?'
    );
    if (!confirmed) return;
    _setBusy(true);
    try {
      const data = await deps.api('/backup/restore', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ backup_id: id, restore_config: false }),
      });
      const ok = data.ok !== false;
      showBackupResult(data.message || 'Restored', !ok);
      await _toast(data.message || 'Restored', !ok);
      await reloadBackups();
    } catch (err) {
      const msg = err?.message || String(err);
      showBackupResult(msg, true);
      await _toast(msg, true);
    } finally {
      _setBusy(false);
    }
  });

  schedForm?.addEventListener('submit', async (e) => {
    e.preventDefault();
    if (_busy) return;
    _setBusy(true);
    try {
      const data = await deps.api('/backup/schedule', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          schedule_enabled: Boolean(schedEnabled?.checked),
          schedule_interval_days: Number(schedInterval?.value || 7),
          retention_days: Number(schedRetention?.value || 30),
          include_drafts: Boolean(includeDrafts?.checked),
        }),
      });
      showBackupResult('Backup schedule saved', false);
      await _toast('Backup schedule saved', false);
      if (schedEnabled) schedEnabled.checked = Boolean(data.schedule_enabled);
    } catch (err) {
      const msg = err?.message || String(err);
      showBackupResult(msg, true);
      await _toast(msg, true);
    } finally {
      _setBusy(false);
    }
  });

  retentionAuto?.addEventListener('change', () => {
    syncRetentionControls();
    if (retentionAuto.checked && !_retentionWarned) {
      _retentionWarned = true;
      window.alert(
        'Old unpinned drafts will be removable by cleanup / schedule. Pin drafts you want to keep.'
      );
    }
    reloadRetentionPreview().catch(() => {});
  });

  retentionMonths?.addEventListener('change', () => {
    reloadRetentionPreview().catch(() => {});
  });

  retentionSave?.addEventListener('click', async () => {
    showRetentionError('');
    try {
      const data = await deps.api('/drafts/retention', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          auto_delete_old: Boolean(retentionAuto?.checked),
          retention_months: Number(retentionMonths?.value || 6),
          schedule_enabled: Boolean(retentionSchedule?.checked),
        }),
      });
      applyRetention(data);
      await reloadRetentionPreview();
      await _toast('Draft retention saved', false);
    } catch (err) {
      const msg = err?.message || String(err);
      showRetentionError(msg);
      await _toast(msg, true);
    }
  });

  retentionCleanup?.addEventListener('click', async () => {
    if (!retentionAuto?.checked) {
      showRetentionError('Turn on automatic deletion first');
      return;
    }
    showRetentionError('');
    try {
      await reloadRetentionPreview();
      const n = _previewWouldDelete;
      const m = Number(retentionMonths?.value || 6);
      if (n > 0) {
        const ok = window.confirm(
          `Delete ${n} drafts older than ${m} months? Pinned drafts and autosaves are kept.`
        );
        if (!ok) return;
      }
      const data = await deps.api('/drafts/retention/cleanup', { method: 'POST' });
      if (data.reason === 'disabled') {
        await _toast('Turn on automatic deletion first', true);
        return;
      }
      if (data.deleted > 0 && data.notice) {
        await _toast(data.notice, false);
      } else {
        await _toast('Nothing to clean up', false);
      }
      await reloadRetention();
    } catch (err) {
      const msg = err?.message || String(err);
      showRetentionError(msg);
      await _toast(msg, true);
    }
  });

  companionSave?.addEventListener('click', async () => {
    if (companionError) {
      companionError.hidden = true;
      companionError.textContent = '';
    }
    const body = {
      companion: {
        enabled: Boolean(companionEnabled?.checked),
        pair_code_minutes: Number(companionPairMins?.value || 15),
        session_hours: Number(companionSessionHrs?.value || 48),
        inbox_enabled: Boolean(companionInboxEnabled?.checked),
        inbox_path: (companionInboxPath?.value || '').trim() || null,
        inbox_auto_import: Boolean(companionInboxAuto?.checked),
        public_base_url: (companionPublicUrl?.value || '').trim() || null,
      },
    };
    try {
      const data = await deps.api('/settings', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      });
      applyLoaded(data);
      await _toast('Companion settings saved', false);
    } catch (err) {
      const msg = err?.message || String(err);
      if (companionError) {
        companionError.textContent = msg;
        companionError.hidden = false;
      }
      await _toast(msg, true);
    }
  });

  companionRevoke?.addEventListener('click', async () => {
    const ok = window.confirm('Revoke all paired phones? They must pair again.');
    if (!ok) return;
    try {
      const data = await deps.api('/companion/sessions/revoke-all', { method: 'POST' });
      await _toast(`Revoked ${data.revoked || 0} session(s)`, false);
      await reloadCompanionSessions();
    } catch (err) {
      await _toast(err?.message || String(err), true);
    }
  });

  container.dataset.mounted = '1';
  container._sysforgeReloadSettings = async () => {
    await reload();
    await reloadSchedule();
    await reloadBackups();
    await reloadRetention();
    await reloadCompanionSessions();
  };
}

/**
 * @param {HTMLElement} container
 */
export async function activateSettings(container) {
  const heading = container.querySelector('.sysforge-view-heading');
  heading?.focus?.({ preventScroll: true });
  if (typeof container._sysforgeReloadSettings === 'function') {
    try {
      await container._sysforgeReloadSettings();
    } catch (err) {
      const errorEl = container.querySelector('#sysforge-settings-error');
      if (errorEl) {
        errorEl.textContent = err?.message || String(err);
        errorEl.hidden = false;
      }
    }
  }
}
