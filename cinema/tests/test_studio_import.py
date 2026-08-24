"""The reader/writer shared by the management command and the admin uploader."""

import datetime
import tempfile
from io import BytesIO
from pathlib import Path

import openpyxl
from cinema.models import Studio, StudioTitle
from cinema.studio_import import (
    StudioImportError,
    import_rows,
    read_csv,
    read_upload,
    read_xlsx,
)
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import SimpleTestCase, TestCase

# A title with a comma in it, quoted the way any CSV writer would quote it.
BAD_GUYS = '"BAD GUYS 2, THE",2025-08-01,Scope,"5.1, 7.1, Atmos",PG,104,2D & 3D'

HEADER = (
    "TITLE,U.S. RELEASE (YYYY-MM-DD),ASPECT RATIO,AUDIO,"
    "MPA RATING,RUN TIME (MINUTES),ADDITIONAL INFORMATION"
)


def csv_bytes(*lines: str, prefix: str = "") -> BytesIO:
    return BytesIO((prefix + "\r\n".join((HEADER, *lines)) + "\r\n").encode())


def workbook_bytes(rows, sheet_name="by TITLE") -> BytesIO:
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = sheet_name
    ws.append(HEADER.split(","))
    for row in rows:
        ws.append(row)
    buffer = BytesIO()
    wb.save(buffer)
    buffer.seek(0)
    return buffer


class ReadCsvTests(SimpleTestCase):
    def test_reads_a_row(self):
        rows = read_csv(csv_bytes(BAD_GUYS))

        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual(row.original_title, "BAD GUYS 2, THE")
        self.assertEqual(row.title, "The Bad Guys 2")
        self.assertEqual(row.release_date, datetime.date(2025, 8, 1))
        self.assertEqual(row.aspect_ratio, "Scope")
        self.assertEqual(row.audio, "5.1, 7.1, Atmos")
        self.assertEqual(row.mpa_rating, "PG")
        self.assertEqual(row.runtime_minutes, 104)
        self.assertEqual(row.runtime_raw, "")
        self.assertEqual(row.notes, "2D & 3D")

    def test_skips_the_header_and_blank_rows(self):
        rows = read_csv(csv_bytes(
            "NOBODY 2,2025-08-15,Scope,5.1,R,89,",
            ",,,,,,",
            "",
            "DRACULA,1931-02-13,Flat,1,,75,",
        ))

        self.assertEqual(
            [row.original_title for row in rows], ["NOBODY 2", "DRACULA"]
        )

    def test_tolerates_short_rows(self):
        # Trailing empty columns get trimmed by whatever wrote the file.
        rows = read_csv(csv_bytes("NOBODY 2,2025-08-15"))

        self.assertEqual(rows[0].original_title, "NOBODY 2")
        self.assertEqual(rows[0].mpa_rating, "")
        self.assertIsNone(rows[0].runtime_minutes)

    def test_strips_the_excel_byte_order_mark(self):
        # Excel's "CSV UTF-8" export leads with a BOM; without stripping it the
        # first title imports as "﻿NOBODY 2" and never matches again.
        rows = read_csv(csv_bytes("NOBODY 2,2025-08-15,,,,,", prefix="﻿"))

        self.assertEqual(rows[0].original_title, "NOBODY 2")

    def test_reads_windows_encoded_text(self):
        # Excel on Windows writes cp1252, which is not valid UTF-8.
        # \x92 is cp1252's curly apostrophe and not valid UTF-8 on its own.
        raw = b"TITLE,RELEASE\r\nBRIDGET JONES\x92S DIARY,2001-04-13\r\n"
        rows = read_csv(BytesIO(raw))

        self.assertEqual(rows[0].original_title, "BRIDGET JONES’S DIARY")

    def test_a_file_with_only_a_header_reads_as_nothing(self):
        self.assertEqual(read_csv(csv_bytes()), [])


class ReadXlsxTests(SimpleTestCase):
    def test_reads_a_row_from_a_stream(self):
        rows = read_xlsx(workbook_bytes([
            ["BAD GUYS 2, THE", datetime.datetime(2025, 8, 1),
             "Scope", "5.1, 7.1, Atmos", "PG", 104, "2D & 3D"],
        ]), "by TITLE")

        self.assertEqual(rows[0].title, "The Bad Guys 2")
        self.assertEqual(rows[0].release_date, datetime.date(2025, 8, 1))

    def test_a_missing_sheet_names_the_sheets_it_found(self):
        stream = workbook_bytes([["NOBODY 2", None, "", "", "", "", ""]],
                                sheet_name="by DATE")

        with self.assertRaises(StudioImportError) as caught:
            read_xlsx(stream, "by TITLE")

        self.assertIn("by DATE", str(caught.exception))


class ReadUploadTests(SimpleTestCase):
    """Dispatch on the filename, so the admin form does not have to."""

    def test_dispatches_on_extension(self):
        csv_file = SimpleUploadedFile(
            "catalog.csv", csv_bytes("NOBODY 2,2025-08-15,,,,,").getvalue()
        )
        xlsx_file = SimpleUploadedFile(
            "catalog.xlsx",
            workbook_bytes([["NOBODY 2", datetime.datetime(2025, 8, 15)]]).getvalue(),
        )

        self.assertEqual(read_upload(csv_file, "by TITLE")[0].title, "Nobody 2")
        self.assertEqual(read_upload(xlsx_file, "by TITLE")[0].title, "Nobody 2")

    def test_an_unreadable_extension_is_an_import_error(self):
        with self.assertRaises(StudioImportError) as caught:
            read_upload(SimpleUploadedFile("catalog.pdf", b"%PDF-"), "by TITLE")

        self.assertIn(".pdf", str(caught.exception))

    def test_reads_a_path_from_disk(self):
        path = Path(tempfile.mkdtemp()) / "catalog.csv"
        path.write_bytes(csv_bytes("NOBODY 2,2025-08-15,,,,,").getvalue())

        self.assertEqual(read_upload(path, "by TITLE")[0].title, "Nobody 2")


class ImportRowsTests(TestCase):
    """The writing half. Behaviour is the command's, moved intact."""

    def setUp(self):
        self.studio = Studio.objects.create(
            slug="universal", name="Universal Pictures"
        )

    def test_reports_what_it_wrote(self):
        rows = read_csv(csv_bytes(
            "NOBODY 2,2025-08-15,Scope,5.1,R,89,",
            "DRACULA,1931-02-13,Flat,1,,75,",
        ))

        result = import_rows(self.studio, rows)

        self.assertEqual((result.created, result.updated), (2, 0))
        self.assertEqual(result.rows_read, 2)
        self.assertEqual(StudioTitle.objects.count(), 2)

    def test_a_second_import_updates_rather_than_duplicates(self):
        rows = read_csv(csv_bytes("NOBODY 2,2025-08-15,Scope,5.1,R,89,"))
        import_rows(self.studio, rows)

        result = import_rows(self.studio, rows)

        self.assertEqual((result.created, result.updated), (0, 1))
        self.assertEqual(StudioTitle.objects.count(), 1)

    def test_a_csv_and_a_workbook_produce_the_same_row(self):
        from_csv = read_csv(csv_bytes(BAD_GUYS))
        from_xlsx = read_xlsx(workbook_bytes([
            ["BAD GUYS 2, THE", datetime.datetime(2025, 8, 1),
             "Scope", "5.1, 7.1, Atmos", "PG", 104, "2D & 3D"],
        ]), "by TITLE")

        import_rows(self.studio, from_csv)
        csv_row = StudioTitle.objects.values().get()
        StudioTitle.objects.all().delete()
        import_rows(self.studio, from_xlsx)
        xlsx_row = StudioTitle.objects.values().get()

        for field in ("title", "original_title", "release_date", "aspect_ratio",
                      "audio", "mpa_rating", "runtime_minutes", "runtime_raw",
                      "notes", "variant_note"):
            self.assertEqual(csv_row[field], xlsx_row[field], field)
