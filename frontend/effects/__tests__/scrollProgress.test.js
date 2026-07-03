import { describe, it, expect, vi, beforeEach } from 'vitest';
import { onScrollProgress, scrollSubscriberCount } from '../core/scrollProgress';

function nextFrame() {
  return new Promise((resolve) => requestAnimationFrame(() => resolve()));
}

function elementWithTop(top) {
  const el = document.createElement('div');
  el.getBoundingClientRect = () => ({
    top,
    bottom: top + 100,
    left: 0,
    right: 100,
    width: 100,
    height: 100,
  });
  document.body.appendChild(el);
  return el;
}

describe('scrollProgress', () => {
  beforeEach(() => {
    Object.defineProperty(window, 'innerHeight', { value: 800, configurable: true });
  });

  it('reports 0 when the element top sits at the viewport bottom', async () => {
    const cb = vi.fn();
    const el = elementWithTop(800);
    const unsubscribe = onScrollProgress(el, cb);
    await nextFrame();
    expect(cb).toHaveBeenCalledWith(0);
    unsubscribe();
  });

  it('reports interpolated progress and clamps at 1', async () => {
    const cb = vi.fn();
    const el = elementWithTop(560); // (800-560)/(800*0.6) = 0.5
    const unsubscribe = onScrollProgress(el, cb);
    await nextFrame();
    expect(cb).toHaveBeenLastCalledWith(0.5);

    el.getBoundingClientRect = () => ({
      top: 80, bottom: 180, left: 0, right: 100, width: 100, height: 100,
    }); // (800-80)/480 = 1.5 -> clamped to 1
    window.dispatchEvent(new Event('scroll'));
    await nextFrame();
    expect(cb).toHaveBeenLastCalledWith(1);
    unsubscribe();
  });

  it('only notifies when progress changes', async () => {
    const cb = vi.fn();
    const el = elementWithTop(560);
    const unsubscribe = onScrollProgress(el, cb);
    await nextFrame();
    const calls = cb.mock.calls.length;
    window.dispatchEvent(new Event('scroll')); // same rect, same progress
    await nextFrame();
    expect(cb.mock.calls.length).toBe(calls);
    unsubscribe();
  });

  it('delivers initial progress synchronously on subscribe (no flash frame)', () => {
    // jsdom has no IntersectionObserver, so entries start active:true here.
    // The synchronous computeEntry call is intentionally unconditional so the
    // guarantee also holds in real browsers where IO is present (active:false
    // initially) — without this, below-the-fold sections would paint visible
    // for one frame before the first IO callback hides them.
    const cb = vi.fn();
    const el = elementWithTop(560);
    const unsubscribe = onScrollProgress(el, cb);
    expect(cb).toHaveBeenCalledWith(0.5); // before any animation frame
    unsubscribe();
  });

  it('drops to zero subscribers and removes listeners on last unsubscribe', () => {
    const removeSpy = vi.spyOn(window, 'removeEventListener');
    const el = elementWithTop(0);
    const unsubscribe = onScrollProgress(el, () => {});
    expect(scrollSubscriberCount()).toBe(1);
    unsubscribe();
    expect(scrollSubscriberCount()).toBe(0);
    expect(removeSpy).toHaveBeenCalledWith('scroll', expect.any(Function));
    removeSpy.mockRestore();
  });
});
