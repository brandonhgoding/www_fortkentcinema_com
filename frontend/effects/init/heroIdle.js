// Pauses a hero's looping animations while it is scrolled out of view.
//
// Hero.css pauses the grain and the twinkle under
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
  // Both home folds (the film hero and the empty week) carry data-hero-idle.
  root.querySelectorAll('[data-hero-idle]').forEach((hero) => {
    if (hero.dataset.heroIdleInit) return;
    hero.dataset.heroIdleInit = '1';
    try {
      attach(hero);
    } catch (err) {
      console.error('[effects] hero idle disabled:', err);
    }
  });
}
