"""Event names typed into an engagement's title.

Staff mark a themed night by typing it into the event title, in whatever
case comes to hand: "Attack of the Giant Leeches (HECKLE NIGHT)" one month,
"The Brain That Wouldn't Die (Heckle Night)" the next. The title is data and
stays as typed — the dashboard and the social cards still read it — so the
public pages tidy it on the way out instead.

Only the event names below count. Any other trailing parenthetical is part
of the title ("(Dubbed)", "9 (2009)").
"""

import re

# Lower-cased as typed -> how the site writes it.
EVENT_NAMES = {
    "heckle night": "Heckle Night",
    "craft night": "Craft Night",
    "craft cinema night": "Craft Cinema Night",
}

_TRAILING_PARENTHETICAL = re.compile(r"^(?P<base>.*\S)\s*\(\s*(?P<name>[^()]+?)\s*\)\s*$")


def split_event_suffix(title: str) -> tuple[str, str | None]:
    """("Attack of the Giant Leeches", "Heckle Night") from the typed title,
    or (title, None) when it carries no event suffix."""
    match = _TRAILING_PARENTHETICAL.match(title or "")
    if match:
        name = EVENT_NAMES.get(" ".join(match["name"].lower().split()))
        if name:
            return match["base"], name
    return title, None


def listing_title(title: str) -> str:
    """The title for a mixed listing (Coming Soon), where the suffix is worth
    keeping — it is how a reader tells a Heckle Night from a regular run —
    but in one consistent case."""
    base, name = split_event_suffix(title)
    return f"{base} ({name})" if name else title


def event_page_title(title: str) -> str:
    """The title on the event's own page, where the suffix only repeats the
    page's name."""
    return split_event_suffix(title)[0]
