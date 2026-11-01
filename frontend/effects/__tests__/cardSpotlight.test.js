import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import { initCardSpotlight } from '../init/cardSpotlight.js';

// matchMedia that answers true for the given queries only.
function stubMatchMedia(matching) {
  vi.stubGlobal('matchMedia', (q) => ({ matches: matching.includes(q), media: q }));
}

// No spotlight node appended and no effect classes added to the grid.
function expectUntouched() {
  const grid = document.getElementById('g');
  expect(grid.children).toHaveLength(1);
  expect(grid.className).toBe('');
}

describe('initCardSpotlight', () => {
  beforeEach(() => {
    document.body.innerHTML = '<div data-spotlight id="g"><article>a</article></div>';
  });
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('attaches the spotlight on the full motion tier', () => {
    stubMatchMedia([]);
    initCardSpotlight(document);
    expect(document.getElementById('g').children).toHaveLength(2);
  });

  it('leaves the grid untouched under reduced motion', () => {
    stubMatchMedia(['(prefers-reduced-motion: reduce)']);
    initCardSpotlight(document);
    expectUntouched();
  });

  it('leaves the grid untouched on touch devices', () => {
    stubMatchMedia(['(pointer: coarse)']);
    initCardSpotlight(document);
    expectUntouched();
  });
});
