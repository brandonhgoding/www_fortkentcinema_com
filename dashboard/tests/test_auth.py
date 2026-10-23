import json

from django.http import HttpResponse
from django.test import TestCase, override_settings
from django.urls import path, reverse
from django.views import View

from accounts.tests.factories import make_user
from dashboard.mixins import StaffRequiredMixin
from dashboard.tests.helpers import make_staff
from fortkentcinema.urls import urlpatterns as project_urlpatterns


class ProbeView(StaffRequiredMixin, View):
    permission_required = "cinema.view_screen"

    def get(self, request) -> HttpResponse:
        return HttpResponse("ok")

    def post(self, request) -> HttpResponse:
        return HttpResponse("posted")


class ProbeAllView(ProbeView):
    permission_required = ("cinema.view_screen", "cinema.add_screen")


urlpatterns = [
    path("perm-probe", ProbeView.as_view()),
    path("perm-probe-all", ProbeAllView.as_view()),
    *project_urlpatterns,
]


class DashboardAuthTests(TestCase):
    def setUp(self) -> None:
        self.staff = make_staff(
            email="staffer@example.com", password="pw12345"
        )
        self.plain = make_user(
            email="plain@example.com", password="pw12345", is_staff=False
        )

    def test_anonymous_redirected_to_login(self) -> None:
        resp = self.client.get(reverse("dashboard:home"))
        self.assertEqual(resp.status_code, 302)
        self.assertIn("/login", resp["Location"])
        self.assertIn("next=", resp["Location"])

    def test_non_staff_forbidden(self) -> None:
        self.client.login(username="plain@example.com", password="pw12345")
        resp = self.client.get(reverse("dashboard:home"))
        self.assertEqual(resp.status_code, 403)

    def test_staff_ok(self) -> None:
        self.client.login(username="staffer@example.com", password="pw12345")
        resp = self.client.get(reverse("dashboard:home"))
        self.assertEqual(resp.status_code, 200)

    def test_named_routes_resolve(self) -> None:
        self.assertEqual(reverse("dashboard:home"), "/dashboard/")
        self.assertEqual(reverse("dashboard:screens"), "/dashboard/screens")
        self.assertEqual(reverse("dashboard:engagements"), "/dashboard/engagements")


@override_settings(ROOT_URLCONF="dashboard.tests.test_auth")
class DashboardPermissionTests(TestCase):
    def login(self, perms) -> None:
        make_staff(email="viewer@example.com", perms=perms)
        self.client.login(username="viewer@example.com", password="pw12345")

    def test_staff_without_permission_forbidden(self) -> None:
        self.login(())
        self.assertEqual(self.client.get("/perm-probe").status_code, 403)

    def test_staff_with_permission_ok(self) -> None:
        self.login(("cinema.view_screen",))
        self.assertEqual(self.client.get("/perm-probe").status_code, 200)

    def test_superuser_without_explicit_permission_ok(self) -> None:
        make_user(
            email="root@example.com",
            password="pw12345",
            is_staff=True,
            is_superuser=True,
        )
        self.client.login(username="root@example.com", password="pw12345")
        self.assertEqual(self.client.get("/perm-probe").status_code, 200)

    def test_htmx_denied_carries_toast(self) -> None:
        self.login(())
        resp = self.client.post("/perm-probe", HTTP_HX_REQUEST="true")
        self.assertEqual(resp.status_code, 403)
        trigger = json.loads(resp["HX-Trigger"])
        self.assertEqual(
            trigger["dashboard-toast"],
            {"kind": "error", "message": "You don't have permission to do that."},
        )

    def test_tuple_requires_every_permission(self) -> None:
        self.login(("cinema.view_screen",))
        self.assertEqual(self.client.get("/perm-probe-all").status_code, 403)

    def test_make_staff_default_holds_every_dashboard_permission(self) -> None:
        user = make_staff()
        self.assertTrue(user.has_perm("cinema.view_screen"))
        self.assertTrue(user.has_perm("phone.delete_voicemail"))
        self.assertTrue(user.has_perm("boxoffice.view_salespull"))
        self.assertTrue(user.has_perm("blog.view_blogauthor"))
