/**
 * Placeholder module panels for remaining P1 routes.
 * Do not look like empty data tables — copy only.
 */

const COPY = {};

/**
 * @param {HTMLElement} container
 * @param {string} routeId
 */
export function mountPlaceholder(container, routeId) {
  if (container.dataset.mounted === '1') return;
  const meta = COPY[routeId] || {
    title: routeId,
    body: 'This module is coming in P1.',
  };
  container.innerHTML = `
    <div class="sysforge-placeholder">
      <h3 class="sysforge-view-heading" tabindex="-1">${meta.title}</h3>
      <p class="sysforge-placeholder-body">${meta.body}</p>
      <p class="sysforge-placeholder-note">Coming in P1</p>
    </div>`;
  container.dataset.mounted = '1';
}

/**
 * @param {HTMLElement} container
 */
export function activatePlaceholder(container) {
  const heading = container.querySelector('.sysforge-view-heading');
  heading?.focus?.({ preventScroll: true });
}

export function placeholderRouteIds() {
  return Object.keys(COPY);
}
