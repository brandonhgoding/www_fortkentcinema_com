from django.test import TestCase
from django.urls import reverse
from dashboard.tests.helpers import make_staff


class PrimitiveTests(TestCase):
    def setUp(self) -> None:
        make_staff(email="s@example.com", password="pw12345")
        self.client.login(username="s@example.com", password="pw12345")

    def test_toast_and_confirm_regions_rendered(self) -> None:
        html = self.client.get(reverse("dashboard:home")).content.decode()
        # toast region + confirm dialog scaffolding present on every page
        self.assertIn('class="alertContainer"', html)
        self.assertIn("$store.toast", html)
        self.assertIn("$store.confirm", html)
