import csv
from io import StringIO

from django.test import SimpleTestCase

from dashboard.csv_export import safe_csv_writer


class SafeCsvWriterTests(SimpleTestCase):
    def rows(self, *values):
        buffer = StringIO()
        safe_csv_writer(buffer).writerow(values)
        return next(csv.reader(StringIO(buffer.getvalue())))

    def test_formula_starts_are_neutralised(self) -> None:
        cells = self.rows('=HYPERLINK("http://x","y")', "+1", "-2", "@SUM(A1)")
        self.assertTrue(all(cell.startswith("'") for cell in cells))

    def test_ordinary_text_and_numbers_pass_through(self) -> None:
        self.assertEqual(
            self.rows("Ann", "ann@example.com", 25, ""),
            ["Ann", "ann@example.com", "25", ""],
        )
