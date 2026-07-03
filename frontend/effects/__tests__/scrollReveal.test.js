import { describe, it, expect, beforeEach, vi } from 'vitest';
import { initScrollReveal } from '../init/scrollReveal.js';

describe('initScrollReveal', () => {
  beforeEach(() => {
    document.body.innerHTML = '<div data-reveal id="t">hi</div>';
  });

  it('marks elements revealed immediately under reduced motion', () => {
    // Force the "static" tier: no matchMedia => getMotionTier() === 'static'
    vi.stubGlobal('matchMedia', undefined);
    initScrollReveal(document);
    const el = document.getElementById('t');
    expect(el.classList.contains('fx-reveal')).toBe(true);
    expect(el.classList.contains('fx-revealed')).toBe(true);
  });
});
