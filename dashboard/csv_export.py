"""CSV writing for the dashboard's exports.

Staff open these in Excel or Sheets, which run a cell that starts with
=, +, -, @ (or a tab or carriage return) as a formula. Names, notes and
emails come from the public signup form, so a text cell starting with one
of those is prefixed with an apostrophe and shown as plain text.
"""

import csv

_FORMULA_START = ("=", "+", "-", "@", "\t", "\r")


def _neutralise(value):
    if isinstance(value, str) and value.startswith(_FORMULA_START):
        return "'" + value
    return value


class _SafeWriter:
    def __init__(self, stream):
        self._writer = csv.writer(stream)

    def writerow(self, row):
        return self._writer.writerow([_neutralise(v) for v in row])


def safe_csv_writer(stream) -> _SafeWriter:
    return _SafeWriter(stream)
