# Homepage Visual Hierarchy Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Regroup the homepage below the hero into six weighted sections (Now Showing, Membership, Coming Soon, Get involved, Our story, Support) under one set of type, spacing, button and card rules.

**Architecture:** Server-rendered Django templates. Each section is a partial included by `web/templates/web/home.html`. Shared homepage styles go in one new stylesheet, `static/css/HomeSections.css`, imported in the esbuild bundle. `HomeView` gains one context value, `membership_from_price`.

**Tech Stack:** Django 5 templates and TestCase, plain CSS bundled by esbuild (`npm run build:css` in `frontend/`), Alpine/htmx already on the page (untouched).

**Spec:** `docs/superpowers/specs/2026-10-12-home-visual-hierarchy-design.md`. The research brief is `docs/superpowers/research/2026-10-12-visual-hierarchy.md`.

## Global Constraints

- The hero (`partials/hero.html`, `Hero.css`) is not changed.
- Final order below the hero: `now-showing`, `membership`, `coming-soon`, `get-involved`, `our-story`, `support`. Each is a `<section>` with that `id`, rendered exactly once.
- Heading sizes below the hero come only from `--type-title` (section h2), `--type-heading` (Membership headline) and `--type-lead` (card h3). No literal font sizes for headings. Eyebrows use `--type-label`, Cabin Condensed, uppercase, `--track-label`, `--color-text-muted`.
- Spacing: 96px between sections (64px at ≤600px), 32px from section header to content (homepage only), 24px between cards, 16px inside cards. Use `--spacing-*` tokens where they match.
- Button ladder: `.btn-ticket` only inside `#now-showing`; the gold button (`.btn-member`) only in `#membership`; `.btn-secondary` for "All posts"; every other action is a text link ending in " →" with class `home-link`.
- One card shape: `.home-card` (eyebrow `.home-card__eyebrow`, h3 `.home-card__title`, sentence `.home-card__body`, link `.home-link` pushed to the bottom). No images in home cards.
- Each section has one flat ground. The old gradients, glows, hairlines, gold rules and the `.cta-pair` grid go.
- Nothing below the hero is hidden on phones. Tap targets are at least 44px.
- Existing class markers stay on their blocks: `sponsored-cta`, `vote-cta`, `open-mic-cta`, `gift-card-cta`, `history-cta`, `blog`, `sponsor-cta`, `donate-cta`. Existing `data-track` names stay.
- CSS tasks use the `frontend-design:frontend-design` skill for the visual build, inside these rules. The research brief is its input.
- After any CSS change: `cd frontend && npm run build:css`, and commit `static/css/bundle.css`.
- Tests: `.venv/bin/python manage.py test <labels>` (run serially; `--parallel` hides failures). The full suite must pass at every commit. Format with black and lint with flake8, on touched files only.

## Review Focus

1. **Gold on blue contrast:** Membership band text and the gold button must pass WCAG AA. Task 1 pins the colour tokens used, and the manual check measures them.
2. **Hidden cheaper tier:** a tier with `show_on_membership_page=False` and a lower price must not set "From $N". Task 1 test.
3. **One open poll vs several:** the vote card's details line must stay singular for one round and plural for N. Task 3 test.
4. **No blog posts:** Our story must render the history card and "All posts", with no empty grid. Task 4 test.
5. **Donate link without its disclaimer:** the disclaimer must render wherever the donate link does. Task 4 test.

---

### Task 1: Section foundation and Membership band

**Files:**
- Create: `static/css/HomeSections.css`, `templates/partials/home_membership.html`, `web/tests/test_home_membership.py`
- Modify: `web/views.py` (`HomeView.get_context_data`), `web/templates/web/home.html` (include after `now_showing`), `frontend/styles/main.css`, `static/css/bundle.css`

**Interfaces:**
- Produces: context `membership_from_price: int | None`. CSS classes `.home-section` (section padding and ground hook), `.home-section--raised`, `--alt`, `--surface`, `--sunken`, `--accent` (grounds), `.home-section .section-header` (32px gap), `.home-cards` (card row, 24px gap, stacks ≤900px), `.home-card` and parts, `.home-link`, `.btn-member`. Later tasks use these classes only.

- [ ] **Step 1: Write failing tests** in `web/tests/test_home_membership.py`:
  - `test_band_renders_after_now_showing`: the HTML has `id="membership"` after `id="now-showing"` and before `id="coming-soon"`.
  - `test_price_is_cheapest_listed_tier`: tiers at 35 and 60 (listed) plus one at 10 with `show_on_membership_page=False`. Expect "From $35 a year." and no "$10".
  - `test_no_tiers_omits_price_line`: no tiers. `id="membership"`, "Become a member" and the `/membership/` link render, and "From $" does not.
  - `test_copy_and_button`: the HTML contains "Movies, perks, and a hand in keeping the marquee lit." and exactly one `btn-member` link to `reverse("membership")` with `data-track="membership_cta_click"`.
- [ ] **Step 2: Run** `manage.py test web.tests.test_home_membership`. Expected: FAIL.
- [ ] **Step 3: Implement.** `HomeView`: set `membership_from_price` with `MembershipTier.objects.filter(show_on_membership_page=True).aggregate(Min("price"))["price__min"]`. Partial per spec §2, with the section classes `home-section home-section--accent`. Create `HomeSections.css` with the foundation classes listed above and the band (blue `--color-accent` ground, `--brand-warm-white` headline, `--brand-parchment` line, `.btn-member` gold `--brand-gold` fill with `--brand-rich-black` text, at least 44px tall). Import it in `main.css`, then rebuild the bundle. If `web/tests/test_performance.py` pins the home query count, raise it by exactly 1 and say why in the comment.
- [ ] **Step 4: Run** the new tests plus `web.tests.test_performance web.tests.test_pages`. Expected: PASS.
- [ ] **Step 5: Commit** `feat(home): membership band after the showtimes`.

### Task 2: Sponsored screening inside Now Showing

**Files:**
- Modify: `templates/partials/now_showing.html`, `templates/partials/cta_sponsored.html`, `web/templates/web/home.html` (remove its include), `static/css/SponsoredCTA.css`, `static/css/NowShowing.css`, `static/css/bundle.css`
- Test: `web/tests/test_sponsored_screening.py`

**Interfaces:**
- Consumes: `.home-section`, `.home-section--raised` from Task 1.

- [ ] **Step 1: Update tests.** Replace the "banner above now-showing" assertion with `test_sponsored_card_is_inside_now_showing`: `sponsored-cta` appears after `id="now-showing"` and before the first schedule markup (`ticket-info` or the date nav), exactly once. Keep `test` coverage for "not booked → absent" and "not hidden on phones". Add `test_ticket_button_only_in_now_showing`: in the home HTML after the hero's closing tag, every `btn-ticket` occurs between `id="now-showing"` and `id="membership"`. This test may fail until Tasks 3 and 4; mark it `@expectedFailure` with a comment, and Task 4 removes the marker.
- [ ] **Step 2: Run** `manage.py test web.tests.test_sponsored_screening`. Expected: FAIL on the placement test.
- [ ] **Step 3: Implement.** Include `cta_sponsored.html` inside `now_showing.html` directly after the section header (both the showtimes and the empty branches). Restyle it as a card: `--color-surface-raised`, a 2px `--brand-gold` border, and title at `--type-heading`, replacing the 2rem literal. Give Now Showing `home-section home-section--raised`.
- [ ] **Step 4: Run** the sponsored, home-sections and pages tests. Expected: PASS (except the marked expected failure).
- [ ] **Step 5: Commit** `feat(home): sponsored screening as the first card in Now Showing`.

### Task 3: Get involved

**Files:**
- Create: `templates/partials/home_get_involved.html`
- Modify: `templates/partials/cta_vote.html`, `cta_openmic.html`, `cta_giftcard.html`, `web/templates/web/home.html`, `static/css/VoteCTA.css`, `OpenMicCTA.css`, `GiftCardCTA.css` (trim to nothing home-specific, or delete and remove from `main.css`), `static/css/bundle.css`
- Test: `web/tests/test_vote_integration.py`, `web/tests/test_open_mic.py`, `web/tests/test_home_sections.py`

**Interfaces:**
- Consumes: `.home-section`, `.home-cards`, `.home-card*`, `.home-link`.

- [ ] **Step 1: Update tests.**
  - The vote card renders only with an open round. With one round, "One round is open right now." With three, "3 rounds are open right now." Title "Vote on what plays next", link "Cast your vote →" to `/vote/`. This replaces the "VOTE ON WHAT PLAYS NEXT" pin.
  - The open-mic card has "Every Monday", "Open Mic" and "How to sign up →", and still agrees with `OPEN_MIC` (keep the existing agreement test, updated to the new copy "6:30 PM · doors open at 6:00.").
  - The gift-card card has "Give the gift of cinema", "An e-gift card for a night at the movies." and "Buy an e-gift card →", with `target="_blank"` and an aria-label containing "opens in new window".
  - `id="get-involved"` contains all three cards in the order vote, open mic, gift card, and none of them contains `btn-ticket`.
- [ ] **Step 2: Run** those test modules. Expected: FAIL.
- [ ] **Step 3: Implement** per spec §4: the wrapper section `home-section home-section--surface` with h2 "Get involved" and a `.home-cards` row, plus the three partials rewritten as `.home-card` with their class markers and `data-track` names. Insert the wrapper after `coming_soon` in `home.html`, and remove the old standalone includes.
- [ ] **Step 4: Run** the modules plus `web.tests.test_pages`. Expected: PASS.
- [ ] **Step 5: Commit** `feat(home): group vote, open mic and gift cards under Get involved`.

### Task 4: Our story and Support

**Files:**
- Create: `templates/partials/home_our_story.html`, `templates/partials/home_support.html`
- Modify: `templates/partials/cta_history.html`, `cta_sponsor.html`, `cta_donate.html`, `blog_teaser.html` (or replace it with the our-story partial and delete it), `web/views.py` (`recent_posts` from 6 to 3, comment updated), `web/templates/web/home.html`, CSS: delete `CtaPair.css` and trim `HistoryCTA.css`, `SponsorCTA.css` and `DonateCTA.css` (removing them from `main.css` as needed), `static/css/bundle.css`
- Test: `web/tests/test_home_sections.py`, `web/tests/test_donate_cta.py`, `web/tests/test_sponsored_screening.py` (remove the `@expectedFailure` marker)

**Interfaces:**
- Consumes: Task 1 classes; `sponsorship_from_price`, `donation`, `recent_posts`.

- [ ] **Step 1: Update tests.**
  - `id="our-story"` has the history card first ("Since 1917", "A century on this lot", "Read the history →" to `/history/`), then at most 3 post cards with "Read →", then an "All posts" link with class `btn-secondary` to `reverse("blog_list")`. Create 5 posts and expect 3 cards. The section keeps the `blog` marker.
  - `test_our_story_without_posts`: no posts. The history card and "All posts" render, and there is no `blog-grid`.
  - `id="support"` has `sponsor-cta` with "Sponsor a screening, from $N →" (N is `min` of `SPONSORSHIP_TIERS` prices), replacing the `sponsor-cta__body` "From $N." pin.
  - Donate: with `DONATION["url"]` blank, there is no `donate-cta`. When set (override settings or patch the constant, following the existing test's approach), the link text is `donation.button + " →"` and the disclaimer renders in the same section.
  - `.cta-pair` no longer appears. `support` is the last section before the footer.
- [ ] **Step 2: Run** those modules. Expected: FAIL.
- [ ] **Step 3: Implement** per spec §5–6. Our story uses `home-section home-section--alt`, with the history `.home-card` and then the post `.home-card`s (eyebrow is the post date, body is the excerpt clamped to 2 lines). Support uses `home-section home-section--sunken` as a slim strip of `.home-link`s, with the donate disclaimer in `--type-label` muted text. Replace the pair, blog and donate includes in `home.html`.
- [ ] **Step 4: Run** the modules plus `web.tests.test_sponsored_screening` (the button-ladder test now passes unmarked) and `web.tests.test_pages`. Expected: PASS.
- [ ] **Step 5: Commit** `feat(home): Our story and Support the Cinema replace the CTA pair, blog and donate bands`.

### Task 5: Composition, type and spacing pass

**Files:**
- Modify: `web/templates/web/home.html` (final order and the top comment rewritten for the new structure), `static/css/ComingSoon.css` (drop the gold rules, flat `--color-surface-alt`, `home-section` classes on the section), `static/css/NowShowing.css` and `Blog*.css` (only home-only rules), `static/css/HomeSections.css`, `static/css/bundle.css`
- Test: `web/tests/test_pages.py`, `web/tests/test_home_sections.py`

- [ ] **Step 1: Update tests.**
  - `test_full_home_composition_order`: hero, then the six ids in the Global Constraints order, each exactly once.
  - `test_home_sections`: the class-marker inventory matches the new structure.
  - `test_one_member_button`: `btn-member` appears exactly once.
  - The bundle probe: `static/css/bundle.css` contains `.home-card`, `.home-section--accent` and `.btn-member`, and does not contain `.cta-pair`.
- [ ] **Step 2: Run.** Expected: FAIL where the structure is not final yet.
- [ ] **Step 3: Implement.** Finish the order. Apply the spacing scale and the three heading sizes to every homepage section, and remove the literal 1.1rem, 1.35rem and 2rem heading sizes from homepage selectors. Scope the 32px header gap to `.home-section`. Use the frontend-design skill for the visual polish within the Global Constraints.
- [ ] **Step 4: Run the full suite**, then `makemigrations --check`, flake8 and black on touched Python. Expected: all pass.
- [ ] **Step 5: Manual check.** Seed a local DB with 3 films and showtimes, a sponsored run, an open poll, 2 listed tiers, 3 posts and a donation URL (a throwaway script in the session scratchpad, not committed). Load `/` at 375px and 1280px. Check the order, the squint test, contrast on the blue band (≥4.5:1 text), no horizontal scroll, and 44px tap targets. Report findings. Fix anything that breaks the Global Constraints.
- [ ] **Step 6: Commit** `feat(home): one type and spacing system below the hero`.
