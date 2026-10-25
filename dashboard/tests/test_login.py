from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.utils import timezone
from django.test import TestCase, override_settings
from dashboard.tests.helpers import make_staff


class LoginTests(TestCase):
    def setUp(self) -> None:
        cache.clear()
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

    def test_login_asks_for_email(self) -> None:
        html = self.client.get("/login").content.decode()
        self.assertIn('type="email"', html)
        self.assertIn('autocomplete="email"', html)
        self.assertIn(">Email<", html)

    def test_wrong_password_says_email(self) -> None:
        resp = self.client.post(
            "/login", {"username": "staffer@example.com", "password": "no"}
        )
        self.assertContains(resp, "Invalid email or password.")

    def test_login_ignores_email_case(self) -> None:
        resp = self.client.post(
            "/login", {"username": "Staffer@Example.com", "password": "pw12345"}
        )
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
        cache.clear()
        make_staff(email="staffer@example.com", password="pw12345")

    def attempt(self, password: str):
        return self.client.post(
            "/login",
            {"username": "staffer@example.com", "password": password},
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

    def test_mixed_case_tries_count_against_one_email(self) -> None:
        for i in range(settings.AXES_FAILURE_LIMIT):
            email = "staffer@example.com" if i % 2 == 0 else "STAFFER@example.com"
            self.client.post("/login", {"username": email, "password": "nope"})
        self.assertEqual(self.attempt("pw12345").status_code, 429)

    def test_lockout_is_per_username_not_site_wide(self) -> None:
        make_staff(email="other@example.com", password="pw12345")
        for _ in range(settings.AXES_FAILURE_LIMIT):
            self.attempt("nope")
        resp = self.client.post(
            "/login",
            {"username": "other@example.com", "password": "pw12345"},
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


class StaffNextTests(TestCase):
    def setUp(self) -> None:
        cache.clear()

    def test_staff_password_login_still_honours_next(self) -> None:
        make_staff(email="staffer@example.com", password="pw12345")
        resp = self.client.post(
            "/login",
            {
                "username": "staffer@example.com",
                "password": "pw12345",
                "next": "/dashboard/members",
            },
        )
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp["Location"], "/dashboard/members")


PRODUCTION_BACKENDS = [
    "axes.backends.AxesStandaloneBackend",
    "django.contrib.auth.backends.ModelBackend",
]
UNVERIFIED = "Please confirm your email first. We can send a new link."


def make_member(verified: bool, email: str = "member@example.com"):
    user = get_user_model().objects.create_user(email, "pw12345", is_staff=False)
    if verified:
        user.email_verified_at = timezone.now()
        user.save(update_fields=["email_verified_at"])
    return user


class MemberSignInTests(TestCase):
    def setUp(self) -> None:
        cache.clear()

    def test_login_single_form(self) -> None:
        html = self.client.get("/login").content.decode()
        self.assertNotIn("<details", html)
        self.assertNotIn("Email me a sign-in link", html)
        self.assertIn('href="/register"', html)
        self.assertIn("Create an account", html)
        self.assertEqual(html.count("<form"), 1)

    def _assert_unverified(self, resp) -> None:
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, UNVERIFIED)
        self.assertContains(resp, "Send a new link")
        self.assertContains(resp, 'action="/register/resend"')
        self.assertContains(resp, 'name="email" value="member@example.com"')
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_unverified_member_not_signed_in_sees_resend(self) -> None:
        make_member(verified=False)
        resp = self.client.post(
            "/login", {"username": "member@example.com", "password": "pw12345"}
        )
        self._assert_unverified(resp)

    @override_settings(AXES_ENABLED=True, AUTHENTICATION_BACKENDS=PRODUCTION_BACKENDS)
    def test_unverified_member_with_axes_enabled(self) -> None:
        make_member(verified=False)
        resp = self.client.post(
            "/login", {"username": "member@example.com", "password": "pw12345"}
        )
        self._assert_unverified(resp)

    def test_unverified_wrong_password_says_invalid(self) -> None:
        make_member(verified=False)
        resp = self.client.post(
            "/login", {"username": "member@example.com", "password": "nope"}
        )
        self.assertContains(resp, "Invalid email or password.")
        self.assertNotContains(resp, UNVERIFIED)
        self.assertNotContains(resp, "Send a new link")

    def test_verified_member_signs_in_to_dashboard(self) -> None:
        make_member(verified=True)
        resp = self.client.post(
            "/login", {"username": "member@example.com", "password": "pw12345"}
        )
        self.assertEqual((resp.status_code, resp["Location"]), (302, "/dashboard/"))

    def test_staff_without_verification_still_signs_in(self) -> None:
        make_staff(email="staffer@example.com", password="pw12345")
        resp = self.client.post(
            "/login", {"username": "staffer@example.com", "password": "pw12345"}
        )
        self.assertEqual(resp["Location"], "/dashboard/")

    def test_signed_in_visitor_redirected_from_login(self) -> None:
        make_member(verified=True)
        self.client.login(username="member@example.com", password="pw12345")
        resp = self.client.get("/login")
        self.assertEqual((resp.status_code, resp["Location"]), (302, "/dashboard/"))

    def test_signed_in_visitor_with_next_sees_the_form(self) -> None:
        make_member(verified=True)
        self.client.login(username="member@example.com", password="pw12345")
        resp = self.client.get("/login?next=/dashboard/members")
        self.assertEqual(resp.status_code, 200)


@override_settings(
    AXES_ENABLED=True,
    AUTHENTICATION_BACKENDS=[
        "axes.backends.AxesStandaloneBackend",
        "django.contrib.auth.backends.ModelBackend",
    ],
)
class LoginIpCapTests(TestCase):
    """The axes lockout is per (email, address), so one address trying one
    password against many emails never trips it. A looser per-address cap
    (LOGIN_IP_FAILURE_LIMIT per AXES_COOLOFF_TIME) stops that spray without
    letting one mistyped password lock a shared connection out."""

    IP = "203.0.113.5"

    def setUp(self) -> None:
        cache.clear()
        make_staff(email="staffer@example.com", password="pw12345")

    def attempt(self, email: str, password: str, ip: str = IP):
        return self.client.post(
            "/login", {"username": email, "password": password}, REMOTE_ADDR=ip
        )

    def spray(self, count: int, ip: str = IP) -> None:
        for i in range(count):
            resp = self.attempt(f"member{i}@example.com", "Winter2026!", ip)
            self.assertEqual(resp.status_code, 200)

    def test_spraying_many_emails_from_one_address_locks_that_address(self) -> None:
        self.spray(settings.LOGIN_IP_FAILURE_LIMIT)
        resp = self.attempt("staffer@example.com", "pw12345")
        self.assertEqual(resp.status_code, 429)
        html = resp.content.decode()
        self.assertIn("Too many sign-in attempts", html)
        self.assertNotIn("staffer@example.com", html)

    def test_under_the_cap_the_right_password_still_works(self) -> None:
        self.spray(settings.LOGIN_IP_FAILURE_LIMIT - 1)
        self.assertEqual(
            self.attempt("staffer@example.com", "pw12345").status_code, 302
        )

    def test_other_addresses_are_unaffected(self) -> None:
        self.spray(settings.LOGIN_IP_FAILURE_LIMIT)
        resp = self.attempt("staffer@example.com", "pw12345", ip="203.0.113.6")
        self.assertEqual(resp.status_code, 302)

    def test_the_cap_lifts_after_the_cooloff(self) -> None:
        import time
        from unittest import mock

        self.spray(settings.LOGIN_IP_FAILURE_LIMIT)
        later = time.time() + settings.AXES_COOLOFF_TIME.total_seconds() + 1
        with mock.patch("time.time", return_value=later):
            resp = self.attempt("staffer@example.com", "pw12345")
        self.assertEqual(resp.status_code, 302)

    def test_no_address_means_no_cap(self) -> None:
        # gunicorn behind nginx without X-Real-IP: nothing to count against.
        self.spray(settings.LOGIN_IP_FAILURE_LIMIT, ip="")
        self.assertEqual(
            self.attempt("staffer@example.com", "pw12345", ip="").status_code, 302
        )

    def test_get_is_never_blocked(self) -> None:
        self.spray(settings.LOGIN_IP_FAILURE_LIMIT)
        self.assertEqual(
            self.client.get("/login", REMOTE_ADDR=self.IP).status_code, 200
        )


class SessionLengthTests(TestCase):
    def setUp(self) -> None:
        cache.clear()

    def test_signing_in_sets_a_twelve_hour_session_cookie(self) -> None:
        make_staff(email="staffer@example.com", password="pw12345")
        resp = self.client.post(
            "/login", {"username": "staffer@example.com", "password": "pw12345"}
        )
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(int(resp.cookies["sessionid"]["max-age"]), 12 * 60 * 60)
