# Blog Indexability — Design

**Date:** 2026-07-13
**Status:** Approved

## Problem

The blog has 77 posts. Search Console reports **9 pages indexed sitewide, 74 not indexed**, with 29 of those filed under "Crawled — currently not indexed."

Discovery is not the bottleneck. `web/sitemaps.py` already lists all 77 posts, and Google has crawled them. It crawled them and *declined to index them*.

Two causes, both structural:

1. **The posts are orphaned.** Nothing on the site links to them except the sitemap. Blog pagination is HTMX-only — `_post_cards.html` renders a `<div hx-get=… hx-trigger="revealed">` with no `<a href>` — so a crawler executing no JavaScript sees the first 6 posts and stops. The other 71 have zero inbound internal links. A page with no internal links pointing at it reads to Google as a page the site itself does not consider important, which is a well-known cause of "crawled, currently not indexed."

2. **Paginated pages disown themselves.** `base.html` hardcodes `<link rel="canonical">` to `request.path`, so `/blog/?page=2` declares itself a duplicate of `/blog/`. Even when Google reaches page 2, that canonical tells it to discard the page — and the links on it.

## Approach

Make the blog a properly connected, crawlable link graph. Two levers: real pagination links, and sibling links between posts.

### 1. Numbered pagination replaces infinite scroll

Delete the HTMX load-more machinery and render a plain numbered nav from `page_obj`:

```
‹ Prev   1  2  3 … 7   Next ›
```

Every page becomes an `<a href="/blog/?page=N">`. No JavaScript involved, so there is nothing for a crawler to fail to execute, and every listing page sits one hop from `/blog/`.

This removes rather than works around the problem. The alternative — keeping infinite scroll and hiding a crawlable `<a>` beneath it — was considered and rejected as more moving parts for no user-visible gain.

**Code to delete:** the `hx-get`/`hx-trigger`/`hx-swap` load-more div and the `hx-swap-oob` count block in `_post_cards.html`; the `get_template_names()` HTMX branch and the `is_htmx` context flag in `PostListView`. All of it becomes dead once paging is links.

### 2. `paginate_by` 6 → 12

77 posts at 6/page is 13 pages — a long nav and a lot of thin listing pages. At 12/page it is 7 pages: a cleaner nav, and each listing page carries more real content.

### 3. Self-canonical the paginated pages

Add a `{% block canonical %}` to `base.html` (it currently has no override point) and override it in `post_list.html` so `/blog/?page=2` canonicals to itself. Page 1 continues to canonical to the bare `/blog/`, so we do not mint a `?page=1` duplicate.

### 4. Related posts on post detail

`PostDetailView` gains 3 related posts: same `category`, excluding self, most recent first — backfilled with recent posts from any category when a category is too thin to yield 3. Rendered with the existing `partials/blog_card.html`; no new card CSS.

This is the lever that actually addresses "crawled, currently not indexed." Pagination gives each post *one* inbound link; sibling links give it many, from topically related pages.

### 5. Fix the `/blog` nav link

`web/constants.py` points the nav at `/blog` (no trailing slash), so every internal click to the blog eats a 301. One character. Folded in here rather than left as a known redirect sitting on the exact path we are trying to strengthen.

## Not doing

- **`rel="next"` / `rel="prev"`** — Google dropped these as indexing signals in 2019.
- **Sitemap changes** — `web/sitemaps.py` is already correct and already lists every post.

## Testing

The tests should assert what a *crawler* sees, since that is the entire point:

- `/blog/` contains a real `<a href>` to page 2.
- All 7 listing pages are reachable and return 200.
- **All 77 post URLs are reachable by following only `<a href>` links from `/blog/`**, with no JavaScript. This is the test that would have caught the original bug.
- `/blog/?page=2` self-canonicals; `/blog/` canonicals to `/blog/`.
- A post detail page renders links to sibling posts.
- Related posts exclude the post itself, and backfill when a category is thin.

## Success criteria

Measured in Search Console over the weeks after deploy:

- "Crawled — currently not indexed" (29) falls.
- Indexed pages climb from 9 toward the ~82 the sitemap offers.
- Blog posts begin accruing non-brand impressions.

Related: [legacy URL redirects](../../../web/redirects.py) shipped first — the two together are the indexing half of the July 2026 SEO audit backlog.
