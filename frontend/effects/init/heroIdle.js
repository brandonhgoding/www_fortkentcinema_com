// Pauses the hero's looping animations while it is scrolled out of view.
//
// Hero.css pauses the grain, the twinkle and the bulb chase under
// `.hero--offscreen`; this is the only thing that sets it. Without an
// IntersectionObserver the hero simply keeps animating, as before.

const CLASS = 'hero--offscreen';

function attach(hero) {
  const observer = new IntersectionObserver((entries) => {
    entries.forEach((entry) => {
      entry.target.classList.toggle(CLASS, !entry.isIntersecting);
    });
  });
  observer.observe(hero);
}

export function initHeroIdle(root = document) {
  if (typeof IntersectionObserver !== 'function') return;
  root.querySelectorAll('[data-neon]').forEach((hero) => {
    if (hero.dataset.heroIdleInit) return;
    hero.dataset.heroIdleInit = '1';
    try {
      attach(hero);
    } catch (err) {
      console.error('[effects] hero idle disabled:', err);
    }
  });
}
