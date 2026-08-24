"""Read a studio's availability list and write it into StudioTitle.

Both the `import_studio_catalog` management command and the admin uploader
on the StudioTitle changelist go through here, so a list imported from the
terminal and the same list imported through a browser land identically.

Studios send .xlsx. A CSV of the same columns is read too, for the times a
list arrives pasted into a mail or exported from someone else's system.

Idempotent: rows are matched on (studio, original_title, release_date), so
re-running after a studio ships an updated list adds the new titles and
refreshes the old ones without duplicating anything. `is_available` and
`hidden_reason` are deliberately NOT refreshed — a title you hid must stay
hidden across the next catalog drop.
"""

import csv
import io
from dataclasses import dataclass
from pathlib import Path
from typing import Any, BinaryIO

from cinema.models import Studio, StudioTitle
from cinema.studio_catalog import (
    clean_cell,
    normalize_title,
    parse_release_date,
    parse_runtime,
)

DEFAULT_SHEET = "by TITLE"

# Slug -> display name. A studio must be listed here (or already have a row)
# before its list can be imported, so a typo fails loudly instead of silently
# creating a "Univrsal" catalog nobody can find.
KNOWN_STUDIOS = {
    "universal": "Universal Pictures",
}

# Column order in every studio list we have seen so far.
COL_TITLE = 0
COL_RELEASE = 1
COL_ASPECT = 2
COL_AUDIO = 3
COL_RATING = 4
COL_RUNTIME = 5
COL_NOTES = 6


class StudioImportError(Exception):
    """A list we cannot read. Message is shown to whoever handed it over."""


class ParsedRow:
    """One spreadsheet row, cleaned up."""

    def __init__(self, cells: tuple) -> None:
        def cell(index: int) -> Any:
            return cells[index] if index < len(cells) else None

        raw_title = clean_cell(cell(COL_TITLE))
        self.original_title = raw_title
        self.title = normalize_title(raw_title)

        self.release_date = parse_release_date(cell(COL_RELEASE))

        self.aspect_ratio = clean_cell(cell(COL_ASPECT))
        self.audio = clean_cell(cell(COL_AUDIO))
        self.mpa_rating = clean_cell(cell(COL_RATING))
        self.runtime_minutes, self.runtime_raw = parse_runtime(cell(COL_RUNTIME))
        self.notes = clean_cell(cell(COL_NOTES))

    @property
    def key(self) -> tuple[str, object]:
        return (self.original_title, self.release_date)

    @property
    def filled(self) -> int:
        """How many optional fields carry a value — the variant tie-break."""
        return sum(
            1
            for value in (
                self.aspect_ratio, self.audio, self.mpa_rating,
                self.runtime_raw, self.notes,
            )
            if value
        )

    def summary(self) -> str:
        """One-line description of this variant, for `variant_note`."""
        bits = [
            self.notes,
            f"{self.runtime_minutes} min" if self.runtime_minutes else "",
            self.audio,
            self.mpa_rating,
        ]
        return ", ".join(bit for bit in bits if bit)


@dataclass
class ImportResult:
    created: int = 0
    updated: int = 0
    collapsed: int = 0
    rows_read: int = 0

    @property
    def titles(self) -> int:
        return self.created + self.updated


def _rows_from(raw_rows) -> list[ParsedRow]:
    """Drop the header and anything with no title, then parse the rest."""
    return [
        ParsedRow(tuple(cells))
        for cells in raw_rows
        if cells and clean_cell(cells[COL_TITLE])
    ]


def _decode(data: bytes) -> str:
    """Text out of a CSV whoever's Excel wrote.

    utf-8-sig covers the "CSV UTF-8" export and eats its byte order mark,
    which would otherwise glue itself to the first title and keep that row
    from ever matching on re-import. Windows Excel writes cp1252 instead,
    which is not valid UTF-8 and has no BOM to tell us so.
    """
    try:
        return data.decode("utf-8-sig")
    except UnicodeDecodeError:
        return data.decode("cp1252", errors="replace")


def read_csv(stream: BinaryIO) -> list[ParsedRow]:
    """Parse a CSV of the studio columns. The first row is a header."""
    text = _decode(stream.read())
    reader = csv.reader(io.StringIO(text, newline=""))
    try:
        next(reader, None)  # header
        return _rows_from(reader)
    except csv.Error as error:
        raise StudioImportError(f"Could not read that CSV: {error}") from error


def read_xlsx(stream: BinaryIO, sheet: str = DEFAULT_SHEET) -> list[ParsedRow]:
    """Parse one worksheet of a studio workbook. The first row is a header."""
    # Imported here so this module loads even if openpyxl is missing, which
    # keeps `manage.py help` working with a clearer error.
    import openpyxl

    try:
        book = openpyxl.load_workbook(stream, data_only=True, read_only=True)
    except Exception as error:  # openpyxl raises a zoo of these
        raise StudioImportError(f"Could not read that workbook: {error}") from error

    try:
        if sheet not in book.sheetnames:
            raise StudioImportError(
                f"No sheet named '{sheet}'. "
                f"Found: {', '.join(book.sheetnames)}"
            )
        rows = _rows_from(book[sheet].iter_rows(min_row=2, values_only=True))
    finally:
        book.close()
    return rows


def read_upload(source, sheet: str = DEFAULT_SHEET) -> list[ParsedRow]:
    """Read an uploaded file or a path, picking the parser by extension."""
    name = getattr(source, "name", str(source))
    suffix = Path(str(name)).suffix.lower()

    if suffix == ".csv":
        reader = read_csv
    elif suffix in (".xlsx", ".xlsm"):
        reader = read_xlsx
    else:
        raise StudioImportError(
            f"Cannot read a '{suffix or 'nameless'}' file. "
            "Studio lists come as .xlsx or .csv."
        )

    if isinstance(source, (str, Path)):
        with open(source, "rb") as handle:
            data = handle.read()
    else:
        source.seek(0)
        data = source.read()

    stream = io.BytesIO(data)
    return reader(stream) if reader is read_csv else reader(stream, sheet)


def studio_choices() -> list[tuple[str, str]]:
    """Every studio a list can be imported for: the known ones plus any row.

    A studio added by hand in the admin belongs in the dropdown too — the
    hardcoded map exists to catch typos, not to be the only way in.
    """
    choices = dict(KNOWN_STUDIOS)
    choices.update(Studio.objects.values_list("slug", "name"))
    return sorted(choices.items(), key=lambda pair: pair[1])


def get_or_create_studio(slug: str) -> Studio:
    studio, _ = Studio.objects.get_or_create(
        slug=slug, defaults={"name": KNOWN_STUDIOS.get(slug, slug.title())}
    )
    return studio


def _group(rows: list[ParsedRow]) -> dict:
    """Bucket rows by natural key, preserving sheet order within a bucket."""
    groups: dict = {}
    for row in rows:
        groups.setdefault(row.key, []).append(row)
    return groups


def _primary(group: list[ParsedRow]) -> ParsedRow:
    """Pick the row that best represents a group of DCP variants.

    Longest runtime wins (the roadshow cut, the reconstruction). Ties go
    to the most complete row, then to sheet order — without that last
    step the two Dracula 1931-02-13 rows, identical but for their audio,
    would import differently run to run.
    """
    best = group[0]
    for row in group[1:]:
        if (row.runtime_minutes or 0) > (best.runtime_minutes or 0):
            best = row
        elif (row.runtime_minutes or 0) == (best.runtime_minutes or 0):
            if row.filled > best.filled:
                best = row
    return best


def preview(rows: list[ParsedRow]) -> ImportResult:
    """What an import of these rows would do, without touching the database."""
    groups = _group(rows)
    return ImportResult(
        rows_read=len(rows),
        collapsed=len(rows) - len(groups),
    )


def import_rows(studio: Studio, rows: list[ParsedRow]) -> ImportResult:
    """Write these rows into `studio`'s catalog. Caller owns the transaction."""
    result = ImportResult(rows_read=len(rows))

    for group in _group(rows).values():
        primary = _primary(group)
        others = [row for row in group if row is not primary]
        result.collapsed += len(others)

        # Skip any variant that describes the same thing as the primary.
        # Notting Hill is listed twice, identically — without this the
        # page would advertise an "also available" version that is just
        # the row itself.
        seen = {primary.summary()}
        summaries = []
        for row in others:
            summary = row.summary()
            if not summary or summary in seen:
                continue
            seen.add(summary)
            summaries.append(summary)

        variant_note = (
            f"Also available: {'; '.join(summaries)}"[:300] if summaries else ""
        )

        _, was_created = StudioTitle.objects.update_or_create(
            studio=studio,
            original_title=primary.original_title,
            release_date=primary.release_date,
            defaults={
                "title": primary.title,
                "aspect_ratio": primary.aspect_ratio,
                "audio": primary.audio,
                "mpa_rating": primary.mpa_rating,
                "runtime_minutes": primary.runtime_minutes,
                "runtime_raw": primary.runtime_raw,
                "notes": primary.notes,
                "variant_note": variant_note,
                # NOTE: is_available / hidden_reason are absent on purpose.
                # A re-import must never un-hide a title.
            },
        )
        if was_created:
            result.created += 1
        else:
            result.updated += 1

    return result
