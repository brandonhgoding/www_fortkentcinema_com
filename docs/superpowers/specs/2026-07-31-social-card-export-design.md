# Social Card Export — Design

**Date:** 2026-07-31
**Status:** Approved, ready for plan

## Problem

Promoting an engagement on Facebook or Instagram currently means hand-building
an image in Canva from the Fort Kent Cinema YouTube thumbnail template
(`fkc-thumbnail-template-blank.png`): dark navy field, glowing cream/gold
geometric type, an outlined category badge, a vertical marquee bulb strip, a
pine-tree silhouette along the bottom, and a framed area for artwork. Every post
repeats that work by hand, and the results drift from each other.

The dashboard already knows everything the image needs — title, run dates, film
posters. We want a button.

## Scope

A "Social Images" panel on the engagement detail page that renders theme-matched
PNGs on demand:

- **Facebook** — 1200 × 630 landscape
- **Instagram** — 1080 × 1080 square

Each with a **Coming Soon** / **Now Playing** badge toggle, the engagement's run
dates, and the fixed line `VISIT WWW.FORTKENTCINEMA.COM FOR SHOWTIMES`.

Out of scope: Instagram Stories (1080 × 1920), posting to the platforms
directly, caption text generation, storing rendered images, and any use of these
cards on the public site (Open Graph images remain a separate concern).

## Rendering approach

**Server-side Pillow**, already a dependency. Chosen over browser-canvas and
html2canvas because:

- The server fetches TMDB artwork directly — no CORS or tainted-canvas problem.
- Output is deterministic and unit-testable in the existing Django suite.
- No new JavaScript dependency.

The costs accepted: glow and typography are hand-coded rather than free from
CSS, and real `.ttf` font files must be vendored — Pillow cannot read the
`.woff2` files in `static/fonts/`.

## Module layout

New package `cinema/social_cards/`, modeled on the existing `cinema/tmdb/`
package. It lives in `cinema` rather than `dashboard` because it is engagement
domain logic; the dashboard is only its first consumer.

| File | Responsibility |
| --- | --- |
| `theme.py` | Palette, font paths, glow parameters, canvas dimensions. Single source of the look. |
| `card.py` | `CardData` dataclass and `CardData.from_engagement()`. Pure Python, no Pillow. |
| `posters.py` | Fetch artwork bytes with timeout and cache; return a PIL image or `None`. |
| `draw.py` | Primitives: glowing text, marquee bulbs, tree silhouette, gradient fade, fit-and-wrap text. |
| `layouts.py` | `render_facebook(card)` and `render_instagram(card)` — composition only. |
| `fonts/` | Vendored `Poppins-ExtraBold.ttf` and `Poppins-SemiBold.ttf` (SIL Open Font License). |

Keeping `card.py` free of Pillow is deliberate: every content rule below is
testable without rendering a pixel.

### Boundaries

- `card.py` depends on `cinema.models` only. It answers: *what text and which
  artwork URLs go on this card?*
- `posters.py` depends on `requests`, Django's cache, and Pillow. It answers:
  *give me a usable image for this URL, or nothing.*
- `draw.py` depends on Pillow and `theme.py` only. It knows nothing about
  engagements.
- `layouts.py` composes the three. It is the only module that knows where things
  sit on the canvas.

## Content rules

These live in `CardData` and are the bulk of what gets tested.

### Badge

Two values: `COMING SOON` and `NOW PLAYING`.

Default when the panel first loads: `COMING SOON` if
`engagement.start_date > today`, otherwise `NOW PLAYING`. The toggle always
overrides — the default is a convenience, never a constraint.

### Headline

`engagement.display_title`, which already resolves `event_title` when set and
joins multiple films as `Film A + Film B`.

Rendered uppercase, auto-fitted: begin at the layout's maximum size, wrap to the
available column width, and shrink by a fixed step until the wrapped block fits
the allotted box, down to a minimum size. If the block still does not fit at the
minimum size, it renders at that size and is allowed to overflow the box rather
than shrinking further — a title that long is a signal to set a shorter
`event_title`, not a reason to render something illegible.

When the headline wraps to two or more lines, the **final line renders gold**
and the preceding lines cream, matching the template's `YOUR HEADLINE` / `HERE`
treatment. A headline that fits on one line renders entirely cream.

An engagement with no films and no `event_title` yields an empty
`display_title`; the headline falls back to `FORT KENT CINEMA` and the artwork
area renders as an empty framed panel.

### Date line

Phrased per badge, uppercase:

| Case | Badge | Output |
| --- | --- | --- |
| Multi-day | `NOW PLAYING` | `NOW THROUGH AUGUST 14` |
| Multi-day | `COMING SOON` | `STARTS AUGUST 8` |
| `start_date == end_date` | either | `ONE NIGHT ONLY · AUGUST 8` |

Month names are spelled out in full. No year is shown — these are posted within
days of the run.

### Fixed elements

Every card, both platforms, both badges:

- `FORT KENT CINEMA` wordmark in gold beneath the date line.
- A bottom strip reading `VISIT WWW.FORTKENTCINEMA.COM FOR SHOWTIMES`.

## Artwork

### Source selection

`CardData` resolves an ordered list of artwork sources, one per film on the
engagement:

- **Facebook** and **double-feature panels** use `film.poster_url`. Both target
  areas are portrait-shaped, so a 2:3 poster drops in with minimal cropping.
- **Instagram's single-film band is landscape** (1080 × 600). It prefers
  `film.backdrop_url`, which is 16:9 and composed for that shape. When the film
  has no backdrop it falls back to `film.poster_url`, cropped with a **bias
  toward the top of the image** — posters place key art in the upper portion and
  title treatments and credits at the bottom, so a centered crop is the wrong
  default.

When a film has neither poster nor backdrop, or the fetch fails, the artwork
area renders as a dark panel with a thin gold dashed border — the template's
empty state. The card still renders; artwork is never load-bearing.

### Resolution

`Film.poster_url` stores TMDB `w500` URLs, which upscale poorly to a 1080-wide
canvas. When a URL matches the TMDB pattern `image.tmdb.org/t/p/w<N>/`, the size
segment is rewritten to `original` before fetching. URLs that do not match are
used verbatim.

Fetches use a short timeout and are rejected if the response exceeds a size
guard (5 MB) or the decoded image exceeds 8000 px on either axis. Successful
fetches are cached by URL in the Django cache for 24 hours. The rendered PNG is
**not** cached — it must always reflect the current state of the engagement.

## Layouts

Both share the same background treatment: a radial dark-navy field, the pine
tree silhouette along the bottom edge, a glowing gold marquee bulb strip as the
seam between artwork and type, and the bottom URL strip.

**Facebook (1200 × 630)** — type on the left, artwork full-bleed off the right
edge fading into the background, vertical bulb strip at the seam. Reading order
down the left column: badge, headline, date line, wordmark.

**Instagram (1080 × 1080)** — artwork occupies the top band edge to edge, fading
into solid dark; the badge overlays its top-left corner. A horizontal bulb strip
marks the seam. Headline, date line, and wordmark stack in the lower portion on
solid background, so type never competes with artwork.

Two-film engagements split the artwork area into two equal panels, one film
each. Three or more films — rare, but `EngagementFilm` permits it — use the
first two.

### Glow

Text glow is produced by rendering the glyphs to a transparent layer, applying
two Gaussian blurs at different radii (tight and wide), tinting them cream and
gold respectively, compositing both beneath the crisp text.

## Delivery

One view, registered as:

```
GET /dashboard/engagements/<int:pk>/social/<platform>.png
```

`<platform>` is `facebook` or `instagram`; anything else returns 400. Unknown
`pk` returns 404. Access is gated by the existing `StaffRequiredMixin`.

Query parameters:

- `badge` — `now_playing` or `coming_soon`. Omitted or unrecognised falls back
  to the date-derived default.
- `download` — when present, the response carries
  `Content-Disposition: attachment` with a filename of the form
  `fkc-<title-slug>-<badge>-<platform>.png`, where `<title-slug>` is the
  slugified `display_title`, or `engagement-<pk>` when that slug is empty.
  Omitted, the image is served inline.

The inline form is what the preview `<img>` requests; the download form is what
the buttons link to.

## Dashboard UI

A `dashboard/templates/dashboard/_social_cards.html` partial, included on the
engagement detail page as a card in the existing grid:

- A two-option badge toggle, pre-selected from the date-derived default.
- A preview `<img>` pointing at the inline Instagram URL.
- Two download buttons, Facebook and Instagram.

Toggling the badge rewrites the preview `src` and both button `href`s in
JavaScript. No htmx round trip — there is no server-rendered state to swap, only
three URLs to update. Styles go in a new
`dashboard/static/dashboard/css/social_cards.css`, matching the existing
per-page stylesheet convention.

## Testing

`cinema/tests/test_social_cards.py`:

- Badge default derives correctly from `start_date` relative to today, on both
  sides of the boundary and on the start date itself.
- Date line phrasing for each badge, multi-day and single-day, including a run
  that crosses a month boundary.
- Headline resolution: single film, two films, `event_title` override, no films.
- Headline auto-fit shrinks and wraps a long title; the final line is gold only
  when the headline wraps.
- TMDB URL size rewriting, including a non-TMDB URL passing through untouched.
- Instagram artwork prefers backdrop, falls back to poster, and tolerates
  neither being present.
- Poster fetch failure, timeout, and oversize response all yield `None` rather
  than raising.
- Render smoke tests: each layout returns a PNG of the expected dimensions
  containing more than one distinct pixel value.

`dashboard/tests/test_social_cards.py`:

- Anonymous users are redirected; authenticated non-staff get 403.
- Unknown `pk` → 404; unknown platform → 400.
- Response is `image/png`.
- `download` present → `Content-Disposition: attachment` with the expected
  filename; absent → inline.
- The engagement detail page renders the social panel with both download links.

All artwork fetches are mocked. No test touches the network.

## Dependencies

No new Python packages — Pillow and `requests` are both already in
`requirements.txt`. Two Poppins `.ttf` files are vendored into the repository
under `cinema/social_cards/fonts/`, with their SIL Open Font License text
alongside them.
