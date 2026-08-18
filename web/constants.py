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
        {"label": "Rentals", "href": "/rentals/"},
        # {"label": "About", "href": "/about/"},  # About page temporarily hidden
        {"label": "Blog", "href": "/blog/"},
    ],
}

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
