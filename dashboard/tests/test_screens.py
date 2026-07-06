from cinema.models import Screen
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

User = get_user_model()


class ScreenListTests(TestCase):
    def setUp(self) -> None:
        User.objects.create_user(username="s", password="pw12345", is_staff=True)
        self.client.login(username="s", password="pw12345")

    def test_empty_state(self) -> None:
        html = self.client.get(reverse("dashboard:screens")).content.decode()
        self.assertIn("empty-state", html)
        self.assertIn("No Screens Configured", html)

    def test_rows_and_labels(self) -> None:
        Screen.objects.create(
            name="Screen 1", capacity=150, screen_type="dolby_cinema",
            aspect_ratio="scope", sound_system="standard", supports_3d=True,
        )
        html = self.client.get(reverse("dashboard:screens")).content.decode()
        self.assertIn("Screen 1", html)
        self.assertIn("150 seats", html)
        self.assertIn("Dolby Cinema", html)          # screen_type label
        self.assertIn("Scope (2.39:1)", html)        # aspect_ratio label
        self.assertIn("Standard", html)              # sound label (NOT "Standard Surround")
        self.assertNotIn("Standard Surround", html)
        self.assertIn("badge3d", html)               # 3D badge present

    def test_requires_staff(self) -> None:
        self.client.logout()
        self.assertEqual(self.client.get(reverse("dashboard:screens")).status_code, 302)
        User.objects.create_user(username="p", password="pw12345", is_staff=False)
        self.client.login(username="p", password="pw12345")
        self.assertEqual(self.client.get(reverse("dashboard:screens")).status_code, 403)
