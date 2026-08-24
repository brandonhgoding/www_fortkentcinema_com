"""Parsing helpers for studio DCP availability spreadsheets.

Studio lists are typed by hand and read like it: titles are shouted in caps
with the article moved to the end ("BAD GUYS 2, THE"), runtimes are sometimes
two numbers ("119 & 146") or carry a note about an attached short, and the
audio column arrives from openpyxl as an int, a float, or a string depending
on the row.

These functions are pure so the awkward cases can be tested without a
spreadsheet or a database.
"""

import datetime
import re

# Lowercased inside a title, but never as the first or last word, and never
# straight after a colon.
_SMALL_WORDS = frozenset(
    {
        "a", "an", "and", "as", "at", "but", "by", "for", "from", "in",
        "nor", "of", "on", "or", "the", "to", "vs", "with",
    }
)

_TRAILING_PAREN = re.compile(r"\s*(\([^()]*\))\s*$")
_LEADING_INT = re.compile(r"\s*(\d+)")

# ISO first: it is what our own exports write. The slashed forms are what
# Excel writes when a US-locale sheet is saved as CSV.
_DATE_FORMATS = ("%Y-%m-%d", "%m/%d/%Y", "%m/%d/%y")

# Studios move the article to a trailing ", THE"/", A"/", AN" — either at the
# very end ("BAD GUYS 2, THE") or right before a subtitle's colon
# ("LOST WORLD, THE: JURASSIC PARK"). The lookahead keeps this from firing on
# a mid-title comma-article, e.g. "20,000 LEAGUES UNDER THE SEA" or
# "HONEY, DON'T!", where ", THE"/", A"/", AN" is not the whole remainder.
_TRAILING_ARTICLE = re.compile(r"^(.*?),\s*(THE|A|AN)(?=$|:)(.*)$", re.IGNORECASE)


def clean_cell(value: object) -> str:
    """Stringify a spreadsheet cell without float artifacts.

    openpyxl gives the AUDIO column as 1 (int), 5.1 (float), or
    "5.1, 7.1, Atmos" (str). `str(1.0)` would render "1.0"; `:g` gives "1".
    """
    if value is None:
        return ""
    if isinstance(value, float):
        return f"{value:g}"
    return str(value).strip()


def _titlecase(text: str) -> str:
    """Title-case whole words, so apostrophes and hyphens survive.

    `str.title()` splits on every non-alpha character and renders
    "FREDDY'S" as "Freddy'S". This walks tokens instead.
    """
    tokens = re.split(r"(\s+|-)", text)
    words = [t for t in tokens if t.strip() and t != "-"]
    total = len(words)

    out: list[str] = []
    index = 0
    previous = ""
    for token in tokens:
        if not token.strip() or token == "-":
            out.append(token)
            continue
        lowered = token.lower()
        edge = index in (0, total - 1)
        after_colon = previous.endswith(":")
        if lowered in _SMALL_WORDS and not edge and not after_colon:
            out.append(lowered)
        else:
            out.append(lowered[:1].upper() + lowered[1:])
        previous = token
        index += 1
    return "".join(out)


def normalize_title(raw: object) -> str:
    """Turn a studio's shouted title into something printable.

    "BAD GUYS 2, THE" -> "The Bad Guys 2"
    """
    text = (str(raw) if raw is not None else "").strip()
    if not text:
        return ""

    paren = ""
    match = _TRAILING_PAREN.search(text)
    if match:
        paren = match.group(1)
        text = text[: match.start()].strip()

    match = _TRAILING_ARTICLE.match(text)
    if match:
        text = f"{match.group(2)} {match.group(1).strip()}{match.group(3)}"

    result = _titlecase(text)

    if paren:
        inner = paren[1:-1]
        # "(aka Fast & Furious 2)" is already cased by hand; "(1932)" is not.
        if any(char.islower() for char in inner):
            result = f"{result} {paren}"
        else:
            result = f"{result} ({_titlecase(inner)})"
    return result


def parse_runtime(value: object) -> tuple[int | None, str]:
    """Return (minutes, original_string).

    The original is kept whenever it carried more than a number, so
    "119 & 146" is not silently reduced to 119 on the page.
    """
    if value is None:
        return None, ""
    if isinstance(value, int) and not isinstance(value, bool):
        return value, ""
    raw = str(value).strip()
    # A CSV hands over "104" where openpyxl hands over 104. Keeping the raw
    # here would make the same list import differently by file format.
    if raw.isdigit():
        return int(raw), ""
    match = _LEADING_INT.match(raw)
    return (int(match.group(1)) if match else None), raw


def parse_release_date(value: object) -> datetime.date | None:
    """Return the release date, whatever the file format called it.

    openpyxl types this column for us; a CSV cannot, so the text forms
    Excel exports have to be read back. Anything else in the column —
    "TBD", "SUMMER 2026", a blank — is simply no date, the same answer the
    workbook path gives for an empty cell.
    """
    if isinstance(value, datetime.datetime):
        return value.date()
    if isinstance(value, datetime.date):
        return value

    text = clean_cell(value)
    if not text:
        return None

    for fmt in _DATE_FORMATS:
        try:
            return datetime.datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    return None
