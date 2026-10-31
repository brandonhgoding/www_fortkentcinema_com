// One requestAnimationFrame loop shared by every per-frame effect, so the
// page never runs more than one. It only runs while something subscribes
// and the tab is visible.

const subscribers = new Set();
let frame = null;
let startedAt = null;

function step(now) {
  if (startedAt === null) startedAt = now;
  const elapsed = now - startedAt;
  subscribers.forEach((fn) => {
    try {
      fn(elapsed);
    } catch (err) {
      console.error('[effects] tick subscriber threw; removing it:', err);
      subscribers.delete(fn);
    }
  });
  frame = subscribers.size ? requestAnimationFrame(step) : null;
  if (frame === null) startedAt = null;
}

function ensureLoop() {
  if (frame !== null || subscribers.size === 0) return;
  if (typeof document !== 'undefined' && document.hidden) return;
  frame = requestAnimationFrame(step);
}

function stopLoop() {
  if (frame !== null) {
    cancelAnimationFrame(frame);
    frame = null;
  }
  startedAt = null;
}

// Subscribe a per-frame callback. Returns an unsubscribe function.
// NOTE: `elapsed` is relative to the current loop instance and resets to ~0
// after any pause (tab hidden/shown, drain-to-zero). Do not treat it as a
// monotonic clock across the lifetime of the page.
export function onTick(fn) {
  subscribers.add(fn);
  ensureLoop();
  return () => {
    subscribers.delete(fn);
    if (subscribers.size === 0) stopLoop();
  };
}

// Pause the whole loop while the tab is hidden; resume on return.
if (typeof document !== 'undefined') {
  document.addEventListener('visibilitychange', () => {
    if (document.hidden) {
      stopLoop();
    } else {
      ensureLoop();
    }
  });
}
