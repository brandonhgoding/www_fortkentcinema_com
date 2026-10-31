"""The throttle counters as production runs them: on the database cache,
where cache.incr is a plain get + set that resets the key's expiry to the
default five minutes. Every window here must last as long as it says."""

import time
from contextlib import contextmanager
from datetime import timedelta
from unittest import mock

from django.conf import settings
from django.core.cache import cache
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.utils import timezone

from accounts import forms, lockout, throttle
from accounts.tests.test_migrate_cache_table import DB_CACHE


@contextmanager
def later(seconds: float):
    """Move both clocks the database cache reads: time.time() when a row is
    written, timezone.now() when one is read."""
    real_time = time.time()
    real_now = timezone.now()
    shift = timedelta(seconds=seconds)
    with mock.patch("time.time", return_value=real_time + seconds), mock.patch(
        "django.core.cache.backends.db.tz_now", return_value=real_now + shift
    ):
        yield


@override_settings(CACHES=DB_CACHE)
class DatabaseCacheCounterTests(TestCase):
    def setUp(self):
        call_command("createcachetable", verbosity=0)
        cache.clear()

    def test_bump_returns_the_running_count(self):
        self.assertEqual([throttle.bump("k", 3600) for _ in range(3)], [1, 2, 3])
        self.assertEqual(throttle.count("k"), 3)

    def test_unknown_key_counts_zero(self):
        self.assertEqual(throttle.count("never"), 0)

    def test_window_outlasts_the_cache_default_timeout(self):
        for _ in range(5):
            throttle.bump("k", 3600)
        with later(10 * 60):
            self.assertEqual(throttle.count("k"), 5)
            self.assertEqual(throttle.bump("k", 3600), 6)

    def test_window_starts_at_the_first_event_not_the_last(self):
        throttle.bump("k", 3600)
        with later(50 * 60):
            self.assertEqual(throttle.bump("k", 3600), 2)
        with later(61 * 60):
            self.assertEqual(throttle.count("k"), 0)
            self.assertEqual(throttle.bump("k", 3600), 1)

    def test_reset_ip_cap_holds_for_the_hour(self):
        for _ in range(forms.RESET_IP_CAP):
            self.assertTrue(forms.ip_allowed("203.0.113.9"))
        with later(6 * 60):
            self.assertFalse(forms.ip_allowed("203.0.113.9"))
        with later(forms.RESET_IP_WINDOW + 1):
            self.assertTrue(forms.ip_allowed("203.0.113.9"))

    def test_login_ip_lock_holds_for_the_cooloff(self):
        request = mock.Mock(META={"REMOTE_ADDR": "203.0.113.9"})
        for _ in range(settings.LOGIN_IP_FAILURE_LIMIT):
            lockout.record_failed_login(None, request=request)
        with later(6 * 60):
            self.assertTrue(lockout.ip_locked(request))
        with later(settings.AXES_COOLOFF_TIME.total_seconds() + 1):
            self.assertFalse(lockout.ip_locked(request))
