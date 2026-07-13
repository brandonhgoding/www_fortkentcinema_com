# Conversion Tracking — Design

**Date:** 2026-07-13
**Status:** Approved

Item #5 of the July 2026 SEO backlog.

## Problem

GA4 reports **key events = 0**. It records pageviews and nothing else. There is no way to tell whether a membership was sold, a gift card bought, or the phone rung — which means there is no way to tell whether any of the SEO work in items #1–#4 actually did anything for the business.

The site has no online ticketing (tickets are sold at the box office), so every conversion is an **outbound click to Square** or a contact action.

## The trap: a click is not a purchase

The obvious implementation — fire `membership_join_click` with `value: 60` — makes GA4 report $60 of revenue for someone who bounced off the Square page without paying. The reports would systematically overstate sales, and they would be reports we make decisions on. That is worse than no tracking.

So conversions are measured in two distinct layers, and the money only ever attaches to the second:

1. **Intent** — outbound clicks. Real, useful, and incapable of lying because no value is attached.
2. **Purchase** — a `/thanks` page that Square redirects to *after payment succeeds*. It only loads if money actually changed hands.

Together they give a click → purchase conversion rate.

## 1. GA4 measurement ID → environment variable

`templates/base.html` hardcodes `G-S2PR27SWGD`, so local dev and any staging deploy send hits into production analytics.

```python
# settings.py
GA4_MEASUREMENT_ID = config("GA4_MEASUREMENT_ID", default="")
```

Exposed through the existing `web.context_processors.site_config`. The gtag snippet renders **only when the value is set** — absent in dev, absent in tests, present in production via `.env`.

This lands first. There is no point starting to trust these numbers while dev traffic mixes into them.

## 2. Click events — data-attribute driven

A single delegated listener in `static/js/analytics.js`. No inline `onclick`; templates declare intent and the JS does the work:

```html
<a href="{{ tier.checkout_url }}"
   data-track="membership_join_click"
   data-track-tier="{{ tier.slug }}">Join</a>
```

| Event | Params | Key event |
|---|---|---|
| `membership_join_click` | `tier` | yes |
| `giftcard_click` | — | yes |
| `phone_click` | `location` (`footer` / `rentals`) | yes |
| `rental_email_click` | — | yes |
| `trailer_play` | `film` | **no** |

**No `value` on any of these.** They are intent. Attaching money to a click is exactly the trap above.

`trailer_play` is fired but deliberately *not* marked as a key event — it is an engagement signal, and marking engagement as conversion pollutes the conversion rate. It is worth having to know which films draw interest.

## 3. `/thanks` — the purchase event

A new `ThanksView`. Fires `purchase` with `currency: "USD"` and a `value` **looked up server-side** from `MEMBERSHIP` in `web/constants.py`, keyed by the `?tier=` slug.

The value is never read from the query string. A visitor editing `?value=` in the URL must not be able to forge revenue.

An unknown or missing tier renders a generic thank-you and fires **no event at all**, rather than a garbage one. Gift cards have a variable amount, so they redirect here without a tier and get exactly that.

The page is `noindex` and is linked from nowhere.

**Known limitation, accepted:** this is trust-on-redirect. Anyone visiting `/thanks?tier=family` directly would fire a purchase event. Verifying properly means a Square webhook and server-side payment validation — heavy machinery for a two-screen cinema. The page is unlinked and noindexed, so realistically only Square redirects reach it.

### Square configuration (manual, post-deploy)

The five Payment Links must be repointed to redirect after payment:

| Tier | Redirect to |
|---|---|
| silver-screen | `https://www.fortkentcinema.com/thanks?tier=silver-screen` |
| individual | `https://www.fortkentcinema.com/thanks?tier=individual` |
| cinema-supporter | `https://www.fortkentcinema.com/thanks?tier=cinema-supporter` |
| family | `https://www.fortkentcinema.com/thanks?tier=family` |
| family-plus | `https://www.fortkentcinema.com/thanks?tier=family-plus` |

Until this is done, click events work and `purchase` never fires. The two layers are independent by design.

## 4. Key events in GA4

GA4's "New key event" registers an event name before it has ever been received, so all five can be pre-registered and will count from the first hit. `trailer_play` is not registered.

## Testing

- Data-attributes present on every tracked element (tier cards, gift card, both `tel:` links, the `mailto:`).
- `/thanks?tier=cinema-supporter` emits `purchase` with `value: 120`; an unknown tier emits no event; the value comes from `MEMBERSHIP`, not the query string.
- `/thanks` carries `noindex` and is absent from the sitemap.
- The gtag snippet is absent when `GA4_MEASUREMENT_ID` is unset (this is the dev/test default, so it is also the tests' own default).
- vitest unit tests for `analytics.js` against the existing `frontend/` harness.
- One Selenium e2e: click a tracked link, assert `dataLayer` received the event.

## Success criteria

- GA4 key events stops reading 0.
- A click → purchase conversion rate exists for membership.
- Production analytics no longer contains local-dev traffic.

Follows [per-movie pages](2026-07-13-per-movie-pages-design.md). This item is what makes the rest measurable.
