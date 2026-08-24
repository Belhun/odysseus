/** Settings → Phone: PhonePi host/port copy + Google Messages QR pair/repair. */

const API = '/api/phonepi';

let pollTimer = null;
let bound = false;

function el(id) {
  return document.getElementById(id);
}

function setMsg(id, text, ok) {
  const node = el(id);
  if (!node) return;
  node.textContent = text || '';
  node.style.color = ok === false ? 'var(--red,#ff5555)' : 'inherit';
}

async function api(path, method = 'GET') {
  const res = await fetch(API + path, { method, credentials: 'same-origin' });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    throw new Error(data.error || data.detail || `HTTP ${res.status}`);
  }
  return data;
}

function showQr(wrapId, imgId, dataUri) {
  const wrap = el(wrapId);
  const img = el(imgId);
  if (!wrap || !img) return;
  if (dataUri) {
    img.src = dataUri;
    wrap.style.display = '';
  } else {
    wrap.style.display = 'none';
    img.removeAttribute('src');
  }
}

async function copyText(text) {
  if (!text) return;
  try {
    await navigator.clipboard.writeText(text);
  } catch {
    const box = document.createElement('textarea');
    box.value = text;
    document.body.appendChild(box);
    box.select();
    document.execCommand('copy');
    box.remove();
  }
}

function renderStatus(data) {
  const enabled = el('phonepi-enabled-pill');
  if (enabled) {
    enabled.textContent = data.phonepi_enabled ? 'Enabled' : 'Off (set PHONEPI_ENABLED=true)';
  }
  const host = data.connect && data.connect.host;
  const port = data.connect && data.connect.port;
  const hostInput = el('phonepi-host');
  const portInput = el('phonepi-port');
  const linkInput = el('phonepi-deeplink');
  if (hostInput) hostInput.value = host || '';
  if (portInput) portInput.value = port != null ? String(port) : '';
  if (linkInput) linkInput.value = data.connect_deeplink || '';
  showQr('phonepi-connect-qr-wrap', 'phonepi-connect-qr', data.connect_qr);
  const phoneappUrl = el('phoneapp-setup-url');
  if (phoneappUrl && data.phoneapp && data.phoneapp.url) {
    phoneappUrl.value = data.phoneapp.url;
  }

  const gm = data.gmessages || {};
  const pill = el('gmessages-status-pill');
  if (pill) {
    if (!gm.binary) pill.textContent = 'Bridge not built';
    else if (gm.pairing_live || gm.state === 'waiting') pill.textContent = 'Scan the QR';
    else if (gm.paired && gm.bridge_running) pill.textContent = 'Paired, syncing';
    else if (gm.paired) pill.textContent = 'Paired, sync stopped';
    else pill.textContent = 'Not paired';
  }
  const showPairQr = Boolean(gm.qr) && (gm.pairing_live || gm.state === 'waiting');
  showQr('gmessages-qr-wrap', 'gmessages-qr', showPairQr ? gm.qr : '');
  const cancel = el('gmessages-cancel-btn');
  if (cancel) cancel.style.display = showPairQr ? '' : 'none';
  if (gm.paired && gm.bridge_running) {
    setMsg('gmessages-msg', 'Google Messages is paired and the sync server is running.', true);
  } else if (gm.paired) {
    setMsg('gmessages-msg', 'Paired. Click Restart sync if chats are stale.', true);
  } else if (showPairQr) {
    setMsg('gmessages-msg', 'Keep this page open until the phone scans the code.', true);
  } else if (!gm.binary) {
    setMsg('gmessages-msg', 'Rebuild Odysseus so the Google Messages binary is in the image.', false);
  } else {
    setMsg('gmessages-msg', 'Click Show pairing QR, then scan it in Google Messages.', true);
  }
}

export async function refreshPhonePanel() {
  try {
    const data = await api('/status');
    renderStatus(data);
    const pairing = data.gmessages && (data.gmessages.pairing_live || data.gmessages.state === 'waiting');
    if (pairing) startPoll();
    else stopPoll();
  } catch (err) {
    setMsg('phonepi-msg', err.message || String(err), false);
    stopPoll();
  }
}

function startPoll() {
  if (pollTimer) return;
  pollTimer = setInterval(() => {
    refreshPhonePanel();
  }, 2000);
}

function stopPoll() {
  if (pollTimer) {
    clearInterval(pollTimer);
    pollTimer = null;
  }
}

export function initPhonePanel() {
  if (bound) return;
  bound = true;
  el('phonepi-copy-host')?.addEventListener('click', async () => {
    await copyText(el('phonepi-host')?.value || '');
    setMsg('phonepi-msg', 'Host copied.', true);
  });
  el('phonepi-copy-both')?.addEventListener('click', async () => {
    const host = el('phonepi-host')?.value || '';
    const port = el('phonepi-port')?.value || '';
    await copyText(`${host}\n${port}`);
    setMsg('phonepi-msg', 'Host and port copied.', true);
  });
  el('phonepi-copy-deeplink')?.addEventListener('click', async () => {
    await copyText(el('phonepi-deeplink')?.value || '');
    setMsg('phonepi-msg', 'PhonePi setup link copied.', true);
  });
  let lastPhoneappDeeplink = '';
  el('phoneapp-mint-qr-btn')?.addEventListener('click', async () => {
    setMsg('phoneapp-setup-msg', 'Minting PhoneApp token...');
    try {
      const res = await fetch(API + '/phoneapp-setup', {
        method: 'POST',
        credentials: 'same-origin',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name: 'PhoneApp QR' }),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(data.error || data.detail || `HTTP ${res.status}`);
      lastPhoneappDeeplink = data.deeplink || '';
      showQr('phoneapp-setup-qr-wrap', 'phoneapp-setup-qr', data.qr);
      const prefix = el('phoneapp-setup-prefix');
      if (prefix) prefix.textContent = data.token_prefix
        ? `Token prefix ${data.token_prefix}... Scan the QR in PhoneApp. Full token is in the QR, not shown here.`
        : '';
      const copyBtn = el('phoneapp-copy-deeplink');
      if (copyBtn) copyBtn.style.display = lastPhoneappDeeplink ? '' : 'none';
      setMsg('phoneapp-setup-msg', 'QR ready. Scan with the Pixel camera or PhoneApp.', true);
    } catch (err) {
      setMsg('phoneapp-setup-msg', err.message || String(err), false);
    }
  });
  el('phoneapp-copy-deeplink')?.addEventListener('click', async () => {
    await copyText(lastPhoneappDeeplink);
    setMsg('phoneapp-setup-msg', 'Setup link copied. It includes the token; treat it as a secret.', true);
  });
  el('phonepi-restart-btn')?.addEventListener('click', async () => {
    setMsg('phonepi-msg', 'Restarting PhonePi...');
    try {
      const data = await api('/restart', 'POST');
      setMsg('phonepi-msg', data.ok ? 'PhonePi restarted.' : (data.error || 'Restart failed.'), data.ok);
      await refreshPhonePanel();
    } catch (err) {
      setMsg('phonepi-msg', err.message || String(err), false);
    }
  });
  el('gmessages-pair-btn')?.addEventListener('click', async () => {
    setMsg('gmessages-msg', 'Starting pairing...');
    try {
      const data = await api('/gmessages/pair', 'POST');
      if (!data.ok) throw new Error(data.error || 'Pair failed');
      startPoll();
      await refreshPhonePanel();
    } catch (err) {
      setMsg('gmessages-msg', err.message || String(err), false);
    }
  });
  el('gmessages-repair-btn')?.addEventListener('click', async () => {
    if (!window.confirm('This drops the current Google Messages pairing and shows a new QR. Continue?')) return;
    setMsg('gmessages-msg', 'Resetting pairing...');
    try {
      const data = await api('/gmessages/repair', 'POST');
      if (!data.ok) throw new Error(data.error || 'Repair failed');
      startPoll();
      await refreshPhonePanel();
    } catch (err) {
      setMsg('gmessages-msg', err.message || String(err), false);
    }
  });
  el('gmessages-cancel-btn')?.addEventListener('click', async () => {
    try {
      await api('/gmessages/cancel', 'POST');
      stopPoll();
      await refreshPhonePanel();
    } catch (err) {
      setMsg('gmessages-msg', err.message || String(err), false);
    }
  });
  el('gmessages-serve-btn')?.addEventListener('click', async () => {
    setMsg('gmessages-msg', 'Starting sync...');
    try {
      const data = await api('/gmessages/serve', 'POST');
      setMsg('gmessages-msg', data.ok ? 'Sync server started.' : (data.error || 'Could not start sync.'), data.ok);
      await refreshPhonePanel();
    } catch (err) {
      setMsg('gmessages-msg', err.message || String(err), false);
    }
  });
}

export default { initPhonePanel, refreshPhonePanel };
