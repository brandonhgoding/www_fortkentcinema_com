# Visual hierarchy brief: Fort Kent Cinema homepage

Evidence note: NN/g pages and the cinema homepages were fetched directly (sections observed 12 Oct 2026). Refactoring UI figures come from secondary summaries of the book, and the CTA-hierarchy rules from design-system docs (Basis, Cieden). Neither is NN/g. Treat the numbers as sensible defaults, not research findings.

## 1. Core principles
- **Scale.** Larger means more important. NN/g: limit type to about three sizes; the most important element is largest and no more than two elements are large. Example web range: body 14-16px, subheads 18-22px, headers to 32px. https://www.nngroup.com/articles/visual-hierarchy-ux-definition/
- **Contrast and colour.** Hierarchy comes from value and saturation contrast, not hue. Reserve bright colours for important items. Use about 2 primary and 2 secondary colours, and at most 3 contrast variations. "If everything is emphasized, nothing stands out." Never rely on colour alone. Same NN/g URL.
- **Proximity and common region (Gestalt).** Items close together read as a group, and a heading should sit nearer its own content than the previous section. Add a border or background only if spacing is not enough. https://lawsofux.com/law-of-proximity/ , https://lawsofux.com/law-of-common-region/
- **Alignment, grid and repetition.** One left edge and one container width. Every item of the same kind (showtime, tier, poll, event) uses the same component. Repetition teaches users what a card is, and difference (Von Restorff) then signals the one thing that matters. https://lawsofux.com/von-restorff-effect/
- **Choice load.** Fewer visible options means faster decisions. https://lawsofux.com/hicks-law/ . Keep groups small: https://lawsofux.com/millers-law/ . First and last items are remembered best: https://lawsofux.com/serial-position-effect/
- **Reading patterns.** NN/g: with no strong cues, people fall into an F-pattern, which is a failure mode. A page with clear headings gets layer-cake scanning, where eyes jump heading to heading and skip body text. Seekers use a spotted pattern, hunting for a number, time or button. So section headings must carry the meaning, begin with the key word, and be visually distinct. https://www.nngroup.com/articles/f-shaped-pattern-reading-web-content/
- **Progressive disclosure.** Show the summary (title, next times, price line). Put synopsis, full lists and archives one click away.
- **Process (Refactoring UI via summaries).** Design in greyscale first and add colour last. De-emphasise secondary content (lighter, smaller) instead of inflating primary content. Combine size, weight and colour rather than size alone. https://refactoringui.com/

## 2. Requirements that can be written down
**Type**
- Modular scale at ratio 1.25 (a 16px base gives roughly 16, 20, 25, 31, 39, 49px). Use 1.333 only for the hero or display size.
- Show at most 3 levels below the hero: section title (h2, about 31-39px), card title (h3, about 20-25px), body (16px+). Small meta text (14px) is a fourth role used sparingly.
- Headings line-height 1.1-1.25, body 1.5-1.7. One or two font families. Bold for emphasis only.
- Body line length 45-75 characters.

**Spacing**
- Fixed scale on a 4/8 base: 4, 8, 16, 24, 32, 48, 64, 96px.
- Rule: space between sections (64-96px) is at least 2x space between cards (24-32px), which is at least 2x space inside a card (8-16px).
- Heading-to-content gap is smaller than the gap above the heading.
- Start with too much whitespace, then trim.

**Section rhythm**
- One container width and one gutter. Separate sections by alternating background (for example dark, dark-raised, dark) or a single consistent divider, not both.
- Each section has the same anatomy: eyebrow or h2, one-line lede, content grid, one link.

**CTAs**
- Exactly one primary button style (filled, accent colour), used for ticket buying. Secondary is outline. Tertiary is a text link with an arrow.
- Per section: one primary or secondary action, not three. Only one primary CTA in view at a time (hero's "Showtimes/Tickets" is the primary; lower sections use secondary or tertiary). Sources: https://cieden.com/book/atoms/button/how-to-create-button-hierarchy , https://design.basis.com/components/buttons
- Buttons look like buttons. Do not style headings as clickable. https://www.nngroup.com/articles/clickable-elements/

**Cards**
- Same card shape, radius, padding, image ratio and title/meta/action order across films, events, votes and tiers. Variants may change content, not structure.
- Cap each section at 3-4 cards on desktop, with a "see all" link.

**Accents**
- One accent colour (CTA and key highlights), one neutral text pair, one muted tone for meta. Status colours (sold out, voting open) are the only extras. No more than 1 accent-filled element per section.

## 3. How cinema sites order the homepage (fetched Oct 2026)
Pattern: **showtimes first, then conversion offers (membership), then discovery (coming soon, events), then editorial, then practical info and email signup.**
- **Coolidge Corner Theatre** (https://www.coolidge.org/): hero, donation appeal, quick links, Now Playing with date selector and calendar, Membership promo, Highlights (events), Coming Soon, News, About (address, phones), Email signup, footer. Membership comes immediately after showtimes.
- **Prince Charles Cinema** (https://www.princecharlescinema.com/): promo banner, mailing list, date selector, then film listings with booking buttons per time, then address, pricing and fee details, then a poster grid. The bare listing carries the page.
- **Picturehouse** (https://www.picturehouses.com/): booking widget, featured Now Playing with "Book Now", Membership promo, more films, event promos, Coming Soon, blog, footer. Membership appears right after the first films.
- **Metrograph** (https://metrograph.com/): a stack of promo banners (membership first), then day selector and Today's Films, upcoming showtimes, series, Journal. It is the busier example, and the promo stack pushes the showtimes down.
- **Alamo Drafthouse**: page did not load for the fetch tool, so no claim made.
- Takeaway for Fort Kent: one date-led showtimes block directly under the hero. Then, in this order, Membership (one strip), Vote on what plays next, Events and Coming Soon, then Visit info and mailing list. Practical info and prices sit near showtimes, as at Prince Charles.

## 4. Audit checklist
- **Squint/blur test** (NN/g, same visual hierarchy URL): blur at several levels. Expected order: hero, then showtimes, then everything else as quiet equal-weight blocks. If a decorative or vividly coloured card pulls the eye, fix it. Test with real content, since photos and badges can overpower the template.
- **Five-second test:** show the page for 5 seconds. Ask: what's playing, when, how do I buy, what is this place? If they cannot answer, the hierarchy fails.
- **One thing per section:** write one sentence for each ("this section exists so visitors can ___"). If it needs "and", split or cut. Each section gets one h2, one primary action, and a visible primary element.
- **Heading skim (layer-cake):** read only the h2s top to bottom. They should tell the story: Showtimes, Membership, Vote, Events, Visit.
- **Count test:** at most 2 large type elements, 3 type sizes, 1 accent, and 1 primary button per view.
- **Spacing audit:** between-section gap exceeds between-card gap exceeds in-card gap. No arbitrary pixel values outside the scale.
- **Consistency audit:** put the cards side by side. Radius, padding, image ratio and CTA style should match.
- **Mobile pass:** the same order, one column, tap targets 44px+, showtimes visible without scrolling past two sections.
