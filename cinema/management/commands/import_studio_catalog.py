"""Import a studio's DCP availability list into StudioTitle.

Studios send a spreadsheet of everything they will rent us. This loads one
into the catalog behind the /sponsor/ page. A CSV of the same columns works
too.

The reading and writing live in `cinema.studio_import`, shared with the
"Import catalog" uploader on the StudioTitle changelist, so a list imported
here and the same list imported through the admin land identically.

Safe to run on prod:
    python manage.py import_studio_catalog --studio universal \\
        --file "Universal DCP List - Updated 3.4.26.xlsx"

Use --dry-run first to see the counts without writing.
"""

from pathlib import Path
from typing import Any

from cinema.studio_import import (
    DEFAULT_SHEET,
    KNOWN_STUDIOS,
    StudioImportError,
    get_or_create_studio,
    import_rows,
    preview,
    read_upload,
    studio_choices,
)
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction


class Command(BaseCommand):
    help = "Import a studio's DCP availability spreadsheet into StudioTitle."

    def add_arguments(self, parser) -> None:
        parser.add_argument(
            "--studio", required=True,
            help=(
                f"Studio slug: one of {', '.join(sorted(KNOWN_STUDIOS))}, "
                "or any studio already added in the admin."
            ),
        )
        parser.add_argument(
            "--file", required=True, help="Path to the .xlsx or .csv file."
        )
        parser.add_argument(
            "--sheet", default=DEFAULT_SHEET,
            help=(
                "Worksheet to read, .xlsx only. Universal ships 'by DATE' and "
                "'by TITLE' with identical content, so the default is fine."
            ),
        )
        parser.add_argument(
            "--dry-run", action="store_true",
            help="Report what would change without writing.",
        )

    def handle(self, *args: Any, **options: Any) -> None:
        slug = options["studio"]
        # Same list as the admin uploader: the known studios plus any row.
        known = dict(studio_choices())
        if slug not in known:
            raise CommandError(
                f"Unknown studio '{slug}'. Known: {', '.join(sorted(known))}"
            )

        path = Path(options["file"])
        if not path.is_file():
            raise CommandError(f"No such file: {path}")

        try:
            rows = read_upload(path, options["sheet"])
        except StudioImportError as error:
            raise CommandError(str(error)) from error

        if options["dry_run"]:
            result = preview(rows)
            self.stdout.write(self.style.WARNING("DRY RUN — nothing written."))
            self.stdout.write(
                f"Would import {result.rows_read - result.collapsed} titles "
                f"from {result.rows_read} rows "
                f"({result.collapsed} variants collapsed)."
            )
            return

        with transaction.atomic():
            studio = get_or_create_studio(slug)
            result = import_rows(studio, rows)

        self.stdout.write(
            self.style.SUCCESS(
                f"{studio.name}: {result.created} created, {result.updated} "
                f"updated, {result.collapsed} variants collapsed, "
                f"{result.rows_read} rows read."
            )
        )
