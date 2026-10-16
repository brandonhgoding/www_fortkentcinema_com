import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import { initHeroIdle } from '../init/heroIdle.js';

// A stand-in IntersectionObserver that hands the callback back to the test.
function stubObserver() {
  const state = { callback: null, observed: [] };
  vi.stubGlobal(
    'IntersectionObserver',
    class {
      constructor(callback) {
        state.callback = callback;
      }
      observe(el) {
        state.observed.push(el);
      }
      disconnect() {}
    },
  );
  return state;
}

describe('initHeroIdle', () => {
  beforeEach(() => {
    document.body.innerHTML = '<section class="hero" data-neon id="h"></section>';
  });
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('marks the hero offscreen when it leaves the viewport and clears it when it returns', () => {
    const io = stubObserver();
    initHeroIdle(document);
    const hero = document.getElementById('h');
    expect(io.observed).toEqual([hero]);

    io.callback([{ target: hero, isIntersecting: false }]);
    expect(hero.classList.contains('hero--offscreen')).toBe(true);

    io.callback([{ target: hero, isIntersecting: true }]);
    expect(hero.classList.contains('hero--offscreen')).toBe(false);
  });

  it('leaves the hero alone when the browser has no IntersectionObserver', () => {
    vi.stubGlobal('IntersectionObserver', undefined);
    expect(() => initHeroIdle(document)).not.toThrow();
    expect(document.getElementById('h').classList.contains('hero--offscreen')).toBe(false);
  });

  it('attaches once per hero', () => {
    const io = stubObserver();
    initHeroIdle(document);
    initHeroIdle(document);
    expect(io.observed).toHaveLength(1);
  });
});
