import datetime

from cinema.models import Film, Studio, StudioTitle
from django.db import IntegrityError
from django.test import TestCase


class StudioTitleTests(TestCase):
    def setUp(self) -> None:
        self.studio = Studio.objects.create(
            name="Universal Pictures", slug="universal"
        )

    def make(self, **kwargs) -> StudioTitle:
        defaults = {
            "studio": self.studio,
            "original_title": "BAD GUYS 2, THE",
            "title": "The Bad Guys 2",
            "release_date": datetime.date(2025, 8, 1),
        }
        defaults.update(kwargs)
        return StudioTitle.objects.create(**defaults)

    def test_release_year_from_date(self):
        self.assertEqual(self.make().release_year, 2025)

    def test_release_year_is_none_without_a_date(self):
        self.assertIsNone(self.make(release_date=None).release_year)

    def test_format_summary_joins_non_empty_parts(self):
        title = self.make(
            aspect_ratio="Scope", audio="5.1, 7.1, Atmos", notes="4K"
        )
        self.assertEqual(title.format_summary, "Scope · 5.1, 7.1, Atmos · 4K")

    def test_format_summary_skips_blanks(self):
        self.assertEqual(self.make(aspect_ratio="Scope").format_summary, "Scope")
        self.assertEqual(self.make(original_title="X").format_summary, "")

    def test_available_excludes_hidden_titles(self):
        self.make()
        self.make(original_title="HIDDEN", title="Hidden", is_available=False)
        self.assertEqual(
            [t.title for t in StudioTitle.objects.available()], ["The Bad Guys 2"]
        )

    def test_available_excludes_inactive_studios(self):
        self.make()
        other = Studio.objects.create(name="Gone", slug="gone", is_active=False)
        StudioTitle.objects.create(
            studio=other, original_title="X", title="X"
        )
        self.assertEqual(
            [t.title for t in StudioTitle.objects.available()], ["The Bad Guys 2"]
        )

    def test_natural_key_is_unique(self):
        self.make()
        with self.assertRaises(IntegrityError):
            self.make()

    def test_same_title_different_release_date_is_allowed(self):
        # Dracula (1931) really does ship under two release dates.
        self.make(original_title="DRACULA", release_date=datetime.date(1931, 2, 13))
        self.make(original_title="DRACULA", release_date=datetime.date(1931, 4, 24))
        self.assertEqual(
            StudioTitle.objects.filter(original_title="DRACULA").count(), 2
        )

    def test_film_link_is_optional_and_survives_film_deletion(self):
        film = Film.objects.create(title="The Bad Guys 2")
        title = self.make(film=film)
        film.delete()
        title.refresh_from_db()
        self.assertIsNone(title.film)

    def test_str_is_the_display_title(self):
        self.assertEqual(str(self.make()), "The Bad Guys 2")
