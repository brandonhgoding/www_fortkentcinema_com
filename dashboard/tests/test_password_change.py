import re

from django.contrib.auth import get_user_model
from django.test import Client, TestCase

from accounts.tests.factories import make_user
from dashboard.tests.helpers import make_staff

User = get_user_model()

URL = "/password-change"
OLD = "pw12345"
NEW = "popcorn-balcony-42"


def change(old=OLD, new1=NEW, new2=NEW):
    return {"old_password": old, "new_password1": new1, "new_password2": new2}


class PasswordChangeTests(TestCase):
    """A signed-in user, staff or member, picks a new password from the
    dashboard by proving the current one."""

    def setUp(self) -> None:
        self.user = make_staff(email="staffer@example.com", password=OLD)
        self.client.force_login(self.user)

    def fresh_hash(self) -> str:
        return User.objects.get(pk=self.user.pk).password

    def test_anonymous_is_sent_to_login(self) -> None:
        resp = Client().get(URL)
        self.assertEqual(resp.status_code, 302)
        self.assertTrue(resp["Location"].startswith("/login?next="))

    def test_page_shows_the_form_inside_the_dashboard(self) -> None:
        resp = self.client.get(URL)
        self.assertEqual(resp.status_code, 200)
        html = resp.content.decode()
        self.assertIn('name="old_password"', html)
        self.assertIn('name="new_password1"', html)
        self.assertIn('name="new_password2"', html)
        self.assertIn("sidebar.css", html)
        self.assertIn('href="/password-reset"', html)

    def test_inputs_carry_the_dashboard_input_class(self) -> None:
        html = self.client.get(URL).content.decode()
        for name in ("old_password", "new_password1", "new_password2"):
            with self.subTest(name=name):
                tag = re.search(rf'<input[^>]*name="{name}"[^>]*>', html).group(0)
                self.assertIn('class="input"', tag)

    def test_wrong_current_password_is_rejected(self) -> None:
        before = self.fresh_hash()
        resp = self.client.post(URL, change(old="not-it"))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "incorrectly")
        self.assertEqual(self.fresh_hash(), before)

    def test_weak_new_password_is_rejected(self) -> None:
        before = self.fresh_hash()
        resp = self.client.post(URL, change(new1="short", new2="short"))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "too short")
        self.assertEqual(self.fresh_hash(), before)

    def test_mismatched_confirmation_is_rejected(self) -> None:
        resp = self.client.post(URL, change(new2=NEW + "x"))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "didn’t match")

    def test_success_sets_the_new_password_and_redirects_with_a_toast(self) -> None:
        resp = self.client.post(URL, change())
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp["Location"], "/dashboard/")
        self.assertTrue(User.objects.get(pk=self.user.pk).check_password(NEW))
        home = self.client.get("/dashboard/")
        self.assertContains(home, "Password changed")

    def test_success_keeps_this_session_signed_in(self) -> None:
        self.client.post(URL, change())
        self.assertEqual(self.client.get("/dashboard/").status_code, 200)

    def test_success_signs_out_other_sessions(self) -> None:
        other = Client()
        other.force_login(self.user)
        self.assertEqual(other.get("/dashboard/").status_code, 200)
        self.client.post(URL, change())
        resp = other.get("/dashboard/")
        self.assertEqual(resp.status_code, 302)
        self.assertTrue(resp["Location"].startswith("/login"))

    def test_sidebar_links_to_the_page(self) -> None:
        self.assertContains(self.client.get("/dashboard/"), f'href="{URL}"')


class MemberPasswordChangeTests(TestCase):
    """Non-staff members use the same page from their membership home."""

    def setUp(self) -> None:
        self.user = make_user(email="member@example.com", password=OLD)
        self.client.force_login(self.user)

    def test_member_can_change_password(self) -> None:
        resp = self.client.post(URL, change())
        self.assertEqual(resp.status_code, 302)
        self.assertTrue(User.objects.get(pk=self.user.pk).check_password(NEW))

    def test_member_home_sidebar_links_to_the_page(self) -> None:
        self.assertContains(self.client.get("/dashboard/"), f'href="{URL}"')
