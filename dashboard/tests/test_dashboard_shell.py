"""Dashboard-wide plumbing, checked through the Engagements page: HTMX posts
carry the CSRF token, and the film search offers TMDB only to staff who may
add films. (These rode on the Screens page until it left the dashboard,
2026-10-31, then on the Blog page until the blog went, 2026-11-01.)"""

from cinema.models import Engagement, Film, Screen
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from dashboard.tests.helpers import make_staff
from dashboard.tests.test_engagements import make_engagement


class HtmxCsrfTests(TestCase):
    """The Delete buttons in _engagement_list.html are hx-post on a bare
    <button> (not inside a <form>), so htmx must supply the header itself."""

    def setUp(self) -> None:
        make_staff(email="s@example.com", password="pw12345")
        today = timezone.localdate()
        self.engagement = make_engagement(
            Screen.objects.create(name="S1", capacity=50), start=today, end=today
        )
        self.delete_url = (
            reverse("dashboard:engagement_delete", args=[self.engagement.pk])
            + "?tab=CURRENT"
        )

    def test_body_has_csrf_hx_headers(self) -> None:
        self.client.login(username="s@example.com", password="pw12345")
        html = self.client.get(reverse("dashboard:engagements")).content.decode()
        self.assertIn("hx-headers", html)
        self.assertIn("X-CSRFToken", html)

    def _client(self):
        # Django's default test client disables CSRF enforcement entirely.
        client = Client(enforce_csrf_checks=True)
        client.login(username="s@example.com", password="pw12345")
        # Load a page first so the CSRF cookie is set, as a browser would.
        client.get(reverse("dashboard:engagements"))
        return client

    def test_delete_with_csrf_header_succeeds_under_enforcement(self) -> None:
        client = self._client()
        resp = client.post(
            self.delete_url,
            HTTP_X_CSRFTOKEN=client.cookies["csrftoken"].value,
        )
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(Engagement.objects.filter(pk=self.engagement.pk).exists())

    def test_delete_without_csrf_header_is_rejected_under_enforcement(self) -> None:
        client = self._client()
        resp = client.post(self.delete_url)
        self.assertEqual(resp.status_code, 403)
        self.assertTrue(Engagement.objects.filter(pk=self.engagement.pk).exists())


class FilmSearchTests(TestCase):
    def test_film_search_hides_tmdb_without_add_film(self) -> None:
        Film.objects.create(title="Casablanca")
        make_staff(email="viewer@example.com", perms=("cinema.view_film",))
        self.client.login(username="viewer@example.com", password="pw12345")
        html = self.client.get(
            reverse("dashboard:film_search"), {"q": "Casa"}
        ).content.decode()
        self.assertIn("Casablanca", html)
        self.assertNotIn(reverse("dashboard:film_search_tmdb"), html)
