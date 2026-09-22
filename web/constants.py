import datetime
from urllib.parse import quote_plus

# Ported verbatim from the React SPA's src/data/siteConfig.json.
SITE_CONFIG = {
    "cinema": {
        "name": "Fort Kent Cinema",
        "tagline": "Maine's Northernmost Picture Show",
        "heroQuote": "Where the movies come to life under the northern lights",
        "address": {
            "street": "13 Hall Street",
            "city": "Fort Kent",
            "state": "ME",
            "zip": "04743",
        },
        "phone": "(207) 231-5287",
    },
    "hours": {
        "weekday": {"days": "Monday - Thursday", "open": "4:00 PM", "close": "9:00 PM"},
        "weekend": {"days": "Friday - Sunday", "open": "2:00 PM", "close": "10:00 PM"},
    },
    "social": {"facebook": "https://facebook.com/fortkentcinema"},
    # Items with "children" render as a dropdown; everything else is a plain
    # link. FIVE TOP-LEVEL ITEMS IS THE CEILING, counting each dropdown as
    # one — the nav collapses to a hamburger at 768px, and a sixth is what
    # strained the 768-900px range. A dropdown costs the same width as a
    # link plus a caret, so trading a link for a menu is width-neutral;
    # adding one is not.
    "navigation": [
        {"label": "Now Showing", "href": "#now-showing"},
        {"label": "Coming Soon", "href": "#coming-soon"},
        # Trailing slashes are required — these routes are defined with them, and
        # a bare /blog costs a 301 on every click and every crawl.
        {"label": "Membership", "href": "/membership/"},
        {
            # Events took the slot Rentals held. A rental is something you
            # buy from us; an event is something you turn up to, and the
            # things people turn up to had no home in the nav at all —
            # Craft Night was buried under "More" with the sponsor form and
            # the blog. Rentals moved down rather than out.
            "label": "Events",
            # No "href": this opens a menu, it is not a destination.
            "children": [
                # Chronological by night of the month, not alphabetical:
                # Heckle Night is the third Friday, Craft Night the last
                # Tuesday. Two entries is the whole Events menu, so the
                # order is cheap to hold and reads as a month.
                {"label": "Heckle Night", "href": "/heckle-night/"},
                {"label": "Craft Night", "href": "/craft-night/"},
            ],
        },
        {
            "label": "More",
            # No "href": this opens a menu, it is not a destination.
            "children": [
                {"label": "Rentals", "href": "/rentals/"},
                {"label": "Sponsor", "href": "/sponsor/"},
                {"label": "History", "href": "/history/"},
                # About page temporarily hidden:
                # {"label": "About", "href": "/about/"},
                {"label": "Blog", "href": "/blog/"},
                # Bare, unlike the section pages above — urls.py defines
                # path("vote", ...) without a slash. APPEND_SLASH only adds
                # slashes, so /vote/ is a hard 404, not a recoverable 301.
                {"label": "Film Vote", "href": "/vote"},
            ],
        },
    ],
}


# Everything below is derived from SITE_CONFIG above, so the config stays the
# single source of truth. SITE_CONFIG["seo"] is what templates read: it rides
# along on the existing `site_config` context variable, which is why it lives
# here rather than in a second context processor.

_WEEK = [
    "Monday",
    "Tuesday",
    "Wednesday",
    "Thursday",
    "Friday",
    "Saturday",
    "Sunday",
]


def _expand_days(label):
    """"Monday - Thursday" -> ["Monday", ..., "Thursday"].

    The hours blocks are written for humans ("Friday - Sunday"); schema.org
    wants the days named one by one. Ranges wrap, so "Saturday - Monday"
    would work too.
    """
    parts = [part.strip() for part in label.split("-")]
    if len(parts) == 1:
        return [parts[0]]
    start, end = _WEEK.index(parts[0]), _WEEK.index(parts[-1])
    if start <= end:
        return _WEEK[start : end + 1]
    return _WEEK[start:] + _WEEK[: end + 1]


def _iso_time(label):
    """"4:00 PM" -> "16:00". schema.org opens/closes are 24-hour ISO."""
    return datetime.datetime.strptime(label, "%I:%M %p").strftime("%H:%M")


OPENING_HOURS_SPECIFICATION = [
    {
        "dayOfWeek": _expand_days(block["days"]),
        "opens": _iso_time(block["open"]),
        "closes": _iso_time(block["close"]),
    }
    for block in SITE_CONFIG["hours"].values()
]

_ADDRESS = SITE_CONFIG["cinema"]["address"]
_MAP_QUERY = quote_plus(
    "{street}, {city}, {state} {zip}".format(
        street=_ADDRESS["street"],
        city=_ADDRESS["city"],
        state=_ADDRESS["state"],
        zip=_ADDRESS["zip"],
    )
)

SITE_CONFIG["seo"] = {
    "opening_hours": OPENING_HOURS_SPECIFICATION,
    # hasMap on the MovieTheater. Built from the address rather than pasted,
    # so moving the theater moves the pin.
    "map_url": "https://www.google.com/maps/search/?api=1&query=" + _MAP_QUERY,
}

# The rental policies, as questions.
#
# These were nine bullets inside a collapsed "POLICIES & INFORMATION"
# <details> at the foot of /rentals/ — the terms someone has to know BEFORE
# they call, hidden behind a click and written as house rules rather than as
# answers. Every one of those bullets survives here, several folded together
# where they answer the same question: the deposit and the signed agreement
# are both "how do I hold a date", and damages and decorations are both "what
# can we do to the room".
#
# Same contract as SPONSORSHIP_FAQ: nothing here is a new policy. If a term
# changes it changes here, and the page and its FAQPage markup follow, because
# both render this list.
RENTALS_FAQ = [
    {
        "question": "How do I reserve a date?",
        "answer": (
            "A 50% deposit holds it. We'll send a rental agreement to sign — "
            "the booking is confirmed once that's back — and the balance is "
            "due on the day of the event."
        ),
    },
    {
        "question": "What if I have to cancel?",
        "answer": (
            "Cancel seven or more days ahead and the deposit is refunded in "
            "full. Inside seven days the deposit is forfeited."
        ),
    },
    {
        "question": "How long do we get, and how late can we stay?",
        "answer": (
            "The base rate covers two hours, and each additional half-hour is "
            "$50. Whatever the length, every event has to end by 11:00 PM."
        ),
    },
    {
        "question": "Can we bring our own food and drink?",
        "answer": (
            "No — food and drink have to be bought from us or arranged with "
            "us beforehand. Popcorn for your group is already included in the "
            "rate."
        ),
    },
    {
        "question": "Can we decorate?",
        "answer": (
            "Yes, as long as we've approved it in advance. No confetti, no "
            "glitter, and nothing that could damage the seats or the screen. "
            "The renting party covers any damage to the theater or the "
            "equipment during the event."
        ),
    },
    {
        "question": "Can we sell tickets or advertise the event?",
        "answer": (
            "Not for a private screening — those are for invited family and "
            "friends, with your own DVD or Blu-ray. Selling tickets or "
            "promoting it publicly makes it a licensed screening: we arrange "
            "the license through our partners and quote the film fee per "
            "film, on top of the base rate."
        ),
    },
]

# Ported verbatim from the React SPA's src/data/membershipFaq.json.
MEMBERSHIP_FAQ = [
    {
        "question": "How long does a membership last?",
        "answer": "Each tier specifies its duration (most are annual). Your card shows the exact end date.",
    },
    {
        "question": "What's included with a family tier?",
        "answer": "Family tiers cover the cardholder plus immediate family members. Just give your name at the box office.",
    },
    {
        # The badge this answer points at is Engagement.is_free_for_members,
        # which paints "Free for Members" on the home page listings and on the
        # film's own page. The answer describes what the site already shows —
        # it does not promise how often one is booked.
        "question": "Which films are free for members?",
        "answer": (
            "The ones marked Free for Members — you'll see the badge on the "
            "poster on the home page and on the film's own page. Give your "
            "name at the box office, the same as any other visit."
        ),
    },
    {
        "question": "How do I use my membership at the box office?",
        "answer": "Tell us your name. We'll look you up and apply your member benefits.",
    },
    {
        "question": "Can I get a refund?",
        "answer": "Memberships are non-refundable. Reach out to the box office if you have questions.",
    },
    {
        "question": "Do I get a card?",
        "answer": "Yes — a printable PDF card is emailed to you immediately after purchase.",
    },
]

# The current sponsored screening, or None between them.
#
# Everything a banner needs is already in the catalog — title, dates,
# showtimes, poster, trailer — and web.views.sponsored_screening() reads it
# from those rows so the homepage and Now Showing cannot disagree. What is
# NOT in the catalog is who paid: cinema.Engagement has no sponsor field, and
# SponsorshipInquiry records a business *asking*, not a booking it underwrote.
# That gap is why this constant exists at all.
#
# `film_slug` is the join. It fails safe: no matching film, or a run that has
# ended, and the banner simply does not render. Note that Film.generate_slug()
# suffixes collisions, so booking a second copy of a title moves its slug and
# quietly retires the banner — check here first if it stops appearing.
#
# None between runs. The banner already retires itself on the booking's
# end_date, so clearing this is tidying rather than a deadline — but leaving a
# finished run configured means the next slug collision or re-booking of the
# same film can bring the banner back unannounced.
#
# The Land Before Time, sponsored by AParadis Photography over Labor Day
# weekend 2026, was the first run. Its config is the shape to fill in:
#
#     SPONSORED_SCREENING = {
#         "film_slug": "the-land-before-time",
#         "sponsor": "AParadis Photography",
#         # The occasion, when there is one. A holiday weekend sells a family
#         # matinee better than the word "sponsored" does. Blank falls back to
#         # "Sponsored screening" in the template.
#         "eyebrow": "Labor Day Weekend",
#         # A price on the homepage is a promise we have to honour at the
#         # door — leave it out rather than guess.
#         "admission": "$4",
#     }
SPONSORED_SCREENING = None

# Sponsorship program. A local business underwrites a screening; the tiers
# stack, each one adding to the one before it.
#
# Pricing is derived, not guessed: Universal charges a flat $200 to book a
# library title, so tier 1 leaves $99 for staff, projection and the promotion
# we do for the sponsor. Tier 2 adds free public admission — cheap for us,
# because at ~6 admissions per showtime a free promoted screening fills a room
# that would otherwise be near-empty rather than displacing ticket sales.
# Tier 3 adds popcorn: 100 mediums retail at $625, but at a 30-50% concession
# attach rate the real cost is ~$250 of forgone sales plus ~$60 of materials.
# See docs/superpowers/specs/2026-08-23-film-sponsorships-design.md.
SPONSORSHIP_POPCORN_CAP = 100

# The two worked examples on /sponsor/. A named local business sells far
# harder than "Your Business Here", and both of these approved being named.
#
# They live here rather than in the template because "upcoming" has a shelf
# life: the day The Wild Robot plays, it becomes the past example and the
# upcoming slot needs the next booking or nothing at all. That should be a
# data edit, not a template edit — the same reason SPONSORED_SCREENING is a
# constant. Either slot may be None and its card simply does not render.
#
# Do not add a date to `upcoming` unless it is confirmed. This block used to
# be headed "Happening this month", which was true when it was written and
# silently stopped being true afterwards.
SPONSORSHIP_SHOWCASE = {
    "past": {
        "sponsor": "AParadis Photography",
        "film": "The Land Before Time",
        # The first sponsored run. Admission was $4 at the door; see the
        # retired SPONSORED_SCREENING config above for the full shape.
        "occasion": "Labor Day weekend",
    },
    "upcoming": {
        "sponsor": "A.H. Custom Carpentry",
        "film": "The Wild Robot",
    },
}

SPONSORSHIP_TIERS = [
    {
        "key": "presenting",
        "name": "Presenting Sponsor",
        "eyebrow": "Cover the film",
        "price": 299,
        "includes": [
            "We book the title you pick",
            "Social media posts in the run-up to the show",
            "Your name on the big screen before the film",
        ],
    },
    {
        "key": "community",
        "name": "Community Screening",
        "eyebrow": "Cover the film and admission",
        "price": 499,
        "includes": [
            "We book the title you pick",
            "Social media posts in the run-up to the show",
            "Your name on the big screen before the film",
            "Admission is free for everyone who comes",
        ],
    },
    {
        "key": "full_house",
        "name": "Full House",
        "eyebrow": "Cover the film, admission and popcorn",
        "price": 799,
        "includes": [
            "We book the title you pick",
            "Social media posts in the run-up to the show",
            "Your name on the big screen before the film",
            "Admission is free for everyone who comes",
            "Medium buttered popcorn for the first 100 guests",
        ],
    },
]

# tier key -> display name, for surfaces that only have the key (e.g. a
# SponsorshipInquiry.tier value on the dashboard). SponsorshipInquiry.tier
# has no `choices` of its own — cinema doesn't import web — so this is the
# one place the mapping lives.
SPONSORSHIP_TIER_LABELS = {t["key"]: t["name"] for t in SPONSORSHIP_TIERS}

# Rendered twice on /sponsor/: as a <dl> a reader can see, and as FAQPage
# structured data in the head. Google penalises FAQ markup whose answers are
# not visible on the page, so the two renderings read from this one list.
#
# Every answer here is a restatement of something the page already commits to
# elsewhere — the tier note about prices depending on the title, the catalog
# header's "ask anyway", the confirmation message's couple of days. Nothing in
# here is a new promise; if a policy changes, the tier or the copy it came
# from changes with it.
SPONSORSHIP_FAQ = [
    {
        "question": "What does sponsoring a film cost?",
        "answer": (
            "There are three levels, starting at $299 to cover the film, "
            "$499 to cover the film and everyone's admission, and $799 to "
            "add popcorn. Those are starting prices — some titles cost us "
            "more to book than others, so the final number depends on the "
            "film you pick."
        ),
    },
    {
        "question": "Can I choose the movie?",
        "answer": (
            "Yes. The catalog on this page lists everything we can book "
            "right now, and you can search and sort it. If the film you "
            "want isn't on the list, ask anyway — we'll find out whether we "
            "can get it."
        ),
    },
    {
        "question": "Can I pick the date?",
        "answer": (
            "Tell us the week you have in mind and we'll work out a date "
            "that fits the schedule. The date and the film get settled in "
            "the same conversation, so you don't need both decided before "
            "you write."
        ),
    },
    {
        "question": "What does my business actually get?",
        "answer": (
            "Your name on the big screen before the film, and in every "
            "social media post we make in the run-up to the show."
        ),
    },
    {
        "question": "Is a sponsored screening open to the public?",
        "answer": (
            "Yes. A Presenting Sponsor screening is a normal ticketed show "
            "with your name on it. At the Community Screening and Full "
            "House levels admission is free for everyone who comes. If you "
            "want the theater to yourself instead, that's a private rental "
            "rather than a sponsorship."
        ),
    },
    {
        "question": "What happens after I get in touch?",
        "answer": (
            "We'll be back to you within a couple of days to talk through "
            "dates and which film makes sense. Nothing is committed by "
            "sending the form — it just starts the conversation."
        ),
    },
]


# Recreated Savoy Theatre playbills, transcribed from the originals held by the
# Fort Kent Historical Society and reproduced in Lisa Ornstein's "Going to the
# Movies in Fort Kent" (The Northern Maine Journal No. 48, April/June 2000).
#
# Transcribed VERBATIM, including the printer's punctuation: single quotes
# around titles, "&" not "and", the trailing period on abbreviated weekdays.
# Do not tidy these into house style — the whole point is the sheet as it was
# set. `tag` is the line the printer ran under every title; in 1931 "All
# Talking" was a selling point, not a description.
#
# `youtube_url` is deliberately blank. The template renders a plain <span>
# when it is empty and an <a> when it is filled, so an unfilled row is never
# a dead link — adding one later is a one-line edit here and nothing else.
SAVOY_PLAYBILLS = [
    {
        "slug": "1931-04-06",
        "theatre": "Savoy",
        "sub": "Theatre",
        "town": "Ft. Kent, Me.",
        "label": "Week of April 6, 1931",
        "shows": [
            {
                "day": "Mon.", "date": "April 6",
                "star": "Marie Dressler & Polly Moran", "film": "Reducing",
                "quotes": "double", "tag": "All Talking", "youtube_url": "",
            },
            {
                "day": "Tues.", "date": "April 7", "star": "Richard Cromwell",
                "film": "Tol'able David", "quotes": "double", "tag": "All Talking",
                "youtube_url": "",
            },
            {
                "day": "Wed.", "date": "April 8", "star": "Edna Best",
                "film": "The Escape", "tag": "All Talking", "youtube_url": "",
            },
            {
                "day": "Thur.", "date": "April 9", "star": "",
                "film": "Cohens & Kellys in Africa",
                "after": "With Geo. Sidney & Chas. Murray", "tag": "All Talking",
                "youtube_url": "",
            },
            {
                "day": "Fri.", "date": "April 10", "star": "Lowell Sherman",
                "film": "The Royal Bed", "quotes": "double", "tag": "All Talking",
                "youtube_url": "",
            },
            {
                "day": "Sat.", "date": "April 11", "star": "Evelyn Brent",
                "film": "The Silver Horde", "quotes": "double", "tag": "All Talking",
                "youtube_url": "",
            },
        ],
    },
    {
        "slug": "1931-04-13",
        "theatre": "Savoy",
        "sub": "Theatre",
        "town": "Ft. Kent, Me.",
        "label": "Week of April 13, 1931",
        "shows": [
            {
                "day": "Mon.", "date": "April 13", "star": "Wheeler & Woolsey",
                "film": "Hook, Line & Sinker", "tag": "All Talking", "youtube_url": "",
            },
            {
                "day": "Tues.", "date": "April 14", "star": "Joan Crawford",
                "film": "Dance Fools Dance", "tag": "All Talking", "youtube_url": "",
            },
            {
                "day": "Wed.", "date": "April 15", "star": "Norman Foster",
                "film": "It Pays to Advertise", "tag": "All Talking", "youtube_url": "",
            },
            {
                "day": "Thur.", "date": "April 16", "star": "Lawrence Tibbett",
                "film": "The Southerner", "tag": "All Talking", "youtube_url": "",
            },
            {
                "day": "Fri.", "date": "April 17", "star": "Ralph Forbes",
                "film": "Beau Ideal", "tag": "All Talking", "youtube_url": "",
            },
            {
                "day": "Sat.", "date": "April 18", "star": "Leon Errol",
                "film": "Finn and Hattie", "tag": "All Talking", "youtube_url": "",
            },
        ],
    },
    {
        "slug": "1931-05-18",
        "theatre": "Savoy",
        "sub": "Theatre",
        "town": "Ft. Kent, Me.",
        "label": "Week of May 18, 1931",
        "shows": [
            {
                "day": "Mon.", "date": "May 18", "star": "Loretta Young",
                "film": "Three Girls Lost", "tag": "", "youtube_url": "",
            },
            {
                "day": "Tues.", "date": "May 19", "star": "Dorothy Mackaill",
                "film": "Kept Husbands", "tag": "", "youtube_url": "",
            },
            {
                "day": "Wed.", "date": "May 20", "star": "Constance Bennett",
                "film": "The Easiest Way", "tag": "", "youtube_url": "",
            },
            {
                "day": "Thur.", "date": "May 21", "star": "Charlotte Greenwood",
                "film": "Stepping Out", "tag": "", "youtube_url": "",
            },
            {
                "day": "Fri.", "date": "May 22", "star": "Spencer Tracy",
                "film": "Six Cylinder Love", "tag": "", "youtube_url": "",
            },
            {
                "day": "Sat.", "date": "May 23", "star": "Jack Holt",
                "film": "Subway Express", "tag": "", "youtube_url": "",
            },
        ],
    },
    {
        "slug": "1931-06-01",
        "theatre": "Savoy",
        "sub": "Theatre",
        "town": "Ft. Kent, Me.",
        "label": "Week of June 1, 1931",
        "shows": [
            {
                "day": "Mon.", "date": "June 1", "star": "Wm. Powell",
                "film": "Ladies Man", "tag": "", "youtube_url": "",
            },
            {
                "day": "Tues.", "date": "June 2", "star": "Betty Compson",
                "film": "The Lady Refuses", "tag": "", "youtube_url": "",
            },
            {
                "day": "Wed.", "date": "June 3", "star": "Elissa Landi",
                "film": "Always Goodbye", "tag": "", "youtube_url": "",
            },
            {
                "day": "Thur.", "date": "June 4", "star": "Clive Brook",
                "film": "Tarnished Lady", "tag": "", "youtube_url": "",
            },
            {
                "day": "Fri.", "date": "June 5", "star": "Lois Moran",
                "film": "Young Sinners", "tag": "", "youtube_url": "",
            },
            {
                "day": "Sat.", "date": "June 6", "star": "Richard Arlen",
                "film": "Gun Smoke", "tag": "", "youtube_url": "",
            },
        ],
    },
    {
        "slug": "1931-06-22",
        "theatre": "Savoy",
        "sub": "Theatre",
        "town": "Ft. Kent, Me.",
        "label": "Week of June 22, 1931",
        "shows": [
            {
                "day": "Mon.", "date": "June 22", "star": "Warwick Ward",
                "film": "The Perfect Alibi", "tag": "", "youtube_url": "",
            },
            {
                "day": "Tues.", "date": "June 23", "star": "Warner Oland",
                "film": "The Black Camel", "tag": "", "youtube_url": "",
            },
            {
                "day": "Wed.", "date": "June 24", "star": "Janet Gaynor",
                "film": "Daddy Long Legs", "quotes": "none", "tag": "",
                "youtube_url": "",
            },
            {
                "day": "Thur.", "date": "June 25", "star": "Ramon Novarro",
                "film": "Daybreak", "tag": "", "youtube_url": "",
            },
            {
                "day": "Fri.", "date": "June 26", "star": "Lowell Sherman",
                "film": "Bachelor Apartment", "tag": "", "youtube_url": "",
            },
            {
                "day": "Sat.", "date": "June 27", "star": "Bela Lugosi",
                "film": "Dracula", "tag": "", "youtube_url": "",
            },
        ],
    },
    {
        "slug": "1931-07-06",
        "theatre": "Savoy",
        "sub": "Theatre",
        "town": "Ft. Kent, Me.",
        "label": "Week of July 6, 1931",
        "shows": [
            {
                "day": "Mon.", "date": "July 6", "star": "Joan Bennett",
                "film": "Hush Money", "tag": "", "youtube_url": "",
            },
            {
                "day": "Tues.", "date": "July 7", "star": "Lupe Velez",
                "film": "Resurrection", "tag": "", "youtube_url": "",
            },
            {
                "day": "Wed.", "date": "July 8", "star": "Adolphe Menjou",
                "film": "L'Enigmatique Monsieur Parkes", "quotes": "double", "tag": "",
                "youtube_url": "",
            },
            {
                "day": "Thur.", "date": "July 9", "star": "Lew Ayres",
                "film": "Iron Man", "joiner": "", "tag": "", "youtube_url": "",
            },
            {
                "day": "Fri.", "date": "July 10",
                "star": "Victor McLaglen, Edmund Lowe", "film": "Women of All Nations",
                "tag": "", "youtube_url": "",
            },
            {
                "day": "Sat.", "date": "July 11", "star": "Jack Oakie",
                "film": "The Dude Ranch", "tag": "", "youtube_url": "",
            },
        ],
    },
]


# The Fort Kent Historical Society's own account of this history, recorded by
# the local public-access station. Embedded on /history/ behind the same
# click-to-load facade the trailers use, so the page costs nothing until
# someone actually asks for it.
#
# It is not archival film footage — it is a docent walking through the
# Society's 2017 centennial exhibit — and the page says so, because calling it
# "archive footage" would set the wrong expectation before someone spends 26
# minutes on it.
FILM_HISTORY_VIDEO = {
    "youtube_id": "sDXlW6nfasw",
    "title": "History of Fort Kent Movie Theaters",
    "channel": "WFKT TV 4",
    "year": 2019,
    "duration": "26:44",
    # Same length, in the ISO 8601 form schema.org's VideoObject wants. Kept
    # beside the human string so the two cannot drift apart.
    "iso_duration": "PT26M44S",
    "blurb": (
        "A Fort Kent Historical Society docent walks through the Society\u2019s "
        "2017 centennial exhibit \u2014 the photographs, playbills and artifacts "
        "this page is built from."
    ),
}


# Craft Cinema Night — the last Tuesday of the month, with Rivertown
# Community Arts Center.
#
# Lights dimmed rather than out, bring your own project, and Rivertown's
# members pay our member rate. Rivertown has signed off on the partnership
# and on being named here.
#
# The DATES are not in this dict, and deliberately so: they are computed
# from the calendar in web/services/craft_night.py, because "last Tuesday of
# the month" is a rule and a typed list of dates silently stops being true.
# Same reason SPONSORSHIP_SHOWCASE carries no dates.
CRAFT_NIGHT = {
    "partner": "Rivertown Community Arts Center",
    # What people actually call them, for the second and third mention.
    "partner_short": "Rivertown",
    "partner_url": "https://www.rivertowncac.org/",
    # Rivertown's logo, as a path under static/. The file they sent us: a
    # 400x400 circular badge on a transparent ground, so the template sizes
    # it square.
    #
    # Deliberately NOT hotlinked from rivertowncac.org: a partner's mark is
    # theirs to grant, separately from agreeing to the partnership, so we
    # serve the copy they gave us. Blank it and the template renders the
    # name alone, which is still a correct page.
    "partner_logo": "img/rivertown-logo.png",
    # Alt text for it. A logo is a name, so the alt text is the name — not
    # "Rivertown logo", which reads the decoration aloud and not the fact.
    "partner_logo_alt": "Rivertown Community Arts Center",
    # The standing start time. Shown only where no real showtime is known —
    # once a Tuesday is booked, the page renders that Showtime's own start,
    # so a moved show moves the page instead of contradicting it.
    "start_label": "6:30 PM",
    # Floor for "the evening slot" when matching a Tuesday's showtimes.
    # A floor rather than an exact 18:30 match: a show that shifts to 7:00
    # is still the evening show, and the page should follow it.
    "evening_from": datetime.time(17, 0),
    # Member and general evening admission. Both are stated because this
    # page has to answer "what does it cost if I'm not a member" — the
    # whole pitch is that everyone is welcome, and a page that prices only
    # the member rate reads like a members-only night.
    #
    # NOTE: these two numbers are the same promise /membership/ makes as
    # "$4 off evening tickets". If evening admission is ever repriced, that
    # benefit line and these constants have to move together or the site
    # contradicts itself in public.
    "member_price": 4,
    "general_price": 8,
    # How many nights the page lists. Six is two quarters — far enough out
    # to look like a standing fixture rather than a one-off, and short
    # enough that the list is still a list rather than a calendar.
    "months_ahead": 6,
}

# Rendered twice on /craft-night/ — as the visible FAQ and as FAQPage
# structured data in the head — from this one list. Same contract as
# SPONSORSHIP_FAQ and RENTALS_FAQ above: Google penalises FAQ markup whose
# answers are not on the page.
#
# Nothing here is a new policy. The craft restrictions are the rental
# decoration rule (no glitter, nothing that damages the seats) applied to a
# room full of projects, and the $4 is the existing member rate rather than
# a discount invented for this night.
CRAFT_NIGHT_FAQ = [
    {
        "question": "Do I have to be a member to come?",
        "answer": (
            "No. Craft Cinema Night is a regular evening show and anyone can "
            "buy a ticket at the door. Being a member — ours or Rivertown's "
            "— is what gets you the $4 rate, not what gets you in."
        ),
    },
    {
        "question": "How do I get the $4 rate?",
        "answer": (
            "Tell us at the box office that you're a Rivertown member, or "
            "give us your name if you're one of ours. It's the same $4 off "
            "an evening ticket our members get any night of the week — this "
            "is just the night it reaches Rivertown's members too."
        ),
    },
    {
        "question": "Do I have to bring a craft?",
        "answer": (
            "Not at all. Come and watch the movie. The only things different "
            "about this night are the lighting and the company."
        ),
    },
    {
        "question": "What movie plays?",
        "answer": (
            "Whatever is in the 6:30 slot that Tuesday — it's a regular "
            "showing, run a little differently. The dates on this page fill "
            "in with the title as soon as the booking is set, which is "
            "usually two or three weeks ahead."
        ),
    },
    {
        "question": "How dark does it get?",
        "answer": (
            "Dimmed, not dark. Low enough that the screen still looks like a "
            "screen, bright enough to find your place in a row of stitches. "
            "If your project needs more light than that, a small clip light "
            "is fine — please keep it pointed at your lap."
        ),
    },
    {
        "question": "What can I bring, and what should I leave home?",
        "answer": (
            "Anything quiet that fits in your own seat: knitting, crochet, "
            "cross stitch, embroidery, hand quilting, beadwork, a "
            "sketchbook, a coloring book, a journal. Leave the paint, glue "
            "and glitter at home, along with anything that needs a table, an "
            "outlet or a blade near the upholstery. If you're not sure, call "
            "us before you pack it."
        ),
    },
    {
        "question": "Can I bring my kids?",
        "answer": (
            "Yes — it's a public show and the film's rating is the film's "
            "rating, the same as any other night. It tends to run quiet, so "
            "it suits a child who has a project of their own to work on."
        ),
    },
    {
        "question": "Do I need a ticket in advance?",
        "answer": (
            "No. Come to the door. If a particular night looks like it's "
            "going to fill, we'll say so on Facebook first."
        ),
    },
]


# Heckle Night — /heckle-night/
#
# A bad public domain movie, monthly, that the room is invited to talk over.
# The premise is MST3K's, and the page says so once to explain itself; the
# name is not theirs and neither are the episodes, so nothing here borrows
# either. "Heckle Night" is ours and describes the night literally.
#
# The film comes from the schedule, the same way Craft Night's does — see
# web/services/heckle_night.py. What is NOT computable, and therefore lives
# here, is the rule, the price and who the night is for.
HECKLE_NIGHT = {
    # The rule, and the first night it applies to.
    #
    # "Third Friday" is a rule so the calendar can answer it, for the same
    # reason CRAFT_NIGHT's dates are computed: a typed list of dates goes
    # stale in public, and it goes stale silently.
    #
    # starts_on is the part craft night did not need. This night has never
    # run, so the rule alone would advertise a September date that no one
    # has planned. Nothing before this date renders. October 16 2026 IS the
    # third Friday of October, so the first night and the rule agree — if
    # that start date is ever moved to a date the rule does not produce,
    # the page will skip it and show the next real third Friday instead.
    "starts_on": datetime.date(2026, 10, 16),
    # The standing start time. Shown only where no real showtime is known:
    # once a Friday is booked the page renders that Showtime's own start,
    # so a moved show moves the page rather than contradicting it.
    "start_label": "7:00 PM",
    # Floor for "the evening slot" when matching a Friday's showtimes.
    # Same floor craft night uses, and a floor rather than an exact 19:00
    # match for the same reason: a show that shifts is still the show.
    "evening_from": datetime.time(17, 0),
    # $4 at the door, free if you're a member.
    #
    # The number matches what a member pays for a regular evening show
    # ($8 general admission less the "$4 off evening tickets" /membership/
    # promises), so the door price here is the member rate offered to
    # everybody — and members go one better and come in free. That makes
    # this the cheapest night of the month for everyone and the only free
    # one for members, which is the right shape for a night whose whole
    # problem is getting a crowd into the room.
    #
    # NOTE: $8 general evening admission is published on /craft-night/ and
    # implied by /membership/'s benefit line. This $4 reads as "the member
    # rate, for everyone" only while that stays true, so a reprice of
    # evening admission has to look at this number too.
    "general_price": 4,
    # Members in free, every Heckle Night.
    #
    # The MECHANISM already exists and this page must not invent a second
    # one: Engagement.is_free_for_members paints "Free for Members" on the
    # home page listings and the film's own page, and MEMBERSHIP_FAQ
    # already explains how to redeem it — give your name at the box office.
    # This page states the standing policy; each booked Heckle Night
    # engagement has to CARRY THAT FLAG or the badge and this page disagree
    # in public. That is a booking step, not something the code can do.
    #
    # Deliberately NOT the monthly free-admission allowance (audience
    # .FreeAdmission). That allowance is drawn down only when staff record
    # a redemption, and nothing here records one — so a member coming to
    # Heckle Night keeps whatever their tier gives them. The FAQ says so,
    # because otherwise the counter has to improvise an answer.
    "members_free": True,
    # Who the night is for, stated on the page because in a small town the
    # answer decides whether someone brings their kids. All ages means the
    # room is asked to keep the jokes PG — which is a house rule, not a
    # rating, and the film still carries whatever rating it carries.
    "audience": "All ages",
    # How many nights the page lists. Six, matching craft night: far enough
    # out to read as a standing fixture, short enough to still be a list.
    "months_ahead": 6,
}

# Rendered twice on /heckle-night/ — as the visible FAQ and as FAQPage
# structured data in the head — from this one list. Same contract as
# CRAFT_NIGHT_FAQ, SPONSORSHIP_FAQ and RENTALS_FAQ above: Google penalises
# FAQ markup whose answers are not on the page.
HECKLE_NIGHT_FAQ = [
    {
        "question": "I'm not funny. Should I come?",
        "answer": (
            "Yes. Half the room is there to laugh at the other half's "
            "jokes, and that half has the easier job. Nobody is keeping "
            "score."
        ),
    },
    {
        "question": "Can I just watch quietly?",
        "answer": (
            "You can, but the room won't be quiet, and that isn't a fault "
            "in the room. If you want a normal screening, every other "
            "showtime we run is one."
        ),
    },
    {
        "question": "Can I bring my kids?",
        "answer": (
            "Yes. Heckle Night is all ages, and we ask the room to keep "
            "the jokes PG — it's a house rule rather than a rating, and "
            "we'll say something if it drifts. The films themselves are "
            "old, cheap and harmless."
        ),
    },
    {
        # Points at the mechanism the site already has rather than
        # inventing a second one — see HECKLE_NIGHT["members_free"]. The
        # last sentence is the one the box office needs: a free night does
        # not spend a tier's monthly free admission.
        "question": "I'm a member. What do I pay?",
        "answer": (
            "Nothing. Every Heckle Night is free for members — give your "
            "name at the box office, the same as any other visit. If your "
            "tier includes free admissions each month, this doesn't use "
            "one up: the whole night is free for members, not just the "
            "first few through the door."
        ),
    },
    {
        "question": "What movie plays?",
        "answer": (
            "Something old, cheap and gloriously bad, and always in the "
            "public domain. The dates on this page fill in with the title "
            "as soon as the booking is set, usually two or three weeks "
            "ahead."
        ),
    },
    {
        "question": "Do I need a ticket in advance?",
        "answer": (
            "No. Come to the door. If a night looks like it's going to "
            "fill, we'll say so on Facebook first."
        ),
    },
    {
        "question": "Is this Mystery Science Theater 3000?",
        "answer": (
            "No, and we're not affiliated with them. We mention the show "
            "because it's the fastest way to explain what this night is. "
            "The movies are ours to pick and the jokes are yours to make."
        ),
    },
    {
        "question": "How loud is too loud?",
        "answer": (
            "If the person two rows over can't hear the next line of the "
            "movie, that's too loud. The film has to stay audible — it's "
            "the straight man, and the jokes don't work without it."
        ),
    },
]
