from django.db.utils import IntegrityError
from django.test import TestCase

from cinema.models import Film  # Assuming Film model uses SlugModelMixin


class SlugModelMixinTestCase(TestCase):
    def setUp(self) -> None:
        # Ensure the database is clean before each test
        Film.objects.all().delete()

    def test_slug_is_unique(self) -> None:
        film1 = Film.objects.create(title="Elio", imdb_id="1", youtube_id="1")
        self.assertIsNotNone(film1.slug)
        self.assertEqual(film1.slug, "elio")
        with self.assertRaises(IntegrityError):
            Film.objects.create(title="Elio", imdb_id="2", youtube_id="2")
