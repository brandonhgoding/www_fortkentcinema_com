import { onScrollProgress } from '../core/scrollProgress.js';
import { getMotionTier } from '../core/motionPrefs.js';

const FADE_SPAN = 0.3;

function reveal(node) {
  try {
    if (getMotionTier() === 'static') {
      node.classList.add('fx-reveal', 'fx-revealed');
      return;
    }
    node.classList.add('fx-reveal');
    let unsubscribe = onScrollProgress(node, (progress) => {
      node.style.setProperty('--fx-draw', String(progress));
      node.style.setProperty('--fx-fade', String(Math.min(progress / FADE_SPAN, 1)));
      if (progress >= 1) {
        node.classList.add('fx-revealed');
        if (unsubscribe) { unsubscribe(); unsubscribe = null; }
      }
    });
  } catch (err) {
    console.error('[effects] scroll reveal disabled:', err);
    node.classList.add('fx-reveal', 'fx-revealed');
  }
}

export function initScrollReveal(root = document) {
  root.querySelectorAll('[data-reveal]').forEach((node) => {
    if (node.dataset.revealInit) return; // idempotent across HTMX swaps
    node.dataset.revealInit = '1';
    reveal(node);
  });
}
