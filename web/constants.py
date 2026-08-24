import datetime
from zoneinfo import ZoneInfo

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

# Ported verbatim from the React SPA's src/data/membership.json.
# Consumed by the Membership page plan. The source file is a JSON array of
# tier objects, so this is transcribed as a Python list of dicts.
MEMBERSHIP = [
    {
        "id": "silver-screen",
        "slug": "silver-screen",
        "name": "Silver Screen",
        "eyebrow": "Seniors 65+",
        "price": 35,
        "duration_months": 12,
        "is_family_tier": False,
        "featured": False,
        "perks": [
            "$2 off matinee tickets",
            "$1 off evening tickets",
            "$1 off small popcorn",
            "$1 off medium & large popcorn",
            "Free small popcorn during your birthday month",
            "10% off rentals",
        ],
        "checkout_url": "https://square.link/u/UnQLNeHp",
    },
    {
        "id": "individual",
        "slug": "individual",
        "name": "Individual",
        "price": 60,
        "duration_months": 12,
        "is_family_tier": False,
        "featured": False,
        "perks": [
            "$2 off matinee tickets",
            "$4 off evening tickets",
            "$1 off small popcorn",
            "$2 off medium & large popcorn",
            "Free small popcorn during your birthday month",
            "10% off rentals",
        ],
        "checkout_url": "https://square.link/u/zricPsRR",
    },
    {
        "id": "cinema-supporter",
        "slug": "cinema-supporter",
        "name": "Cinema Supporter",
        "price": 120,
        "duration_months": 12,
        "is_family_tier": False,
        "featured": True,
        "perks": [
            "$2 off matinee tickets",
            "$4 off evening tickets",
            "$1 off small popcorn",
            "$2 off medium & large popcorn",
            "Free small popcorn during your birthday month",
            "15% off rentals & parties",
        ],
        "checkout_url": "https://square.link/u/2HnpAb9N",
    },
    {
        "id": "family",
        "slug": "family",
        "name": "Family",
        "price": 150,
        "duration_months": 12,
        "is_family_tier": True,
        "featured": False,
        "perks": [
            "$2 off matinee tickets",
            "$4 off evening tickets",
            "$1 off small popcorn",
            "$2 off medium & large popcorn",
            "Free small popcorn during your birthday month",
            "15% off rentals & parties",
        ],
        "checkout_url": "https://square.link/u/FkcUasKu",
    },
    {
        "id": "family-plus",
        "slug": "family-plus",
        "name": "Family Plus",
        "price": 250,
        "duration_months": 12,
        "is_family_tier": True,
        "featured": False,
        "perks": [
            "$2 off matinee tickets",
            "$4 off evening tickets",
            "$1 off small popcorn",
            "$2 off medium & large popcorn",
            "Free small popcorn during your birthday month",
            "20% off rentals & parties",
        ],
        "checkout_url": "https://square.link/u/1YSgMFSQ",
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

CINEMA_TZ = ZoneInfo("America/New_York")

# Silents Synced: A Woman of the World × Pearl Jam — a one-night special event.
#
# Deliberately NOT a cinema.Engagement: this screening is not booked in the
# catalog, so it does not appear in Now Showing, Coming Soon, or the calendar.
# Its page at /events/<slug> is the only surface, and these constants are the
# only source of truth for it. If it is ever booked properly, the listings pick
# it up without this page changing.
#
# `starts_at` is load-bearing beyond display: web.views computes `is_upcoming`
# from it, and the homepage CTA renders only while that is true. The CTA
# therefore retires itself the moment the show ends — nobody has to remember.
EVENT_SILENTS_SYNCED = {
    "slug": "silents-synced-a-woman-of-the-world",
    "series": "Silents Synced",
    "title": "A Woman of the World",
    "year": 1925,
    "artist": "Pearl Jam",
    "albums": [
        {"title": "Vs.", "year": 1993},
        {"title": "Vitalogy", "year": 1994},
    ],
    "starts_at": datetime.datetime(2026, 9, 1, 18, 30, tzinfo=CINEMA_TZ),
    "runtime": "75 minutes",
    # Official series trailer: "Silents Synced: Pearl Jam VS. A Woman of the
    # World Trailer". Embedded from youtube-nocookie.com and only after a click
    # — see the facade in the event template.
    "youtube_id": "JnRPMubIBY8",
    "rating": "Not Rated",
    "director": "Malcolm St. Clair",
    "remixed_by": "Josh Frank",
    "cast": [
        "Pola Negri",
        "Blanche Mehaffey",
        "Charles Emmett Mack",
        "Chester Conklin",
        "Holmes Herbert",
    ],
    # Confirmed by the theater 2026-08-15. The template omits either line if it
    # is blanked out again — an unconfirmed door time or ticket price on a
    # public event page is a promise we would have to keep.
    "admission": "$5",
    "doors": "6:00 PM",
}

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
    "blurb": (
        "A Fort Kent Historical Society docent walks through the Society\u2019s "
        "2017 centennial exhibit \u2014 the photographs, playbills and artifacts "
        "this page is built from."
    ),
}
