import datetime

from boxoffice.models import MembershipSale, SaleLine, SalesPull
from cinema.models import Engagement, EngagementFilm, Film, Screen, Showtime
from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
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

    def test_active_count_leaves_out_ended_and_upcoming_runs(self) -> None:
        today = timezone.localdate()
        make_eng(self.screen, self.film)  # running now
        make_eng(self.screen, self.film, start=today - datetime.timedelta(days=30),
                 end=today - datetime.timedelta(days=20))
        make_eng(self.screen, self.film, start=today + datetime.timedelta(days=5))
        resp = self.client.get(reverse("dashboard:home"))
        self.assertEqual(resp.context["active_engagements_count"], 1)

    def test_cancelled_showtimes_are_not_counted(self) -> None:
        eng = make_eng(self.screen, self.film)
        today = timezone.localdate()
        tomorrow = today + datetime.timedelta(days=1)
        Showtime.objects.create(engagement=eng, starts_at=self._local(today, 23),
                                is_cancelled=True)
        Showtime.objects.create(engagement=eng, starts_at=self._local(tomorrow, 19),
                                is_cancelled=True)
        resp = self.client.get(reverse("dashboard:home"))
        self.assertEqual(resp.context["today_showtimes_count"], 0)
        self.assertIn("no-showtimes-tomorrow", [a["id"] for a in resp.context["alerts"]])

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

    @override_settings(SQUARE_ACCESS_TOKEN="")
    def test_sales_panel_hidden_without_token(self) -> None:
        html = self.client.get(reverse("dashboard:home")).content.decode()
        self.assertNotIn("Yesterday&#x27;s Sales", html)
        self.assertNotIn("Yesterday's Sales", html)

    @override_settings(SQUARE_ACCESS_TOKEN="tok")
    def test_sales_panel_empty_state(self) -> None:
        html = self.client.get(reverse("dashboard:home")).content.decode()
        self.assertIn("No sales pulled yet", html)

    @override_settings(SQUARE_ACCESS_TOKEN="tok")
    def test_sales_panel_with_sales_and_failed_pull_alert(self) -> None:
        yesterday = timezone.localdate() - datetime.timedelta(days=1)
        SalesPull.objects.create(
            business_date=yesterday, status=SalesPull.Status.FAILED)
        SaleLine.objects.create(
            order_id="O1", line_uid="L1", business_date=yesterday,
            closed_at=timezone.now(), item_name="Popcorn", quantity=1,
            gross_cents=500)
        html = self.client.get(reverse("dashboard:home")).content.decode()
        self.assertIn("$5.00", html)
        self.assertIn("0 tickets", html)
        self.assertIn("Square sales pull failed", html)

    def test_failed_membership_sale_alert(self) -> None:
        MembershipSale.objects.create(order_id="O1", status="FAILED", error="boom")
        MembershipSale.objects.create(order_id="O2", status="SKIPPED")
        html = self.client.get(reverse("dashboard:home")).content.decode()
        self.assertIn("1 Square membership sale needs attention", html)
