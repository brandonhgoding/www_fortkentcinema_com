# Crawl Leaks + Housekeeping — Design

**Date:** 2026-07-13
**Status:** Approved

Items #9 and #10 of the July 2026 SEO backlog, shipped as one cleanup pass.

## #9 — Crawl leaks

### The calendar is an unbounded crawl trap

`/calendar/<year>/<month>/` serves a bare HTML fragment: no `<html>`, no `<head>`, no `<title>`, no `robots` meta. It carries prev/next navigation, and the view validates only `datetime.MINYEAR <= year <= datetime.MAXYEAR`.

`/calendar/1900/0/` returns **200**. A crawler following prev/next can walk roughly **120,000 URLs** of thin, near-empty content.

Two fixes, belt and braces:

1. **`X-Robots-Tag: noindex, nofollow`** on the response. A `<meta name="robots">` is impossible — there is no `<head>` to put it in — so the HTTP header is the only mechanism available. `nofollow` is the part that actually closes the trap: it stops Google walking prev/next.
2. **Bound the year range** to ±2 years of today; outside that, 404. The trap must not depend on a crawler honouring a header.

### robots.txt

Add `Disallow` for `/dashboard/`, `/login`, `/logout/`.

**Deliberately NOT disallowing `/calendar/`.** A disallowed URL is never fetched, so Google would never see the `noindex` on any calendar URL it already holds. Disallow and noindex are mutually defeating here; noindex is the one that removes content from the index.

## #10 — Housekeeping

### og:image is a 3.5MB camera original

`static/img/og-image.jpg` is **5760×3844, 3,699,584 bytes** — a raw photo that was never resized. It is the fallback `og:image` for every page. Crawlers time out fetching it, so link previews on Facebook, Twitter, iMessage and Slack are almost certainly failing today.

Resize to **1200×630** (the OG spec's aspect ratio, center-cropped from the 3:2 original) at under ~300KB.

### `BlogPosting` JSON-LD on post detail

`post_detail.html` already sets `og:type=article` but emits no structured data, despite having title, subtitle, author, `post_date` and `header_image` on hand.

Note `BlogPost` has no `updated_at`/`modified` field, so `dateModified` cannot be emitted honestly. It is omitted rather than faked with `post_date`.

### `FAQPage` JSON-LD on /membership

`MEMBERSHIP_FAQ` in `web/constants.py` is already a literal Q&A list, already rendered on the page. A free rich result that has been sitting unclaimed.

### Dynamic `/classics` title

The page renders a specific `next_screening` film but hardcodes `Classic Movie Night — Fort Kent Cinema`. Name the film in the title and description; fall back to the static text when nothing is scheduled.

## Not doing

**`apple-touch-icon` points at an SVG**, which iOS does not support — iPhone home-screen bookmarks get a blank icon. The fix is a 180×180 PNG, but that means rasterising `favicon.svg` and making cropping/padding decisions about the brand mark. Flagged for Brandon rather than guessed at.

## Testing

- `X-Robots-Tag: noindex, nofollow` present on `/calendar/`, absent on real pages.
- Out-of-range calendar years 404; in-range still 200.
- robots.txt disallows `/dashboard/`, `/login`, `/logout/` and does **not** disallow `/calendar/`.
- og-image is 1200×630 and under 300KB.
- `BlogPosting` and `FAQPage` JSON-LD parse, and carry the real values.
- `dateModified` is absent from `BlogPosting` (no field backs it).
- `/classics` title names the scheduled film, and degrades to the static title when nothing is scheduled.
