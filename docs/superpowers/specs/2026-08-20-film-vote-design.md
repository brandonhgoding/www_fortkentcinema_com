# Film Vote — Design

**Date:** 2026-08-20
**Status:** Approved, ready for plan

## Problem

The site has no mechanism that brings anyone back. There is no email capture, no
accounts, no notifications — a visitor arrives from a Facebook post or a brand
search, reads a showtime, and leaves with nothing connecting them to the next
visit.

The July 2026 SEO work fixed the structural problems it could: redirects, blog
indexability, per-movie pages, JSON-LD, conversion tracking, Core Web Vitals.
What it could not fix is the size of the addressable audience. Fort Kent has
roughly 4,000 people, "fort kent cinema" already ranks #1, and ~95% of clicks are
brand queries. There is no large pool of untapped searchers to win. The only
remaining SEO item is earning local backlinks, which is outreach rather than
code.

So the lever is not *new* visitors from search. It is giving the people who
already know the theater a reason to return to the site directly, and something
worth sharing when they do.

Separately, Classic Movie Night was retired from the public site because
programming it was a guess. Booking a repertory title without knowing whether
anyone wants it is a risk at ~4,600 admissions/year.

Both problems have one answer: **let the audience choose the next repertory
title, and capture an email address at the moment they care most.**

## Scope

A curated, single-choice public vote that feeds a real repertory slot, plus the
email list it builds.

- A public voting page at a stable `/vote` URL, with an archive of past rounds.
- Ballots of four to six films, chosen by staff from the existing `Film` catalog.
- One vote per browser per round, enforced in the database.
- An optional email capture shown immediately after voting.
- A dashboard surface for building rounds, watching tallies, announcing a
  winner, and exporting subscribers.

**Out of scope:** email *sending* (deliberately deferred — see Email Delivery),
public nominations, user accounts, ranked-choice or multi-select ballots.

## Key decisions

**The vote feeds a real programming slot.** Voting relaunches Classic Movie
Night (or its successor) with demand proven before booking. A vote whose winner
never screens is worse than no vote at all, because it teaches people the site
lies.

**The ballot is curated, not open.** Staff pick every candidate. This removes the
moderation queue, the nomination model, and — most importantly — the risk of a
winner that cannot be licensed, afforded, or wanted. It is also the load-bearing
defense against ballot stuffing: a stuffed ballot still returns a film already
approved for screening.

**Voting is one click; the email ask comes after.** No form stands between a
visitor and a vote. The email ask lands immediately after, at peak intent. The
alternative — requiring a confirmed address to vote — buys hard integrity at the
cost of a friction wall that would lose more real votes than the integrity is
worth in a town this size.

**Ballots are single-choice.** One vote, one film. Not ranked-choice, not
pick-two.

**Subscribers live in their own app, not in `cinema`.** The list is not a
cinema-domain object and is the piece most likely to outlive this feature —
showtime alerts, announcements, and any future newsletter all want it. A new app
means the next consumer imports one clean model rather than reaching into
`cinema` for something that was never about films.

## Data model

### New app: `audience`

```python
class Subscriber:
    email              # unique, normalized to lowercase on save
    status             # active | unsubscribed
    source             # 'poll_vote' today; free to grow
    consent_at         # when they opted in
    consent_ip         # proof of opt-in, for CAN-SPAM
    unsubscribe_token  # UUID, permanent, generated at creation
    unsubscribed_at
```

Nothing in this model references films or polls; `source` is only a label.

A manager method `Subscriber.objects.record(email, source, ip)` makes signup
idempotent, so re-voting in a later round does not error — and **never
resurrects an unsubscribed address.** Once someone opts out, a subsequent vote
must not silently re-add them.

`unsubscribe_token` is generated from the first row even though nothing sends
mail yet. Retrofitting tokens onto an existing list is a migration worth
avoiding.

### `cinema` app

```python
class Poll:
    title, slug, blurb
    opens_at, closes_at
    status            # draft | open | closed | announced
    results_visible   # live tallies, or hidden until close
    winner            -> PollOption (nullable)
    engagement        -> Engagement (nullable)

class PollOption:
    poll, film -> Film, blurb, sort_order
    # unique(poll, film)

class Vote:
    poll, option, voter_key, ip_hash, created_at
    # unique(poll, voter_key)
```

`PollOption` points at real `Film` records, so a ballot reuses posters,
runtimes, and TMDB metadata that already exist. Building a round is picking
films, not typing metadata.

`unique(poll, voter_key)` is a database constraint rather than an application
check, so double-voting fails at the write even if view logic is wrong.

`Poll.engagement` closes the loop: once the winner is booked, the results page
points at actual showtimes instead of dead-ending at "X won."

## Public flow

**One canonical URL: `/vote`.** This is the link pasted into Facebook, and it
stays valid across every round. Closed polls are archived at `/vote/<slug>` so
past results stay linkable. While a poll is live, its slug URL redirects to
`/vote`, so exactly one page collects shares and links.

There is no separate archive index route. `/vote` carries a "past rounds"
section listing closed polls, each linking to its `/vote/<slug>` page. Both
`/vote` and every archived poll page belong in the sitemap. An unlinked page is
a page Google will not index — the recurring lesson from the July SEO work.

Page states, all five of which must render correctly:

| State | What renders |
|---|---|
| No poll open | Last round's winner and when it plays; link to archive |
| Open, hasn't voted | The ballot — poster, title, runtime, staff blurb |
| Open, just voted | Results (if `results_visible`) plus the email ask |
| Closed, not announced | "Voting's closed, we're booking it" |
| Announced | Winner and showtimes, via `Poll.engagement` |

State resolution lives in a service under `web/services/`, matching the existing
`cinema_data` / `showtimes` convention, and is unit-tested independently of the
views.

**Casting a vote** is an HTMX POST that swaps in the results partial. HTMX is
already loaded in `base.html`, so this adds no dependency. It degrades to a plain
form POST with a redirect when JavaScript is unavailable.

**The email ask** appears only after voting, inline where the ballot was, worded
to match what can actually be delivered: *"Want us to let you know what won and
when it's playing?"* No "newsletter", no promised cadence.

**Internal linking**, folded in deliberately:

- A self-expiring homepage CTA, reusing the pattern the Silents Synced banner
  already uses, so it retires itself when the poll closes.
- An "on the ballot — vote" link on `/movies/<slug>` for any film currently up
  for a vote, pushing crawlers between the 46 movie pages and `/vote`.

## Dashboard

Follows the existing `dashboard/views.py` patterns: `StaffRequiredMixin`, HTMX
partial swaps, matching URL style.

```
/dashboard/polls                    list
/dashboard/polls/new                create
/dashboard/polls/<pk>               detail — options + live tallies
/dashboard/polls/<pk>/edit          edit
/dashboard/polls/<pk>/status        draft -> open -> closed -> announced
/dashboard/polls/<pk>/options/...   add / remove / reorder
/dashboard/subscribers              list, count, CSV export
```

Adding an option reuses `_film_search_combo.html`, the TMDB-backed film picker
already used to build engagements. Creating a round is: name it, set the close
date, search four to six films.

**At most one poll may be `open` at a time.** The public page assumes a single
live poll, so opening a second is a mistake the dashboard refuses via the status
transition, surfaced as a plain error message.

**The announce step** defaults the winner to the current leader (overridable),
then attaches the `Engagement` once booked.

**Subscriber export** is a CSV button. Since sending is deferred, this export is
the delivery mechanism: close a round, export, paste into Square Marketing.
Unsubscribes are honored in the export itself, not only in the database, so an
opt-out cannot leak into a send.

## Email delivery

Nothing in this project sends email today: there are no `EMAIL_*` settings, no
provider, no task queue, and no scheduled jobs. Adding a sender was considered
and deferred by decision.

Consequently the consent record is built correctly from day one — timestamp,
source, IP, permanent unsubscribe token — and the list is exportable to CSV.
Announcements are sent by hand from Square Marketing, which already carries the
domain's sending reputation. Wiring a transactional provider later is additive
rather than a rewrite.

The public copy must not promise more than a manual send can deliver. It says
the theater will let you know what won; it does not promise a schedule.

## Vote integrity

A `voter_key` — a random UUID in an httpOnly, one-year cookie — is set on first
visit to `/vote`. Combined with `unique(poll, voter_key)`, one-vote-per-browser
is a database guarantee.

Each vote also stores a **salted hash** of the IP, never the raw address. This
allows spotting 200 votes from one connection without holding PII, and supports
a soft cap of 5 votes per IP per round — high enough that a family, the library,
or UMFK's NAT are unaffected; low enough that scripting gets boring.

This is deliberately soft. Someone determined can clear cookies and vote from a
phone. No CAPTCHA is proposed: the friction would cost more real votes than the
cheating costs the theater, and the curated ballot is the actual defense.

The one hard rule: **a closed poll rejects votes at the server**, so a stale
browser tab cannot write into a finished round.

The email field carries a honeypot input, normalization, and validation.

## Testing

TDD throughout, against the gates that actually run in this project — `flake8`
and `manage.py test`. (mypy cannot run here and black is configured but
unapplied; neither is claimed as verification.)

- **Models** — the double-vote constraint holds; an unsubscribed address is never
  resurrected by a later vote; the one-open-poll invariant.
- **Services** — all five `/vote` states resolve correctly, including the
  "closed but not yet announced" window.
- **Views** — voting twice returns the already-voted state rather than a 500; the
  no-JS form fallback works; a closed poll refuses the write.
- **Dashboard** — staff-required on every route; opening a second poll is
  refused; CSV export excludes unsubscribes.
- **Crawl/sitemap** — `/vote` and archived poll pages appear in the sitemap, and
  every archived poll is reachable from `/vote`; extends the existing
  `web/tests/test_crawl_and_schema.py`.

## Success criteria

- A round can be created, opened, voted on, closed, and announced end to end
  without touching the Django admin or a shell.
- The winner's results page links to real showtimes.
- Votes cannot be cast twice from one browser, or at all after close.
- Email addresses accumulate with a valid consent record and export cleanly,
  with unsubscribes excluded.
