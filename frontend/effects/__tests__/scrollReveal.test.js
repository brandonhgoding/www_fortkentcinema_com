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

  it('does not throw a TDZ error for an element already revealed on the initial synchronous progress call', () => {
    // Force the "full" motion tier: matchMedia present, nothing matches
    // (not reduced-motion, not coarse pointer).
    vi.stubGlobal('matchMedia', vi.fn().mockReturnValue({ matches: false }));
    vi.stubGlobal('innerHeight', 768);

    const el = document.getElementById('t');
    // Place the element at the very top of the viewport so
    // onScrollProgress's initial synchronous computeEntry() call yields
    // progress >= 1 immediately, before onScrollProgress even returns.
    el.getBoundingClientRect = () => ({ top: 0, bottom: 0, left: 0, right: 0, width: 0, height: 0 });

    const errorSpy = vi.spyOn(console, 'error').mockImplementation(() => {});

    expect(() => initScrollReveal(document)).not.toThrow();
    expect(el.classList.contains('fx-reveal')).toBe(true);
    expect(el.classList.contains('fx-revealed')).toBe(true);
    // The old buggy implementation hits a TDZ ReferenceError on the
    // synchronous initial callback; the outer try/catch swallows it and
    // logs via console.error, masking the bug as an uncaught-throw check
    // alone won't catch it. Assert no such fallback was triggered.
    expect(errorSpy).not.toHaveBeenCalled();

    errorSpy.mockRestore();
  });
});
