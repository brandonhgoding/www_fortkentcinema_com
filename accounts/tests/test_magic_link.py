import time
from unittest import mock

from django.core import mail
from django.core.cache import cache
from django.core.mail import EmailMessage
from django.test import RequestFactory, TestCase
from django.utils import timezone

from accounts import magic_link
from accounts.tests.factories import make_user
from dashboard.tests.helpers import make_staff


class MagicLinkTokenTests(TestCase):
    def setUp(self):
        cache.clear()

    def test_round_trip_for_new_address(self):
        token = magic_link.make_token("ann@example.com")
        self.assertEqual(magic_link.read_token(token), "ann@example.com")

    def test_expires_after_five_minutes(self):
        token = magic_link.make_token("ann@example.com")
        with mock.patch("time.time", return_value=time.time() + 301):
            self.assertIsNone(magic_link.read_token(token))

    def test_spent_once_account_signs_in(self):
        user = make_user("ann@example.com", is_staff=False)
        token = magic_link.make_token("ann@example.com")
        user.last_login = timezone.now()
        user.save()
        self.assertIsNone(magic_link.read_token(token))

    def test_spent_once_account_created(self):
        token = magic_link.make_token("ann@example.com")
        make_user("ann@example.com", is_staff=False, last_login=timezone.now())
        self.assertIsNone(magic_link.read_token(token))

    def test_tampered_token(self):
        token = magic_link.make_token("a@example.com")
        self.assertIsNone(magic_link.read_token(token + "x"))

    def test_staff_and_inactive_refused(self):
        staff = make_staff(email="boss@example.com", password="pw12345")
        gone = make_user("gone@example.com", is_active=False)
        member = make_user("ann@example.com", is_staff=False)
        for address in ("boss@example.com", "gone@example.com"):
            self.assertIsNone(magic_link.read_token(magic_link.make_token(address)))
        self.assertFalse(magic_link.link_allowed_for(staff))
        self.assertFalse(magic_link.link_allowed_for(gone))
        self.assertTrue(magic_link.link_allowed_for(None))
        self.assertTrue(magic_link.link_allowed_for(member))


class MagicLinkEmailTests(TestCase):
    def setUp(self):
        cache.clear()

    def test_send_link_email(self):
        request = RequestFactory().post("/login/link")
        magic_link.send_link(request, "ann@example.com")
        self.assertEqual(len(mail.outbox), 1)
        message = mail.outbox[0]
        self.assertEqual(message.subject, "Your Fort Kent Cinema sign-in link")
        self.assertEqual(message.to, ["ann@example.com"])
        self.assertIn("http://testserver/login/link/", message.body)
        self.assertIn("5 minutes", message.body)
        self.assertIn("ignore", message.body)

    def test_send_failure_is_logged_not_raised(self):
        request = RequestFactory().post("/login/link")
        with mock.patch.object(EmailMessage, "send", side_effect=OSError("down")):
            with self.assertLogs("accounts.magic_link", "ERROR"):
                magic_link.send_link(request, "ann@example.com")
