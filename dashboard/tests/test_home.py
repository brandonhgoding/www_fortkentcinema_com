import datetime

from cinema.models import Engagement, EngagementFilm, Film, Screen, Showtime
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

User = get_user_model()


def make_eng(screen, film, *, status="CONFIRMED", start=None, end=None):
    eng = Engagement.objects.create(
        screen=screen, status=status,
        start_date=start or timezone.localdate(),
        end_date=end or timezone.localdate() + datetime.timedelta(days=10),
    )
    EngagementFilm.objects.create(engagement=eng, film=film, position=1)
    return eng


class HomeViewTests(TestCase):
    def setUp(self) -> None:
        User.objects.create_user(username="staffer", password="pw12345", is_staff=True,
                                 first_name="Bran")
        self.client.login(username="staffer", password="pw12345")
        self.screen = Screen.objects.create(name="Screen 1", capacity=100)
        self.film = Film.objects.create(title="Dune", runtime_minutes=155)

    def _local(self, day, hh, mm=0):
        return timezone.make_aware(datetime.datetime.combine(day, datetime.time(hh, mm)))

    def test_counts(self) -> None:
        make_eng(self.screen, self.film, status="CONFIRMED")
        make_eng(self.screen, self.film, status="DRAFT")
        Screen.objects.create(name="Screen 2", capacity=60)
        resp = self.client.get(reverse("dashboard:home"))
        ctx = resp.context
        self.assertEqual(ctx["active_engagements_count"], 1)   # only CONFIRMED
        self.assertEqual(ctx["screens_count"], 2)

    def test_today_showtimes_tz_correct(self) -> None:
        eng = make_eng(self.screen, self.film)
        today = timezone.localdate()
        # 23:00 local today -> counts today, not tomorrow
        Showtime.objects.create(engagement=eng, starts_at=self._local(today, 23, 0))
        # tomorrow -> excluded
        Showtime.objects.create(engagement=eng,
                                starts_at=self._local(today + datetime.timedelta(days=1), 12, 0))
        resp = self.client.get(reverse("dashboard:home"))
        self.assertEqual(resp.context["today_showtimes_count"], 1)

    def test_display_name_first_name(self) -> None:
        resp = self.client.get(reverse("dashboard:home"))
        self.assertEqual(resp.context["display_name"], "Bran")

    def test_requires_staff(self) -> None:
        self.client.logout()
        self.assertEqual(self.client.get(reverse("dashboard:home")).status_code, 302)
        User.objects.create_user(username="p", password="pw12345", is_staff=False)
        self.client.login(username="p", password="pw12345")
        self.assertEqual(self.client.get(reverse("dashboard:home")).status_code, 403)


class HomeRenderTests(TestCase):
    def setUp(self) -> None:
        User.objects.create_user(username="s", password="pw12345", is_staff=True)
        self.client.login(username="s", password="pw12345")
        self.screen = Screen.objects.create(name="Screen 1", capacity=100)
        self.film = Film.objects.create(title="Dune", runtime_minutes=155)

    def _local(self, day, hh, mm=0):
        return timezone.make_aware(datetime.datetime.combine(day, datetime.time(hh, mm)))

    def test_cards_and_links(self) -> None:
        html = self.client.get(reverse("dashboard:home")).content.decode()
        self.assertIn("Active Engagements", html)
        self.assertIn("Today's Showtimes", html)
        self.assertIn("Screens", html)
        self.assertIn(reverse("dashboard:engagements"), html)
        self.assertIn(reverse("dashboard:screens"), html)
        self.assertIn("summaryGrid", html)

    def test_today_showtimes_table(self) -> None:
        eng = make_eng(self.screen, self.film)
        Showtime.objects.create(engagement=eng, starts_at=self._local(timezone.localdate(), 19, 30))
        html = self.client.get(reverse("dashboard:home")).content.decode()
        self.assertIn("Dune", html)
        self.assertIn("Screen 1", html)
        self.assertIn("Active", html)

    def test_empty_state(self) -> None:
        html = self.client.get(reverse("dashboard:home")).content.decode()
        self.assertIn("No Showtimes Today", html)

    def test_alerts_rendered(self) -> None:
        # a confirmed engagement with no showtimes tomorrow -> no-showtimes-tomorrow warning
        make_eng(self.screen, self.film)
        html = self.client.get(reverse("dashboard:home")).content.decode()
        self.assertIn("No showtimes scheduled for tomorrow", html)
        self.assertIn("alertContainer", html)
        self.assertIn("dismissButton", html)
