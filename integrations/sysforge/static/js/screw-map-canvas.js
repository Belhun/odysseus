/**
 * Letterboxed image + SVG markers. Normalized coords [0,1] on image content.
 * Single-click empty area places; drag moves; dots show ScrewNumber.
 * Wheel zoom + middle/Alt drag pan. Note markers = square pin + "N".
 */

const MIN_ZOOM = 1;
const MAX_ZOOM = 6;

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
 * Map screen (wrap-local) coords through zoom/pan into letterbox space.
 * @param {{scale:number,tx:number,ty:number}} view
 * @param {number} screenX
 * @param {number} screenY
 */
export function screenToLetterbox(view, screenX, screenY) {
  const s = view.scale || 1;
  return {
    x: (screenX - (view.tx || 0)) / s,
    y: (screenY - (view.ty || 0)) / s,
  };
}

/**
 * @param {{scale:number,tx:number,ty:number}} view
 * @param {number} letterX
 * @param {number} letterY
 */
export function letterboxToScreen(view, letterX, letterY) {
  const s = view.scale || 1;
  return {
    x: letterX * s + (view.tx || 0),
    y: letterY * s + (view.ty || 0),
  };
}

/**
 * Zoom toward a screen point; returns new view.
 * @param {{scale:number,tx:number,ty:number}} view
 * @param {number} screenX
 * @param {number} screenY
 * @param {number} factor
 * @param {number} [min]
 * @param {number} [max]
 */
export function zoomAtPoint(view, screenX, screenY, factor, min = MIN_ZOOM, max = MAX_ZOOM) {
  const oldScale = view.scale || 1;
  let newScale = oldScale * factor;
  if (newScale < min) newScale = min;
  if (newScale > max) newScale = max;
  if (newScale === oldScale) return { ...view, scale: oldScale };
  const worldX = (screenX - (view.tx || 0)) / oldScale;
  const worldY = (screenY - (view.ty || 0)) / oldScale;
  return {
    scale: newScale,
    tx: screenX - worldX * newScale,
    ty: screenY - worldY * newScale,
  };
}

/**
 * @param {HTMLElement} host
 * @param {{
 *   getImageUrl: () => string|null,
 *   getMarkers: () => Array<{id:number,screw_number:number,position_x:number,position_y:number}>,
 *   getNoteMarkers?: () => Array<{id:number,position_x:number,position_y:number}>,
 *   getSelectedId: () => number|null,
 *   getSelectedKind?: () => 'screw'|'note'|null,
 *   getPlaceMode?: () => 'screw'|'note',
 *   isReadOnly: () => boolean,
 *   onPlace: (x:number, y:number, kind:'screw'|'note') => void,
 *   onSelect: (id:number|null, kind:'screw'|'note'|null) => void,
 *   onMove: (id:number, x:number, y:number, kind:'screw'|'note') => void,
 * }} opts
 */
export function createScrewMapCanvas(host, opts) {
  host.innerHTML = `
    <div class="sysforge-sm-canvas-wrap">
      <img class="sysforge-sm-canvas-img" alt="" draggable="false" />
      <svg class="sysforge-sm-canvas-svg" aria-label="Screw markers"></svg>
      <p class="sysforge-sm-canvas-empty">No photos yet. Use Add new photo below to start documenting this repair.</p>
      <div class="sysforge-sm-zoom-bar" hidden>
        <button type="button" class="btn-secondary sysforge-sm-zoom-out" title="Zoom out">−</button>
        <button type="button" class="btn-secondary sysforge-sm-zoom-reset" title="Reset view">100%</button>
        <button type="button" class="btn-secondary sysforge-sm-zoom-in" title="Zoom in">+</button>
      </div>
    </div>`;

  const wrap = /** @type {HTMLElement} */ (host.querySelector('.sysforge-sm-canvas-wrap'));
  const img = /** @type {HTMLImageElement} */ (host.querySelector('.sysforge-sm-canvas-img'));
  const svg = /** @type {SVGSVGElement} */ (host.querySelector('.sysforge-sm-canvas-svg'));
  const empty = /** @type {HTMLElement} */ (host.querySelector('.sysforge-sm-canvas-empty'));
  const zoomBar = /** @type {HTMLElement} */ (host.querySelector('.sysforge-sm-zoom-bar'));
  const zoomLabel = /** @type {HTMLButtonElement} */ (host.querySelector('.sysforge-sm-zoom-reset'));

  /** @type {{offsetX:number,offsetY:number,drawW:number,drawH:number}} */
  let box = { offsetX: 0, offsetY: 0, drawW: 0, drawH: 0 };
  /** @type {{scale:number,tx:number,ty:number}} */
  let view = { scale: 1, tx: 0, ty: 0 };

  /** @type {{kind:'screw'|'note', id:number}|null} */
  let dragTarget = null;
  let dragMoved = false;
  let dragStart = null;
  let suppressClick = false;

  let panActive = false;
  let panStart = null;
  let panOrigin = null;
  let spaceDown = false;

  function placeMode() {
    return opts.getPlaceMode?.() === 'note' ? 'note' : 'screw';
  }

  function selectedKind() {
    return opts.getSelectedKind?.() || (opts.getSelectedId() != null ? 'screw' : null);
  }

  function updateZoomChrome() {
    if (zoomLabel) zoomLabel.textContent = `${Math.round(view.scale * 100)}%`;
    if (zoomBar) zoomBar.hidden = !opts.getImageUrl();
  }

  function clearView() {
    view = { scale: 1, tx: 0, ty: 0 };
  }

  function layout() {
    const url = opts.getImageUrl();
    const has = Boolean(url);
    empty.hidden = has;
    img.hidden = !has;
    svg.hidden = !has;
    if (!has) {
      img.removeAttribute('src');
      svg.innerHTML = '';
      clearView();
      updateZoomChrome();
      return;
    }
    if (img.getAttribute('src') !== url) {
      img.src = url;
      clearView();
    }
    const rect = wrap.getBoundingClientRect();
    const nw = img.naturalWidth || 1;
    const nh = img.naturalHeight || 1;
    box = computeLetterbox(rect.width, rect.height, nw, nh);
    const scr = letterboxToScreen(view, box.offsetX, box.offsetY);
    img.style.left = `${scr.x}px`;
    img.style.top = `${scr.y}px`;
    img.style.width = `${box.drawW * view.scale}px`;
    img.style.height = `${box.drawH * view.scale}px`;
    svg.setAttribute('viewBox', `0 0 ${rect.width} ${rect.height}`);
    svg.setAttribute('width', String(rect.width));
    svg.setAttribute('height', String(rect.height));
    renderMarkers();
    updateZoomChrome();
  }

  function renderMarkers() {
    const markers = opts.getMarkers() || [];
    const notes = opts.getNoteMarkers?.() || [];
    const selected = opts.getSelectedId();
    const selKind = selectedKind();
    const parts = [];

    for (const m of markers) {
      const letter = normalizedToClient(box, m.position_x, m.position_y);
      const pt = letterboxToScreen(view, letter.x, letter.y);
      const sel = selKind === 'screw' && selected === m.id ? ' is-selected' : '';
      parts.push(`
        <g class="sysforge-sm-marker${sel}" data-kind="screw" data-id="${m.id}"
           transform="translate(${pt.x},${pt.y})">
          <circle r="14" class="sysforge-sm-marker-dot" />
          <text class="sysforge-sm-marker-num" text-anchor="middle" dy="4">${m.screw_number}</text>
        </g>`);
    }

    for (const n of notes) {
      const letter = normalizedToClient(box, n.position_x, n.position_y);
      const pt = letterboxToScreen(view, letter.x, letter.y);
      const sel = selKind === 'note' && selected === n.id ? ' is-selected' : '';
      parts.push(`
        <g class="sysforge-sm-note-marker${sel}" data-kind="note" data-id="${n.id}"
           transform="translate(${pt.x},${pt.y})">
          <rect x="-12" y="-12" width="24" height="24" rx="3" class="sysforge-sm-note-dot" />
          <text class="sysforge-sm-marker-num" text-anchor="middle" dy="4">N</text>
        </g>`);
    }

    svg.innerHTML = parts.join('');
  }

  function localPoint(e) {
    const rect = wrap.getBoundingClientRect();
    return { x: e.clientX - rect.left, y: e.clientY - rect.top };
  }

  function normFromScreen(screenX, screenY) {
    const letter = screenToLetterbox(view, screenX, screenY);
    return clientToNormalized(box, letter.x, letter.y);
  }

  function markerAt(el) {
    const g = el?.closest?.('[data-kind][data-id]');
    if (!g) return null;
    const id = Number(g.getAttribute('data-id'));
    const kind = g.getAttribute('data-kind');
    if (!Number.isFinite(id) || (kind !== 'screw' && kind !== 'note')) return null;
    return { id, kind: /** @type {'screw'|'note'} */ (kind) };
  }

  function wantsPan(e) {
    return e.button === 1 || (e.button === 0 && (e.altKey || spaceDown));
  }

  function setCursor() {
    if (panActive || spaceDown) {
      svg.style.cursor = 'grab';
      return;
    }
    svg.style.cursor = placeMode() === 'note' ? 'cell' : 'crosshair';
  }

  svg.addEventListener('pointerdown', (e) => {
    if (wantsPan(e)) {
      e.preventDefault();
      panActive = true;
      panStart = localPoint(e);
      panOrigin = { ...view };
      suppressClick = true;
      svg.setPointerCapture?.(e.pointerId);
      svg.style.cursor = 'grabbing';
      return;
    }
    if (opts.isReadOnly()) return;
    const hit = markerAt(e.target);
    if (hit == null) return;
    e.preventDefault();
    e.stopPropagation();
    dragTarget = hit;
    dragMoved = false;
    dragStart = localPoint(e);
    opts.onSelect(hit.id, hit.kind);
    svg.setPointerCapture?.(e.pointerId);
  });

  svg.addEventListener('pointermove', (e) => {
    if (panActive && panStart && panOrigin) {
      const pt = localPoint(e);
      view = {
        scale: panOrigin.scale,
        tx: panOrigin.tx + (pt.x - panStart.x),
        ty: panOrigin.ty + (pt.y - panStart.y),
      };
      layout();
      return;
    }
    if (dragTarget == null || opts.isReadOnly()) return;
    const pt = localPoint(e);
    if (
      dragStart &&
      (Math.abs(pt.x - dragStart.x) > 3 || Math.abs(pt.y - dragStart.y) > 3)
    ) {
      dragMoved = true;
    }
    if (!dragMoved) return;
    const norm = normFromScreen(pt.x, pt.y);
    if (!norm) return;
    if (dragTarget.kind === 'screw') {
      const markers = opts.getMarkers();
      const m = markers.find((x) => x.id === dragTarget.id);
      if (m) {
        m.position_x = norm.x;
        m.position_y = norm.y;
        renderMarkers();
      }
    } else {
      const notes = opts.getNoteMarkers?.() || [];
      const n = notes.find((x) => x.id === dragTarget.id);
      if (n) {
        n.position_x = norm.x;
        n.position_y = norm.y;
        renderMarkers();
      }
    }
  });

  function endDrag(e) {
    if (panActive) {
      panActive = false;
      panStart = null;
      panOrigin = null;
      setCursor();
      try {
        svg.releasePointerCapture?.(e.pointerId);
      } catch (_) {
        /* ignore */
      }
      return;
    }
    if (dragTarget == null) return;
    const target = dragTarget;
    const moved = dragMoved;
    dragTarget = null;
    dragStart = null;
    if (moved) {
      suppressClick = true;
      if (target.kind === 'screw') {
        const markers = opts.getMarkers();
        const m = markers.find((x) => x.id === target.id);
        if (m) opts.onMove(target.id, m.position_x, m.position_y, 'screw');
      } else {
        const notes = opts.getNoteMarkers?.() || [];
        const n = notes.find((x) => x.id === target.id);
        if (n) opts.onMove(target.id, n.position_x, n.position_y, 'note');
      }
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
    const hit = markerAt(e.target);
    if (opts.isReadOnly()) {
      opts.onSelect(hit?.id ?? null, hit?.kind ?? null);
      return;
    }
    if (hit != null) {
      opts.onSelect(hit.id, hit.kind);
      return;
    }
    const pt = localPoint(e);
    const norm = normFromScreen(pt.x, pt.y);
    if (!norm) return;
    opts.onPlace(norm.x, norm.y, placeMode());
  });

  svg.addEventListener('contextmenu', (e) => {
    e.preventDefault();
    if (opts.isReadOnly()) return;
    const hit = markerAt(e.target);
    if (hit != null) {
      opts.onSelect(hit.id, hit.kind);
      return;
    }
    const pt = localPoint(e);
    const norm = normFromScreen(pt.x, pt.y);
    if (!norm) return;
    opts.onPlace(norm.x, norm.y, 'note');
  });

  svg.addEventListener(
    'wheel',
    (e) => {
      if (!opts.getImageUrl()) return;
      e.preventDefault();
      const pt = localPoint(e);
      const factor = e.deltaY < 0 ? 1.12 : 1 / 1.12;
      view = zoomAtPoint(view, pt.x, pt.y, factor);
      layout();
    },
    { passive: false }
  );

  wrap.querySelector('.sysforge-sm-zoom-in')?.addEventListener('click', () => {
    const rect = wrap.getBoundingClientRect();
    view = zoomAtPoint(view, rect.width / 2, rect.height / 2, 1.2);
    layout();
  });
  wrap.querySelector('.sysforge-sm-zoom-out')?.addEventListener('click', () => {
    const rect = wrap.getBoundingClientRect();
    view = zoomAtPoint(view, rect.width / 2, rect.height / 2, 1 / 1.2);
    layout();
  });
  wrap.querySelector('.sysforge-sm-zoom-reset')?.addEventListener('click', () => {
    clearView();
    layout();
  });

  function onKeyDown(e) {
    if (e.code === 'Space' && !e.repeat) {
      spaceDown = true;
      setCursor();
    }
  }
  function onKeyUp(e) {
    if (e.code === 'Space') {
      spaceDown = false;
      if (!panActive) setCursor();
    }
  }
  window.addEventListener('keydown', onKeyDown);
  window.addEventListener('keyup', onKeyUp);

  img.addEventListener('load', () => layout());
  window.addEventListener('resize', layout);
  setCursor();

  return {
    refresh() {
      setCursor();
      layout();
    },
    resetView() {
      clearView();
      layout();
    },
    getView() {
      return { ...view };
    },
    destroy() {
      window.removeEventListener('resize', layout);
      window.removeEventListener('keydown', onKeyDown);
      window.removeEventListener('keyup', onKeyUp);
      host.innerHTML = '';
    },
  };
}

export default {
  computeLetterbox,
  clientToNormalized,
  normalizedToClient,
  screenToLetterbox,
  letterboxToScreen,
  zoomAtPoint,
  createScrewMapCanvas,
};
