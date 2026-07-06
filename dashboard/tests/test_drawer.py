from pathlib import Path

from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

User = get_user_model()
CSS_DIR = Path(settings.BASE_DIR) / "dashboard" / "static" / "dashboard" / "css"


class DrawerTests(TestCase):
    def setUp(self) -> None:
        User.objects.create_user(username="s", password="pw12345", is_staff=True)
        self.client.login(username="s", password="pw12345")

    def test_drawer_shell_rendered(self) -> None:
        html = self.client.get(reverse("dashboard:home")).content.decode()
        self.assertIn('id="drawer-content"', html)
        self.assertIn('id="drawer-footer"', html)
        self.assertIn("$store.drawer", html)

    def test_drawer_css_byte_identical(self) -> None:
        src = Path(
            "/Users/bgoding/code/SoftwareMaine/www_leprinceos_com/src/components/Drawer.module.css"
        ).read_bytes()
        self.assertEqual((CSS_DIR / "drawer.css").read_bytes(), src)

    def test_js_has_bridges(self) -> None:
        js = (
            Path(settings.BASE_DIR)
            / "dashboard" / "static" / "dashboard" / "js" / "dashboard.js"
        ).read_text()
        self.assertIn("close-drawer", js)
        self.assertIn("dashboard-toast", js)
        self.assertIn("htmx:confirm", js)
        self.assertIn("Alpine.store('drawer'", js)
