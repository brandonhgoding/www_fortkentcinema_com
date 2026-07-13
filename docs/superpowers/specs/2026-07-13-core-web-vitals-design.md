# Core Web Vitals — Design

**Date:** 2026-07-13
**Status:** Approved

Item #6 of the July 2026 SEO backlog.

## Correcting the original audit

The audit blamed images: "no `width`/`height` → guaranteed layout shift", "0 good URLs driven by images". **That was wrong.**

Measured (Lighthouse, mobile, simulated 4G):

| Metric | Value | |
|---|---|---|
| Performance | 81 | |
| **LCP** | **3.9s** | FAIL |
| **FCP** | **3.0s** | FAIL |
| Speed Index | 4.1s | FAIL |
| **CLS** | **0.00** | fine |
| TBT | 10ms | fine |
| TTFB | 190ms (server) | fine |

CLS is already zero. There is no layout shift to fix.

The LCP element is a **text heading** (`<h2 class="section-title">NOW SHOWING`), and **83% of its time is render delay** — the browser idle, waiting for CSS.

## The actual critical path

```
HTML                                     669ms
 └─> global.css (3KB)                    146ms
      ├─> fonts.googleapis.com/css2      603ms   <- @import, cross-origin
      │    └─> 5 x fonts.gstatic.com     ~600ms each  <- a THIRD host
      └─> variables.css                  580ms   <- @import
 └─> 14 more stylesheets                 146-707ms each
```

Longest chain: **2,228ms**. Worst single render-blocking resource: `fonts.googleapis.com` at **911ms**.

`static/css/global.css` lines 1–2:

```css
@import url('https://fonts.googleapis.com/css2?family=Playfair+Display...&display=swap');
@import './variables.css';
```

A CSS `@import` is the worst way to load anything. The browser cannot *discover* it until `global.css` has been downloaded and parsed; it then opens a fresh cross-origin connection (DNS + TCP + TLS), which chains to *another* host for the font files. Four levels deep, every level blocking paint.

Total CSS across the homepage is ~25KB. **The bytes are irrelevant. The round trips are everything.**

## Changes

### 1. Self-host the fonts

woff2 files for Playfair Display, Cormorant Garamond and Poiret One into `static/fonts/`, and a new `static/css/fonts.css` with `@font-face` declarations carrying `font-display: swap` (preserving current behaviour — no invisible-text flash). Both `@import`s leave `global.css`.

Removes **both** third-party hosts from the critical path: no DNS, no TCP, no TLS to Google. The fonts inherit our own 1-year cache headers.

All three faces are OFL-licensed; self-hosting is permitted.

### 2. One CSS bundle

`frontend/styles/main.css` imports every stylesheet in cascade order (`variables` → `fonts` → `global` → `effects` → components → pages). Vite builds `static/css/bundle.css` — the same build workflow already used for `effects.js`.

`base.html` links it once. Every `{% block extra_css %}` and its 15 `<link>` tags are removed. Source files stay where they are; only delivery changes.

Lighthouse estimates ~1,680ms saved. Second pageview downloads zero CSS.

### 3. Preconnect to `image.tmdb.org`

Posters come from there and the connection starts cold (~160ms).

### 4. Lazy-load offscreen images

`loading="lazy"` + `decoding="async"` on posters — 137KB nobody scrolls to. **The first now-showing poster stays eager:** lazy-loading an above-the-fold image delays LCP, which is the opposite of the goal.

### 5. `WHITENOISE_MAX_AGE` = 1 year

Assets are hash-named, so they are safe to cache indefinitely. Currently 30 days.

## Not doing

- **`width`/`height` for CLS.** CLS is 0.00. Adding markup to fix a problem that does not exist is noise.
- **Critical-CSS inlining.** Needs an extraction step and rots as styles change. Bundling gets most of the win for a fraction of the complexity.
- **`srcset` on posters** (Lighthouse: 81KB). Real but secondary; revisit after measuring the above.

## Out of scope — HTTP/2 (Brandon must do this)

The site serves **HTTP/1.1**. Lighthouse: "24 requests not served via HTTP/2." With HTTP/1.1's ~6-connection-per-host limit, every request queues — this is the amplifier under everything above.

The fix is one line in nginx (`listen 443 ssl http2;` or `http2 on;` in newer nginx), but **nginx config lives in a separate ansible repo** and is not editable from here. Bundling reduces the request count enough that this matters less than it does today, but it remains free performance.

## Testing

- `base.html` links exactly one stylesheet.
- No `fonts.googleapis.com` or `fonts.gstatic.com` reference anywhere in templates or shipped CSS.
- No `@import` in the built bundle.
- The bundle contains rules from every source stylesheet (a smoke check that the cascade order held and nothing was dropped).
- Font files are served from our own origin, and `collectstatic` rewrites the `@font-face` URLs to their hashed names — **verify empirically, do not assume**: Django's `ManifestStaticFilesStorage` rewriting of `url()` inside a vite-built bundle is the fragile seam in this change.
- The first now-showing poster is eager; subsequent posters are lazy.
- Before/after Lighthouse on production, with numbers reported rather than an improvement asserted.

## Success criteria

- LCP under 2.5s; FCP under 1.8s.
- Search Console mobile Core Web Vitals moves off "0 good URLs".
- Render-blocking resources: one stylesheet, no third-party font hosts.
