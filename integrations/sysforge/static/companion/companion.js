/**
 * SysForge S5 phone companion — pair, context sync, camera upload.
 */
(function () {
  const STORAGE_KEY = 'sysforge_companion_session';
  const API = '/api/sysforge/companion/phone';

  const params = new URLSearchParams(window.location.search);
  const pairToken = params.get('t') || sessionStorage.getItem('sf_c_pair_token') || '';
  if (params.get('t')) {
    sessionStorage.setItem('sf_c_pair_token', params.get('t'));
  }

  const els = {
    pair: document.getElementById('sf-c-pair'),
    main: document.getElementById('sf-c-main'),
    needToken: document.getElementById('sf-c-need-token'),
    code: document.getElementById('sf-c-code'),
    pairBtn: document.getElementById('sf-c-pair-btn'),
    pairError: document.getElementById('sf-c-pair-error'),
    context: document.getElementById('sf-c-context'),
    file: document.getElementById('sf-c-file'),
    refresh: document.getElementById('sf-c-refresh'),
    status: document.getElementById('sf-c-status'),
    uploadError: document.getElementById('sf-c-upload-error'),
    unpair: document.getElementById('sf-c-unpair'),
  };

  let sessionToken = localStorage.getItem(STORAGE_KEY) || '';
  let eventSource = null;
  let pollTimer = null;

  function showError(el, msg) {
    if (!el) return;
    if (!msg) {
      el.hidden = true;
      el.textContent = '';
      return;
    }
    el.hidden = false;
    el.textContent = msg;
  }

  function showStatus(msg) {
    if (!els.status) return;
    if (!msg) {
      els.status.hidden = true;
      els.status.textContent = '';
      return;
    }
    els.status.hidden = false;
    els.status.textContent = msg;
  }

  async function api(path, opts) {
    const headers = Object.assign({}, (opts && opts.headers) || {});
    if (sessionToken) {
      headers.Authorization = 'Bearer ' + sessionToken;
      headers['X-Companion-Token'] = sessionToken;
    }
    const res = await fetch(API + path, Object.assign({}, opts, { headers }));
    let body = null;
    const ct = res.headers.get('content-type') || '';
    if (ct.includes('application/json')) {
      body = await res.json();
    } else {
      body = { detail: await res.text() };
    }
    if (!res.ok) {
      const detail = body && (body.detail || body.error || body.message);
      const err = new Error(typeof detail === 'string' ? detail : res.statusText);
      err.status = res.status;
      throw err;
    }
    return body;
  }

  function renderContext(ctx) {
    if (!els.context || !ctx) return;
    const title = ctx.project_title || 'No active project';
    const model = ctx.device_model ? ' · ' + ctx.device_model : '';
    const next = ctx.next_image_number || 1;
    const locked = ctx.is_locked ? '<p class="sf-c-warn">Map is locked — uploads blocked.</p>' : '';
    const can = ctx.can_upload
      ? `<p class="sf-c-muted">Screw map · Image ${next} next</p>`
      : `<p class="sf-c-warn">${escapeHtml(ctx.message || 'Cannot upload')}</p>`;
    els.context.innerHTML =
      `<strong>${escapeHtml(title)}</strong>` +
      `<p class="sf-c-muted">${escapeHtml((ctx.mode || 'screw_map') + model)}</p>` +
      can +
      locked;
  }

  function escapeHtml(s) {
    return String(s ?? '')
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');
  }

  function showPair() {
    if (els.pair) els.pair.hidden = false;
    if (els.main) els.main.hidden = true;
    if (els.needToken) els.needToken.hidden = !!pairToken;
    stopSync();
  }

  function showMain() {
    if (els.pair) els.pair.hidden = true;
    if (els.main) els.main.hidden = false;
    if (els.needToken) els.needToken.hidden = true;
    startSync();
  }

  async function refreshContext() {
    const data = await api('/context');
    renderContext(data.context);
    return data.context;
  }

  function startSync() {
    stopSync();
    // Prefer SSE; fall back to poll every 3s
    try {
      const url =
        API +
        '/events?last_revision=0';
      // EventSource cannot set Authorization headers — use query token workaround
      // via cookie-less fetch poll as primary when EventSource auth fails.
      eventSource = null;
    } catch (_) {
      eventSource = null;
    }
    void refreshContext().catch((err) => {
      if (err.status === 401) {
        clearSession();
        showPair();
      }
    });
    pollTimer = setInterval(() => {
      void refreshContext().catch((err) => {
        if (err.status === 401) {
          clearSession();
          showPair();
        }
      });
    }, 3000);

    // SSE with token in query is avoided (token leakage in logs).
    // Use fetch stream for events when supported.
    void startFetchSSE();
  }

  async function startFetchSSE() {
    if (!sessionToken || !window.fetch) return;
    try {
      const res = await fetch(API + '/events?last_revision=0', {
        headers: {
          Authorization: 'Bearer ' + sessionToken,
          'X-Companion-Token': sessionToken,
          Accept: 'text/event-stream',
        },
      });
      if (!res.ok || !res.body) return;
      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let buf = '';
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buf += decoder.decode(value, { stream: true });
        const parts = buf.split('\n\n');
        buf = parts.pop() || '';
        for (const chunk of parts) {
          const line = chunk.split('\n').find((l) => l.startsWith('data: '));
          if (!line) continue;
          try {
            const event = JSON.parse(line.slice(6));
            if (event.kind === 'context' || event.kind === 'upload') {
              const ctx = event.payload && event.payload.context
                ? event.payload.context
                : event.payload;
              if (ctx && (ctx.project_id !== undefined || ctx.revision !== undefined)) {
                renderContext(ctx);
              } else {
                void refreshContext();
              }
              if (event.kind === 'upload') {
                showStatus('Photo received on laptop');
                setTimeout(() => showStatus(''), 2500);
              }
            }
          } catch (_) {
            /* ignore parse */
          }
        }
      }
    } catch (_) {
      /* poll remains */
    }
  }

  function stopSync() {
    if (pollTimer) {
      clearInterval(pollTimer);
      pollTimer = null;
    }
    if (eventSource) {
      try {
        eventSource.close();
      } catch (_) {
        /* ignore */
      }
      eventSource = null;
    }
  }

  function clearSession() {
    sessionToken = '';
    localStorage.removeItem(STORAGE_KEY);
    stopSync();
  }

  async function doPair() {
    showError(els.pairError, '');
    const code = (els.code && els.code.value ? els.code.value : '').trim();
    if (!pairToken) {
      showError(els.pairError, 'Open this page from the laptop QR link.');
      return;
    }
    if (!/^\d{6}$/.test(code)) {
      showError(els.pairError, 'Enter the 6-digit code from the laptop.');
      return;
    }
    try {
      const data = await fetch(API + '/pair', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          pair_token: pairToken,
          pair_code: code,
          device_label: navigator.userAgent.slice(0, 60),
        }),
      }).then(async (res) => {
        const body = await res.json();
        if (!res.ok) {
          throw new Error(body.detail || res.statusText);
        }
        return body;
      });
      sessionToken = data.session_token;
      localStorage.setItem(STORAGE_KEY, sessionToken);
      showMain();
      await refreshContext();
    } catch (err) {
      showError(els.pairError, err.message || String(err));
    }
  }

  async function doUpload(file) {
    showError(els.uploadError, '');
    showStatus('Uploading…');
    const fd = new FormData();
    fd.append('file', file, file.name || 'photo.jpg');
    try {
      const data = await api('/upload', { method: 'POST', body: fd });
      showStatus('Uploaded · image ' + (data.context && data.context.image_count));
      if (data.context) renderContext(data.context);
      setTimeout(() => showStatus(''), 2000);
    } catch (err) {
      showStatus('');
      showError(els.uploadError, err.message || String(err));
      if (err.status === 401) {
        clearSession();
        showPair();
      }
    }
  }

  els.pairBtn &&
    els.pairBtn.addEventListener('click', () => {
      void doPair();
    });
  els.code &&
    els.code.addEventListener('keydown', (e) => {
      if (e.key === 'Enter') void doPair();
    });
  els.refresh &&
    els.refresh.addEventListener('click', () => {
      void refreshContext().catch((err) => showError(els.uploadError, err.message));
    });
  els.file &&
    els.file.addEventListener('change', () => {
      const f = els.file.files && els.file.files[0];
      if (f) void doUpload(f);
      els.file.value = '';
    });
  els.unpair &&
    els.unpair.addEventListener('click', () => {
      clearSession();
      showPair();
    });

  // Boot
  if (sessionToken) {
    showMain();
    void refreshContext().catch((err) => {
      if (err.status === 401) {
        clearSession();
        if (pairToken) showPair();
        else if (els.needToken) {
          els.needToken.hidden = false;
          if (els.pair) els.pair.hidden = true;
          if (els.main) els.main.hidden = true;
        }
      } else {
        showError(els.uploadError, err.message);
      }
    });
  } else if (pairToken) {
    showPair();
  } else if (els.needToken) {
    els.needToken.hidden = false;
  }
})();
