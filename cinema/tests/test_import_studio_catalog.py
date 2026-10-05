import datetime
import tempfile
from io import StringIO
from pathlib import Path

import openpyxl
from cinema.models import Studio, StudioTitle
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase

HEADER = [
    "TITLE", "U.S. RELEASE (YYYY-MM-DD)", "ASPECT RATIO", "AUDIO",
    "MPA RATING", "RUN TIME (MINUTES)", "ADDITIONAL INFORMATION",
]


def workbook(rows, sheet_name="by TITLE") -> str:
    """Write a temp .xlsx shaped like a studio list; return its path."""
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = sheet_name
    ws.append(HEADER)
    for row in rows:
        ws.append(row)
    path = Path(tempfile.mkdtemp()) / "catalog.xlsx"
    wb.save(path)
    return str(path)


class ImportStudioCatalogTests(TestCase):
    def run_import(self, path, **kwargs):
        out = StringIO()
        call_command(
            "import_studio_catalog",
            studio="universal", file=path, stdout=out, **kwargs
        )
        return out.getvalue()

    def test_creates_studio_and_titles(self):
        path = workbook([
            ["BAD GUYS 2, THE", datetime.datetime(2025, 8, 1),
             "Scope", "5.1, 7.1, Atmos", "PG", 104, "2D & 3D"],
        ])
        self.run_import(path)

        studio = Studio.objects.get(slug="universal")
        self.assertEqual(studio.name, "Universal Pictures")

        title = StudioTitle.objects.get()
        self.assertEqual(title.original_title, "BAD GUYS 2, THE")
        self.assertEqual(title.title, "The Bad Guys 2")
        self.assertEqual(title.release_date, datetime.date(2025, 8, 1))
        self.assertEqual(title.runtime_minutes, 104)
        self.assertEqual(title.notes, "2D & 3D")
        self.assertTrue(title.is_available)

    def test_is_idempotent(self):
        path = workbook([
            ["NOBODY 2", datetime.datetime(2025, 8, 15), "Scope", 5.1, "R", 89, None],
        ])
        self.run_import(path)
        self.run_import(path)
        self.assertEqual(StudioTitle.objects.count(), 1)

    def test_reimport_does_not_resurrect_a_hidden_title(self):
        path = workbook([
            ["NOBODY 2", datetime.datetime(2025, 8, 15), "Scope", 5.1, "R", 89, None],
        ])
        self.run_import(path)
        StudioTitle.objects.update(is_available=False, hidden_reason="too violent")

        self.run_import(path)

        title = StudioTitle.objects.get()
        self.assertFalse(title.is_available)
        self.assertEqual(title.hidden_reason, "too violent")

    def test_collapses_variants_and_records_them(self):
        # Touch of Evil ships as two cuts under one release date.
        path = workbook([
            ["TOUCH OF EVIL", datetime.datetime(1958, 3, 15), "Flat", 1,
             "N/A", 95, "4K Restoration (Original 1958 Theatrical Version)"],
            ["TOUCH OF EVIL", datetime.datetime(1958, 3, 15), "Flat", 1,
             "PG-13", 110, "4K Restoration (1998 Reconstructed Version)"],
        ])
        self.run_import(path)

        title = StudioTitle.objects.get()
        # Longest runtime wins the primary slot.
        self.assertEqual(title.runtime_minutes, 110)
        self.assertIn("95 min", title.variant_note)
        self.assertIn("1958 Theatrical", title.variant_note)

    def test_a_true_duplicate_gets_no_variant_note(self):
        # Notting Hill is listed twice, identically. There is no second
        # version to advertise.
        path = workbook([
            ["NOTTING HILL", datetime.datetime(1999, 5, 28), "Scope", 5.1,
             "PG-13", 124, "2K Restoration"],
            ["NOTTING HILL", datetime.datetime(1999, 5, 28), "Scope", 5.1,
             "PG-13", 124, "2K Restoration"],
        ])
        self.run_import(path)
        self.assertEqual(StudioTitle.objects.get().variant_note, "")

    def test_same_title_different_dates_stay_separate(self):
        path = workbook([
            ["DRACULA", datetime.datetime(1931, 2, 13), "Flat (1.33)", 1,
             "N/A", 75, "2K Restoration"],
            ["DRACULA", datetime.datetime(1931, 4, 24), "Flat (1.33)", 1,
             "N/A", 103, "2K Restoration"],
        ])
        self.run_import(path)
        self.assertEqual(StudioTitle.objects.count(), 2)

    def test_variant_tie_break_is_deterministic(self):
        # Both Dracula 1931-02-13 rows are 75 min and differ only in audio;
        # sheet order decides, so two runs must agree.
        rows = [
            ["DRACULA", datetime.datetime(1931, 2, 13), "Flat (1.33)", 1,
             "N/A", 75, "2K Restoration"],
            ["DRACULA", datetime.datetime(1931, 2, 13), "Flat (1.33)", 5.1,
             "N/A", 75, "2K Restoration"],
        ]
        self.run_import(workbook(rows))
        first = StudioTitle.objects.get().audio
        StudioTitle.objects.all().delete()
        self.run_import(workbook(rows))
        self.assertEqual(StudioTitle.objects.get().audio, first)
        self.assertEqual(first, "1")

    def test_handles_missing_release_date(self):
        path = workbook([
            ["MYSTERY TITLE", None, "Flat", 5.1, "N/A", 90, None],
        ])
        self.run_import(path)
        self.assertIsNone(StudioTitle.objects.get().release_date)

    def test_preserves_awkward_runtime_string(self):
        path = workbook([
            ["1941", datetime.datetime(1979, 12, 14), "Scope", 5.1,
             "PG & N/A", "119 & 146", None],
        ])
        self.run_import(path)
        title = StudioTitle.objects.get()
        self.assertEqual(title.runtime_minutes, 119)
        self.assertEqual(title.runtime_raw, "119 & 146")

    def test_skips_blank_rows(self):
        path = workbook([
            ["NOBODY 2", datetime.datetime(2025, 8, 15), "Scope", 5.1, "R", 89, None],
            [None, None, None, None, None, None, None],
        ])
        self.run_import(path)
        self.assertEqual(StudioTitle.objects.count(), 1)

    def test_dry_run_writes_nothing(self):
        path = workbook([
            ["NOBODY 2", datetime.datetime(2025, 8, 15), "Scope", 5.1, "R", 89, None],
        ])
        output = self.run_import(path, dry_run=True)
        self.assertEqual(StudioTitle.objects.count(), 0)
        self.assertEqual(Studio.objects.count(), 0)
        self.assertIn("dry run", output.lower())

    def test_unknown_studio_slug_is_an_error(self):
        path = workbook([])
        with self.assertRaises(CommandError):
            call_command("import_studio_catalog", studio="pathe", file=path)

    def test_a_studio_added_in_the_admin_is_accepted(self):
        Studio.objects.create(slug="sony", name="Sony Pictures")
        path = workbook([])
        call_command(
            "import_studio_catalog", studio="sony", file=path, stdout=StringIO()
        )

    def test_missing_file_is_an_error(self):
        with self.assertRaises(CommandError):
            call_command(
                "import_studio_catalog", studio="universal", file="/nope.xlsx"
            )

    def test_missing_sheet_is_an_error(self):
        path = workbook([], sheet_name="something else")
        with self.assertRaises(CommandError):
            call_command(
                "import_studio_catalog", studio="universal", file=path
            )


def csv_file(*lines: str) -> str:
    """Write a temp .csv shaped like a studio list; return its path."""
    path = Path(tempfile.mkdtemp()) / "catalog.csv"
    path.write_text("\r\n".join((",".join(HEADER), *lines)) + "\r\n")
    return str(path)


class ImportStudioCatalogCsvTests(ImportStudioCatalogTests):
    """The same command, handed a CSV instead of a workbook."""

    def test_imports_a_csv(self):
        path = csv_file("NOBODY 2,2025-08-15,Scope,5.1,R,89,")

        output = self.run_import(path)

        title = StudioTitle.objects.get()
        self.assertEqual(title.title, "Nobody 2")
        self.assertEqual(title.release_date, datetime.date(2025, 8, 15))
        self.assertEqual(title.runtime_minutes, 89)
        self.assertIn("1 created", output)

    def test_csv_ignores_the_sheet_argument(self):
        path = csv_file("NOBODY 2,2025-08-15,,,,,")

        self.run_import(path, sheet="by DATE")

        self.assertEqual(StudioTitle.objects.count(), 1)

    def test_an_unreadable_extension_is_an_error(self):
        path = Path(tempfile.mkdtemp()) / "catalog.pdf"
        path.write_bytes(b"%PDF-")

        with self.assertRaises(CommandError) as caught:
            self.run_import(str(path))

        self.assertIn(".pdf", str(caught.exception))
