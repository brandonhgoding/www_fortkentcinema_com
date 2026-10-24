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
    "navigation": [
        {"label": "Now Showing", "href": "#now-showing"},
        {"label": "Buy Ad Space", "href": "/advertise/"},
        {"label": "Rent the Cinema", "href": "/rentals/"},
    ],
    # Membership, as a button at the right end of the nav rather than a link
    # in the row (the owner's call, 2026-10-13). The Events menu came out the
    # same day; Heckle Night and Open Mic are on the home page's "Be part of
    # the show" row, and Craft Night was deleted (it is in git history).
    # Trailing slash required — the route is defined with it, and a bare
    # /membership costs a 301 on every click and every crawl.
    "nav_cta": {"label": "Become a Member", "href": "/membership/"},
    # The footer's Events column. Empty since 2026-10-13: Heckle Night moved
    # to the home page's "Be part of the show" row and Craft Night was
    # deleted. The owner kept the heading; the footer renders it alone until
    # this has links again (same shape as footer_navigation).
    "footer_events": [],
    # The footer's link column, on every page. Blog, Film Vote and History
    # moved here from the nav's "More" menu on 2026-10-13, and "More" went
    # with them. Rentals joined on 2026-10-14 (the owner's call).
    "footer_navigation": [
        # Alphabetical by label (the owner's call). "note" renders as a
        # second line inside the same link, saying what a name like "From
        # the Booth" or "You Choose" doesn't on its own. Rentals and
        # advertising carry the same label as the nav and their page title.
        {
            "label": "Buy Ad Space",
            "note": "Your business on the big screen",
            "href": "/advertise/",
        },
        {
            "label": "Century Theatre in Fort Kent",
            "note": "A brief, semi-accurate history",
            "href": "/history/",
        },
        {
            "label": "From the Booth",
            "note": "The Fort Kent Cinema Blog",
            "href": "/blog/",
        },
        {
            "label": "Member sign in",
            "note": "See your membership",
            "href": "/login",
        },
        {
            "label": "Rent the Cinema",
            "note": "Rent the whole theater",
            "href": "/rentals/",
        },
        # Bare, unlike the section pages around it — urls.py defines
        # path("vote", ...) without a slash. APPEND_SLASH only adds
        # slashes, so /vote/ is a hard 404, not a recoverable 301.
        {
            "label": "You Choose",
            "note": "Vote to help us pick the films",
            "href": "/vote",
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
#
# NOTE: HECKLE_NIGHT's price and /membership/'s "$4 off
# evening tickets" restate these numbers; a reprice has to move them together.
TICKET_PRICES = {
    "adult": 8,
    "senior": 7,
    "child": 6,
    "matinee": 6,
    "member": 4,
    "matinee_until": datetime.time(16, 0),
}

# These govern online ticket sales (the `tickets` app).
TICKET_ONLINE_SHARE = 0.5
TICKET_HOLD_MINUTES = 20
TICKET_CUTOFF_MINUTES = 30


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
            "We reserve the right to decline any ad, and we don't run "
            "political ads."
        ),
    },
]

# Ported verbatim from the React SPA's src/data/membershipFaq.json.
MEMBERSHIP_FAQ = [
    {
        "question": "How long does a membership last?",
        "answer": (
            "The length shown on your tier, counted from the day you join. "
            "Ask at the box office and we'll tell you the exact end date."
        ),
    },
    {
        "question": "What's included with a family tier?",
        "answer": (
            "Everyone in your household, with no headcount limit. Just give "
            "your name at the box office."
        ),
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


# Heckle Night — /heckle-night/
#
# A bad public domain movie, monthly, that the room is invited to talk over.
# The premise is MST3K's, and the page says so once to explain itself; the
# name is not theirs and neither are the episodes, so nothing here borrows
# either. "Heckle Night" is ours and describes the night literally.
#
# The film comes from the schedule — see web/services/heckle_night.py. What is NOT computable, and therefore lives
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
    # The start time, and it is now EXACT rather than a floor.
    #
    # The interim lineup lookup claims nothing (see heckle_showtimes). When
    # the Event model lands, a Heckle Night is the 7:00 PM event on the
    # third Friday; one at any other time that Friday is a different night
    # and the page will not claim it.
    #
    # Known and accepted cost: if a Heckle Night is ever booked for 7:30
    # once the lookup is live, this page goes blank for that date and says
    # "Not booked yet" while the listings show the event. That is a crude
    # rule and it is the rule we want for now — it fails visibly rather
    # than silently.
    #
    # start_label is what the page PRINTS and start_time is what it
    # MATCHES, so the two are now load-bearing together — a booking made
    # at the printed time has to be a booking this finds. A test asserts
    # they agree; change one and change the other.
    "start_label": "7:00 PM",
    "start_time": datetime.time(19, 0),
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
    # NOTE: $8 general evening admission (TICKET_PRICES) is implied by
    # /membership/'s benefit line. This $4 reads as "the member
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
# RENTALS_FAQ above: Google penalises
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


# Open Mic — /open-mic/
#
# Every Monday in the Century auditorium: karaoke, original music, comedy,
# anything. Unlike craft night and heckle night there is no film, so
# nothing here comes from the schedule and no booking is needed for the
# page to be right. The only computed thing is the next date — see
# web/services/open_mic.py.
#
# The home page has advertised "Open Mic Every Monday, 6:30 PM, doors open
# at 6:00" since the React port (templates/partials/cta_openmic.html). That
# band and this page have to agree; a test holds them together.
OPEN_MIC = {
    # Monday, as datetime.date.weekday() counts it.
    "weekday": 0,
    "day_label": "Monday",
    "room": "the Century auditorium",
    "doors_label": "6:00 PM",
    "start_label": "6:30 PM",
    # The advertised finish. The night can end earlier when the sign-up
    # sheet runs out, which the page says — 9:00 is a ceiling, not a
    # promise.
    "end_label": "9:00 PM",
    # What upcoming_nights() rolls over at: until 9 PM on a Monday, the
    # next open mic is tonight.
    "end_time": datetime.time(21, 0),
    # Free to perform and free to watch. No member angle, because there is
    # nothing for membership to discount.
    "price_label": "Free",
    # All ages, so acts keep it PG — a house rule, the same one Heckle
    # Night runs, not a rating.
    "audience": "All ages",
}

# Rendered twice on /open-mic/ — visible FAQ and FAQPage structured data —
# from this one list, the same contract as HECKLE_NIGHT_FAQ above.
#
# Only what the owner has actually decided goes in here: the night, the
# times, free, sign-up sheet at the door, all ages and PG. Slot lengths,
# what gear the room has and whether there is a karaoke library are NOT
# decided, so no answer promises any of them.
OPEN_MIC_FAQ = [
    {
        "question": "How do I get a slot?",
        "answer": (
            "Put your name on the sign-up sheet at the door when you "
            "arrive. Acts go up in the order they signed, first come, "
            "first served. There's no booking ahead."
        ),
    },
    {
        "question": "What can I do?",
        "answer": (
            "Anything. Karaoke, songs you wrote, covers, stand-up, poetry, "
            "a magic trick. If you can do it on a stage, it counts."
        ),
    },
    {
        "question": "What does it cost?",
        "answer": (
            "Nothing. It's free to perform and free to come and watch."
        ),
    },
    {
        "question": "Can I just come and watch?",
        "answer": (
            "Please do. An open mic is only as good as its audience, and "
            "the people on the sheet will be glad you came."
        ),
    },
    {
        "question": "Can kids come, or get up on stage?",
        "answer": (
            "Yes to both. Open mic is all ages, so we ask every act to "
            "keep it PG. That's a house rule, and it covers song lyrics "
            "too."
        ),
    },
    {
        "question": "When does it finish?",
        "answer": (
            "We start at 6:30 and go until 9:00 PM, or until everyone on "
            "the sheet has had their turn, whichever comes first."
        ),
    },
]
