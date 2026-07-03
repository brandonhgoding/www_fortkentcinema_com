// One scroll/resize listener + one IntersectionObserver for every subscribed
// element. The IO gates rect computation to elements near the viewport;
// where IO is unavailable (jsdom), every element is treated as active.

const REVEAL_SPAN = 0.6; // fully revealed once element top rises 60% of viewport

const entries = new Map(); // el -> { cb, progress, active }
let listening = false;
let rafId = 0;
let io = null;

function computeEntry(el, entry, vh) {
  const rect = el.getBoundingClientRect();
  const raw = (vh - rect.top) / (vh * REVEAL_SPAN);
  const progress = Math.max(0, Math.min(1, raw));
  if (progress !== entry.progress) {
    entry.progress = progress;
    entry.cb(progress);
  }
}

function compute() {
  rafId = 0;
  const vh = window.innerHeight;
  entries.forEach((entry, el) => {
    if (!entry.active) return;
    computeEntry(el, entry, vh);
  });
}

function schedule() {
  if (!rafId) rafId = requestAnimationFrame(compute);
}

function ensureIO() {
  if (io || typeof IntersectionObserver === 'undefined') return;
  io = new IntersectionObserver(
    (observed) => {
      observed.forEach((o) => {
        const entry = entries.get(o.target);
        if (entry) entry.active = o.isIntersecting;
      });
      schedule();
    },
    { rootMargin: '20% 0px' },
  );
}

export function onScrollProgress(el, cb) {
  ensureIO();
  const entry = { cb, progress: -1, active: !io };
  entries.set(el, entry);
  if (io) io.observe(el);
  if (!listening) {
    window.addEventListener('scroll', schedule, { passive: true });
    window.addEventListener('resize', schedule);
    listening = true;
  }
  // Deliver initial progress synchronously — even for entries IO will later
  // gate — so the first paint carries correct values (no flash frame).
  // (IO gating applies to all SUBSEQUENT computes inside compute() via the
  // `active` flag — that logic is left untouched.)
  computeEntry(el, entry, window.innerHeight);
  schedule();
  return () => {
    entries.delete(el);
    if (io) io.unobserve(el);
    if (entries.size === 0) {
      if (listening) {
        window.removeEventListener('scroll', schedule);
        window.removeEventListener('resize', schedule);
        listening = false;
      }
      if (rafId) {
        cancelAnimationFrame(rafId);
        rafId = 0;
      }
    }
  };
}

export function scrollSubscriberCount() {
  return entries.size;
}
