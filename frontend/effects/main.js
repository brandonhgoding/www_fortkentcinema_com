import { initAmbientDust } from './init/ambientDust.js';
import { initScrollReveal } from './init/scrollReveal.js';

function boot() {
  initAmbientDust(document);
  initScrollReveal(document);
}

if (document.readyState !== 'loading') {
  boot();
} else {
  document.addEventListener('DOMContentLoaded', boot);
}

// Re-arm scroll reveals on HTMX-swapped content (used from later plans).
document.body.addEventListener('htmx:afterSwap', (e) => initScrollReveal(e.target));
