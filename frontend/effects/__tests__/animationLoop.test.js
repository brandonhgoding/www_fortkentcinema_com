import { describe, it, expect, vi } from 'vitest';
import { onTick } from '../core/animationLoop.js';

// The loop runs on requestAnimationFrame (vitest.setup.js shims it onto
// setTimeout when jsdom lacks it); frames are ~16ms, so the waits leave
// room for several.
describe('onTick', () => {
  it('calls a subscriber every frame with the time since the loop started', async () => {
    const seen = [];
    const off = onTick((elapsed) => seen.push(elapsed));
    await new Promise((r) => setTimeout(r, 100));
    off();
    expect(seen.length).toBeGreaterThan(1);
    expect(seen[0]).toBeGreaterThanOrEqual(0);
    expect(seen[seen.length - 1]).toBeGreaterThan(seen[0]);
  });

  it('stops calling once unsubscribed', async () => {
    const fn = vi.fn();
    const off = onTick(fn);
    await new Promise((r) => setTimeout(r, 60));
    off();
    const calls = fn.mock.calls.length;
    await new Promise((r) => setTimeout(r, 100));
    expect(fn.mock.calls.length).toBe(calls);
  });

  it('drops a subscriber that throws and keeps the others', async () => {
    const err = vi.spyOn(console, 'error').mockImplementation(() => {});
    const bad = vi.fn(() => { throw new Error('boom'); });
    const good = vi.fn();
    const offBad = onTick(bad);
    const offGood = onTick(good);
    await new Promise((r) => setTimeout(r, 100));
    offBad(); offGood();
    expect(bad).toHaveBeenCalledTimes(1);
    expect(good.mock.calls.length).toBeGreaterThan(1);
    err.mockRestore();
  });
});
