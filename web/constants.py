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
    # link. Four primary items is the ceiling — the nav collapses to a
    # hamburger at 768px, and a fifth was what strained the 768-900px range.
    "navigation": [
        {"label": "Now Showing", "href": "#now-showing"},
        {"label": "Coming Soon", "href": "#coming-soon"},
        # Trailing slashes are required — these routes are defined with them, and
        # a bare /blog costs a 301 on every click and every crawl.
        {"label": "Membership", "href": "/membership/"},
        {"label": "Rentals", "href": "/rentals/"},
        {
            "label": "More",
            # No "href": this opens a menu, it is not a destination.
            "children": [
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
            "Your name on the marquee",
            "Your name on screen before the film",
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
            "Your name on the marquee",
            "Your name on screen before the film",
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
            "Your name on the marquee",
            "Your name on screen before the film",
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
        "question": "What does my business actually get?",
        "answer": (
            "Your name on the marquee on Hall Street, on screen before the "
            "film, and in every social media post we make in the run-up to "
            "the show."
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
