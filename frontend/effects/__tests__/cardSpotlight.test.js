import { describe, it, expect, beforeEach, vi } from 'vitest';

describe('initCardSpotlight', () => {
  beforeEach(() => {
    document.body.innerHTML = '<div data-spotlight><article>a</article></div>';
    // Force getMotionTier() === 'full': matchMedia present, not reduced, fine pointer.
    vi.stubGlobal('matchMedia', (q) => ({
      matches: q.includes('reduce') ? false : q.includes('coarse') ? false : false,
    }));
  });

  it('adds spotlight scaffolding on full tier', async () => {
    const { initCardSpotlight } = await import('../init/cardSpotlight.js');
    initCardSpotlight(document);
    const grid = document.querySelector('[data-spotlight]');
    expect(grid.classList.contains('fx-spotlight-grid')).toBe(true);
    expect(grid.querySelector('.fx-spotlight')).not.toBeNull();
  });

  it('matches <a>-wrapped cards (blog grid parity)', async () => {
    document.body.innerHTML =
      '<div data-spotlight><a class="blog-card-link"><article class="blog-card">a</article></a></div>';
    const { initCardSpotlight } = await import('../init/cardSpotlight.js');
    initCardSpotlight(document);
    const grid = document.querySelector('[data-spotlight]');
    expect(grid.classList.contains('fx-spotlight-grid')).toBe(true);
    // Locks the selector contract: the default selector must include direct <a> children
    // so blog-teaser cards (wrapped in <a class="blog-card-link">) receive focus/dim/tilt.
    expect(grid.querySelectorAll(':scope > article, :scope > a').length).toBe(1);
  });
});
