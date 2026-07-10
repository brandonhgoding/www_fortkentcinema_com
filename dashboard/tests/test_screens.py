from cinema.models import Screen
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

User = get_user_model()


class ScreenListTests(TestCase):
    def setUp(self) -> None:
        User.objects.create_user(username="s", password="pw12345", is_staff=True)
        self.client.login(username="s", password="pw12345")

    def test_empty_state(self) -> None:
        html = self.client.get(reverse("dashboard:screens")).content.decode()
        self.assertIn("empty-state", html)
        self.assertIn("No Screens Configured", html)

    def test_rows_and_labels(self) -> None:
        Screen.objects.create(
            name="Screen 1", capacity=150, screen_type="dolby_cinema",
            aspect_ratio="scope", sound_system="standard", supports_3d=True,
        )
        html = self.client.get(reverse("dashboard:screens")).content.decode()
        self.assertIn("Screen 1", html)
        self.assertIn("150 seats", html)
        self.assertIn("Dolby Cinema", html)          # screen_type label
        self.assertIn("Scope (2.39:1)", html)        # aspect_ratio label
        self.assertIn("Standard", html)              # sound label (NOT "Standard Surround")
        self.assertNotIn("Standard Surround", html)
        self.assertIn("badge3d", html)               # 3D badge present

    def test_requires_staff(self) -> None:
        self.client.logout()
        self.assertEqual(self.client.get(reverse("dashboard:screens")).status_code, 302)
        User.objects.create_user(username="p", password="pw12345", is_staff=False)
        self.client.login(username="p", password="pw12345")
        self.assertEqual(self.client.get(reverse("dashboard:screens")).status_code, 403)

    def test_screens_css_linked(self) -> None:
        html = self.client.get(reverse("dashboard:screens")).content.decode()
        self.assertIn("dashboard/css/screens.css", html)


import json


class ScreenCreateEditTests(TestCase):
    def setUp(self) -> None:
        User.objects.create_user(username="s", password="pw12345", is_staff=True)
        self.client.login(username="s", password="pw12345")

    def test_get_create_form(self) -> None:
        html = self.client.get(reverse("dashboard:screen_create")).content.decode()
        self.assertIn('id="screen-form"', html)
        self.assertIn("Create Screen", html)  # footer submit label

    def test_post_create_valid(self) -> None:
        resp = self.client.post(
            reverse("dashboard:screen_create"),
            {"name": "Main", "capacity": 200, "screen_type": "standard",
             "aspect_ratio": "flat", "sound_system": "standard", "supports_3d": ""},
        )
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(Screen.objects.filter(name="Main").exists())
        self.assertIn('id="screen-list"', resp.content.decode())  # OOB list swap
        self.assertIn("close-drawer", resp["HX-Trigger"])
        self.assertIn("dashboard-toast", resp["HX-Trigger"])

    def test_post_create_invalid_shows_errors(self) -> None:
        resp = self.client.post(
            reverse("dashboard:screen_create"),
            {"name": "", "capacity": 0, "screen_type": "standard",
             "aspect_ratio": "flat", "sound_system": "standard"},
        )
        self.assertEqual(resp.status_code, 200)
        self.assertIn('id="screen-form"', resp.content.decode())
        self.assertNotIn("HX-Trigger", resp)  # drawer stays open, no close
        self.assertEqual(Screen.objects.count(), 0)

    def test_get_edit_prefilled(self) -> None:
        s = Screen.objects.create(name="Edit Me", capacity=99, screen_type="imax",
                                  aspect_ratio="scope", sound_system="dolby_atmos", supports_3d=True)
        html = self.client.get(reverse("dashboard:screen_edit", args=[s.pk])).content.decode()
        self.assertIn("Edit Me", html)
        self.assertIn("Save Changes", html)  # footer submit label for edit

    def test_post_edit_updates(self) -> None:
        s = Screen.objects.create(name="Old", capacity=50, screen_type="standard",
                                  aspect_ratio="flat", sound_system="standard", supports_3d=False)
        resp = self.client.post(
            reverse("dashboard:screen_edit", args=[s.pk]),
            {"name": "New", "capacity": 75, "screen_type": "standard",
             "aspect_ratio": "flat", "sound_system": "standard", "supports_3d": "on"},
        )
        self.assertEqual(resp.status_code, 200)
        s.refresh_from_db()
        self.assertEqual(s.name, "New")
        self.assertTrue(s.supports_3d)


import datetime

from cinema.models import Engagement, Showtime


class ScreenDeleteTests(TestCase):
    def setUp(self) -> None:
        User.objects.create_user(username="s", password="pw12345", is_staff=True)
        self.client.login(username="s", password="pw12345")

    def test_delete_unreferenced(self) -> None:
        s = Screen.objects.create(name="Trash", capacity=10, screen_type="standard",
                                  aspect_ratio="flat", sound_system="standard", supports_3d=False)
        resp = self.client.post(reverse("dashboard:screen_delete", args=[s.pk]))
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(Screen.objects.filter(pk=s.pk).exists())
        self.assertIn("dashboard-toast", resp["HX-Trigger"])

    def test_delete_protected(self) -> None:
        s = Screen.objects.create(name="Busy", capacity=100, screen_type="standard",
                                  aspect_ratio="flat", sound_system="standard", supports_3d=False)
        Engagement.objects.create(screen=s, start_date=datetime.date(2026, 7, 1),
                                  end_date=datetime.date(2026, 7, 7))
        resp = self.client.post(reverse("dashboard:screen_delete", args=[s.pk]))
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(Screen.objects.filter(pk=s.pk).exists())  # NOT deleted
        trigger = resp["HX-Trigger"]
        self.assertIn("dashboard-toast", trigger)
        self.assertIn("Can't delete", trigger)
        self.assertIn("engagement", trigger)


from pathlib import Path

from django.test import Client


class HtmxCsrfTests(TestCase):
    """Covers the whole-branch review fix: HTMX POSTs need a CSRF token,
    since the Delete buttons in _screen_list.html are hx-post on a bare
    <button> (not inside a <form>), so htmx must supply the header itself."""

    def setUp(self) -> None:
        User.objects.create_user(username="s", password="pw12345", is_staff=True)

    def test_body_has_csrf_hx_headers(self) -> None:
        self.client.login(username="s", password="pw12345")
        html = self.client.get(reverse("dashboard:screens")).content.decode()
        self.assertIn("hx-headers", html)
        self.assertIn("X-CSRFToken", html)

    def test_delete_with_csrf_header_succeeds_under_enforcement(self) -> None:
        # Django's default test client disables CSRF enforcement entirely,
        # which is exactly why this bug wasn't caught by existing tests.
        client = Client(enforce_csrf_checks=True)
        client.login(username="s", password="pw12345")

        # Load a page first so the CSRF cookie is set on the client,
        # mirroring what the browser does before htmx fires its request.
        client.get(reverse("dashboard:screens"))
        token = client.cookies["csrftoken"].value

        screen = Screen.objects.create(
            name="Csrf Target", capacity=10, screen_type="standard",
            aspect_ratio="flat", sound_system="standard", supports_3d=False,
        )
        resp = client.post(
            reverse("dashboard:screen_delete", args=[screen.pk]),
            HTTP_X_CSRFTOKEN=token,
        )
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(Screen.objects.filter(pk=screen.pk).exists())

    def test_delete_without_csrf_header_is_rejected_under_enforcement(self) -> None:
        client = Client(enforce_csrf_checks=True)
        client.login(username="s", password="pw12345")
        client.get(reverse("dashboard:screens"))

        screen = Screen.objects.create(
            name="Csrf Target 2", capacity=10, screen_type="standard",
            aspect_ratio="flat", sound_system="standard", supports_3d=False,
        )
        resp = client.post(reverse("dashboard:screen_delete", args=[screen.pk]))
        self.assertEqual(resp.status_code, 403)
        self.assertTrue(Screen.objects.filter(pk=screen.pk).exists())


class FieldErrorStylingTests(TestCase):
    def setUp(self) -> None:
        User.objects.create_user(username="s", password="pw12345", is_staff=True)
        self.client.login(username="s", password="pw12345")

    def test_field_error_styling_linked(self) -> None:
        html = self.client.get(reverse("dashboard:screens")).content.decode()
        self.assertIn("dashboard/css/dashboard.css", html)

        css_path = (
            Path(__file__).resolve().parent.parent
            / "static" / "dashboard" / "css" / "dashboard.css"
        )
        self.assertIn(".field-error", css_path.read_text())
