/**
 * Browser-like integration test: router + view mounts must leave visible HTML.
 * Run: node tests/scripts/test_sysforge_view_visibility.mjs
 */
import { Window } from 'happy-dom';
import { fileURLToPath } from 'node:url';
import path from 'node:path';

const repoRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../..');
const jsRoot = path.join(repoRoot, 'integrations/sysforge/static/js');

const window = new Window({
  url: 'http://localhost:7000/',
  settings: {
    disableJavaScriptFileLoading: false,
    disableJavaScriptEvaluation: false,
    disableCSSFileLoading: true,
    disableIframePageLoading: true,
    enableFileSystemHttpRequests: false,
  },
});

const { document } = window;
globalThis.window = window;
globalThis.document = document;
globalThis.HTMLElement = window.HTMLElement;
globalThis.Element = window.Element;
globalThis.Node = window.Node;
globalThis.Event = window.Event;
globalThis.KeyboardEvent = window.KeyboardEvent;
globalThis.MouseEvent = window.MouseEvent;
globalThis.CustomEvent = window.CustomEvent;
globalThis.AbortController = window.AbortController;
globalThis.fetch = async () => ({
  ok: true,
  status: 200,
  json: async () => ({}),
});

const router = await import(`file:///${jsRoot.replace(/\\/g, '/')}/router.js`);
const { mountSettings } = await import(`file:///${jsRoot.replace(/\\/g, '/')}/views/settings.js`);
const { mountDiagnostics } = await import(`file:///${jsRoot.replace(/\\/g, '/')}/views/diagnostics.js`);
const { mountClients } = await import(`file:///${jsRoot.replace(/\\/g, '/')}/views/clients.js`);
const { mountClientDashboard } = await import(`file:///${jsRoot.replace(/\\/g, '/')}/views/client-dashboard.js`);
const { mountClientMerge } = await import(`file:///${jsRoot.replace(/\\/g, '/')}/views/client-merge.js`);
const { mountOutstandingInvoices } = await import(
  `file:///${jsRoot.replace(/\\/g, '/')}/views/outstanding-invoices.js`
);
const { mountDashboard } = await import(`file:///${jsRoot.replace(/\\/g, '/')}/views/dashboard.js`);

const api = async () => ({});

function visibleHtml(host) {
  const active = [...host.children].find((el) => !el.hidden);
  if (!active) return { active: null, len: 0, hiddenCount: host.children.length };
  const style = active.ownerDocument.defaultView.getComputedStyle(active);
  return {
    route: active.dataset.route,
    len: active.innerHTML.length,
    hidden: active.hidden,
    display: style.display,
    visibility: style.visibility,
  };
}

router._resetForTests();
const host = document.createElement('div');
host.id = 'sysforge-view-host';
document.body.appendChild(host);

router.mount(host, { syncHash: false });

const routeIds = [
  'dashboard',
  'settings',
  'diagnostics',
  'clients',
  'client-dashboard',
  'client-merge',
  'invoices-outstanding',
];

router.register('dashboard', {
  title: 'dashboard',
  mount: (el) => mountDashboard(el, { navigate: () => {}, api }),
  activate: () => {},
});
router.register('settings', {
  title: 'settings',
  mount: (el) => mountSettings(el, { api }),
  activate: () => {},
});
router.register('diagnostics', {
  title: 'diagnostics',
  mount: (el) => mountDiagnostics(el, { api }),
  activate: () => {},
});
router.register('clients', {
  title: 'clients',
  mount: (el) => mountClients(el, { api, navigate: () => {} }),
  activate: () => {},
});
router.register('client-dashboard', {
  title: 'client-dashboard',
  mount: (el) =>
    mountClientDashboard(el, {
      api,
      navigate: () => {},
      navigateToNewInvoice: () => {},
    }),
  activate: () => {},
});
router.register('client-merge', {
  title: 'client-merge',
  mount: (el) => mountClientMerge(el, { api, navigate: () => {} }),
  activate: () => {},
});
router.register('invoices-outstanding', {
  title: 'invoices-outstanding',
  mount: (el) => mountOutstandingInvoices(el, { api, navigate: () => {} }),
  activate: () => {},
});

const results = {};
const broken = [];

for (const route of routeIds) {
  router.navigate(route);
  const info = visibleHtml(host);
  results[route] = info;
  if (!info.len || info.display === 'none' || info.visibility === 'hidden') {
    broken.push(route);
  }
}

// Same-surface reapply must keep content visible (desktop CurrentView lesson).
router.applyNavigation('settings', {}, { replace: true, reason: 'reapply' });
const reapply = visibleHtml(host);
if (!reapply.len) broken.push('settings-reapply');

console.log(JSON.stringify({ results, reapply, broken }));

if (broken.length) {
  process.exit(1);
}
