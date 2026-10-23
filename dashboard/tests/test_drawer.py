from pathlib import Path

from django.conf import settings
from django.test import TestCase
from django.urls import reverse
from dashboard.tests.helpers import make_staff

CSS_DIR = Path(settings.BASE_DIR) / "dashboard" / "static" / "dashboard" / "css"


class DrawerTests(TestCase):
    def setUp(self) -> None:
        make_staff(email="s@example.com", password="pw12345")
        self.client.login(username="s@example.com", password="pw12345")

    def test_drawer_shell_rendered(self) -> None:
        html = self.client.get(reverse("dashboard:home")).content.decode()
        self.assertIn('id="drawer-content"', html)
        self.assertIn('id="drawer-footer"', html)
        self.assertIn("$store.drawer", html)

    def test_js_has_bridges(self) -> None:
        js = (
            Path(settings.BASE_DIR)
            / "dashboard" / "static" / "dashboard" / "js" / "dashboard.js"
        ).read_text()
        self.assertIn("close-drawer", js)
        self.assertIn("dashboard-toast", js)
        self.assertIn("htmx:confirm", js)
        self.assertIn("Alpine.store('drawer'", js)
