from unittest import mock

from django.contrib.auth import get_user_model
from django.db import IntegrityError
from django.test import TestCase

from accounts.magic_link import make_token, normalise
from accounts.tests.factories import make_user
from dashboard.tests.helpers import make_staff

EXPIRED = "This sign-in link has expired or was already used."


def link(email="ann@example.com"):
    return "/login/link/" + make_token(normalise(email))


class MagicLinkSignInTests(TestCase):
    def test_get_shows_button_and_changes_nothing(self):
        resp = self.client.get(link())
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Sign in as ann@example.com")
        self.assertEqual(get_user_model().objects.count(), 0)
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_post_creates_member_and_signs_in(self):
        resp = self.client.post(link())
        self.assertRedirects(resp, "/dashboard/", fetch_redirect_response=False)
        user = get_user_model().objects.get(email="ann@example.com")
        self.assertFalse(user.is_staff)
        self.assertFalse(user.has_usable_password())
        self.assertIsNotNone(user.last_login)
        self.assertEqual(self.client.session["_auth_user_id"], str(user.pk))

    def test_existing_member_signs_in_without_duplicate(self):
        member = make_user("ann@example.com")
        resp = self.client.post(link())
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(get_user_model().objects.count(), 1)
        self.assertEqual(self.client.session["_auth_user_id"], str(member.pk))

    def test_second_post_is_expired(self):
        url = link()
        self.client.post(url)
        self.client.logout()
        resp = self.client.post(url)
        self.assertContains(resp, EXPIRED, status_code=410)
        self.assertEqual(get_user_model().objects.count(), 1)

    def test_expired_and_tampered_show_expired_page_with_form(self):
        for url in (link() + "x", "/login/link/garbage"):
            for method in (self.client.get, self.client.post):
                resp = method(url)
                self.assertContains(resp, EXPIRED, status_code=410)
                self.assertContains(resp, "Email me a sign-in link", status_code=410)
        self.assertEqual(get_user_model().objects.count(), 0)

    def test_mixed_case_link_matches_existing_account(self):
        member = make_user("ann@example.com")
        self.client.post("/login/link/" + make_token(normalise(" Ann@Example.com ")))
        self.assertEqual(get_user_model().objects.count(), 1)
        self.assertEqual(self.client.session["_auth_user_id"], str(member.pk))

    def test_signed_in_staff_opening_member_link_stays_staff(self):
        staff = make_staff(email="staffer@example.com", password="pw12345")
        self.client.force_login(staff)
        url = link()
        for method in (self.client.get, self.client.post):
            resp = method(url)
            self.assertRedirects(resp, "/dashboard/", fetch_redirect_response=False)
        self.assertEqual(self.client.session["_auth_user_id"], str(staff.pk))
        self.assertFalse(get_user_model().objects.filter(email="ann@example.com"))

    def test_integrity_error_on_create_shows_expired(self):
        with mock.patch.object(
            get_user_model().objects, "create_user", side_effect=IntegrityError
        ):
            resp = self.client.post(link())
        self.assertContains(resp, EXPIRED, status_code=410)
        self.assertNotIn("_auth_user_id", self.client.session)
