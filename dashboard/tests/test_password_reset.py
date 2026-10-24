import re
from datetime import datetime, timedelta
from unittest import mock

from axes.models import AccessAttempt
from django.conf import settings
from django.core import mail
from django.core.cache import cache
from django.test import TestCase, override_settings

from dashboard.tests.helpers import make_staff

NEW_PASSWORD = {
    "new_password1": "popcorn-balcony-42",
    "new_password2": "popcorn-balcony-42",
}

# What reset links read the time from, so a test can step past their expiry.
TOKEN_CLOCK = "django.contrib.auth.tokens.PasswordResetTokenGenerator._now"


class PasswordResetTests(TestCase):
    """A staff member who has forgotten their password asks for a link by
    email from the login screen, follows it, and chooses a new one."""

    def setUp(self) -> None:
        cache.clear()
        self.staff = make_staff(email="staffer@example.com", password="pw12345")

    def request_link(self, email: str = "staffer@example.com"):
        return self.client.post("/password-reset", {"email": email})

    def link_in(self, message) -> str:
        match = re.search(r"http://testserver(/password-reset/\S+)", message.body)
        self.assertIsNotNone(match, message.body)
        return match.group(1)

    def test_login_page_links_to_reset(self) -> None:
        self.assertContains(self.client.get("/login"), 'href="/password-reset"')

    def test_reset_page_asks_for_email_on_the_login_card(self) -> None:
        resp = self.client.get("/password-reset")
        self.assertEqual(resp.status_code, 200)
        html = resp.content.decode()
        self.assertIn('type="email"', html)
        self.assertIn("login.css", html)
        self.assertIn("fkc-logo-black.png", html)
        self.assertIn("noindex", html)

    def test_known_email_gets_a_link(self) -> None:
        resp = self.request_link(" Staffer@Example.COM ")
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp["Location"], "/password-reset/sent")
        self.assertEqual(len(mail.outbox), 1)
        message = mail.outbox[0]
        self.assertEqual(message.to, ["staffer@example.com"])
        self.assertEqual(message.subject, "Reset your LeprinceOS password")
        self.assertIn("5 minutes", message.body)
        self.link_in(message)

    def test_unknown_email_looks_the_same_but_sends_nothing(self) -> None:
        resp = self.request_link("nobody@example.com")
        self.assertEqual(resp["Location"], "/password-reset/sent")
        self.assertEqual(mail.outbox, [])

    def test_honeypot_gets_the_same_reply_and_sends_nothing(self) -> None:
        resp = self.client.post(
            "/password-reset",
            {"email": "staffer@example.com", "website": "http://spam.example"},
        )
        self.assertEqual(resp["Location"], "/password-reset/sent")
        self.assertEqual(mail.outbox, [])

    def test_reset_page_carries_the_honeypot(self) -> None:
        html = self.client.get("/password-reset").content.decode()
        self.assertIn('name="website"', html)
        self.assertIn('aria-hidden="true"', html)

    def test_sent_page_does_not_say_whether_the_account_exists(self) -> None:
        self.assertContains(
            self.client.get("/password-reset/sent"), "If that email has an account"
        )

    def test_second_request_within_five_minutes_sends_nothing(self) -> None:
        self.request_link()
        resp = self.request_link("STAFFER@example.com")
        self.assertEqual(resp["Location"], "/password-reset/sent")
        self.assertEqual(len(mail.outbox), 1)

    def test_request_after_the_wait_sends_again(self) -> None:
        self.request_link()
        cache.clear()  # the five-minute entry has expired
        self.request_link()
        self.assertEqual(len(mail.outbox), 2)

    def test_following_the_link_sets_a_new_password(self) -> None:
        self.request_link()
        resp = self.client.get(self.link_in(mail.outbox[0]), follow=True)
        self.assertContains(resp, "New password")
        resp = self.client.post(
            resp.redirect_chain[-1][0],
            NEW_PASSWORD,
        )
        self.assertEqual(resp["Location"], "/password-reset/done")
        self.assertContains(self.client.get("/password-reset/done"), "Password changed")
        self.assertTrue(
            self.client.login(
                username="staffer@example.com", password="popcorn-balcony-42"
            )
        )

    def test_weak_password_is_refused(self) -> None:
        self.request_link()
        resp = self.client.get(self.link_in(mail.outbox[0]), follow=True)
        resp = self.client.post(
            resp.redirect_chain[-1][0],
            {"new_password1": "12345678", "new_password2": "12345678"},
        )
        self.assertEqual(resp.status_code, 200)
        self.staff.refresh_from_db()
        self.assertTrue(self.staff.check_password("pw12345"))

    def test_link_works_only_once(self) -> None:
        self.request_link()
        link = self.link_in(mail.outbox[0])
        resp = self.client.get(link, follow=True)
        self.client.post(
            resp.redirect_chain[-1][0],
            NEW_PASSWORD,
        )
        resp = self.client.get(link, follow=True)
        self.assertContains(resp, "This link has expired")
        self.assertContains(resp, 'href="/password-reset"')

    def test_link_expires_after_five_minutes(self) -> None:
        self.request_link()
        link = self.link_in(mail.outbox[0])
        later = datetime.now() + timedelta(minutes=5, seconds=1)
        with mock.patch(TOKEN_CLOCK, return_value=later):
            resp = self.client.get(link, follow=True)
        self.assertContains(resp, "This link has expired")

    def test_link_still_works_just_inside_five_minutes(self) -> None:
        self.request_link()
        link = self.link_in(mail.outbox[0])
        later = datetime.now() + timedelta(minutes=4, seconds=55)
        with mock.patch(TOKEN_CLOCK, return_value=later):
            resp = self.client.get(link, follow=True)
        self.assertContains(resp, "New password")


@override_settings(
    AXES_ENABLED=True,
    AUTHENTICATION_BACKENDS=[
        "axes.backends.AxesStandaloneBackend",
        "django.contrib.auth.backends.ModelBackend",
    ],
)
class PasswordResetLockoutTests(TestCase):
    """Someone who locked themselves out, then reset their password, can
    sign in straight away with the new one instead of waiting it out."""

    def setUp(self) -> None:
        cache.clear()
        make_staff(email="staffer@example.com", password="pw12345")

    def test_reset_clears_the_sign_in_lockout(self) -> None:
        for _ in range(settings.AXES_FAILURE_LIMIT):
            self.client.post(
                "/login", {"username": "Staffer@example.com", "password": "nope"}
            )
        self.assertTrue(AccessAttempt.objects.exists())

        self.client.post("/password-reset", {"email": "staffer@example.com"})
        link = re.search(
            r"http://testserver(/password-reset/\S+)", mail.outbox[0].body
        ).group(1)
        resp = self.client.get(link, follow=True)
        self.client.post(
            resp.redirect_chain[-1][0],
            NEW_PASSWORD,
        )

        self.assertFalse(AccessAttempt.objects.exists())
        resp = self.client.post(
            "/login",
            {"username": "staffer@example.com", "password": "popcorn-balcony-42"},
        )
        self.assertEqual((resp.status_code, resp["Location"]), (302, "/dashboard/"))
