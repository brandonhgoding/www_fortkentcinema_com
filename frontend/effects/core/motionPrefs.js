// Motion tiers: 'static' = no motion (reduced-motion or no matchMedia),
// 'ambient' = motion but no cursor-driven effects (touch devices),
// 'full' = everything.
export function getMotionTier() {
  try {
    if (typeof window === 'undefined' || typeof window.matchMedia !== 'function') {
      return 'static';
    }
    if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) {
      return 'static';
    }
    if (window.matchMedia('(pointer: coarse)').matches) {
      return 'ambient';
    }
    return 'full';
  } catch {
    return 'static';
  }
}
