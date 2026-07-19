/**
 * Business dashboard — MVP cards with optional favorites (config.json).
 * Click handlers bind once on mount; activate refreshes order/favorites.
 */

const CARDS = [
  {
    id: 'calc',
    route: 'invoice-calculator',
    title: 'Quick Invoice Calculator',
    preview: 'Calculate invoices quickly',
  },
  {
    id: 'clients',
    route: 'client-dashboard',
    title: 'Clients',
    preview: 'Classic client workspace',
  },
  {
    id: 'drafts',
    route: 'drafts',
    title: 'Drafts',
    preview: 'Resume unsaved invoice drafts',
  },
  {
    id: 'parts',
    route: 'parts',
    title: 'Parts',
    preview: 'Catalog and placeholders',
  },
  {
    id: 'parts-triage',
    route: 'parts-triage',
    title: 'Placeholder triage',
    preview: 'Convert placeholders to catalog parts',
  },
  {
    id: 'projects',
    route: 'projects',
    title: 'Projects',
    preview: 'Work orders and four-column project workspace',
  },
  {
    id: 'placeholder-merge',
    route: 'placeholder-merge',
    title: 'Placeholder Merge',
    preview: 'Merge duplicate placeholders',
  },
  {
    id: 'client-merge',
    route: 'client-merge',
    title: 'Client merge',
    preview: 'Soft-merge duplicate clients',
  },
  {
    id: 'outstanding',
    route: 'invoices-outstanding',
    title: 'Outstanding',
    preview: 'Invoices with balance due',
  },
  {
    id: 'reports',
    route: 'reports-sales',
    title: 'Sales report',
    preview: 'Date-range sales and tax CSV',
  },
  {
    id: 'settings',
    route: 'settings',
    title: 'Settings',
    preview: 'Tax, currency, and draft autosave',
  },
  {
    id: 'diagnostics',
    route: 'diagnostics',
    title: 'Diagnostics',
    preview: 'DB health, schema version, row counts',
  },
];

/**
 * Favorites first (config order), then remaining cards in default order.
 * @param {string[]} favorites
 */
export function orderedCards(favorites = []) {
  const favSet = new Set((favorites || []).map(String));
  const byId = new Map(CARDS.map((c) => [c.id, c]));
  const head = [];
  for (const id of favorites || []) {
    const card = byId.get(String(id));
    if (card) head.push(card);
  }
  const rest = CARDS.filter((c) => !favSet.has(c.id));
  return [...head, ...rest];
}

/**
 * Toggle card id in favorites list (pin / unpin).
 * @param {string[]} favorites
 * @param {string} cardId
 */
export function toggleFavorite(favorites, cardId) {
  const id = String(cardId || '');
  if (!id) return [...(favorites || [])];
  const next = (favorites || []).filter((f) => String(f) !== id);
  if (next.length === (favorites || []).length) {
    next.unshift(id);
  }
  return next;
}

function escapeHtml(s) {
  return String(s ?? '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

/**
 * @param {HTMLElement} container
 * @param {{
 *   navigate: (routeId: string) => void,
 *   api?: (path: string, opts?: object) => Promise<object>,
 * }} deps
 */
export function mountDashboard(container, deps) {
  if (container.dataset.mounted === '1') return;

  container.innerHTML = `
    <div class="sysforge-dashboard">
      <h3 class="sysforge-view-heading" tabindex="-1">Shop home</h3>
      <p class="sysforge-dashboard-lead">Open a module to get started. Star a card to pin it to the top.</p>
      <div class="sysforge-card-grid" role="list"></div>
    </div>`;

  container._sysforgeDash = {
    favorites: [],
    deps,
  };
  container.dataset.mounted = '1';

  // Bind once on the grid (event delegation) — never re-attach on activate.
  const grid = container.querySelector('.sysforge-card-grid');
  grid?.addEventListener('click', (e) => {
    const favBtn = e.target.closest('[data-fav-id]');
    if (favBtn) {
      e.preventDefault();
      e.stopPropagation();
      void toggleFavoriteAndPersist(container, favBtn.getAttribute('data-fav-id'));
      return;
    }
    const card = e.target.closest('.sysforge-card[data-route]');
    if (!card) return;
    const route = card.getAttribute('data-route');
    if (route) deps.navigate(route);
  });

  renderCards(container);
}

function renderCards(container) {
  const state = container._sysforgeDash;
  const grid = container.querySelector('.sysforge-card-grid');
  if (!state || !grid) return;
  const favSet = new Set((state.favorites || []).map(String));
  const cards = orderedCards(state.favorites);
  grid.innerHTML = cards
    .map((c) => {
      const isFav = favSet.has(c.id);
      return `
      <div class="sysforge-card-wrap" role="listitem">
        <button type="button"
          class="sysforge-card${isFav ? ' is-favorite' : ''}"
          id="sysforge-card-${c.route}"
          data-route="${c.route}"
          data-card-id="${c.id}">
          <span class="sysforge-card-title">${escapeHtml(c.title)}</span>
          <span class="sysforge-card-preview">${escapeHtml(c.preview)}</span>
        </button>
        <button type="button"
          class="sysforge-card-fav${isFav ? ' is-on' : ''}"
          data-fav-id="${c.id}"
          title="${isFav ? 'Unpin from favorites' : 'Pin to favorites'}"
          aria-label="${isFav ? 'Unpin' : 'Pin'} ${escapeHtml(c.title)}"
          aria-pressed="${isFav ? 'true' : 'false'}">★</button>
      </div>`;
    })
    .join('');
}

async function toggleFavoriteAndPersist(container, cardId) {
  const state = container._sysforgeDash;
  if (!state || !cardId) return;
  state.favorites = toggleFavorite(state.favorites, cardId);
  renderCards(container);
  if (typeof state.deps?.api === 'function') {
    try {
      await state.deps.api('/settings', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ dashboard_favorites: state.favorites }),
      });
    } catch (_) {
      /* keep local order; next activate reloads */
    }
  }
}

/**
 * @param {HTMLElement} container
 */
export async function activateDashboard(container) {
  const heading = container.querySelector('.sysforge-view-heading');
  heading?.focus?.({ preventScroll: true });

  const state = container._sysforgeDash;
  const fetchApi = state?.deps?.api;
  if (!state || typeof fetchApi !== 'function') return;
  try {
    const cfg = await fetchApi('/settings');
    state.favorites = Array.isArray(cfg.dashboard_favorites)
      ? cfg.dashboard_favorites
      : [];
    renderCards(container);
  } catch (_) {
    /* keep current order */
  }
}

export { CARDS };

export default {
  mountDashboard,
  activateDashboard,
  orderedCards,
  toggleFavorite,
  CARDS,
};
