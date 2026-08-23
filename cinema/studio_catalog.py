"""Parsing helpers for studio DCP availability spreadsheets.

Studio lists are typed by hand and read like it: titles are shouted in caps
with the article moved to the end ("BAD GUYS 2, THE"), runtimes are sometimes
two numbers ("119 & 146") or carry a note about an attached short, and the
audio column arrives from openpyxl as an int, a float, or a string depending
on the row.

These functions are pure so the awkward cases can be tested without a
spreadsheet or a database.
"""

import re

_ARTICLES = ("THE", "A", "AN")

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

    for article in _ARTICLES:
        suffix = f", {article}"
        if text.upper().endswith(suffix):
            text = f"{article} {text[: -len(suffix)].strip()}"
            break

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
    match = _LEADING_INT.match(raw)
    return (int(match.group(1)) if match else None), raw
