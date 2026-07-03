import { timer } from 'd3-timer';

const subscribers = new Set();
let loop = null;

function ensureLoop() {
  if (loop || subscribers.size === 0) return;
  loop = timer((elapsed) => {
    subscribers.forEach((fn) => {
      try {
        fn(elapsed);
      } catch (err) {
        console.error('[effects] tick subscriber threw; removing it:', err);
        subscribers.delete(fn);
      }
    });
  });
}

function stopLoop() {
  if (loop) {
    loop.stop();
    loop = null;
  }
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

export function tickSubscriberCount() {
  return subscribers.size;
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
