"""The DRF posts API was removed 2026-10-31: nothing called it. Posts are
written in the dashboard and read on /blog/."""

from django.conf import settings
from django.test import TestCase


class ApiRemovedTests(TestCase):
    def test_api_urls_are_gone(self):
        for path in ("/api/", "/api/posts/", "/api/authors/", "/api/categories/"):
            with self.subTest(path=path):
                self.assertEqual(self.client.get(path).status_code, 404)

    def test_drf_and_cors_are_not_installed(self):
        for app in ("rest_framework", "corsheaders"):
            self.assertNotIn(app, settings.INSTALLED_APPS)
        self.assertNotIn("corsheaders.middleware.CorsMiddleware", settings.MIDDLEWARE)
        self.assertFalse(hasattr(settings, "REST_FRAMEWORK"))
