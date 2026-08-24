/**
 * Income → category cashflow map.
 * Original SVG layout. Not Ocular echarts.
 */

function privacyOn(ctx) {
  if (ctx && ctx.privacy === true) return true;
  try {
    if (document.querySelector('.finance-privacy-on')) return true;
  } catch {
    /* ignore */
  }
  return false;
}

function money(ctx, cents) {
  if (privacyOn(ctx)) return '••••';
  if (typeof ctx.moneyHtml === 'function') return ctx.moneyHtml(cents);
  const n = (Number(cents) || 0) / 100;
  const sign = n < 0 ? '-' : '';
  return `${sign}$${Math.abs(n).toFixed(2)}`;
}

function esc(ctx, value) {
  if (typeof ctx.escHtml === 'function') return ctx.escHtml(value);
  return String(value ?? '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

function plainMoney(ctx, cents) {
  return String(money(ctx, cents)).replace(/<[^>]+>/g, '');
}

function hostOf(ctx) {
  return ctx.mount || ctx.host || ctx.panel;
}

function bezier(x1, y1, x2, y2) {
  const mx = (x1 + x2) / 2;
  return `M ${x1} ${y1} C ${mx} ${y1}, ${mx} ${y2}, ${x2} ${y2}`;
}

function drawSvg(data, ctx) {
  const rightNodes = (data.nodes || []).filter((n) => n.kind === 'category' || n.kind === 'leftover');
  const links = (data.links || []).filter((l) => Number(l.cents) > 0);
  if (!rightNodes.length && !links.length) {
    return '<p class="finance-sankey-empty">No cashflow this month.</p>';
  }

  const width = 640;
  const height = Math.max(180, 40 + rightNodes.length * 44);
  const leftX = 16;
  const leftW = 96;
  const rightX = 400;
  const rightW = 220;
  const pad = 12;
  const totalOut = Math.max(
    1,
    links.reduce((sum, l) => sum + (Number(l.cents) || 0), 0),
    Number(data.income_cents) || 0,
  );
  const usable = height - pad * 2;
  let y = pad;
  const laid = rightNodes.map((n) => {
    const h = Math.max(20, (Number(n.cents) / totalOut) * usable);
    const box = { ...n, y, h, cy: y + h / 2 };
    y += h + 8;
    return box;
  });
  const leftH = Math.max(52, Math.min(usable, laid.reduce((sum, n) => sum + n.h, 0)));
  const leftY = pad + Math.max(0, (usable - leftH) / 2);

  const paths = links.map((l) => {
    const target = laid.find((n) => n.id === l.target);
    if (!target) return '';
    const color = esc(ctx, target.color || (target.kind === 'leftover' ? '#50fa7b' : '#e06c75'));
    const thickness = Math.max(4, (Number(l.cents) / totalOut) * usable * 0.85);
    const d = bezier(leftX + leftW, leftY + leftH / 2, rightX, target.cy);
    return `<path d="${d}" fill="none" stroke="${color}" stroke-width="${thickness}" stroke-opacity="0.45"></path>`;
  }).join('');

  const rightRects = laid.map((n) => {
    const color = esc(ctx, n.color || (n.kind === 'leftover' ? '#50fa7b' : '#5b8abf'));
    const catId = n.category_id || (n.id === 'uncategorized' ? '' : n.id);
    const clickable = n.kind === 'category'
      ? `data-sankey-cat="${esc(ctx, catId)}" tabindex="0" role="button"`
      : '';
    const label = `${esc(ctx, n.label)} · ${esc(ctx, plainMoney(ctx, n.cents))}`;
    return `<g ${clickable} style="cursor:${n.kind === 'category' ? 'pointer' : 'default'}">
      <rect x="${rightX}" y="${n.y}" width="${rightW}" height="${n.h}" rx="4" fill="${color}"></rect>
      <text x="${rightX + 8}" y="${n.y + Math.min(n.h / 2 + 4, n.h - 4)}" fill="#111" font-size="12">${label}</text>
    </g>`;
  }).join('');

  const incomeLabel = `Income · ${esc(ctx, plainMoney(ctx, data.income_cents))}`;
  return `<svg class="finance-sankey-svg" viewBox="0 0 ${width} ${height}" width="100%" height="${Math.min(height, 420)}" role="img" aria-label="Cashflow map for ${esc(ctx, data.month)}">
    ${paths}
    <rect x="${leftX}" y="${leftY}" width="${leftW}" height="${leftH}" rx="4" fill="#50fa7b"></rect>
    <text x="${leftX + 8}" y="${leftY + 20}" fill="#111" font-size="12">${incomeLabel}</text>
    ${rightRects}
  </svg>`;
}

function listHtml(data, ctx) {
  const nodes = data.nodes || [];
  const byId = Object.fromEntries(nodes.map((n) => [n.id, n]));
  const rows = (data.links || []).map((l) => {
    const node = byId[l.target] || {};
    const catId = node.category_id || (node.id === 'uncategorized' ? '' : node.id);
    const catAttr = node.kind === 'category' ? `data-sankey-cat="${esc(ctx, catId)}"` : '';
    return `<li ${catAttr} style="display:flex;justify-content:space-between;gap:12px;padding:4px 0;cursor:${node.kind === 'category' ? 'pointer' : 'default'};">
      <span>Income → ${esc(ctx, node.label || l.target)}</span>
      <span>${money(ctx, l.cents)}</span>
    </li>`;
  }).join('');
  return `<ul class="finance-sankey-list" style="list-style:none;padding:0;">${rows || '<li>No classified spend this month.</li>'}</ul>`;
}

function bindClicks(host, data, ctx) {
  host.querySelectorAll('[data-sankey-cat]').forEach((el) => {
    const id = el.getAttribute('data-sankey-cat');
    const fire = () => {
      if (typeof ctx.onCategoryClick === 'function') {
        ctx.onCategoryClick(id, data.month);
        return;
      }
      host.dispatchEvent(new CustomEvent('finance-sankey-category', {
        bubbles: true,
        detail: { categoryId: id, month: data.month },
      }));
    };
    el.addEventListener('click', fire);
    el.addEventListener('keydown', (ev) => {
      if (ev.key === 'Enter' || ev.key === ' ') {
        ev.preventDefault();
        fire();
      }
    });
  });
}

export async function renderFinanceSankey(ctx = {}) {
  const host = hostOf(ctx);
  if (!host) return;
  const api = ctx.api;
  const month = ctx.month || new Date().toISOString().slice(0, 7);
  host.innerHTML = '<p>Loading cashflow map…</p>';
  try {
    if (typeof api !== 'function') throw new Error('Missing finance API');
    const data = await api(`/reports/sankey?month=${encodeURIComponent(month)}`);
    const unclassified = Number(data.unclassified_count || 0);
    const incomplete = data.incomplete || unclassified > 0
      ? `<p class="finance-sankey-incomplete" style="color:var(--warn,#f0ad4e);">This month is incomplete — ${unclassified} unclassified row(s), ${plainMoney(ctx, data.unclassified_outflow_cents)} outflow counted by sign. Not fully true spend.</p>`
      : '';
    const hasFlow = Number(data.income_cents) || (data.links || []).length;
    const body = hasFlow
      ? `${drawSvg(data, ctx)}${listHtml(data, ctx)}`
      : '<p class="finance-sankey-empty">No cashflow this month.</p>';
    host.innerHTML = `
      <section class="finance-sankey">
        <h3 style="margin-top:16px;">Cashflow map — ${esc(ctx, data.month)}</h3>
        <p style="font-size:0.85rem;">True income → true spend by category. Transfers are not spend.</p>
        ${incomplete}
        ${body}
      </section>`;
    bindClicks(host, data, ctx);
  } catch (err) {
    const msg = err && err.message ? err.message : String(err);
    host.innerHTML = `<p class="finance-sankey-error">Could not load cashflow map: ${esc(ctx, msg)}</p>`;
  }
}

if (typeof window !== 'undefined') {
  window.renderFinanceSankey = renderFinanceSankey;
  window.renderFinanceSankey = renderFinanceSankey;
}
