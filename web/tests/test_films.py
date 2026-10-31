"""Film slugs.

The /movies/<slug> pages were retired 2026-10-14; the slugs stay on the
model because the legacy redirect still reads them.
"""

from cinema.models import Film
from django.test import TestCase


class FilmSlugTests(TestCase):
    def test_slug_generated_from_title(self):
        film = Film.objects.create(title="The Odyssey")
        self.assertEqual(film.slug, "the-odyssey")

    def test_remake_gets_a_suffix_rather_than_raising(self):
        """Film has no release year, so remakes collide."""
        Film.objects.create(title="The Mummy")
        remake = Film.objects.create(title="The Mummy")
        self.assertEqual(remake.slug, "the-mummy-2")
