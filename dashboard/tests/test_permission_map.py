"""Every dashboard view must 403 without its model permission."""

from django.test import TestCase
from django.urls import reverse

from dashboard.tests.helpers import make_staff, permissions_except

# (url_name, kwargs, method, permission). `permission` is one codename, or a
# tuple of alternatives for an any-of view. Kwargs use non-existent pks: the
# check runs in dispatch before any lookup, so 403 proves denial and 404
# proves the gate opened.
PERMISSION_TABLE: list[tuple[str, dict, str, str | tuple[str, ...]]] = [
    ("screens", {}, "get", "cinema.view_screen"),
    ("screen_create", {}, "get", "cinema.add_screen"),
    ("screen_edit", {"pk": 999999}, "get", "cinema.change_screen"),
    ("screen_delete", {"pk": 999999}, "post", "cinema.delete_screen"),
    ("film_search", {}, "get", "cinema.view_film"),
    ("film_search_tmdb", {}, "get", "cinema.add_film"),
    ("film_from_tmdb", {}, "post", "cinema.add_film"),
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
                    username=f"deny-{i}", perms=permissions_except(*alternatives)
                )
                self.client.login(username=f"deny-{i}", password="pw12345")
                response = getattr(self.client, method)(url)
                self.assertEqual(response.status_code, 403)
                self.client.logout()

                make_staff(username=f"allow-{i}", perms=(alternatives[0],))
                self.client.login(username=f"allow-{i}", password="pw12345")
                response = getattr(self.client, method)(url)
                self.assertNotEqual(response.status_code, 403)
                self.client.logout()
