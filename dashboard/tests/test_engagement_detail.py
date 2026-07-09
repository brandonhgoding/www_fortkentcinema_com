import datetime

from cinema.models import Engagement, EngagementFilm, Film, Screen
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

User = get_user_model()


def make_eng(screen, films=(), **over):
    defaults = dict(screen=screen, start_date=datetime.date(2026, 7, 1),
                    end_date=datetime.date(2026, 7, 7), status="CONFIRMED")
    defaults.update(over)
    eng = Engagement.objects.create(**defaults)
    for i, f in enumerate(films, start=1):
        EngagementFilm.objects.create(engagement=eng, film=f, position=i)
    return eng


class EngagementDetailPageTests(TestCase):
    def setUp(self) -> None:
        User.objects.create_user(username="s", password="pw12345", is_staff=True)
        self.client.login(username="s", password="pw12345")
        self.screen = Screen.objects.create(name="Screen 1", capacity=100)
        self.film = Film.objects.create(title="Dune", runtime_minutes=155,
                                        poster_url="https://img/d.jpg")

    def test_renders_engagement(self) -> None:
        eng = make_eng(self.screen, films=[self.film], notes="Sold out nightly", kind="CLASSIC")
        html = self.client.get(reverse("dashboard:engagement_detail", args=[eng.pk])).content.decode()
        self.assertIn("Dune", html)
        self.assertIn("Screen 1", html)
        self.assertIn("155 min", html)
        self.assertIn("Classic", html)          # KIND_LABELS
        self.assertIn("Sold out nightly", html) # notes
        self.assertIn("Back to Engagements", html)

    def test_hidden_note(self) -> None:
        eng = make_eng(self.screen, films=[self.film], show_in_main_listings=False)
        html = self.client.get(reverse("dashboard:engagement_detail", args=[eng.pk])).content.decode()
        self.assertIn("Hidden from public listings", html)

    def test_404_missing(self) -> None:
        self.assertEqual(self.client.get(reverse("dashboard:engagement_detail", args=[999])).status_code, 404)

    def test_requires_staff(self) -> None:
        eng = make_eng(self.screen, films=[self.film])
        self.client.logout()
        self.assertEqual(self.client.get(reverse("dashboard:engagement_detail", args=[eng.pk])).status_code, 302)

    def test_status_badge_camelcase_class(self) -> None:
        """Regression: status badge should render with camelCase CSS class, not capfirst."""
        eng = make_eng(self.screen, films=[self.film], status="CONFIRMED")
        html = self.client.get(reverse("dashboard:engagement_detail", args=[eng.pk])).content.decode()
        # Should contain the camelCase class
        self.assertIn('statusConfirmed', html)
        # Should NOT contain the broken capfirst class
        self.assertNotIn('statusCONFIRMED', html)
