from django.conf import settings
from django.test import SimpleTestCase


class StaticServingSettingsTests(SimpleTestCase):
    def test_whitenoise_middleware_present(self):
        self.assertIn(
            "whitenoise.middleware.WhiteNoiseMiddleware", settings.MIDDLEWARE
        )

    def test_whitenoise_after_security_middleware(self):
        mw = settings.MIDDLEWARE
        self.assertLess(
            mw.index("django.middleware.security.SecurityMiddleware"),
            mw.index("whitenoise.middleware.WhiteNoiseMiddleware"),
        )

    def test_staticfiles_storage_is_not_manifest_backed_under_tests(self):
        """
        Manifest storage (whitenoise.storage.CompressedManifestStaticFilesStorage)
        requires a prebuilt staticfiles.json from `collectstatic`, which is a
        gitignored build artifact. If it's forced on unconditionally, a fresh
        clone / CI run with no manifest present fails every test that renders
        a template using {% static %}. The test run must use plain storage
        instead so `manage.py test` needs no prior collectstatic step.
        """
        backend = settings.STORAGES["staticfiles"]["BACKEND"]
        self.assertTrue(backend.endswith("StaticFilesStorage"))
        self.assertNotEqual(
            backend, "whitenoise.storage.CompressedManifestStaticFilesStorage"
        )


class ProdSecuritySettingsTests(SimpleTestCase):
    def test_security_settings_default_off_for_dev(self):
        # With no prod env vars set (dev/test), these stay dev-safe.
        from django.conf import settings

        self.assertFalse(getattr(settings, "SECURE_SSL_REDIRECT", False))

    def test_csrf_trusted_origins_configurable(self):
        # The setting exists (possibly empty) and is a list.
        from django.conf import settings

        self.assertIsInstance(getattr(settings, "CSRF_TRUSTED_ORIGINS", []), list)
