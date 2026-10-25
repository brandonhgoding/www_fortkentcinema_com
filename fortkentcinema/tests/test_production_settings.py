"""Settings that only bite in production (accounts security audit 2026-10-24)."""

from django.test import SimpleTestCase

from .settings_probe import load_settings


class CacheSettingsTests(SimpleTestCase):
    def test_production_default_cache_is_shared_across_workers(self):
        # L3: throttles (registration IP cap, per-address claim, reset email,
        # verify-link guesses) count in the default cache. gunicorn runs
        # several workers and recycles them, so an in-process cache gives
        # each worker its own counter that resets at random.
        settings = load_settings()
        default = settings.CACHES["default"]
        self.assertEqual(
            default["BACKEND"], "django.core.cache.backends.db.DatabaseCache"
        )
        self.assertEqual(default["LOCATION"], "django_cache")

    def test_social_card_bytes_stay_in_process(self):
        settings = load_settings()
        self.assertEqual(
            settings.CACHES["social_cards"]["BACKEND"],
            "django.core.cache.backends.locmem.LocMemCache",
        )

    def test_tests_keep_the_in_memory_cache(self):
        settings = load_settings(argv=("manage.py", "test"))
        self.assertEqual(
            settings.CACHES["default"]["BACKEND"],
            "django.core.cache.backends.locmem.LocMemCache",
        )


class SessionSettingsTests(SimpleTestCase):
    def test_sessions_last_twelve_hours(self):
        # L4: Django's default is two weeks. Staff sessions can refund orders
        # and read member PII; a lost laptop should not stay signed in that long.
        settings = load_settings()
        self.assertEqual(settings.SESSION_COOKIE_AGE, 12 * 60 * 60)


class LoginIpCapSettingsTests(SimpleTestCase):
    def test_login_ip_failure_limit(self):
        # L2: one address spraying a password across many emails never trips
        # the per-(email, address) lockout; this looser per-address cap does.
        settings = load_settings()
        self.assertEqual(settings.LOGIN_IP_FAILURE_LIMIT, 30)
        self.assertGreater(settings.LOGIN_IP_FAILURE_LIMIT, settings.AXES_FAILURE_LIMIT)
