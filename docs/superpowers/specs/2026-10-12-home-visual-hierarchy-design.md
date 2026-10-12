# Homepage visual hierarchy: regroup below the hero — Design

**Date:** 2026-10-12
**Status:** Approved design, not yet implemented
**Repo:** `www_fortkentcinema_com` (branch: `feat/home-hierarchy`)
**Research:** `docs/superpowers/research/2026-10-12-visual-hierarchy.md`
(principles, numbers and sources; read it before building)

## Context

The owner likes the hero and the base theme. Below the hero the page is
"jumbled with no visual hierarchy". Today it is ten blocks in this order:
sponsored banner (when booked), Now Showing, Open Mic CTA, Coming Soon,
Gift Card CTA, History + Sponsor pair, Vote CTA (when open), Blog, Donate
(when its URL is set).

What makes it jumbled:

- The listings are interrupted by an ask every other block.
- All six asks are full-width sections that use the same notched
  `.btn-ticket`, so nothing outranks anything.
- Five heading sizes are in use: two tokens plus the literals 2rem, 1.35rem
  and 1.1rem.
- `.section-header` puts 64px (4rem) between a title and its own content,
  about as much as between sections, so titles float loose.
- Nothing below the hero pitches membership. The hero's secondary
  "Join Membership" is the only mention.

Cinema sites the research looked at (Coolidge Corner, Picturehouse) put
showtimes straight under the hero and membership straight after them.

## Goal

A visitor scanning below the hero sees, in order of weight: what's playing,
then one membership pitch, then what's coming, then the smaller ways to get
involved, grouped and quiet. Nothing is dropped from the page.

## Decisions (owner, 2026-10-12)

- **Approach A:** regroup into seven sections with three levels of weight,
  plus a style pass. Approaches rejected: style-only (the asks stay
  interleaved) and a lean page (it drops open mic, gift cards, sponsor and
  history from home).
- **Membership is the one big ask after showtimes.**
- The page map, the visual rules and the per-section content below were
  approved in the browser companion and in chat.

## Page structure

The hero is unchanged: markup, CSS and its two buttons.

| # | Section | Weight | Ground | Renders |
|---|---------|--------|--------|---------|
| 1 | Now Showing (`id="now-showing"`) | tier 1 | `--color-surface-raised` | always |
| 2 | Membership (`id="membership"`) | featured | `--color-accent` (blue) | always |
| 3 | Coming Soon (`id="coming-soon"`) | tier 2 | `--color-surface-alt` | always |
| 4 | Get involved (`id="get-involved"`) | tier 3 | `--color-surface` | always (gift card and open mic always render) |
| 5 | Our story (`id="our-story"`) | tier 3 | `--color-surface-alt` | always (history always renders) |
| 6 | Support the Cinema (`id="support"`) | tier 3, slim | `--color-surface-sunken` | always (sponsor always renders) |

Each section has a single ground colour. The gradients, glows, hairlines
and gold rules on today's CTA bands go, along with the `.cta-pair` grid.
That's six sections plus the hero, seven in all. The sponsored screening
lives inside Now Showing.

### 1. Now Showing

- Content is unchanged: schedule and date nav, ticket price line, and the
  mailing-list signup in both its placements.
- **Sponsored screening:** when `sponsored` is set, it renders as the first
  item inside the section, between the section header and the schedule. It
  is a card with a 2px `--brand-gold` border, keeping today's content
  (eyebrow, title, dates and times, admission, "Sponsored by"). It is not
  hidden on phones. `partials/cta_sponsored.html` moves inside
  `partials/now_showing.html`. The `sponsored-cta` class marker stays.
- Ticket buying here is the only use of `.btn-ticket` below the hero.

### 2. Membership (new, `partials/home_membership.html`)

- Eyebrow, `--type-label`: "Membership".
- Headline h2, `--type-heading`: "Become a member".
- Line: "Movies, perks, and a hand in keeping the marquee lit." (the
  `/membership/` hero's line).
- Price: "From ${{ membership_from_price }} a year." The value is the
  lowest `price` among `MembershipTier` rows with
  `show_on_membership_page=True`. If there are none, the price line is
  omitted and the rest still renders.
- One button: "Become a member" → `{% url 'membership' %}`, gold
  `--brand-gold` fill with `--brand-rich-black` text, `data-track=
  "membership_cta_click"`, `data-track-location="home"`. On the blue ground,
  text is `--brand-warm-white`, and the line uses `--brand-parchment`.
- Contrast: every text and button pairing on blue must meet WCAG AA
  (4.5:1 for body text; gold on blue is used only for the button fill, with
  dark text on it).
- `HomeView` adds `membership_from_price` (one aggregate query; `None` when
  no tiers).

### 3. Coming Soon

- Content and behaviour are unchanged: grid and calendar toggle, trailer
  modal, empty state.
- The gold top and bottom rules and its gold title rule go.
- No "see more" button is added; it has none today.

### 4. Get involved (new wrapper, `partials/home_get_involved.html`)

Section h2 "Get involved". Up to three cards in a row (stacking on narrow
screens), in this order:

| Card | Renders | Eyebrow | Title | Sentence | Link |
|------|---------|---------|-------|----------|------|
| Vote (`vote-cta`) | only when `vote_polls` is non-empty | "Voting open" | "Vote on what plays next" | "One round is open right now." / "N rounds are open right now." (today's details line) | "Cast your vote →" `{% url 'vote' %}`, `data-track="vote_cta_click"` |
| Open mic (`open-mic-cta`) | always | "Every Monday" | "Open Mic" | "6:30 PM · doors open at 6:00." (today's facts; must still agree with `OPEN_MIC`, as `test_open_mic` asserts) | "How to sign up →" `{% url 'open_mic' %}` |
| Gift card (`gift-card-cta`) | always | "Gift cards" | "Give the gift of cinema" | "An e-gift card for a night at the movies." | "Buy an e-gift card →", today's Square URL, `target="_blank"`, `data-track="giftcard_click"`, aria-label noting the new window |

The gift-card sentence is new (today's block has a title only). Each card's root keeps its existing class marker (`vote-cta`,
`open-mic-cta`, `gift-card-cta`) and the `card` shape below. The old
partials `cta_vote.html`, `cta_openmic.html` and `cta_giftcard.html` are
rewritten as these cards, not deleted, so names stay findable.

### 5. Our story (new wrapper, `partials/home_our_story.html`)

Section h2 "Our story". A row of cards:

- **History card first** (`history-cta`): eyebrow "Since 1917", title
  "A century on this lot", one shortened sentence from today's body,
  link "Read the history →" `/history/`, `data-track="history_click"`.
- **Then the three latest blog posts** (`recent_posts[:3]`), each as the
  same card shape: eyebrow is the post date, title, excerpt clipped to one
  sentence or two lines, link "Read →". The section keeps the class marker
  `blog` and adds a secondary outline button "All posts" →
  `{% url 'blog_list' %}`.
- With no posts, only the history card and "All posts" render.

### 6. Support the Cinema (`partials/home_support.html`)

A slim strip, not a card row: label "Support the Cinema", then text links
on one line (wrapping on phones):

- "Sponsor a screening, from ${{ sponsorship_from_price }} →"
  `{% url 'sponsor' %}`, `data-track="sponsor_click"`, inside an element
  with the `sponsor-cta` class marker.
- When `donation.url` is set: "{{ donation.button }} →" to `donation.url`
  (new window, `data-track="donate_click"`, inside `donate-cta`), followed
  by `donation.disclaimer` in `--type-label` muted text. The disclaimer is
  required wherever the donate link shows.

## Visual rules (every section below the hero)

**Type: three heading sizes, from existing tokens only.**

- Section h2: `--type-title` (3 / 2.5 / 1.875rem).
- Membership headline: `--type-heading` (2.25 / 1.875 / 1.5rem).
- Card h3: `--type-lead` (1.266rem).
- Body: 1rem Cabin. Eyebrow and meta: `--type-label`, Cabin Condensed,
  uppercase, `--track-label`, `--color-text-muted`.
- The 2rem, 1.35rem and 1.1rem literals go. No new font sizes.

**Spacing: each level of nesting gets half the space of the one above.**

- Between sections: 96px desktop, 64px phone (vertical section padding).
- Section header to its content: 32px. Scope this to homepage sections
  (for example `.home-section .section-header`); other pages keep 4rem.
- Between cards: 24px. Inside a card: 16px padding and gaps.
- Use the existing `--spacing-*` tokens where they match; add tokens only for
  values the scale lacks.

**Buttons, strongest to quietest:**

1. `.btn-ticket` (notched): ticket buying in Now Showing only.
2. Gold filled: the Membership button only.
3. `.btn-secondary` outline: one "see more" per section ("All posts").
4. Text link with "→": every action in Get involved, Our story and Support.

**One card shape** (`.home-card`): `--color-surface-raised` background,
1px border, the same radius and 16px padding. The order is eyebrow, h3
title, one sentence, then a text link pushed to the bottom. Cards in a row
match heights. No images on these cards (blog thumbnails are dropped on
home for consistency; they stay on `/blog/`).

**Accent:** blue `--color-accent` is the one accent. Gold is used only for
the Membership button and the sponsored card border.

**Phones:** same order, one column, cards stack, tap targets at least 44px.
Nothing below the hero is hidden on phones (`home.css` already forbids
that gate).

## What changes in code

- `web/templates/web/home.html`: the new include order; comments updated.
- New partials: `home_membership.html`, `home_get_involved.html`,
  `home_our_story.html`, `home_support.html`.
- Rewritten as cards or links: `cta_vote.html`, `cta_openmic.html`,
  `cta_giftcard.html`, `cta_history.html`, `cta_sponsor.html`,
  `cta_donate.html`. `cta_sponsored.html` moves into `now_showing.html`.
- `HomeView`: adds `membership_from_price`; `recent_posts` drops from 6 to
  3.
- CSS: a new `static/css/HomeSections.css` for section grounds, spacing,
  `.home-card` and the membership band, imported in
  `frontend/styles/main.css`. The CTA stylesheets for the rewritten blocks
  are trimmed or removed, and `CtaPair.css` is removed. Rebuild
  `static/css/bundle.css` with `npm run build:css` in `frontend/`.
- The hero, other pages and `.btn` definitions are unchanged, except that
  `.btn-ticket` notch colours may be fixed to match its ground.

## Out of scope

- The hero.
- Other pages (`/membership/`, `/blog/` and the rest), except shared CSS that
  must keep working there.
- New copy beyond what's listed above; new imagery.
- Changing what Coming Soon or Now Showing list.

## Testing

Django `TestCase`, rendering `/`.

- Order: hero, `now-showing`, `membership`, `coming-soon`, `get-involved`,
  `our-story`, `support`, each exactly once
  (`test_full_home_composition_order` and `test_home_sections` rewritten).
- Sponsored: when booked, `sponsored-cta` renders inside `now-showing`
  before the schedule; when not booked, not at all.
- Membership: the price shown is the cheapest `show_on_membership_page`
  tier; a hidden cheaper tier is ignored; with no tiers, the band renders
  without a price line; the link goes to `/membership/`.
- Get involved: vote card only with an open round, with the singular and
  plural details lines; open mic and gift card always; the gift-card link
  opens in a new window.
- Our story: history card plus at most 3 posts; no posts gives history
  plus "All posts".
- Support: sponsor link with "from $N"; donate link and disclaimer only
  when `DONATION["url"]` is set.
- Button ladder: `btn-ticket` appears below the hero only inside
  `now-showing`; exactly one gold membership button on the page.
- Existing tests that pin old CTA copy (for example "VOTE ON WHAT PLAYS
  NEXT", the `.cta-pair` wrapper, `sponsor-cta__body`) are updated to the
  new structure, not deleted without replacement.
- Bundle probe: `bundle.css` contains `.home-card` and the membership band
  selector.
- Manual check before merge (dev DB has no films): load home with sample
  films, a sponsored run, an open poll and a donation URL, at 375px and
  desktop. Run the squint test and the five-second test from the research
  brief.
