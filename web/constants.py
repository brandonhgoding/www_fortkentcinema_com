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
        # The same number for machines: tel: links and the MovieTheater
        # block's telephone. A test holds the two to the same digits.
        "phone_e164": "+12072315287",
        # Two auditoriums, named on /history/. Directories disagree on the
        # count (Cinema Treasures says one), so the schema block and
        # llms.txt state it. Owner confirmed both in use, 2026-10-15.
        "screens": [
            {"name": "the Century", "seats": 100},
            {"name": "the Savoy", "seats": 100},
        ],
    },
    # No fixed weekly hours. A table of them ("Wednesday - Thursday,
    # 6-9 PM") contradicted the schedule it sat under — Friday Heckle Night,
    # Tuesday shows, an 11 AM Saturday matinee — and Google read it as
    # "Closed" on every show night it didn't list. The box office opens
    # ahead of each show instead, which is always true.
    "box_office": {"opens_before_show_minutes": 30},
    "social": {"facebook": "https://facebook.com/fortkentcinema"},
    # Items with "children" render as a dropdown (none at present);
    # everything else is a plain link. FIVE TOP-LEVEL ITEMS IS THE CEILING, counting each dropdown as
    # one — the nav collapses to a hamburger at 768px, and a sixth is what
    # strained the 768-900px range. A dropdown costs the same width as a
    # link plus a caret, so trading a link for a menu is width-neutral;
    # adding one is not. Label length counts too: the three links below plus
    # the button only fit the 769-960px range with Nav.css's squeeze tier,
    # with ~15px to spare at 769px. Measure before adding a word to any of
    # them.
    #
    # These are the pages the owner wants Google to offer as sitelinks
    # under the listing (2026-10-14). Google builds sitelinks from pages
    # linked site-wide and labels them from the anchor text and the page
    # title, so each label here is also the page's <title> and <h1>, and
    # its footer label. Coming Soon came out: it is an anchor on the home
    # page, and Google won't sitelink a fragment of the page it already
    # shows. Now Showing stays as the one-click route to tonight's films.
    #
    # Empty since 2026-10-31 (the owner's call): Buy Ad Space and Rent the
    # Cinema left the nav and are linked from the footer only. The Become a
    # Member button went with /membership/ on 2026-11-01, so the bar carries
    # just the logo.
    "navigation": [],
    # The footer's Events column. Empty since 2026-10-13; the event pages it
    # once linked are gone. The owner kept the heading; the footer renders it alone until
    # this has links again (same shape as footer_navigation).
    "footer_events": [],
    # The footer's link column, on every page. Blog moved here from the
    # nav's "More" menu on 2026-10-13, and "More" went with it. History
    # was removed 2026-11-01.
    # Rentals joined on 2026-10-14 (the owner's call). The film vote and the
    # member sign-in links went on 2026-10-31.
    "footer_navigation": [
        # Alphabetical by label (the owner's call). "note" renders as a
        # second line inside the same link, saying what a name like "From
        # the Booth" doesn't on its own. Rentals and
        # advertising carry the same label as the nav and their page title.
        {
            "label": "Buy Ad Space",
            "note": "Your business on the big screen",
            "href": "/advertise/",
        },
        {
            "label": "From the Booth",
            "note": "The Fort Kent Cinema Blog",
            "href": "/blog/",
        },
        {
            "label": "Rent the Cinema",
            "note": "Rent the whole theater",
            "href": "/rentals/",
        },
    ],
}

# Regular admission, in whole dollars. Read by the phone line (phone/speech.py).
# A matinee is a show starting at `matinee_until` or earlier. The member price
# applies to every show, except runs marked `is_free_for_members`.
#
# Square ticket items carry only the adult, senior and child prices
# (boxoffice/spec.py SQUARE_TIERS); matinee and member are register discounts
# set up by hand in Square, so a change to either has to be made there too.
TICKET_PRICES = {
    "adult": 8,
    "senior": 7,
    "child": 6,
    "matinee": 6,
    "member": 4,
    "matinee_until": datetime.time(16, 0),
}


# Everything below is derived from SITE_CONFIG above, so the config stays the
# single source of truth. SITE_CONFIG["seo"] is what templates read: it rides
# along on the existing `site_config` context variable, which is why it lives
# here rather than in a second context processor.

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
    # hasMap on the MovieTheater. Built from the address rather than pasted,
    # so moving the theater moves the pin.
    "map_url": "https://www.google.com/maps/search/?api=1&query=" + _MAP_QUERY,
    # maximumAttendeeCapacity on the MovieTheater: every seat in the house.
    "seat_count": sum(s["seats"] for s in SITE_CONFIG["cinema"]["screens"]),
}

# The Google rating, as the hero shows it beside the member count
# (partials/hero_members.html). Kept by hand, like the phone number: a live
# Places lookup would need a key, billing and a cache for one line of copy.
# Update rating and count when the listing moves; None drops the chip. The
# rating is a string so "4.9" stays "4.9" and never prints as 4.9000000001.
# The link is the map pin, which opens the listing with its reviews.
# Owner's figures, 2026-10-28.
SITE_CONFIG["google_review"] = {
    "rating": "4.9",
    "count": 112,
    "url": SITE_CONFIG["seo"]["map_url"],
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
# Nothing here is a new policy. If a term
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

# The /advertise/ page: pre-show slides and short video spots, sold by the
# calendar month. Rates in dollars a month; artwork is due on the
# AD_ARTWORK_DEADLINE_DAY of the month before it runs.
AD_SLIDE_PRICE = 75
AD_VIDEO_PRICE = 150
AD_VIDEO_MAX_SECONDS = 30
AD_ARTWORK_DEADLINE_DAY = 20

# Rendered twice on /advertise/ — as the visible FAQ and as FAQPage
# structured data in the head — from this one list, as with RENTALS_FAQ.
# Billing is a monthly Square invoice, there is no contract, and we may
# decline any ad (never political ones). If a term changes it changes here
# and nowhere else.
ADVERTISING_FAQ = [
    {
        "question": "When does my ad start?",
        "answer": (
            "Ads run by calendar month. Send us your artwork by the "
            f"{AD_ARTWORK_DEADLINE_DAY}th and it plays from the 1st of the "
            "next month."
        ),
    },
    {
        "question": "How do I pay?",
        "answer": (
            "We send a Square invoice each month. Pay online by card, or at "
            "the box office."
        ),
    },
    {
        "question": "Can I change my ad?",
        "answer": (
            f"Yes. Send new artwork by the {AD_ARTWORK_DEADLINE_DAY}th and it "
            "swaps in on the 1st."
        ),
    },
    {
        "question": "What are the specs?",
        "answer": (
            "Slides: 1920 × 1080 PNG or JPEG. Video: MP4, 1920 × 1080, up to "
            f"{AD_VIDEO_MAX_SECONDS} seconds. We'll check it and send you a "
            "proof."
        ),
    },
    {
        "question": "Is there a contract?",
        "answer": "No. It's month to month — stop whenever you like.",
    },
    {
        "question": "Do you run every ad?",
        "answer": (
            "We reserve the right to decline any ad, and we don't run political ads."
        ),
    },
]
