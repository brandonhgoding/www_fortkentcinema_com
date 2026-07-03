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
});
