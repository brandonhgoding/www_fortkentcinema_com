import time
from unittest import mock

from django.contrib.auth import get_user_model
from django.test import TestCase

from accounts.tests.factories import make_user
from accounts.verification import make_token


class VerifyEmailTests(TestCase):
    def setUp(self):
        self.user = make_user("ann@example.com", "pw-1-long-enough", is_staff=False)
        self.url = "/register/verify/" + make_token(self.user)

    def refreshed(self):
        return get_user_model().objects.get(pk=self.user.pk)

    def test_get_changes_nothing(self):
        response = self.client.get(self.url)
        self.assertContains(response, "Confirm your email, ann@example.com")
        self.assertContains(response, "Confirm my email")
        self.assertIsNone(self.refreshed().email_verified_at)

    def test_post_verifies_and_does_not_sign_in(self):
        response = self.client.post(self.url)
        self.assertContains(response, "Email confirmed. You can sign in now.")
        self.assertIsNotNone(self.refreshed().email_verified_at)
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_second_post_and_bad_tokens_410(self):
        self.assertEqual(self.client.post(self.url).status_code, 200)
        response = self.client.post(self.url)
        self.assertContains(
            response,
            "This confirmation link has expired or was already used.",
            status_code=410,
        )
        self.assertEqual(self.client.get(self.url).status_code, 410)
        for bad in (self.url + "x", "/register/verify/garbage"):
            self.assertEqual(self.client.get(bad).status_code, 410)
            self.assertEqual(self.client.post(bad).status_code, 410)

    def test_expired_410(self):
        with mock.patch("time.time", return_value=time.time() + 86401):
            self.assertEqual(self.client.get(self.url).status_code, 410)
            self.assertEqual(self.client.post(self.url).status_code, 410)
        self.assertIsNone(self.refreshed().email_verified_at)

    def test_never_cache_headers(self):
        self.assertIn("no-cache", self.client.get(self.url)["Cache-Control"])
        self.assertIn("no-cache", self.client.post(self.url)["Cache-Control"])

    def test_button_disables_on_submit(self):
        self.assertContains(self.client.get(self.url), "onsubmit")
