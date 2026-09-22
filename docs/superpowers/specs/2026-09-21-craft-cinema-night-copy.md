# Craft Cinema Night — page content

Draft copy for a new standing page. Nothing here is live yet.

Proposed URL: `/craft-night/` (trailing slash, like `/membership/` and
`/rentals/`). "Craft Cinema Night" is the event name; `craft-night` is the
shorter thing people will type and say.

Items marked **[CONFIRM]** are facts I don't have and did not invent.

---

## Meta

**Title:** Craft Cinema Night | Fort Kent Cinema

**Description:** Bring your knitting, your cross stitch, your sketchbook.
The last Tuesday of every month, the lights stay dimmed instead of dark so
you can work while the movie plays. $4 for Rivertown Arts and Fort Kent
Cinema members. Everyone is welcome.

---

## Hero

**Eyebrow:** With Rivertown Community Arts Center

**Heading:** Craft Cinema Night

**Subheading:** The last Tuesday of every month, we turn the lights down
instead of off — so you can keep your hands busy while the movie plays.

**Next date:** Tuesday, September 29 · [CONFIRM start time]

**Primary button:** See what's playing
**Secondary link:** About Rivertown Arts →

---

## What it is

A movie night for people who can't sit still with empty hands.

Once a month we hold a screening with the house lights dimmed rather than
killed — low enough for the picture to look right, bright enough to find
your place in a row of stitches. Bring whatever you're working on. Knitting
and crochet, cross stitch, embroidery, hand quilting, a sketchbook, a
coloring book, beadwork, a journal. Sit with it for two hours and let
someone else do the entertaining.

We run this one with Rivertown Community Arts Center, a few blocks away on
Market Street. Their members pay our member rate, $4 a ticket. Everyone
else is welcome at regular evening admission — you do not need to belong to
anything to come, and you do not need to bring a project. Plenty of people
just come for the movie.

---

## How it works

- **The lights stay on, dimmed.** Not a dark house. You'll be able to see
  your work without a headlamp.
- **Bring your own project.** We don't supply materials, and we don't teach.
  This is a room to work in, not a class.
- **Keep it to your seat.** If it fits on your lap and in the seat beside
  you, it's fine. Sewing machines, easels and anything that needs a table
  are not going to work in here.
- **Nothing wet, nothing loose.** No paint, no glue, no glitter — same rule
  as our rentals, and for the same reason. Please don't bring anything with
  a blade that could find the upholstery.
- **Quiet counts.** Talk between friends is expected. Anything that clatters
  is not.
- **Concessions are open as usual.** [CONFIRM: any craft-night concession
  deal, e.g. popcorn discount, or drop this line.]

---

## Admission

**$4** — Rivertown Community Arts Center members, and Fort Kent Cinema
members. Show your membership at the box office, or just give your name if
it's ours.

**Regular evening admission** — everyone else. No membership required, no
project required.

[CONFIRM: does a Rivertown member need to present a card, or is a name
enough? Rivertown would need to be willing to confirm names at the door for
the second option to work.]

---

## Dates

Last Tuesday of the month, year round:

- Tuesday, September 29, 2026
- Tuesday, October 27, 2026
- Tuesday, November 24, 2026
- Tuesday, December 29, 2026
- Tuesday, January 26, 2027
- Tuesday, February 23, 2027

*Implementation note: compute this from the date rather than typing the list
into a template. A hardcoded list of dates is a list that goes stale in
public — the same failure mode the sponsor showcase comment warns about.
December 29 falls between Christmas and New Year's; decide now whether that
one runs, because the page will otherwise promise it.*

---

## About Rivertown

Rivertown Community Arts Center opened on Main Street in 2024 and is the
only arts center in the St. John Valley. It's a nonprofit, membership-based
studio and gathering space at 26 Market Street, with a pottery studio around
the corner on East Market — open studios, classes for adults and kids,
music, writing, open mics. Membership starts at $25.

More at rivertowncac.org.

[CONFIRM with Rivertown before publishing: they should approve how we
describe them, the link, and the membership figure. Their own membership
page is the source that can change under us.]

---

## FAQ

Written as a list so it can render twice — visible on the page and as
FAQPage structured data — the same contract as `SPONSORSHIP_FAQ` and
`RENTALS_FAQ` in `web/constants.py`.

**Do I have to be a member to come?**
No. Craft Cinema Night is open to everyone at regular evening admission.
Membership — ours or Rivertown's — is what gets you the $4 rate, not what
gets you in the door.

**How do I get the $4 rate?**
Be a member of Rivertown Community Arts Center or of Fort Kent Cinema, and
say so at the box office. It's the same rate our own members pay on any
evening; this is just the night it extends to Rivertown's members too.

**Do I have to bring a craft?**
No. Come and watch the movie. The only difference on this night is the
lighting and the company.

**What movie plays?**
[CONFIRM. This is the question people actually care about — every writeup of
these nights says attendance tracks the title more than the time or the
price. Decide whether Craft Cinema Night takes whatever is in the evening
slot that Tuesday, or gets a picked title, and say so here. If it's picked,
the page needs a slot showing the next one.]

**How dark is it?**
Dimmed, not dark. Bright enough to work by, dim enough that the screen still
looks like a screen. If you're doing something that needs real light, a
small clip light on your own project is fine — please point it at your lap
and not at the room.

**What can't I bring?**
No paint, glue or glitter. Nothing that needs a table or an outlet, and
nothing bigger than your own seat. If you're not sure, call us before you
pack it — (207) 231-5287.

**Can I bring my kids?**
Yes, with the usual caveat that the film's rating is the film's rating.
[CONFIRM: is this pitched at adults, or families too? It changes which
titles make sense.]

**Do I need a ticket ahead of time?**
[CONFIRM: walk-up only, or advance sale? If seating is capped for this
night, say the cap here.]

---

## Decided

All five open questions were answered on 2026-09-21:

1. **Start time:** 6:30 PM.
2. **What plays:** whatever is in the evening slot that Tuesday. Read from
   the schedule, not typed — see `web/services/craft_night.py`.
3. **First night:** Tuesday, September 29, 2026.
4. **Price:** $4 for members, $8 general evening admission. These are the
   same promise `/membership/` makes as "$4 off evening tickets" — if
   evening admission is ever repriced, that benefit line and
   `CRAFT_NIGHT` have to move together or the site contradicts itself.
   Note that `/craft-night/` is the **first page on the site to publish a
   general admission price at all**.
5. **Rivertown:** signed off on the partnership and on being named.

Still outstanding, and not blocking:

- **Their logo.** `CRAFT_NIGHT["partner_logo"]` is blank and the section
  renders their name alone. Ask Rivertown for the asset rather than taking
  it off their site — a mark is granted separately from a partnership, and
  usually comes with rules about clear space and light grounds. Drop the
  file in `static/img/`, set the constant, done.
- **`og:image`** is still the generic card, same as `/history/`.
- **December 29** falls between Christmas and New Year's. The page promises
  it because the rule produces it. Decide whether it runs.

## What shipped

- `web/services/craft_night.py` — `last_tuesday()`, `upcoming_nights()`,
  `evening_showtimes()`, `get_craft_nights()`.
- `CRAFT_NIGHT` + `CRAFT_NIGHT_FAQ` in `web/constants.py`, and a
  "Craft Night" entry in the More dropdown.
- `CraftNightView`, `path("craft-night/")`, sitemap entry
  (`STATIC_PAGE_LASTMOD["craft_night"]`).
- `web/templates/web/craft_night.html`,
  `static/css/CraftNightPage.css` (registered in
  `frontend/styles/main.css`; bundle rebuilt).
- `web/tests/test_craft_night.py` — 29 tests.
