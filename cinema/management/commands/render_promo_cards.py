"""Regenerate the standing Open Graph cards under static/img/.

These files are committed — a crawler has to GET them, so they cannot be
rendered per request — but they are not hand-made artwork either. This
command is what makes them, so a copy change is an edit to
cinema/social_cards/promo.py plus a re-run, not a trip through an image
editor.

Rendering is deterministic, so re-running with no source change rewrites the
same bytes and leaves the working tree clean.
"""

from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand

from cinema.social_cards import promo

CARDS = {
    "og-sponsor.jpg": promo.render_sponsor_card,
}


class Command(BaseCommand):
    help = "Render the standing Open Graph cards into static/img/."

    def add_arguments(self, parser):
        parser.add_argument(
            "--check",
            action="store_true",
            help="Report whether the committed files are up to date; write nothing.",
        )

    def handle(self, *args, **options):
        out_dir = Path(settings.BASE_DIR) / "static" / "img"
        stale = []
        for name, render in CARDS.items():
            path = out_dir / name
            data = promo.to_jpeg(render())
            if options["check"]:
                current = path.read_bytes() if path.exists() else b""
                if current != data:
                    stale.append(name)
                    self.stderr.write(f"stale: {name}")
                else:
                    self.stdout.write(f"ok: {name}")
                continue
            path.write_bytes(data)
            self.stdout.write(
                self.style.SUCCESS(f"wrote {path} ({len(data):,} bytes)")
            )
        if options["check"] and stale:
            raise SystemExit(1)
