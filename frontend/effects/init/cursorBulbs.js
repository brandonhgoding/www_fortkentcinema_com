import { scaleLinear } from 'd3-scale';
import { easeCubicOut } from 'd3-ease';
import { onPointer } from '../core/pointer.js';
import { getMotionTier } from '../core/motionPrefs.js';

const RADIUS = 90; // px around the cursor where bulbs react

function attach(hero) {
  if (getMotionTier() !== 'full') return;
  try {
    const bulbs = Array.from(hero.querySelectorAll('.bulb'));
    if (bulbs.length === 0) return;

    const intensity = scaleLinear().domain([RADIUS, 0]).range([0, 1]).clamp(true);
    let unsubscribe = null;

    const start = () => {
      if (unsubscribe) return;
      unsubscribe = onPointer((p) => {
        bulbs.forEach((bulb) => {
          const rect = bulb.getBoundingClientRect();
          const dx = p.sx - (rect.left + rect.width / 2);
          const dy = p.sy - (rect.top + rect.height / 2);
          const k = easeCubicOut(intensity(Math.hypot(dx, dy)));
          if (k > 0.01) {
            bulb.style.transform = `scale(${1 + 0.4 * k})`;
            bulb.style.boxShadow =
              `0 0 ${6 + 12 * k}px #fff4c0, ` +
              `0 0 ${12 + 22 * k}px rgba(201, 168, 76, ${0.3 + 0.5 * k})`;
          } else if (bulb.style.transform) {
            bulb.style.transform = '';
            bulb.style.boxShadow = '';
          }
        });
      });
    };

    // Cursor bulbs only react once the neon power-on sequence has gone live
    // (either because it already finished/skipped, or via the event fired
    // by neonPowerOn.js when it does).
    if (hero.classList.contains('hero--live')) {
      start();
    } else {
      hero.addEventListener('neon:live', start, { once: true });
    }
  } catch (err) {
    console.error('[effects] cursor bulbs disabled:', err);
  }
}

export function initCursorBulbs(root = document) {
  root.querySelectorAll('[data-cursor-bulbs]').forEach((hero) => {
    if (hero.dataset.cursorBulbsInit) return;
    hero.dataset.cursorBulbsInit = '1';
    attach(hero);
  });
}
