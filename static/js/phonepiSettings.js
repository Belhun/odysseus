/** Settings → Phone: PhonePi host/port copy + Google Messages pair/repair. */

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

async function api(path, method = 'GET', body) {
  const opts = { method, credentials: 'same-origin' };
  if (body !== undefined) {
    opts.headers = { 'Content-Type': 'application/json' };
    opts.body = JSON.stringify(body);
  }
  const res = await fetch(API + path, opts);
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

function showEmoji(emoji) {
  const wrap = el('gmessages-emoji-wrap');
  const node = el('gmessages-emoji');
  if (!wrap || !node) return;
  if (emoji) {
    node.textContent = emoji;
    wrap.style.display = '';
  } else {
    node.textContent = '';
    wrap.style.display = 'none';
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
  const pairingLive = Boolean(gm.pairing_live);
  const waitingQr = Boolean(gm.qr) && (pairingLive || gm.state === 'waiting') && gm.mode !== 'google';
  const waitingEmoji = (pairingLive || gm.state === 'emoji_wait' || gm.state === 'starting') && gm.mode === 'google';
  if (pill) {
    if (!gm.binary) pill.textContent = 'Bridge not built';
    else if (gm.state === 'error') pill.textContent = 'Pairing failed';
    else if (waitingEmoji && gm.emoji) pill.textContent = 'Tap emoji on phone';
    else if (waitingEmoji) pill.textContent = 'Pairing…';
    else if (waitingQr) pill.textContent = 'Scan the QR';
    else if (gm.paired && gm.bridge_running) pill.textContent = 'Paired, syncing';
    else if (gm.paired) pill.textContent = 'Paired, sync stopped';
    else pill.textContent = 'Not paired';
  }
  showQr('gmessages-qr-wrap', 'gmessages-qr', waitingQr ? gm.qr : '');
  showEmoji(waitingEmoji ? gm.emoji : '');
  const cancel = el('gmessages-cancel-btn');
  if (cancel) cancel.style.display = (waitingQr || waitingEmoji) ? '' : 'none';
  const openWrap = el('gmessages-open-wrap');
  const openLink = el('gmessages-open-link');
  if (openWrap) {
    const inboxUrl = gm.messages_ui_url || '/gmessages/';
    if (openLink) openLink.href = inboxUrl;
    openWrap.style.display = (gm.paired && gm.bridge_running) ? 'flex' : 'none';
  }
  if (gm.paired && gm.bridge_running) {
    setMsg('gmessages-msg', 'Google Messages is paired and the sync server is running.', true);
  } else if (gm.paired) {
    setMsg('gmessages-msg', 'Paired. Click Restart sync if chats are stale.', true);
  } else if (gm.state === 'error' && gm.error) {
    setMsg('gmessages-msg', gm.error, false);
  } else if (waitingEmoji && gm.emoji) {
    setMsg('gmessages-msg', 'On your phone: Google Messages → Device pairing → tap the matching emoji.', true);
  } else if (waitingEmoji) {
    setMsg('gmessages-msg', 'Pairing with Google… keep this page open.', true);
  } else if (waitingQr) {
    setMsg('gmessages-msg', 'Keep this page open until the phone scans the code.', true);
  } else if (!gm.binary) {
    setMsg('gmessages-msg', 'Rebuild Odysseus so the Google Messages binary is in the image.', false);
  } else {
    setMsg('gmessages-msg', 'Paste a fresh cURL from Firefox, then click Pair with Google account.', true);
  }
}

export async function refreshPhonePanel() {
  try {
    const data = await api('/status');
    renderStatus(data);
    const gm = data.gmessages || {};
    const pairing = gm.pairing_live || gm.state === 'waiting' || gm.state === 'emoji_wait' || gm.state === 'starting';
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
  el('gmessages-copy-login-link-btn')?.addEventListener('click', async () => {
    const link = el('gmessages-config-login-link')?.href || 'https://accounts.google.com/AccountChooser?continue=https://messages.google.com/web/config';
    await copyText(link);
    setMsg('gmessages-msg', 'Google login link copied. Open it in a Firefox private window.', true);
  });
  el('gmessages-pair-google-btn')?.addEventListener('click', async () => {
    const cookiesInput = el('gmessages-cookies-input')?.value?.trim() || '';
    if (!cookiesInput) {
      setMsg('gmessages-msg', 'Paste a cURL or JSON cookies first.', false);
      return;
    }
    setMsg('gmessages-msg', 'Starting Google account pairing…');
    try {
      const data = await api('/gmessages/pair-google', 'POST', { input: cookiesInput });
      if (!data.ok) throw new Error(data.error || 'Pair failed');
      const cookiesBox = el('gmessages-cookies-input');
      if (cookiesBox) cookiesBox.value = '';
      startPoll();
      await refreshPhonePanel();
    } catch (err) {
      setMsg('gmessages-msg', err.message || String(err), false);
    }
  });
  el('gmessages-pair-btn')?.addEventListener('click', async () => {
    setMsg('gmessages-msg', 'Starting legacy QR pairing…');
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
    if (!window.confirm('This drops the current Google Messages session. You will need to paste fresh cookies and pair again. Continue?')) return;
    setMsg('gmessages-msg', 'Resetting pairing…');
    try {
      const data = await api('/gmessages/repair', 'POST');
      if (!data.ok) throw new Error(data.error || 'Reset failed');
      showEmoji('');
      showQr('gmessages-qr-wrap', 'gmessages-qr', '');
      stopPoll();
      await refreshPhonePanel();
      setMsg('gmessages-msg', 'Session cleared. Paste fresh cURL and pair again.', true);
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
  el('gmessages-copy-open-link')?.addEventListener('click', async () => {
    const url = el('gmessages-open-link')?.href || '/gmessages/';
    await copyText(url);
    setMsg('gmessages-msg', 'Messages inbox link copied. Open it while signed in to Odysseus.', true);
  });
}

export default { initPhonePanel, refreshPhonePanel };
