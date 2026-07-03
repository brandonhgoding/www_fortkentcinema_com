import { onTick } from './animationLoop';

const SMOOTHING = 0.15;

const subscribers = new Set();
// x/y = raw cursor, sx/sy = smoothed (lerped) position effects should use.
const pointer = { x: -9999, y: -9999, sx: -9999, sy: -9999 };
let stopTick = null;
let listening = false;

function handleMove(event) {
  // First movement: snap the smoothed position so effects don't sweep
  // in from offscreen.
  if (pointer.sx === -9999) {
    pointer.sx = event.clientX;
    pointer.sy = event.clientY;
  }
  pointer.x = event.clientX;
  pointer.y = event.clientY;
}

function teardownIfEmpty() {
  if (subscribers.size !== 0) return;
  if (listening) {
    window.removeEventListener('mousemove', handleMove);
    listening = false;
  }
  if (stopTick) {
    stopTick();
    stopTick = null;
  }
}

function tick() {
  pointer.sx += (pointer.x - pointer.sx) * SMOOTHING;
  pointer.sy += (pointer.y - pointer.sy) * SMOOTHING;
  subscribers.forEach((fn) => {
    try {
      fn(pointer);
    } catch (err) {
      console.error('[effects] pointer subscriber threw; removing it:', err);
      subscribers.delete(fn);
      teardownIfEmpty();
    }
  });
}

export function onPointer(fn) {
  subscribers.add(fn);
  if (!listening) {
    window.addEventListener('mousemove', handleMove);
    listening = true;
  }
  if (!stopTick) stopTick = onTick(tick);
  return () => {
    subscribers.delete(fn);
    teardownIfEmpty();
  };
}

export function pointerSubscriberCount() {
  return subscribers.size;
}
