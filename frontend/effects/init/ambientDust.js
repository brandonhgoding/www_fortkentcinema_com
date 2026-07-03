import { onTick } from '../core/animationLoop.js';
import { onPointer } from '../core/pointer.js';
import { getMotionTier } from '../core/motionPrefs.js';

const REPEL_RADIUS = 70;
const MIN_FADE = 0.35;

function start(canvas) {
  const tier = getMotionTier();
  if (tier === 'static') return;
  try {
    const ctx = canvas.getContext('2d');
    if (!ctx) return;
    let width = 0;
    let height = 0;
    function resize() {
      width = canvas.width = window.innerWidth;
      height = canvas.height = window.innerHeight;
    }
    resize();
    const count = window.innerWidth < 700 ? 25 : 50;
    const motes = Array.from({ length: count }, () => ({
      x: Math.random() * width,
      y: Math.random() * height,
      r: Math.random() * 1.6 + 0.4,
      vx: (Math.random() - 0.5) * 0.15,
      vy: -(Math.random() * 0.2 + 0.05),
      a: Math.random() * 0.4 + 0.1,
    }));
    const cursor = { sx: -9999, sy: -9999 };
    if (tier === 'full') {
      onPointer((p) => { cursor.sx = p.sx; cursor.sy = p.sy; });
    }
    onTick(() => {
      ctx.clearRect(0, 0, width, height);
      const fade = Math.max(MIN_FADE, 1 - window.scrollY / (height * 2));
      motes.forEach((m) => {
        const dx = m.x - cursor.sx;
        const dy = m.y - cursor.sy;
        const dist = Math.hypot(dx, dy);
        if (dist < REPEL_RADIUS && dist > 0) {
          m.x += (dx / dist) * 1.1;
          m.y += (dy / dist) * 1.1;
        }
        m.x += m.vx;
        m.y += m.vy;
        if (m.y < -5) { m.y = height + 5; m.x = Math.random() * width; }
        if (m.x < -5) m.x = width + 5;
        if (m.x > width + 5) m.x = -5;
        ctx.beginPath();
        ctx.arc(m.x, m.y, m.r, 0, Math.PI * 2);
        ctx.fillStyle = `rgba(201, 168, 76, ${m.a * fade})`;
        ctx.fill();
      });
    });
    window.addEventListener('resize', resize);
  } catch (err) {
    console.error('[effects] ambient dust disabled:', err);
  }
}

export function initAmbientDust(root = document) {
  const canvas = root.querySelector('[data-ambient-dust]');
  if (!canvas || canvas.dataset.dustInit) return;
  canvas.dataset.dustInit = '1';
  start(canvas);
}
