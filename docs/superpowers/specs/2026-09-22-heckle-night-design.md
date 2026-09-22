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
| **Night** | Third Friday, 7:00 PM | Friday is when a small town already goes out, and this night does not work without a crowd. 7:00 rather than a late show because people drive in from across the Valley and winter is a real reason to stay home. Most of these films run 60–80 minutes, so the room is out by about 8:30. |
| **First night** | Friday, October 16 2026 | Chosen by the owner. It is also genuinely the third Friday of October, so the first night and the standing rule agree — a test pins that, because a start date the rule does not produce would be skipped silently. |
| **Price** | $5 flat | The film costs nothing to book, so the ticket can be cheap and the night still makes money. Cheap enough to be an impulse. |
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
- **One thing craft night did not need: a start date.** This night has
  never run, so the rule alone would have advertised a September Friday
  nobody planned. `HECKLE_NIGHT["starts_on"]` is a floor.

## Still open

- **A member pays $1 more here than on any other evening.** `/membership/`
  promises "$4 off evening tickets" against $8 general admission, which
  puts a member at $4. At $5 flat, Heckle Night is the one night of the
  month a membership saves nothing. The FAQ answers this head on rather
  than letting someone find out at the box office, but it is a real trade
  and worth revisiting after the first night or two. Changing it is one
  constant and one FAQ answer.
- **The films themselves.** Nothing is booked. Check the copyright status
  of each title before advertising it — "public domain" is claimed more
  often than it is true, and a restored print or its soundtrack can carry
  rights of its own even when the film does not. Worth checking first:
  *Plan 9 from Outer Space*, *Robot Monster*, *The Brain That Wouldn't
  Die*, *Teenagers from Outer Space*, *Attack of the Giant Leeches*, and
  *Santa Claus Conquers the Martians* for December.
- **The first night needs a host.** An empty or scattered room will not
  heckle anything, and nobody wants to go first. Someone to get the first
  laughs, and a few friends who know they are there to start, is the
  difference between this working and dying quietly in month two.
- **No social card of its own.** The page falls back to the generic
  og-image, the same gap `/history/` has.
- **UMFK students are gone May through August.** If they turn out to be a
  big part of the crowd, summer will be quiet. Worth running year round
  first and seeing who shows up.
