from cinema.models import Film, Screen
from django.test import TestCase


class FilmTestCase(TestCase):
    def test_str_is_title(self) -> None:
        film = Film.objects.create(title="Toy Story 5")
        self.assertEqual(str(film), "Toy Story 5")

    def test_blank_external_ids_coerced_to_none(self) -> None:
        # Empty-string ids must become NULL so multiple blank films are allowed
        # under the unique constraints on tmdb_id/imdb_id/youtube_id.
        first = Film.objects.create(title="A", tmdb_id="", imdb_id="", youtube_id="")
        second = Film.objects.create(title="B", tmdb_id="", imdb_id="", youtube_id="")
        first.refresh_from_db()
        self.assertIsNone(first.tmdb_id)
        self.assertIsNone(second.tmdb_id)


class ScreenTestCase(TestCase):
    def test_str_is_name(self) -> None:
        screen = Screen.objects.create(name="Screen 1", capacity=120)
        self.assertEqual(str(screen), "Screen 1")

    def test_defaults(self) -> None:
        screen = Screen.objects.create(name="Main", capacity=200)
        self.assertEqual(screen.screen_type, "standard")
        self.assertEqual(screen.aspect_ratio, "scope")
        self.assertEqual(screen.sound_system, "standard")
        self.assertFalse(screen.supports_3d)
