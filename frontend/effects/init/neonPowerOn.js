import { getMotionTier } from '../core/motionPrefs.js';

export const POWER_ON_STORAGE_KEY = 'fkc-neon-power-on';

const BULB_START = 200; // ms before first bulb ignites
const BULB_STAGGER = 45; // ms between bulbs
const POWER_ON_TOTAL = 2500; // full sequence duration

// Scripted neon sputter for the title (opacity values; glow scales with
// opacity because text-shadow inherits element alpha).
const FLICKER_STEPS = [
  { at: 1300, opacity: '0.7' },
  { at: 1420, opacity: '0.15' },
  { at: 1500, opacity: '0.9' },
  { at: 1610, opacity: '0.3' },
  { at: 1700, opacity: '1' },
  { at: 1780, opacity: '0.5' },
  { at: 1900, opacity: '1' },
];

function hasPlayed() {
  try {
    return sessionStorage.getItem(POWER_ON_STORAGE_KEY) === '1';
  } catch {
    return false;
  }
}

function markPlayed() {
  try {
    sessionStorage.setItem(POWER_ON_STORAGE_KEY, '1');
  } catch {
    // Private browsing edge case: the sequence simply replays next visit.
  }
}

function shouldSkip() {
  try {
    return getMotionTier() === 'static' || hasPlayed();
  } catch {
    return true;
  }
}

function goLive(hero) {
  hero.classList.remove('hero--pre-show');
  hero.classList.add('hero--live');
  hero.dispatchEvent(new CustomEvent('neon:live'));
}

function attach(hero) {
  try {
    if (shouldSkip()) {
      goLive(hero);
      return;
    }

    // No-flash guarantee: this runs synchronously during DOM-scan init, before
    // the browser paints the boot frame, mirroring the SPA's useLayoutEffect
    // timing. effects.css (which darkens via this class) ships in the same
    // bundle as hero styles — the default CSS state is the lit marquee.
    hero.classList.add('hero--pre-show');
    const title = hero.querySelector('.marquee-title');
    if (title) title.style.opacity = '0.06';

    hero.querySelectorAll('.bulb').forEach((bulb, i) => {
      setTimeout(() => bulb.classList.add('bulb--lit'), BULB_START + i * BULB_STAGGER);
    });

    if (title) {
      FLICKER_STEPS.forEach((step) => {
        setTimeout(() => {
          title.style.opacity = step.opacity;
        }, step.at);
      });
    }

    setTimeout(() => {
      if (title) title.style.opacity = '';
      hero.querySelectorAll('.bulb--lit').forEach((bulb) => {
        bulb.classList.remove('bulb--lit');
      });
      markPlayed();
      goLive(hero);
    }, POWER_ON_TOTAL);
  } catch (err) {
    console.error('[effects] neon power-on disabled:', err);
    // Remove pre-show darkness so the hero is never stuck in a dark state.
    goLive(hero);
  }
}

export function initNeonPowerOn(root = document) {
  root.querySelectorAll('[data-neon]').forEach((hero) => {
    if (hero.dataset.neonInit) return;
    hero.dataset.neonInit = '1';
    attach(hero);
  });
}
