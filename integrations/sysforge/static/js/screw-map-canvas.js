/**
 * Letterboxed image + SVG markers. Normalized coords [0,1] on image content.
 * Single-click empty area places; drag moves; dots show ScrewNumber.
 */

/**
 * @param {number} containerW
 * @param {number} containerH
 * @param {number} imageW
 * @param {number} imageH
 */
export function computeLetterbox(containerW, containerH, imageW, imageH) {
  if (!containerW || !containerH || !imageW || !imageH) {
    return { offsetX: 0, offsetY: 0, drawW: 0, drawH: 0 };
  }
  const scale = Math.min(containerW / imageW, containerH / imageH);
  const drawW = imageW * scale;
  const drawH = imageH * scale;
  return {
    offsetX: (containerW - drawW) / 2,
    offsetY: (containerH - drawH) / 2,
    drawW,
    drawH,
  };
}

/**
 * Client point → normalized [0,1] or null if outside letterboxed image.
 * @param {{offsetX:number,offsetY:number,drawW:number,drawH:number}} box
 * @param {number} localX
 * @param {number} localY
 */
export function clientToNormalized(box, localX, localY) {
  if (!box.drawW || !box.drawH) return null;
  const nx = (localX - box.offsetX) / box.drawW;
  const ny = (localY - box.offsetY) / box.drawH;
  if (nx < 0 || nx > 1 || ny < 0 || ny > 1) return null;
  return { x: nx, y: ny };
}

/**
 * @param {{offsetX:number,offsetY:number,drawW:number,drawH:number}} box
 * @param {number} nx
 * @param {number} ny
 */
export function normalizedToClient(box, nx, ny) {
  return {
    x: box.offsetX + nx * box.drawW,
    y: box.offsetY + ny * box.drawH,
  };
}

/**
 * @param {HTMLElement} host
 * @param {{
 *   getImageUrl: () => string|null,
 *   getMarkers: () => Array<{id:number,screw_number:number,position_x:number,position_y:number}>,
 *   getSelectedId: () => number|null,
 *   isReadOnly: () => boolean,
 *   onPlace: (x:number, y:number) => void,
 *   onSelect: (id:number|null) => void,
 *   onMove: (id:number, x:number, y:number) => void,
 * }} opts
 */
export function createScrewMapCanvas(host, opts) {
  host.innerHTML = `
    <div class="sysforge-sm-canvas-wrap">
      <img class="sysforge-sm-canvas-img" alt="" draggable="false" />
      <svg class="sysforge-sm-canvas-svg" aria-label="Screw markers"></svg>
      <p class="sysforge-sm-canvas-empty">No photos yet. Use Add new photo below to start documenting this repair.</p>
    </div>`;

  const wrap = host.querySelector('.sysforge-sm-canvas-wrap');
  const img = /** @type {HTMLImageElement} */ (host.querySelector('.sysforge-sm-canvas-img'));
  const svg = /** @type {SVGSVGElement} */ (host.querySelector('.sysforge-sm-canvas-svg'));
  const empty = /** @type {HTMLElement} */ (host.querySelector('.sysforge-sm-canvas-empty'));

  /** @type {{offsetX:number,offsetY:number,drawW:number,drawH:number}} */
  let box = { offsetX: 0, offsetY: 0, drawW: 0, drawH: 0 };
  let dragId = null;
  let dragMoved = false;
  let dragStart = null;
  let suppressClick = false;

  function layout() {
    const url = opts.getImageUrl();
    const has = Boolean(url);
    empty.hidden = has;
    img.hidden = !has;
    svg.hidden = !has;
    if (!has) {
      img.removeAttribute('src');
      svg.innerHTML = '';
      return;
    }
    if (img.getAttribute('src') !== url) {
      img.src = url;
    }
    const rect = wrap.getBoundingClientRect();
    const nw = img.naturalWidth || 1;
    const nh = img.naturalHeight || 1;
    box = computeLetterbox(rect.width, rect.height, nw, nh);
    img.style.left = `${box.offsetX}px`;
    img.style.top = `${box.offsetY}px`;
    img.style.width = `${box.drawW}px`;
    img.style.height = `${box.drawH}px`;
    svg.setAttribute('viewBox', `0 0 ${rect.width} ${rect.height}`);
    svg.setAttribute('width', String(rect.width));
    svg.setAttribute('height', String(rect.height));
    renderMarkers();
  }

  function renderMarkers() {
    const markers = opts.getMarkers() || [];
    const selected = opts.getSelectedId();
    const parts = markers.map((m) => {
      const pt = normalizedToClient(box, m.position_x, m.position_y);
      const sel = selected === m.id ? ' is-selected' : '';
      const num = m.screw_number;
      return `
        <g class="sysforge-sm-marker${sel}" data-id="${m.id}" transform="translate(${pt.x},${pt.y})">
          <circle r="14" class="sysforge-sm-marker-dot" />
          <text class="sysforge-sm-marker-num" text-anchor="middle" dy="4">${num}</text>
        </g>`;
    });
    svg.innerHTML = parts.join('');
  }

  function localPoint(e) {
    const rect = wrap.getBoundingClientRect();
    return { x: e.clientX - rect.left, y: e.clientY - rect.top };
  }

  function markerAt(el) {
    const g = el?.closest?.('.sysforge-sm-marker');
    if (!g) return null;
    const id = Number(g.getAttribute('data-id'));
    return Number.isFinite(id) ? id : null;
  }

  svg.addEventListener('pointerdown', (e) => {
    if (opts.isReadOnly()) return;
    const id = markerAt(e.target);
    if (id == null) return;
    e.preventDefault();
    e.stopPropagation();
    dragId = id;
    dragMoved = false;
    dragStart = localPoint(e);
    opts.onSelect(id);
    svg.setPointerCapture?.(e.pointerId);
  });

  svg.addEventListener('pointermove', (e) => {
    if (dragId == null || opts.isReadOnly()) return;
    const pt = localPoint(e);
    if (
      dragStart &&
      (Math.abs(pt.x - dragStart.x) > 3 || Math.abs(pt.y - dragStart.y) > 3)
    ) {
      dragMoved = true;
    }
    if (!dragMoved) return;
    const norm = clientToNormalized(box, pt.x, pt.y);
    if (!norm) return;
    const markers = opts.getMarkers();
    const m = markers.find((x) => x.id === dragId);
    if (m) {
      m.position_x = norm.x;
      m.position_y = norm.y;
      renderMarkers();
    }
  });

  function endDrag(e) {
    if (dragId == null) return;
    const id = dragId;
    const moved = dragMoved;
    dragId = null;
    dragStart = null;
    if (moved) {
      suppressClick = true;
      const markers = opts.getMarkers();
      const m = markers.find((x) => x.id === id);
      if (m) opts.onMove(id, m.position_x, m.position_y);
    }
    try {
      svg.releasePointerCapture?.(e.pointerId);
    } catch (_) {
      /* ignore */
    }
  }

  svg.addEventListener('pointerup', endDrag);
  svg.addEventListener('pointercancel', endDrag);

  svg.addEventListener('click', (e) => {
    if (suppressClick) {
      suppressClick = false;
      e.preventDefault();
      return;
    }
    if (opts.isReadOnly()) {
      const id = markerAt(e.target);
      opts.onSelect(id);
      return;
    }
    const hit = markerAt(e.target);
    if (hit != null) {
      opts.onSelect(hit);
      return;
    }
    const pt = localPoint(e);
    const norm = clientToNormalized(box, pt.x, pt.y);
    if (!norm) return;
    opts.onPlace(norm.x, norm.y);
  });

  img.addEventListener('load', () => layout());
  window.addEventListener('resize', layout);

  return {
    refresh() {
      layout();
    },
    destroy() {
      window.removeEventListener('resize', layout);
      host.innerHTML = '';
    },
  };
}

export default { computeLetterbox, clientToNormalized, normalizedToClient, createScrewMapCanvas };
