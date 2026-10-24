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


class VerifyEmailTests(TestCase):
    def setUp(self):
        self.user = make_user("ann@example.com", PW, is_staff=False)
        self.url = "/register/verify/" + make_token(self.user)

    def refreshed(self):
        return get_user_model().objects.get(pk=self.user.pk)

    def test_opening_the_link_verifies_and_does_not_sign_in(self):
        response = self.client.get(self.url)
        self.assertContains(response, DONE)
        self.assertContains(response, 'href="/login"')
        self.assertIsNotNone(self.refreshed().email_verified_at)
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_no_password_asked(self):
        self.assertNotContains(self.client.get(self.url), 'type="password"')

    def test_second_click_still_says_verified(self):
        self.client.get(self.url)
        first = self.refreshed().email_verified_at
        response = self.client.get(self.url)
        self.assertContains(response, DONE)
        self.assertEqual(self.refreshed().email_verified_at, first)

    def test_bad_tokens_410(self):
        for bad in (self.url + "x", "/register/verify/garbage"):
            self.assertContains(self.client.get(bad), EXPIRED, status_code=410)
        self.assertIsNone(self.refreshed().email_verified_at)

    def test_expired_410(self):
        with mock.patch("time.time", return_value=time.time() + 86401):
            self.assertEqual(self.client.get(self.url).status_code, 410)
        self.assertIsNone(self.refreshed().email_verified_at)

    def test_post_not_allowed(self):
        self.assertEqual(self.client.post(self.url).status_code, 405)
        self.assertIsNone(self.refreshed().email_verified_at)

    def test_never_cache_headers(self):
        self.assertIn("no-cache", self.client.get(self.url)["Cache-Control"])

    def test_reregistering_kills_older_links(self):
        # Someone re-registering this address with their own password must
        # not have it verified by the owner clicking the link they had.
        cache.clear()
        register = {"email": "owner@example.com"}
        p1, p2 = "Owner-passphrase-11", "Attacker-passphrase-22"
        self.client.post("/register", {**register, "password1": p1, "password2": p1})
        owner = get_user_model().objects.get(email="owner@example.com")
        old_link = "/register/verify/" + make_token(owner)
        cache.clear()  # the five-minute throttle passes
        self.client.post("/register", {**register, "password1": p2, "password2": p2})
        self.assertEqual(self.client.get(old_link).status_code, 410)
        owner.refresh_from_db()
        self.assertIsNone(owner.email_verified_at)
