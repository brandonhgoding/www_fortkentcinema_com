import { onPointer } from '../core/pointer.js';
import { getMotionTier } from '../core/motionPrefs.js';

const MAX_TILT = 4;

function attach(grid, selector = ':scope > article') {
  if (getMotionTier() !== 'full') return;
  try {
    grid.classList.add('fx-spotlight-grid');
    const spot = document.createElement('div');
    spot.className = 'fx-spotlight';
    spot.setAttribute('aria-hidden', 'true');
    grid.appendChild(spot);
    let wasInside = false;
    const clearCards = () => grid.querySelectorAll(selector).forEach((card) => {
      card.classList.remove('fx-card--focus', 'fx-card--dim');
      card.style.transform = '';
    });
    onPointer((p) => {
      const rect = grid.getBoundingClientRect();
      const inside = p.sx >= rect.left && p.sx <= rect.right && p.sy >= rect.top && p.sy <= rect.bottom;
      grid.classList.toggle('fx-spotlight-grid--active', inside);
      if (!inside) { if (wasInside) { clearCards(); wasInside = false; } return; }
      wasInside = true;
      spot.style.transform = `translate(${p.sx - rect.left}px, ${p.sy - rect.top}px)`;
      grid.querySelectorAll(selector).forEach((card) => {
        const cr = card.getBoundingClientRect();
        const over = p.x >= cr.left && p.x <= cr.right && p.y >= cr.top && p.y <= cr.bottom;
        card.classList.toggle('fx-card--focus', over);
        card.classList.toggle('fx-card--dim', !over);
        if (over) {
          const center = cr.left + cr.width / 2;
          const tilt = ((p.sx - center) / (cr.width / 2)) * MAX_TILT;
          card.style.transform = `translateY(-6px) perspective(800px) rotateY(${tilt}deg)`;
        } else { card.style.transform = ''; }
      });
    });
  } catch (err) { console.error('[effects] card spotlight disabled:', err); }
}

export function initCardSpotlight(root = document) {
  root.querySelectorAll('[data-spotlight]').forEach((grid) => {
    if (grid.dataset.spotlightInit) return;
    grid.dataset.spotlightInit = '1';
    attach(grid);
  });
}
