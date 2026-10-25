from datetime import datetime, timedelta, timezone as dt_timezone
from unittest import mock

from django.contrib.auth import get_user_model
from django.core import mail
from django.core.cache import cache
from django.test import TestCase, override_settings
from django.utils import timezone

from accounts.tests.factories import make_user
from dashboard.tests.helpers import make_staff

URL = "/register"
GOOD = "Tr1cky-passphrase-77"
SENT = "Check your email to confirm your address"


def post(client, email="ann@example.com", p1=GOOD, p2=None, **extra):
    data = {
        "email": email,
        "password1": p1,
        "password2": p1 if p2 is None else p2,
        **extra,
    }
    return client.post(URL, data)


class RegisterTests(TestCase):
    def setUp(self):
        cache.clear()
        self.users = get_user_model().objects

    def test_register_page(self):
        response = self.client.get(URL)
        self.assertContains(response, "Create an account")
        self.assertContains(response, "Create account")

    def test_honeypot_checked_first(self):
        response = post(self.client, email="not-an-email", website="x")
        self.assertContains(response, SENT)
        self.assertEqual(self.users.count(), 0)
        self.assertEqual(len(mail.outbox), 0)

    def test_invalid_and_weak_and_mismatched(self):
        response = post(self.client, email="nope")
        self.assertContains(response, "Create account")
        self.assertTrue(response.context["form"].errors["email"])
        response = post(self.client, p1="12345678")
        self.assertTrue(response.context["form"].errors["password2"])
        response = post(self.client, p2="Different-passphrase-1")
        self.assertTrue(response.context["form"].errors["password2"])
        self.assertEqual(self.users.count(), 0)
        self.assertEqual(len(mail.outbox), 0)

    def test_new_address_creates_unverified_member(self):
        response = post(self.client, email=" Ann@Example.com ")
        self.assertContains(response, SENT)
        user = self.users.get()
        self.assertEqual(user.email, "ann@example.com")
        self.assertFalse(user.is_staff)
        self.assertIsNone(user.email_verified_at)
        self.assertTrue(user.check_password(GOOD))
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(
            mail.outbox[0].subject, "Confirm your Fort Kent Cinema account"
        )
        self.assertEqual(mail.outbox[0].to, ["ann@example.com"])

    def test_unverified_address_resets_password_and_resends(self):
        make_user("ann@example.com", "old-password-1", is_staff=False)
        post(self.client)
        user = self.users.get()
        self.assertTrue(user.check_password(GOOD))
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(
            mail.outbox[0].subject, "Confirm your Fort Kent Cinema account"
        )

    def test_reregistering_refreshes_date_joined(self):
        user = make_user("ann@example.com", "old-password-1", is_staff=False)
        old = timezone.now() - timedelta(days=6)
        self.users.filter(pk=user.pk).update(date_joined=old)
        post(self.client)
        self.assertGreater(self.users.get().date_joined, old + timedelta(days=5))

    def test_similar_password_refused(self):
        response = post(self.client, email="annmarie@example.com", p1="annmarie12")
        self.assertTrue(response.context["form"].errors["password2"])
        self.assertEqual(self.users.count(), 0)

    def test_verified_and_staff_get_already_registered_and_are_unchanged(self):
        from django.utils import timezone

        member = make_user("ann@example.com", "old-password-1", is_staff=False)
        member.email_verified_at = timezone.now()
        member.save()
        staff = make_staff(email="bo@example.com", password="old-password-1")
        for user in (member, staff):
            before = user.password
            cache.clear()
            mail.outbox.clear()
            response = post(self.client, email=user.email)
            self.assertContains(response, SENT)
            user.refresh_from_db()
            self.assertEqual(user.password, before)
            self.assertEqual(len(mail.outbox), 1)
            self.assertEqual(mail.outbox[0].subject, "Your Fort Kent Cinema account")

    def test_inactive_gets_nothing(self):
        user = make_user("ann@example.com", "old-password-1", is_staff=False)
        user.is_active = False
        user.save()
        before = user.password
        response = post(self.client)
        self.assertContains(response, SENT)
        user.refresh_from_db()
        self.assertEqual(user.password, before)
        self.assertEqual(len(mail.outbox), 0)

    def test_same_page_every_case(self):
        from django.utils import timezone

        verified = make_user("v@example.com", "old-password-1", is_staff=False)
        verified.email_verified_at = timezone.now()
        verified.save()
        make_user("u@example.com", "old-password-1", is_staff=False)
        gone = make_user("g@example.com", "old-password-1", is_staff=False)
        gone.is_active = False
        gone.save()
        pages = []
        emails = ("new@example.com", "v@example.com", "u@example.com", "g@example.com")
        for email in emails:
            cache.clear()
            text = post(self.client, email=email).content.decode()
            text = text.replace(email, "ADDR")
            pages.append(" ".join(text.split()))
        # Strip the per-response CSRF token noise, if any.
        import re

        pages = [re.sub(r'value="[^"]{30,}"', "", p) for p in pages]
        self.assertEqual(len(set(pages)), 1)

    def test_throttle_message_exact_time(self):
        start = datetime(2026, 10, 24, 23, 40, tzinfo=dt_timezone.utc)  # 7:40 PM EDT
        with mock.patch("accounts.verification.timezone.now", return_value=start):
            post(self.client)
            response = post(self.client)
        self.assertContains(
            response,
            "We sent an email to this address in the last 5 minutes. Check your "
            "inbox (and spam), or try again after 7:45 PM.",
        )
        self.assertEqual(self.users.count(), 1)
        self.assertEqual(len(mail.outbox), 1)

    def test_ip_cap_429_after_five_across_register_and_resend(self):
        for i in range(3):
            post(self.client, email=f"a{i}@example.com")
        for i in range(2):
            self.client.post("/register/resend", {"email": f"b{i}@example.com"})
        response = post(self.client, email="z@example.com")
        self.assertEqual(response.status_code, 429)
        self.assertContains(
            response,
            "Too many requests from this connection. Try again later.",
            status_code=429,
        )
        self.assertFalse(self.users.filter(email="z@example.com").exists())

    @override_settings(USE_PROXY_HEADERS=True)
    def test_cap_buckets_per_visitor_in_production_shape(self):
        for i in range(6):
            response = self.client.post(
                URL,
                {"email": f"a{i}@example.com", "password1": GOOD, "password2": GOOD},
                REMOTE_ADDR="",
                HTTP_X_REAL_IP=f"203.0.113.{i + 1}",
            )
            self.assertNotEqual(response.status_code, 429)
        statuses = []
        for i in range(6):
            response = self.client.post(
                URL,
                {"email": f"c{i}@example.com", "password1": GOOD, "password2": GOOD},
                REMOTE_ADDR="",
                HTTP_X_REAL_IP="198.51.100.9",
                HTTP_X_FORWARDED_FOR=f"10.0.0.{i}",
            )
            statuses.append(response.status_code)
        self.assertEqual(statuses[:5], [200] * 5)
        self.assertEqual(statuses[5], 429)


class ResendTests(TestCase):
    def setUp(self):
        cache.clear()

    def resend(self, email, **extra):
        return self.client.post("/register/resend", {"email": email, **extra})

    def test_get_not_allowed(self):
        self.assertEqual(self.client.get("/register/resend").status_code, 405)

    def test_resend_only_for_unverified_member(self):
        from django.utils import timezone

        make_user("u@example.com", "pw-1-long-enough", is_staff=False)
        v = make_user("v@example.com", "pw-1-long-enough", is_staff=False)
        v.email_verified_at = timezone.now()
        v.save()
        make_staff(email="s@example.com", password="pw-1-long-enough")
        gone = make_user("g@example.com", "pw-1-long-enough", is_staff=False)
        gone.is_active = False
        gone.save()
        others = ("v@example.com", "s@example.com", "g@example.com", "none@example.com")
        for email in others:
            response = self.resend(email)
            self.assertContains(response, SENT)
        self.assertEqual(len(mail.outbox), 0)
        response = self.resend("u@example.com")
        self.assertContains(response, SENT)
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(
            mail.outbox[0].subject, "Confirm your Fort Kent Cinema account"
        )

    def test_resend_refreshes_date_joined(self):
        user = make_user("u@example.com", "pw-1-long-enough", is_staff=False)
        old = timezone.now() - timedelta(days=6)
        get_user_model().objects.filter(pk=user.pk).update(date_joined=old)
        self.resend("u@example.com")
        joined = get_user_model().objects.get().date_joined
        self.assertGreater(joined, old + timedelta(days=5))

    def test_honeypot_sends_nothing(self):
        make_user("u@example.com", "pw-1-long-enough", is_staff=False)
        response = self.resend("u@example.com", website="x")
        self.assertContains(response, SENT)
        self.assertEqual(len(mail.outbox), 0)

    def test_throttled(self):
        make_user("u@example.com", "pw-1-long-enough", is_staff=False)
        self.resend("u@example.com")
        response = self.resend("u@example.com")
        self.assertContains(response, "in the last 5 minutes")
        self.assertEqual(len(mail.outbox), 1)


class MagicLinkGoneTests(TestCase):
    def test_magic_link_urls_gone(self):
        self.assertEqual(self.client.get("/login/link").status_code, 404)
        self.assertEqual(self.client.post("/login/link", {}).status_code, 404)


class RegisterTimingTests(TestCase):
    """Every outcome shows the same page, but a new or unverified address
    also hashes the password while a verified one only sends mail. Hashing
    on the other branches too keeps the response time from saying which
    addresses already have a confirmed account."""

    def setUp(self):
        cache.clear()

    def hashes_for(self, email):
        with mock.patch("accounts.views.make_password") as dummy:
            post(self.client, email=email)
        return dummy

    def test_verified_and_staff_addresses_pay_for_a_hash(self):
        member = make_user("ann@example.com", "old-password-1", is_staff=False)
        member.email_verified_at = timezone.now()
        member.save()
        make_staff(email="bo@example.com", password="old-password-1")
        for email in ("ann@example.com", "bo@example.com"):
            cache.clear()
            dummy = self.hashes_for(email)
            dummy.assert_called_once_with(GOOD)

    def test_inactive_address_pays_for_a_hash(self):
        user = make_user("ann@example.com", "old-password-1", is_staff=False)
        user.is_active = False
        user.save()
        self.hashes_for("ann@example.com").assert_called_once_with(GOOD)

    def test_new_and_unverified_addresses_hash_only_once(self):
        # create_user / set_password already hash; no second one.
        self.hashes_for("new@example.com").assert_not_called()
        cache.clear()
        self.hashes_for("new@example.com").assert_not_called()
