from datetime import datetime, timezone as dt_timezone
from unittest import mock

from django.contrib.auth import get_user_model
from django.core import mail
from django.core.cache import cache
from django.test import TestCase

from accounts.tests.factories import make_user
from dashboard.tests.helpers import make_staff

URL = "/login/link"


class LoginPageTests(TestCase):
    def test_login_page_leads_with_link_form(self):
        html = self.client.get("/login").content.decode()
        link = html.index("Email me a sign-in link")
        toggle = html.index("Staff: sign in with password")
        self.assertLess(link, toggle)
        details = html.index("<details")
        self.assertLess(details, html.index('name="password"'))
        self.assertLess(link, details)

    def test_password_errors_open_the_staff_toggle(self):
        make_staff(email="staffer@example.com", password="pw12345")
        resp = self.client.post(
            "/login", {"username": "staffer@example.com", "password": "no"}
        )
        html = resp.content.decode()
        details = html[html.index("<details") :]
        self.assertRegex(details[: details.index(">")], r"\bopen\b")

    def test_closed_toggle_by_default(self):
        html = self.client.get("/login").content.decode()
        details = html[html.index("<details") :]
        self.assertNotRegex(details[: details.index(">")], r"\bopen\b")


class MagicLinkRequestTests(TestCase):
    def setUp(self):
        cache.clear()

    def test_unknown_address_gets_link(self):
        resp = self.client.post(URL, {"email": "New@Example.com"})
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Check your email")
        self.assertContains(resp, "new@example.com")
        self.assertContains(resp, "expires in 5 minutes")
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, ["new@example.com"])
        self.assertFalse(get_user_model().objects.filter(email="new@example.com"))

    def test_member_gets_link_staff_and_inactive_do_not(self):
        make_user("member@example.com", is_staff=False)
        make_staff(email="staffer@example.com")
        make_user("gone@example.com", is_staff=False, is_active=False)
        for n, (email, mails) in enumerate(
            [
                ("member@example.com", 1),
                ("staffer@example.com", 0),
                ("gone@example.com", 0),
            ]
        ):
            mail.outbox.clear()
            resp = self.client.post(
                URL, {"email": email}, REMOTE_ADDR=f"203.0.113.{n + 1}"
            )
            self.assertContains(resp, "Check your email")
            self.assertEqual(len(mail.outbox), mails, email)

    def test_honeypot(self):
        resp = self.client.post(URL, {"email": "bot@example.com", "website": "x"})
        self.assertContains(resp, "Check your email")
        self.assertEqual(len(mail.outbox), 0)

    def test_invalid_email_redisplays(self):
        resp = self.client.post(URL, {"email": "nope"})
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Enter a valid email address.")
        self.assertContains(resp, "Email me a sign-in link")
        self.assertContains(resp, "Staff: sign in with password")
        self.assertEqual(len(mail.outbox), 0)

    def test_second_request_within_five_minutes_says_so(self):
        # 14:00 UTC is 10:00 AM in New York (EDT); the retry is 5 minutes on.
        now = datetime(2026, 10, 24, 14, 0, tzinfo=dt_timezone.utc)
        with mock.patch("accounts.magic_link.timezone.now", return_value=now):
            self.client.post(URL, {"email": "ghost@example.com"})
            resp = self.client.post(URL, {"email": "ghost@example.com"})
        self.assertEqual(len(mail.outbox), 1)
        self.assertContains(
            resp,
            "We sent a sign-in link to this address in the last 5 minutes. "
            "Check your inbox (and spam), or try again after 10:05 AM.",
        )

    def test_ip_cap_after_five(self):
        for n in range(5):
            resp = self.client.post(
                URL, {"email": f"a{n}@example.com"}, REMOTE_ADDR="203.0.113.9"
            )
            self.assertEqual(resp.status_code, 200)
        resp = self.client.post(
            URL, {"email": "a5@example.com"}, REMOTE_ADDR="203.0.113.9"
        )
        self.assertEqual(resp.status_code, 429)
        self.assertContains(
            resp,
            "Too many sign-in requests from this connection. Try again later.",
            status_code=429,
        )
        self.assertEqual(len(mail.outbox), 5)

    def test_forged_forwarded_header_does_not_dodge_cap(self):
        for n in range(6):
            resp = self.client.post(
                URL,
                {"email": f"b{n}@example.com"},
                REMOTE_ADDR="203.0.113.10",
                HTTP_X_FORWARDED_FOR=f"198.51.100.{n}",
            )
        self.assertEqual(resp.status_code, 429)

    def test_next_is_ignored_by_link_flow(self):
        self.client.post(URL + "?next=/dashboard/members", {"email": "n@example.com"})
        self.assertEqual(len(mail.outbox), 1)
        self.assertNotIn("next", mail.outbox[0].body)

    def test_get_not_allowed(self):
        self.assertEqual(self.client.get(URL).status_code, 405)
