import datetime

from cinema.models import Engagement, EngagementFilm, Film, Screen
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

User = get_user_model()


def make_engagement(screen, *, start, end, status="CONFIRMED", kind="REGULAR",
                    films=(), show=True, event_title=""):
    eng = Engagement.objects.create(
        screen=screen, start_date=start, end_date=end, status=status, kind=kind,
        show_in_main_listings=show, event_title=event_title,
    )
    for i, f in enumerate(films, start=1):
        EngagementFilm.objects.create(engagement=eng, film=f, position=i)
    return eng


class EngagementListTests(TestCase):
    def setUp(self) -> None:
        User.objects.create_user(username="s", password="pw12345", is_staff=True)
        self.client.login(username="s", password="pw12345")
        self.screen = Screen.objects.create(name="Screen 1", capacity=100)
        self.film = Film.objects.create(title="Jaws", poster_url="https://img/j.jpg")
        self.today = timezone.localdate()

    def test_current_tab_default(self) -> None:
        make_engagement(self.screen, start=self.today - datetime.timedelta(days=1),
                        end=self.today + datetime.timedelta(days=1), films=[self.film])
        html = self.client.get(reverse("dashboard:engagements")).content.decode()
        self.assertIn("Jaws", html)
        self.assertIn("Screen 1", html)

    def test_upcoming_excludes_current(self) -> None:
        make_engagement(self.screen, start=self.today - datetime.timedelta(days=1),
                        end=self.today + datetime.timedelta(days=1), films=[self.film])
        html = self.client.get(reverse("dashboard:engagements"), {"tab": "UPCOMING"}).content.decode()
        self.assertNotIn("Jaws", html)
        self.assertIn("empty-state", html)

    def test_draft_tab(self) -> None:
        make_engagement(self.screen, start=self.today, end=self.today, status="DRAFT",
                        films=[self.film])
        html = self.client.get(reverse("dashboard:engagements"), {"tab": "DRAFT"}).content.decode()
        self.assertIn("Jaws", html)

    def test_kind_and_hidden_badges(self) -> None:
        make_engagement(self.screen, start=self.today, end=self.today, kind="CLASSIC",
                        films=[self.film], show=False, event_title="Noir Night")
        html = self.client.get(reverse("dashboard:engagements")).content.decode()
        self.assertIn("Classic", html)   # kind badge
        self.assertIn("Hidden", html)    # hidden badge

    def test_detail_stub_resolves(self) -> None:
        self.assertEqual(reverse("dashboard:engagement_detail", args=[1]), "/dashboard/engagements/1")

    def test_requires_staff(self) -> None:
        self.client.logout()
        self.assertEqual(self.client.get(reverse("dashboard:engagements")).status_code, 302)
