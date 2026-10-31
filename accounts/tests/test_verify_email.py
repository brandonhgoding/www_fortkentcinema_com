import time
from unittest import mock

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase

from accounts.tests.factories import make_user
from accounts.verification import make_token

PW = "pw-1-long-enough"
DONE = "Your email is verified. Please sign in."
EXPIRED = "This confirmation link has expired or was already used."
WRONG = (
    "That password doesn't match this account. If you've forgotten it, "
    "create the account again with the same email to choose a new password, "
    "then use the newest link."
)


class VerifyEmailTests(TestCase):
    def setUp(self):
        cache.clear()
        self.user = make_user("ann@example.com", PW, is_staff=False)
        self.url = "/register/verify/" + make_token(self.user)

    def refreshed(self):
        return get_user_model().objects.get(pk=self.user.pk)

    def test_opening_the_link_asks_for_the_password_and_changes_nothing(self):
        # A mail scanner or link preview fetching the URL verifies nothing.
        response = self.client.get(self.url)
        self.assertContains(response, "Confirm your email, ann@example.com")
        self.assertContains(response, 'type="password"')
        self.assertContains(response, 'autocomplete="current-password"')
        self.assertContains(
            response, "Enter the password you chose when you created the account."
        )
        self.assertContains(response, "Confirm my email")
        self.assertIsNone(self.refreshed().email_verified_at)

    def test_right_password_verifies_and_does_not_sign_in(self):
        response = self.client.post(self.url, {"password": PW})
        self.assertContains(response, DONE)
        self.assertContains(response, 'href="/login"')
        self.assertIsNotNone(self.refreshed().email_verified_at)
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_wrong_or_missing_password_does_not_verify_and_link_stays_usable(self):
        for data in ({}, {"password": "wrong"}):
            response = self.client.post(self.url, data)
            self.assertContains(response, WRONG)
            self.assertContains(response, "Confirm my email")
            self.assertIsNone(self.refreshed().email_verified_at)
        self.assertEqual(self.client.get(self.url).status_code, 200)
        self.client.post(self.url, {"password": PW})
        self.assertIsNotNone(self.refreshed().email_verified_at)

    def test_already_verified_says_so_without_asking(self):
        # A second visit (or the owner opening a link after confirming on
        # another device) sees the verified page, not another password form.
        self.client.post(self.url, {"password": PW})
        first = self.refreshed().email_verified_at
        for response in (self.client.get(self.url), self.client.post(self.url)):
            self.assertContains(response, DONE)
            self.assertNotContains(response, 'type="password"')
        self.assertEqual(self.refreshed().email_verified_at, first)

    def test_bad_tokens_410(self):
        for bad in (self.url + "x", "/register/verify/garbage"):
            self.assertContains(self.client.get(bad), EXPIRED, status_code=410)
            response = self.client.post(bad, {"password": PW})
            self.assertContains(response, EXPIRED, status_code=410)
        self.assertIsNone(self.refreshed().email_verified_at)

    def test_expired_410(self):
        with mock.patch("time.time", return_value=time.time() + 86401):
            self.assertEqual(self.client.get(self.url).status_code, 410)
            response = self.client.post(self.url, {"password": PW})
            self.assertEqual(response.status_code, 410)
        self.assertIsNone(self.refreshed().email_verified_at)

    def test_never_cache_headers(self):
        self.assertIn("no-cache", self.client.get(self.url)["Cache-Control"])
        response = self.client.post(self.url, {"password": "wrong"})
        self.assertIn("no-cache", response["Cache-Control"])
        response = self.client.post(self.url, {"password": PW})
        self.assertIn("no-cache", response["Cache-Control"])

    def test_button_disables_on_submit(self):
        self.assertContains(self.client.get(self.url), "onsubmit")

    def test_five_wrong_passwords_kill_the_link_for_the_cooloff(self):
        # The link names the account, so guessing here must stop where the
        # sign-in lockout does (AXES_FAILURE_LIMIT per AXES_COOLOFF_TIME).
        for _ in range(5):
            self.assertEqual(
                self.client.post(self.url, {"password": "wrong"}).status_code, 200
            )
        self.assertContains(self.client.get(self.url), EXPIRED, status_code=410)
        response = self.client.post(self.url, {"password": PW})
        self.assertContains(response, EXPIRED, status_code=410)
        self.assertIsNone(self.refreshed().email_verified_at)
        with mock.patch("time.time", return_value=time.time() + 15 * 60 + 1):
            self.assertEqual(self.client.get(self.url).status_code, 200)
            self.client.post(self.url, {"password": PW})
        self.assertIsNotNone(self.refreshed().email_verified_at)

    def test_reregistering_after_wrong_passwords_gives_a_usable_link(self):
        # The wrong-password page says to create the account again with the
        # same email and use the newest link; that link must work at once,
        # since a new password leaves nothing of the old one to guess.
        for _ in range(5):
            self.client.post(self.url, {"password": "wrong"})
        new_pw = "Fresh-passphrase-33"
        self.client.post(
            "/register",
            {"email": "ann@example.com", "password1": new_pw, "password2": new_pw},
        )
        new_url = "/register/verify/" + make_token(self.refreshed())
        self.assertEqual(self.client.get(new_url).status_code, 200)
        self.assertContains(self.client.post(new_url, {"password": new_pw}), DONE)
        self.assertIsNotNone(self.refreshed().email_verified_at)

    def test_failures_count_per_account(self):
        other = make_user("bob@example.com", PW, is_staff=False)
        other_url = "/register/verify/" + make_token(other)
        for _ in range(5):
            self.client.post(self.url, {"password": "wrong"})
        self.assertEqual(self.client.get(other_url).status_code, 200)

    def test_reregistering_kills_older_links(self):
        # Someone re-registering this address with their own password must
        # not have it verified by the owner clicking the link they had.
        register = {"email": "owner@example.com"}
        p1, p2 = "Owner-passphrase-11", "Attacker-passphrase-22"
        self.client.post("/register", {**register, "password1": p1, "password2": p1})
        owner = get_user_model().objects.get(email="owner@example.com")
        old_link = "/register/verify/" + make_token(owner)
        cache.clear()  # the five-minute throttle passes
        self.client.post("/register", {**register, "password1": p2, "password2": p2})
        self.assertEqual(self.client.get(old_link).status_code, 410)
        self.assertEqual(self.client.post(old_link, {"password": p1}).status_code, 410)
        owner.refresh_from_db()
        self.assertIsNone(owner.email_verified_at)

    def test_attacker_reregistration_cannot_be_confirmed_by_the_owner(self):
        # The newest link carries the attacker's password; the owner, who
        # knows only their own, cannot confirm it. Registering again with
        # their own password puts a link they can confirm back in their inbox.
        register = {"email": "owner@example.com"}
        p1, p2 = "Owner-passphrase-11", "Attacker-passphrase-22"
        self.client.post("/register", {**register, "password1": p1, "password2": p1})
        owner = get_user_model().objects.get(email="owner@example.com")
        cache.clear()
        self.client.post("/register", {**register, "password1": p2, "password2": p2})
        owner.refresh_from_db()
        newest = "/register/verify/" + make_token(owner)
        response = self.client.post(newest, {"password": p1})
        self.assertContains(response, WRONG)
        owner.refresh_from_db()
        self.assertIsNone(owner.email_verified_at)
        cache.clear()
        self.client.post("/register", {**register, "password1": p1, "password2": p1})
        owner.refresh_from_db()
        self.client.post("/register/verify/" + make_token(owner), {"password": p1})
        owner.refresh_from_db()
        self.assertIsNotNone(owner.email_verified_at)

    def test_attacker_cannot_be_verified_by_a_curious_click(self):
        # The owner of an address someone else registered opens the email
        # and clicks. Without the attacker's password nothing is verified.
        self.assertEqual(self.client.get(self.url).status_code, 200)
        self.client.post(self.url, {"password": "not-the-registrants"})
        self.assertIsNone(self.refreshed().email_verified_at)
