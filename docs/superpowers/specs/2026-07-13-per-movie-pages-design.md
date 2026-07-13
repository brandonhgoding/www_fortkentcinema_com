# Per-Movie Pages + Movie/ScreeningEvent Structured Data — Design

**Date:** 2026-07-13
**Status:** Approved

Covers items #3 and #4 of the July 2026 SEO backlog. They ship together: the structured data belongs on the movie page, and doing them separately means two passes over the same templates.

## Problem

There are no per-movie pages. A film exists only as a card on `/` or `/classics/`, and the homepage title never names a currently-playing film. So every query with local film intent — "the odyssey fort kent showtimes", "project hail mary fort kent" — has no page to land on. This is the site's largest non-brand content gap.

Separately, the site emits no `Movie` and no `ScreeningEvent` structured data. Search Console reports **no rich-result enhancements at all**. Showtimes are the commercial point of the site and are invisible to Google's rich results, despite `Showtime.starts_at`, `Film.runtime_minutes`, `Film.rating` and `Film.imdb_id` all being present.

## The thin-content trap

The obvious implementation — a page per `Film`, prose from `Film.overview` — walks straight back into the hole we just climbed out of with the blog.

`Film.overview` is the **TMDB blurb**. The identical text sits on TMDB, IMDb, and every other cinema site in the country. A page whose only prose is a TMDB overview is a duplicate-content page. Ship 66 of them and Google files them under "crawled, currently not indexed" — exactly what happened to the blog.

What makes these pages *ours* is the local data nobody else has: our showtimes, our run dates, our screen and format, our member pricing, and our own review where one exists.

**Therefore: a film gets a page only once it has been booked at least once** (≥1 `Engagement`).

Of 66 films in the catalog:

| | |
|---|---|
| 6 | upcoming showtimes — strong pages |
| 40 | past engagements — real run history, unique to us |
| **20** | **never booked — nothing local to say. No page.** |

Those 20 are catalog entries, not pages. Excluding them costs nothing: a film that was never booked never had a URL, so there is no 404 to create.

Pages are still permanent in the sense that matters. Booking is additive — once a film has an engagement it keeps its page forever, and a run ending turns the page into an archive rather than deleting it. We do not repeat the disappearing-URL mistake that `/archive/<movie>` and `/coming-soon/` made.

## Model changes

```python
class Film(models.Model):
    slug = models.SlugField(max_length=200, unique=True, blank=True, null=True)
    review = models.ForeignKey(
        "blog.BlogPost", null=True, blank=True,
        on_delete=models.SET_NULL, related_name="films",
    )
```

- **`slug`** — backfilled from `slugify(title)` in the migration. No collisions in the current catalog, but remakes will collide eventually (*The Little Mermaid*, *The Mummy*), so generation appends a numeric suffix on conflict rather than raising `IntegrityError`.
- **`review`** — optional. Most films will never have one; that is expected and the template must degrade cleanly.

`Film` has no release year, which is why the slug can't be disambiguated by year. Noted, not solved — the numeric suffix is sufficient.

## The page — `/movies/<slug>`

Leads with what is unique to us, not with the TMDB text.

- **Now showing:** showtimes grouped by date, with screen, presentation format (2D/3D), captions (`Showtime.captions`), and member pricing.
- **Previously played:** "Played at Fort Kent Cinema, Oct 3–9 2025" plus a prominent link to what is on now. This is the archive state — real content, not an empty shell.
- Poster, runtime, rating, trailer where `youtube_id` is set, synopsis (falling back to overview).
- **"Read our review →"** where `Film.review` is set; the reverse link back to the film from the blog post.

### Internal linking

Load-bearing, and the reason the blog failed. Movie pages must not be orphaned:

- Homepage now-showing and coming-soon cards link to `/movies/<slug>`.
- Classics page cards link to `/movies/<slug>`.
- Movie pages are added to the sitemap.
- Blog post detail links to the film when `Film.review` points at it.

## Structured data (item #4)

On the movie page, `Movie` JSON-LD:

- `name`, `image` (poster_url), `description` (synopsis or overview)
- `duration` — `runtime_minutes` as ISO-8601 (`PT120M`)
- `contentRating` — `rating` where set
- `sameAs` — `https://www.imdb.com/title/<imdb_id>/` where set (64/66 films have one; a strong entity-disambiguation signal currently going to waste)
- `trailer` — `VideoObject` where `youtube_id` is set
- **`subjectOf` / nested `ScreeningEvent`** for each *upcoming* showtime: `startDate` (`Showtime.starts_at`), `location` (the existing `MovieTheater` entity), `videoFormat` (`presentation_format`)

Only upcoming showtimes get a `ScreeningEvent`. Emitting past screenings as events is wrong and Google will ignore or penalise it.

## Backfilling `Film.review`

A management command matching `"A Review of <Film>"` post titles to films by slug (5 match today, and it re-runs as new reviews are written), plus the field exposed in the **dashboard film form** so links can be made by hand.

## Not doing

- **Re-pointing `/archive/<movie>` at `/movies/<slug>`.** Those URLs came from a previous system and their films are not in the catalog (*Harold and the Purple Crayon*, *Karate Kid: Legends* have no `Film` row). They stay redirected to the homepage.
- **Pages for never-booked films** — see the thin-content section.

## Testing

- Every booked film is reachable by following `<a href>` from `/` — no JS, the same crawl test that caught the blog bug.
- Never-booked films 404 and are absent from the sitemap.
- Slug collisions get a suffix rather than raising.
- A now-showing film renders showtimes; an archive film renders run history and *no* fake showtimes.
- `Movie` JSON-LD parses, and contains exactly one `ScreeningEvent` per upcoming showtime and none for past ones.
- `sameAs`/`trailer`/`contentRating` are omitted cleanly when the underlying field is blank.
- A film with no `review` renders without the review link.

## Success criteria

- Film-title + local queries ("<film> fort kent showtimes") begin returning impressions — currently zero.
- Search Console "Enhancements" shows a `Movie` / `ScreeningEvent` rich result type where it currently shows none.
- Indexed page count rises with the 46 new pages.

Follows [legacy URL redirects](2026-07-13-blog-indexability-design.md) and the blog indexability work; same underlying lesson — a page nothing links to is a page Google won't index.
