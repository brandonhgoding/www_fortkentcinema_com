"""Poster URLs at the size the slot actually shows.

Film.poster_url stores TMDB's w500 (see cinema/tmdb/services.py). The home
page draws that same file into a 340px card, a 120px Coming Soon column and
a 33px calendar cell, so every poster but the first was three to fifteen
times larger than its slot. TMDB serves w92, w154, w185, w342, w500, w780
and original from the same path; these filters only change that segment.

w500 is the ceiling for a srcset candidate: a phone at 3x device pixels
would otherwise pick w780 for a 340px card and fetch more than the page
did before the audit. The JSON-LD keeps the w500 URL untouched, because
Google's event guidelines want the large image there.
"""

import re

from django import template

register = template.Library()

_TMDB_SIZE = re.compile(r"^(https://image\.tmdb\.org/t/p/)(w\d+|original)(/)")

# Smallest first, as srcset lists them; nothing above the stored w500.
SRCSET_WIDTHS = (185, 342, 500)


@register.filter
def tmdb_size(url, size):
    """The same TMDB image at another size; any other URL unchanged."""
    if not url:
        return url
    return _TMDB_SIZE.sub(lambda m: f"{m.group(1)}{size}{m.group(3)}", url, count=1)


@register.filter
def poster_srcset(url):
    """A w185/w342/w500 srcset for a TMDB poster, or "" for anything else so
    the template can leave the attribute off."""
    if not url or not _TMDB_SIZE.match(url):
        return ""
    return ", ".join(f"{tmdb_size(url, f'w{w}')} {w}w" for w in SRCSET_WIDTHS)
