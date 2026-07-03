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
