/**
 * emailApi.js — Route email list/read/search between live IMAP and local mirror.
 */

const API_BASE = window.location.origin;

let _localOnlyCached = null;
let _localModeStatus = null;

export function invalidateLocalOnlyCache() {
  _localOnlyCached = null;
  _localModeStatus = null;
}

export async function loadLocalOnlyMode() {
  if (_localOnlyCached !== null) return _localOnlyCached;
  try {
    const res = await fetch(`${API_BASE}/api/prefs/email_local_only`, { credentials: 'same-origin' });
    if (!res.ok) return false;
    const data = await res.json();
    _localOnlyCached = Boolean(data.value);
  } catch (_) {
    _localOnlyCached = false;
  }
  return _localOnlyCached;
}

export async function setLocalOnlyMode(on) {
  await fetch(`${API_BASE}/api/prefs/email_local_only`, {
    method: 'PUT',
    credentials: 'same-origin',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ value: !!on }),
  });
  _localOnlyCached = !!on;
  _localModeStatus = null;
}

export async function loadLocalModeStatus() {
  if (_localModeStatus) return _localModeStatus;
  try {
    const res = await fetch(`${API_BASE}/api/email/local/mode`, { credentials: 'same-origin' });
    if (!res.ok) return null;
    _localModeStatus = await res.json();
    if (_localModeStatus && typeof _localModeStatus.local_only === 'boolean') {
      _localOnlyCached = _localModeStatus.local_only;
    }
  } catch (_) {
    return null;
  }
  return _localModeStatus;
}

function _acctQS(accountId) {
  return accountId ? `&account_id=${encodeURIComponent(accountId)}` : '';
}

function _mapFilter(filter) {
  if (filter === 'favorites') return 'flagged';
  if (['all', 'unread', 'unanswered', 'flagged'].includes(filter)) return filter;
  return 'all';
}

export async function listEmails({
  folder = 'INBOX',
  limit = 100,
  offset = 0,
  filter = 'all',
  accountId = '',
  hasAttachments = null,
  buster = '',
} = {}) {
  const localOnly = await loadLocalOnlyMode();
  const acct = _acctQS(accountId);
  const mappedFilter = _mapFilter(filter);
  const attQS = hasAttachments ? '&has_attachments=true' : '';
  const bustQS = buster ? (buster.startsWith('&') ? buster : `&${buster}`) : '';

  if (localOnly) {
    const res = await fetch(
      `${API_BASE}/api/email/local/list?folder=${encodeURIComponent(folder)}${acct}&limit=${limit}&offset=${offset}&filter=${encodeURIComponent(mappedFilter)}${attQS}${bustQS}`,
      { credentials: 'same-origin' },
    );
    return res;
  }

  const res = await fetch(
    `${API_BASE}/api/email/list?folder=${encodeURIComponent(folder)}${acct}&limit=${limit}&offset=${offset}&filter=${encodeURIComponent(filter)}${attQS}${bustQS}`,
    { credentials: 'same-origin' },
  );
  return res;
}

export async function readEmail(uid, {
  folder = 'INBOX',
  accountId = '',
  markSeen = true,
} = {}) {
  const localOnly = await loadLocalOnlyMode();
  const acct = _acctQS(accountId);
  if (localOnly) {
    return fetch(
      `${API_BASE}/api/email/local/read/${encodeURIComponent(uid)}?folder=${encodeURIComponent(folder)}${acct}`,
      { credentials: 'same-origin' },
    );
  }
  const markQS = markSeen ? '' : '&mark_seen=false';
  return fetch(
    `${API_BASE}/api/email/read/${encodeURIComponent(uid)}?folder=${encodeURIComponent(folder)}${acct}${markQS}`,
    { credentials: 'same-origin' },
  );
}

export async function searchEmails(q, {
  folder = 'INBOX',
  limit = 100,
  offset = 0,
  accountId = '',
} = {}) {
  const localOnly = await loadLocalOnlyMode();
  const acct = _acctQS(accountId);
  if (localOnly) {
    return fetch(
      `${API_BASE}/api/email/local/search?folder=${encodeURIComponent(folder)}${acct}&q=${encodeURIComponent(q)}&limit=${limit}&offset=${offset}`,
      { credentials: 'same-origin' },
    );
  }
  return fetch(
    `${API_BASE}/api/email/search?folder=${encodeURIComponent(folder)}${acct}&q=${encodeURIComponent(q)}&limit=${limit}&offset=${offset}`,
    { credentials: 'same-origin' },
  );
}

export async function syncLocalNow(body = {}) {
  return fetch(`${API_BASE}/api/email/local/sync`, {
    method: 'POST',
    credentials: 'same-origin',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body || {}),
  });
}
