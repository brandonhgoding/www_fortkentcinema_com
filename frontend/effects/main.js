import { initAmbientDust } from './init/ambientDust.js';
import { initScrollReveal } from './init/scrollReveal.js';
import { initNeonPowerOn } from './init/neonPowerOn.js';
import { initCursorBulbs } from './init/cursorBulbs.js';
import { initCardSpotlight } from './init/cardSpotlight.js';

function boot() {
  initAmbientDust(document);
  initScrollReveal(document);
  initNeonPowerOn(document);
  initCursorBulbs(document);
  initCardSpotlight(document);
}

if (document.readyState !== 'loading') {
  boot();
} else {
  document.addEventListener('DOMContentLoaded', boot);
}

// Re-arm scroll reveals and card spotlights on HTMX-swapped content (used
// from later plans).
document.body.addEventListener('htmx:afterSwap', (e) => {
  initScrollReveal(e.target);
  initCardSpotlight(e.target);
});
