from unittest import mock

from cinema.models import Film
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

User = get_user_model()


class FilmSearchTests(TestCase):
    def setUp(self) -> None:
        User.objects.create_user(username="s", password="pw12345", is_staff=True)
        self.client.login(username="s", password="pw12345")

    def test_local_search_matches(self) -> None:
        Film.objects.create(title="Jaws", runtime_minutes=124)
        Film.objects.create(title="Dune", runtime_minutes=155)
        html = self.client.get(reverse("dashboard:film_search"), {"q": "jaw"}).content.decode()
        self.assertIn("Jaws", html)
        self.assertNotIn("Dune", html)
        self.assertIn("Search TMDB", html)  # the TMDB affordance
        self.assertIn(reverse("dashboard:film_search_tmdb"), html)

    def test_local_search_empty_q(self) -> None:
        html = self.client.get(reverse("dashboard:film_search"), {"q": ""}).content.decode()
        self.assertNotIn("Search TMDB", html)

    @mock.patch("dashboard.views.TMDBService")
    def test_tmdb_search_renders_results(self, MockSvc) -> None:
        MockSvc.return_value.search_films.return_value = [
            {"tmdb_id": 5, "title": "Alien", "release_date": "1979-05-25",
             "overview": "space horror", "poster_path": "https://img/a.jpg", "vote_average": 8.4}
        ]
        html = self.client.get(reverse("dashboard:film_search_tmdb"), {"q": "alien"}).content.decode()
        self.assertIn("Alien", html)
        self.assertIn("1979", html)
        self.assertIn("TMDB Results", html)

    @mock.patch("dashboard.views.TMDBService")
    def test_tmdb_search_error_inline(self, MockSvc) -> None:
        from cinema.tmdb import TMDBAPIError
        MockSvc.return_value.search_films.side_effect = TMDBAPIError("boom")
        resp = self.client.get(reverse("dashboard:film_search_tmdb"), {"q": "x"})
        self.assertEqual(resp.status_code, 200)  # not a 500
        self.assertIn("Couldn't reach TMDB", resp.content.decode())

    def test_requires_staff(self) -> None:
        self.client.logout()
        self.assertEqual(self.client.get(reverse("dashboard:film_search")).status_code, 302)
