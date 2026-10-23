from django.conf import settings
from django.test import TestCase, override_settings
from dashboard.tests.helpers import make_staff


class LoginTests(TestCase):
    def setUp(self) -> None:
        make_staff(email="staffer@example.com", password="pw12345")

    def test_login_page_themed(self) -> None:
        resp = self.client.get("/login")
        self.assertEqual(resp.status_code, 200)
        html = resp.content.decode()
        self.assertIn("LeprinceOS", html)
        self.assertIn("login.css", html)

    def test_login_redirects_to_dashboard(self) -> None:
        resp = self.client.post(
            "/login", {"username": "staffer@example.com", "password": "pw12345"}
        )
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp["Location"], "/dashboard/")

    def test_logout_works(self) -> None:
        self.client.login(username="staffer@example.com", password="pw12345")
        resp = self.client.post("/logout/")
        self.assertEqual(resp.status_code, 302)


@override_settings(
    AXES_ENABLED=True,
    AUTHENTICATION_BACKENDS=[
        "axes.backends.AxesStandaloneBackend",
        "django.contrib.auth.backends.ModelBackend",
    ],
)
class LoginLockoutTests(TestCase):
    """Password guessing against staff accounts was bounded only by the
    password validators. Five wrong tries on a username from one address
    lock that pair out for a while; the right password then waits too."""

    def setUp(self) -> None:
        make_staff(email="staffer@example.com", password="pw12345")

    def attempt(self, password: str):
        return self.client.post(
            "/login", {"username": "staffer@example.com", "password": password}
        )

    def test_wrong_passwords_under_the_limit_do_not_lock(self) -> None:
        for _ in range(settings.AXES_FAILURE_LIMIT - 1):
            self.assertEqual(self.attempt("nope").status_code, 200)
        resp = self.attempt("pw12345")
        self.assertEqual((resp.status_code, resp["Location"]), (302, "/dashboard/"))

    def test_too_many_wrong_passwords_lock_the_account_out(self) -> None:
        for _ in range(settings.AXES_FAILURE_LIMIT - 1):
            self.assertEqual(self.attempt("nope").status_code, 200)
        # The try that reaches the limit is the first one locked out.
        self.assertEqual(self.attempt("nope").status_code, 429)
        resp = self.attempt("pw12345")
        self.assertEqual(resp.status_code, 429)
        html = resp.content.decode()
        self.assertIn("Too many sign-in attempts", html)
        self.assertIn("15 minutes", html)
        self.assertNotIn("staffer@example.com", html)  # the page echoes no email

    def test_lockout_is_per_username_not_site_wide(self) -> None:
        make_staff(email="other@example.com", password="pw12345")
        for _ in range(settings.AXES_FAILURE_LIMIT):
            self.attempt("nope")
        resp = self.client.post(
            "/login", {"username": "other@example.com", "password": "pw12345"}
        )
        self.assertEqual(resp.status_code, 302)

    def test_a_good_login_resets_the_count(self) -> None:
        for _ in range(settings.AXES_FAILURE_LIMIT - 1):
            self.attempt("nope")
        self.assertEqual(self.attempt("pw12345").status_code, 302)
        self.client.logout()
        for _ in range(settings.AXES_FAILURE_LIMIT - 1):
            self.attempt("nope")
        self.assertEqual(self.attempt("pw12345").status_code, 302)
