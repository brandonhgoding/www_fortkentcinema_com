# Heckle Night — design notes

`/heckle-night/`, shipped 2026-09-22. A monthly screening of a bad public
domain film that the room is invited to talk over. The premise is Mystery
Science Theater 3000's; the name, the films and the page are ours.

This is a design note rather than a copy draft — the page is built, and the
copy is in the template. What is recorded here is the set of decisions
behind it, and the things that are still open.

---

## Decided

| | | Why |
|---|---|---|
| **Night** | Third Friday, 7:00 PM exactly | Friday is when a small town already goes out, and this night does not work without a crowd. 7:00 rather than a late show because people drive in from across the Valley and winter is a real reason to stay home. Most of these films run 60–80 minutes, so the room is out by about 8:30. |
| **First night** | Friday, October 16 2026 | Chosen by the owner. It is also genuinely the third Friday of October, so the first night and the standing rule agree — a test pins that, because a start date the rule does not produce would be skipped silently. |
| **Price** | $4 at the door, **free for members** | $4 is exactly what a member pays for a regular evening show ($8 less the $4 `/membership/` promises), so the door price here is the member rate offered to everybody — and members go one better and come in free. Cheapest night of the month for everyone, only free one for members, which is the right shape for a night whose whole problem is filling the room. |
| **Audience** | All ages, jokes kept PG | Bigger pool in a small town, and it lets the night be something a family can do. PG is a house rule, not a rating — the films carry whatever rating they carry, which for most of these is none at all. |
| **Name** | Heckle Night | Describes the night literally, and is ours. MST3K is named twice on the page: once to explain the idea, once in the FAQ to disclaim the affiliation. Never in the title, the URL or the metadata. |

## How it is built

The same shape as `/craft-night/`, deliberately, because it is the same
object: a standing monthly night with a rule, a price, house rules, a date
list and an FAQ.

- **The dates are computed.** "Third Friday" is a rule, so the calendar
  answers it. A typed list of dates goes stale in public and goes stale
  silently — nothing breaks when the last one passes, the page just stops
  having a next date.
- **The film is read from the schedule**, out of the same Engagement and
  Showtime rows Now Showing reads, so the page and the schedule cannot
  disagree. Most listed nights will show "Not booked yet", because the
  sixth Friday on the page is five months out. That is the normal state.
- **And only special events count.** This is where the page parts company
  with craft night. Craft night *adopts* whatever regular show is in that
  Tuesday's evening slot — that is its premise. Heckle Night is its own
  booking, so the query matches `Engagement.Kind.SPECIAL_EVENT` and
  nothing else. Unfiltered, the page would have announced the Friday
  first-run feature as the film the room is invited to shout at.
  `CLASSIC` and `DOUBLE_FEATURE` are near misses and are still misses: a
  night booked as the wrong kind reads "Not booked yet", which is visibly
  wrong and fixable, rather than quietly showing the wrong film.
- **One thing craft night did not need: a start date.** This night has
  never run, so the rule alone would have advertised a September Friday
  nobody planned. `HECKLE_NIGHT["starts_on"]` is a floor.

## Still open

- **Every booked Heckle Night has to start at 7:00 PM exactly.** The
  lineup match is an equality, not a window, so a night booked for 7:30
  makes this page read "Not booked yet" while the listings show the
  event. This is knowingly crude — it fails visibly rather than silently,
  which is the same trade the kind filter makes. The real fix is a flag
  on the Engagement saying "this one is a Heckle Night", which is a
  migration nobody needs yet; until then the start time is the only
  handle the query has.
- **Every booked Heckle Night has to be a Special Event.** `kind` must be
  `SPECIAL_EVENT` or the night does not appear on this page at all. Leave
  "show in main listings" ticked — it defaults on in the dashboard, and
  it is now the only thing keeping private bookings (which are special
  events too) off this page. Clearing it is how a booking is marked
  private, and this page respects that.
- **Every booked Heckle Night has to be flagged `is_free_for_members`.**
  This is the one manual step the code cannot do. The page states "free
  for members" as standing policy; the *badge* on the home page and the
  film page comes from `Engagement.is_free_for_members`, set per booking
  in the dashboard. Miss it and the two disagree in public.
- **The free night must not spend a monthly free admission.**
  `audience.FreeAdmission` is a separate allowance, drawn down only when
  staff record a redemption — nothing about a free night records one, so
  a member keeps whatever their tier gives them. The FAQ says so, and the
  box office needs to know it.
- **$4 reads as "the member rate, for everybody"** only while evening
  admission is $8 less a $4 member benefit. A reprice of evening
  admission has to look at this number too; a test pins the relationship
  so it cannot drift quietly.
- **The films themselves.** Nothing is booked. Check the copyright status
  of each title before advertising it — "public domain" is claimed more
  often than it is true, and a restored print or its soundtrack can carry
  rights of its own even when the film does not. Worth checking first:
  *Plan 9 from Outer Space*, *Robot Monster*, *The Brain That Wouldn't
  Die*, *Teenagers from Outer Space*, *Attack of the Giant Leeches*, and
  *Santa Claus Conquers the Martians* for December.
- **Nothing on the public page explains our side of the economics.**
  Deliberately: what a booking costs us is not the customer's business,
  and a page that argues "this is cheap because it's cheap for us" invites
  the question on every other ticket we sell. The page sells the night.
- **The first night needs a host.** An empty or scattered room will not
  heckle anything, and nobody wants to go first. Someone to get the first
  laughs, and a few friends who know they are there to start, is the
  difference between this working and dying quietly in month two.
- **No social card of its own.** The page falls back to the generic
  og-image, the same gap `/history/` has.
- **UMFK students are gone May through August.** If they turn out to be a
  big part of the crowd, summer will be quiet. Worth running year round
  first and seeing who shows up.
