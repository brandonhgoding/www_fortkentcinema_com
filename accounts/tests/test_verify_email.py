import time
from unittest import mock

from django.contrib.auth import get_user_model
from django.test import TestCase

from accounts.tests.factories import make_user
from accounts.verification import make_token

PW = "pw-1-long-enough"
ERROR = (
    "That password doesn't match this account. If you've forgotten it, "
    "create the account again with the same email to choose a new password, "
    "then use the newest link."
)


class VerifyEmailTests(TestCase):
    def setUp(self):
        self.user = make_user("ann@example.com", PW, is_staff=False)
        self.url = "/register/verify/" + make_token(self.user)

    def refreshed(self):
        return get_user_model().objects.get(pk=self.user.pk)

    def test_get_changes_nothing(self):
        response = self.client.get(self.url)
        self.assertContains(response, "Confirm your email, ann@example.com")
        self.assertContains(response, "Confirm my email")
        self.assertIsNone(self.refreshed().email_verified_at)

    def test_post_verifies_and_does_not_sign_in(self):
        response = self.client.post(self.url, {"password": PW})
        self.assertContains(response, "Email confirmed. You can sign in now.")
        self.assertIsNotNone(self.refreshed().email_verified_at)
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_second_post_and_bad_tokens_410(self):
        self.assertEqual(self.client.post(self.url, {"password": PW}).status_code, 200)
        response = self.client.post(self.url, {"password": PW})
        self.assertContains(
            response,
            "This confirmation link has expired or was already used.",
            status_code=410,
        )
        self.assertEqual(self.client.get(self.url).status_code, 410)
        for bad in (self.url + "x", "/register/verify/garbage"):
            self.assertEqual(self.client.get(bad).status_code, 410)
            self.assertEqual(self.client.post(bad, {"password": PW}).status_code, 410)

    def test_expired_410(self):
        with mock.patch("time.time", return_value=time.time() + 86401):
            self.assertEqual(self.client.get(self.url).status_code, 410)
            response = self.client.post(self.url, {"password": PW})
            self.assertEqual(response.status_code, 410)
        self.assertIsNone(self.refreshed().email_verified_at)

    def test_never_cache_headers(self):
        self.assertIn("no-cache", self.client.get(self.url)["Cache-Control"])
        response = self.client.post(self.url, {"password": PW})
        self.assertIn("no-cache", response["Cache-Control"])

    def test_button_disables_on_submit(self):
        self.assertContains(self.client.get(self.url), "onsubmit")

    def test_post_without_or_with_wrong_password_does_not_verify(self):
        for data in ({}, {"password": "wrong"}):
            response = self.client.post(self.url, data)
            self.assertContains(response, ERROR)
            self.assertContains(response, "Confirm my email")
            self.assertIn("no-cache", response["Cache-Control"])
            self.assertIsNone(self.refreshed().email_verified_at)
        self.assertEqual(self.client.get(self.url).status_code, 200)
        self.client.post(self.url, {"password": PW})
        self.assertIsNotNone(self.refreshed().email_verified_at)

    def test_post_with_right_password_verifies(self):
        response = self.client.post(self.url, {"password": PW})
        self.assertContains(response, "Email confirmed. You can sign in now.")
        self.assertIsNotNone(self.refreshed().email_verified_at)

    def test_confirm_page_asks_for_password(self):
        response = self.client.get(self.url)
        self.assertContains(response, 'autocomplete="current-password"')
        self.assertContains(
            response, "Enter the password you chose when you created the account."
        )

    def test_attacker_reregistration_cannot_be_confirmed_by_owner(self):
        from django.core.cache import cache

        cache.clear()
        register = {"email": "owner@example.com"}
        p1, p2 = "Owner-passphrase-11", "Attacker-passphrase-22"
        self.client.post(
            "/register", {**register, "password1": p1, "password2": p1}
        )
        owner = get_user_model().objects.get(email="owner@example.com")
        old_link = "/register/verify/" + make_token(owner)
        cache.clear()  # the five-minute throttle passes
        self.client.post(
            "/register", {**register, "password1": p2, "password2": p2}
        )
        response = self.client.post(old_link, {"password": p1})
        self.assertContains(response, ERROR)
        owner.refresh_from_db()
        self.assertIsNone(owner.email_verified_at)
        cache.clear()
        self.client.post(
            "/register", {**register, "password1": p1, "password2": p1}
        )
        self.client.post(old_link, {"password": p1})
        owner.refresh_from_db()
        self.assertIsNotNone(owner.email_verified_at)
