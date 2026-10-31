"""Dashboard-wide plumbing, checked through the Members page: HTMX posts
carry the CSRF token, form field errors are styled, and the film search
offers TMDB only to staff who may add films. (These rode on the Screens
page until it left the dashboard, 2026-10-31.)"""

from pathlib import Path

from audience.models import Member
from cinema.models import Film
from django.test import Client, TestCase
from django.urls import reverse

from dashboard.tests.helpers import make_staff


class HtmxCsrfTests(TestCase):
    """The Delete buttons in _member_list.html are hx-post on a bare
    <button> (not inside a <form>), so htmx must supply the header itself."""

    def setUp(self) -> None:
        make_staff(email="s@example.com", password="pw12345")

    def test_body_has_csrf_hx_headers(self) -> None:
        self.client.login(username="s@example.com", password="pw12345")
        html = self.client.get(reverse("dashboard:members")).content.decode()
        self.assertIn("hx-headers", html)
        self.assertIn("X-CSRFToken", html)

    def _client(self):
        # Django's default test client disables CSRF enforcement entirely.
        client = Client(enforce_csrf_checks=True)
        client.login(username="s@example.com", password="pw12345")
        # Load a page first so the CSRF cookie is set, as a browser would.
        client.get(reverse("dashboard:members"))
        return client

    def test_delete_with_csrf_header_succeeds_under_enforcement(self) -> None:
        client = self._client()
        member = Member.objects.create(first_name="Csrf", last_name="Target")
        resp = client.post(
            reverse("dashboard:member_delete", args=[member.pk]),
            HTTP_X_CSRFTOKEN=client.cookies["csrftoken"].value,
        )
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(Member.objects.filter(pk=member.pk).exists())

    def test_delete_without_csrf_header_is_rejected_under_enforcement(self) -> None:
        client = self._client()
        member = Member.objects.create(first_name="Csrf", last_name="Target")
        resp = client.post(reverse("dashboard:member_delete", args=[member.pk]))
        self.assertEqual(resp.status_code, 403)
        self.assertTrue(Member.objects.filter(pk=member.pk).exists())


class FieldErrorStylingTests(TestCase):
    def test_field_error_styling_linked(self) -> None:
        make_staff(email="s@example.com", password="pw12345")
        self.client.login(username="s@example.com", password="pw12345")
        html = self.client.get(reverse("dashboard:members")).content.decode()
        self.assertIn("dashboard/css/dashboard.css", html)
        css_path = (
            Path(__file__).resolve().parent.parent
            / "static" / "dashboard" / "css" / "dashboard.css"
        )
        self.assertIn(".field-error", css_path.read_text())


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
