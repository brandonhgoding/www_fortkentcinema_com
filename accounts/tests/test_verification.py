import time
from datetime import timedelta
from unittest import mock

from django.core import mail
from django.core.cache import cache
from django.core.mail import EmailMessage
from django.test import RequestFactory, TestCase
from django.utils import timezone

from accounts import verification
from accounts.tests.factories import make_user
from dashboard.tests.helpers import make_staff


class VerificationTokenTests(TestCase):
    def setUp(self):
        self.user = make_user("ann@example.com", is_staff=False)

    def test_round_trip(self):
        token = verification.make_token(self.user)
        self.assertEqual(verification.read_token(token), self.user)

    def test_still_valid_just_inside_24h(self):
        token = verification.make_token(self.user)
        with mock.patch("time.time", return_value=time.time() + 86399):
            self.assertEqual(verification.read_token(token), self.user)

    def test_expired_after_24h(self):
        token = verification.make_token(self.user)
        with mock.patch("time.time", return_value=time.time() + 86401):
            self.assertIsNone(verification.read_token(token))

    def test_still_reads_once_verified(self):
        # A second click (or a mail scanner's earlier fetch) still finds the
        # account, so the page can say it is verified rather than expired.
        token = verification.make_token(self.user)
        self.user.email_verified_at = timezone.now()
        self.user.save()
        self.assertEqual(verification.read_token(token), self.user)

    def test_refused_once_password_changes(self):
        token = verification.make_token(self.user)
        self.user.set_password("another-passphrase-9")
        self.user.save()
        self.assertIsNone(verification.read_token(token))

    def test_refused_if_email_changed_user_deleted_staff_or_inactive(self):
        token = verification.make_token(self.user)
        self.user.email = "other@example.com"
        self.user.save()
        self.assertIsNone(verification.read_token(token))
        self.user.email = "ann@example.com"
        self.user.is_active = False
        self.user.save()
        self.assertIsNone(verification.read_token(token))
        self.user.is_active = True
        self.user.is_staff = True
        self.user.save()
        self.assertIsNone(verification.read_token(token))
        self.user.delete()
        self.assertIsNone(verification.read_token(token))

    def test_staff_account_token_refused(self):
        staff = make_staff(email="boss@example.com", password="pw12345")
        staff.email_verified_at = None
        staff.save()
        self.assertIsNone(verification.read_token(verification.make_token(staff)))

    def test_tampered(self):
        token = verification.make_token(self.user)
        self.assertIsNone(verification.read_token(token + "x"))
        self.assertIsNone(verification.read_token("garbage"))

    def test_normalise(self):
        self.assertEqual(
            verification.normalise(" Ann@Example.com "), "ann@example.com"
        )


class VerificationThrottleTests(TestCase):
    def setUp(self):
        cache.clear()

    def test_claim_address_once_per_five_minutes(self):
        self.assertIsNone(verification.claim_address("ann@example.com"))
        retry = verification.claim_address("ann@example.com")
        expected = timezone.now() + timedelta(seconds=300)
        self.assertLess(abs((retry - expected).total_seconds()), 2)

    def test_ip_cap(self):
        for _ in range(5):
            self.assertTrue(verification.ip_allowed("203.0.113.9"))
        self.assertFalse(verification.ip_allowed("203.0.113.9"))
        self.assertTrue(verification.ip_allowed("203.0.113.10"))

    def test_ip_cap_lifts_after_the_hour(self):
        for _ in range(5):
            verification.ip_allowed("203.0.113.9")
        with mock.patch("time.time", return_value=time.time() + 3599):
            self.assertFalse(verification.ip_allowed("203.0.113.9"))
        with mock.patch("time.time", return_value=time.time() + 3601):
            self.assertTrue(verification.ip_allowed("203.0.113.9"))

    def test_cache_keys_use_register_prefix(self):
        verification.ip_allowed("203.0.113.9")
        verification.claim_address("ann@example.com")
        self.assertIsNotNone(cache.get("register:ip:203.0.113.9"))
        self.assertIsNotNone(cache.get("register:addr:ann@example.com"))


class VerificationEmailTests(TestCase):
    def test_verify_email_content(self):
        user = make_user("ann@example.com", is_staff=False)
        request = RequestFactory().post("/register")
        verification.send_verification(request, user)
        self.assertEqual(len(mail.outbox), 1)
        message = mail.outbox[0]
        self.assertEqual(message.subject, "Confirm your Fort Kent Cinema account")
        self.assertEqual(message.to, ["ann@example.com"])
        self.assertIn("http://testserver/register/verify/", message.body)
        self.assertIn("24 hours", message.body)
        self.assertIn("ignore", message.body)

    def test_already_registered_email_content(self):
        request = RequestFactory().post("/register")
        verification.send_already_registered(request, "ann@example.com")
        self.assertEqual(len(mail.outbox), 1)
        message = mail.outbox[0]
        self.assertEqual(message.subject, "Your Fort Kent Cinema account")
        self.assertEqual(message.to, ["ann@example.com"])
        self.assertIn("http://testserver/login", message.body)
        self.assertIn("http://testserver/password-reset", message.body)
        self.assertIn("ignore", message.body)

    def test_send_failure_logged(self):
        user = make_user("ann@example.com", is_staff=False)
        request = RequestFactory().post("/register")
        with mock.patch.object(EmailMessage, "send", side_effect=OSError("down")):
            with self.assertLogs("accounts.verification", "ERROR"):
                verification.send_verification(request, user)
            with self.assertLogs("accounts.verification", "ERROR"):
                verification.send_already_registered(request, "ann@example.com")
