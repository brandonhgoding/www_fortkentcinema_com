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
    "navigation": [
        {"label": "Now Showing", "href": "#now-showing"},
        {"label": "Coming Soon", "href": "#coming-soon"},
        # Trailing slashes are required — these routes are defined with them, and
        # a bare /blog costs a 301 on every click and every crawl.
        {"label": "Membership", "href": "/membership/"},
        {"label": "Rentals", "href": "/rentals/"},
        # {"label": "About", "href": "/about/"},  # About page temporarily hidden
        {"label": "Blog", "href": "/blog/"},
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
