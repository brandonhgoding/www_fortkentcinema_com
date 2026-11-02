"""Every dashboard view must 403 without its model permission."""

import re
from pathlib import Path

from django.conf import settings
from django.test import TestCase
from django.urls import reverse

import dashboard.urls
from dashboard.tests.helpers import (
    DASHBOARD_PERMISSIONS,
    SPEC_PERMISSIONS,
    _declared_by_views,
    make_staff,
    permissions_except,
)
from dashboard.views import HomeView


# (url_name, kwargs, method, permission). `permission` is one codename, or a
# tuple of alternatives for an any-of view. Kwargs use non-existent pks: the
# check runs in dispatch before any lookup, so 403 proves denial and 404
# proves the gate opened.
PERMISSION_TABLE: list[tuple[str, dict, str, str | tuple[str, ...]]] = [
    ("film_search", {}, "get", "cinema.view_film"),
    ("film_search_tmdb", {}, "get", "cinema.add_film"),
    ("film_from_tmdb", {}, "post", "cinema.add_film"),
    ("engagements", {}, "get", "cinema.view_engagement"),
    ("engagement_detail", {"pk": 999999}, "get", "cinema.view_engagement"),
    ("engagement_create", {}, "get", "cinema.add_engagement"),
    ("engagement_edit", {"pk": 999999}, "get", "cinema.change_engagement"),
    ("engagement_status", {"pk": 999999}, "post", "cinema.change_engagement"),
    ("engagement_square_retry", {"pk": 999999}, "post", "cinema.change_engagement"),
    ("engagement_delete", {"pk": 999999}, "post", "cinema.delete_engagement"),
    ("showtime_create", {"eng_pk": 999999}, "get", "cinema.add_showtime"),
    ("showtime_bulk", {"eng_pk": 999999}, "get", "cinema.add_showtime"),
    ("showtime_edit", {"pk": 999999}, "get", "cinema.change_showtime"),
    ("showtime_delete", {"pk": 999999}, "post", "cinema.delete_showtime"),
    ("rental_inquiries", {}, "get", "cinema.view_rentalinquiry"),
    ("rental_inquiry_status", {"pk": 999999}, "post", "cinema.change_rentalinquiry"),
    ("ad_inquiries", {}, "get", "cinema.view_adinquiry"),
    ("ad_inquiry_status", {"pk": 999999}, "post", "cinema.change_adinquiry"),
    ("voicemails", {}, "get", "phone.view_voicemail"),
    ("voicemail_audio", {"pk": 999999}, "get", "phone.view_voicemail"),
    ("voicemail_status", {"pk": 999999}, "post", "phone.change_voicemail"),
    ("voicemail_notes", {"pk": 999999}, "post", "phone.change_voicemail"),
    ("voicemail_delete", {"pk": 999999}, "post", "phone.delete_voicemail"),
    ("subscribers", {}, "get", "audience.view_subscriber"),
    ("subscribers_export", {}, "get", "audience.view_subscriber"),
]


class PermissionMapTests(TestCase):
    def test_every_view_enforces_its_permission(self) -> None:
        for i, (url_name, kwargs, method, permission) in enumerate(
            PERMISSION_TABLE
        ):
            with self.subTest(url_name=url_name):
                url = reverse(f"dashboard:{url_name}", kwargs=kwargs)
                alternatives = (
                    (permission,) if isinstance(permission, str) else permission
                )

                make_staff(
                    email=f"deny-{i}@example.com",
                    perms=permissions_except(*alternatives),
                )
                self.client.login(username=f"deny-{i}@example.com", password="pw12345")
                response = getattr(self.client, method)(url)
                self.assertEqual(response.status_code, 403)
                self.client.logout()

                make_staff(email=f"allow-{i}@example.com", perms=(alternatives[0],))
                self.client.login(username=f"allow-{i}@example.com", password="pw12345")
                response = getattr(self.client, method)(url)
                self.assertNotEqual(response.status_code, 403)
                self.client.logout()

    def test_every_view_but_home_declares_a_permission(self) -> None:
        for pattern in dashboard.urls.urlpatterns:
            view_class = pattern.callback.view_class
            with self.subTest(view=view_class.__name__):
                if view_class is HomeView:
                    self.assertEqual(view_class.permission_required, ())
                else:
                    self.assertTrue(view_class.permission_required)

    def test_every_url_is_in_the_table(self) -> None:
        names = {p.name for p in dashboard.urls.urlpatterns} - {"home"}
        self.assertEqual(names, {row[0] for row in PERMISSION_TABLE})

    def test_declared_permissions_match_the_spec(self) -> None:
        declared = _declared_by_views()
        self.assertEqual(declared - SPEC_PERMISSIONS, set())
        # Only templates and the home page use these two; no view declares them.
        self.assertEqual(
            SPEC_PERMISSIONS - declared,
            {
                "boxoffice.view_salespull",
                "cinema.view_showtime",
            },
        )


class TemplatePermissionStringTests(TestCase):
    def test_template_permission_strings_exist(self) -> None:
        base = Path(settings.BASE_DIR)
        found = set()
        for path in (base / "dashboard/templates/dashboard").rglob("*.html"):
            text = path.read_text(encoding="utf-8")
            found.update(
                f"{app}.{code}"
                for app, code in re.findall(r"perms\.(\w+)\.(\w+)", text)
            )
        self.assertTrue(found)
        self.assertEqual(sorted(found - set(DASHBOARD_PERMISSIONS)), [])
