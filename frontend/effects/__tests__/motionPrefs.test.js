import { describe, it, expect, vi, afterEach } from 'vitest';
import { getMotionTier } from '../core/motionPrefs';

function stubMatchMedia(matching) {
  vi.stubGlobal(
    'matchMedia',
    vi.fn((query) => ({ matches: matching.includes(query), media: query })),
  );
}

describe('getMotionTier', () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('returns static when prefers-reduced-motion is set', () => {
    stubMatchMedia(['(prefers-reduced-motion: reduce)']);
    expect(getMotionTier()).toBe('static');
  });

  it('returns ambient on coarse-pointer (touch) devices', () => {
    stubMatchMedia(['(pointer: coarse)']);
    expect(getMotionTier()).toBe('ambient');
  });

  it('returns full when no constraint matches', () => {
    stubMatchMedia([]);
    expect(getMotionTier()).toBe('full');
  });

  it('returns static when matchMedia is unavailable', () => {
    vi.stubGlobal('matchMedia', undefined);
    expect(getMotionTier()).toBe('static');
  });

  it('returns static when matchMedia throws', () => {
    vi.stubGlobal(
      'matchMedia',
      vi.fn(() => {
        throw new Error('boom');
      }),
    );
    expect(getMotionTier()).toBe('static');
  });
});
