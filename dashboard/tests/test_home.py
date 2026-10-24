import datetime

from accounts.tests.factories import make_user
from boxoffice.models import MembershipSale, SaleLine, SalesPull
from cinema.models import Engagement, EngagementFilm, Film, Screen, Showtime
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from tickets.tests.factories import make_order
from dashboard.tests.helpers import make_staff


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
        make_staff(email="staffer@example.com", password="pw12345")
        self.client.login(username="staffer@example.com", password="pw12345")
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

    def test_display_name_is_email(self) -> None:
        resp = self.client.get(reverse("dashboard:home"))
        self.assertEqual(resp.context["display_name"], "staffer@example.com")

    def test_non_staff_get_member_home_not_staff_home(self) -> None:
        self.client.logout()
        self.assertEqual(self.client.get(reverse("dashboard:home")).status_code, 302)
        make_user(email="p@example.com", password="pw12345", is_staff=False)
        self.client.login(username="p@example.com", password="pw12345")
        resp = self.client.get(reverse("dashboard:home"))
        self.assertTemplateUsed(resp, "dashboard/member_home.html")
        self.assertTemplateNotUsed(resp, "dashboard/home.html")


class HomeRenderTests(TestCase):
    def setUp(self) -> None:
        make_staff(email="s@example.com", password="pw12345")
        self.client.login(username="s@example.com", password="pw12345")
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

    @override_settings(SQUARE_ACCESS_TOKEN="tok", SQUARE_LOCATION_ID="",
                       SQUARE_TICKET_CATEGORY_ID="C")
    def test_sales_panel_hidden_when_misconfigured(self) -> None:
        # The public site hides Buy links on a blank id; the dashboard must
        # agree that Square is off rather than go by the token alone.
        html = self.client.get(reverse("dashboard:home")).content.decode()
        self.assertNotIn("Yesterday's Sales", html)
        self.assertNotIn("No sales pulled yet", html)

    @override_settings(SQUARE_ACCESS_TOKEN="tok", SQUARE_LOCATION_ID="L",
                       SQUARE_TICKET_CATEGORY_ID="C")
    def test_sales_panel_empty_state(self) -> None:
        html = self.client.get(reverse("dashboard:home")).content.decode()
        self.assertIn("No sales pulled yet", html)

    @override_settings(SQUARE_ACCESS_TOKEN="tok", SQUARE_LOCATION_ID="L",
                       SQUARE_TICKET_CATEGORY_ID="C")
    def test_sales_panel_with_sales_and_failed_pull_alert(self) -> None:
        yesterday = timezone.localdate() - datetime.timedelta(days=1)
        SalesPull.objects.create(
            business_date=yesterday, status=SalesPull.Status.FAILED)
        SaleLine.objects.create(
            order_id="O1", line_uid="L1", business_date=yesterday,
            show_date=yesterday,
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

    def test_home_today_panel_shows_online_count(self) -> None:
        eng = make_eng(self.screen, self.film)
        st = Showtime.objects.create(
            engagement=eng, starts_at=self._local(timezone.localdate(), 23, 30))
        make_order(st, status="PAID", lines={"adult": 2, "child": 1})
        make_order(st, status="EXPIRED", lines={"adult": 4})
        html = self.client.get(reverse("dashboard:home")).content.decode()
        self.assertIn("<th>Online</th>", html)
        # Table cell and phone card line.
        self.assertEqual(html.count("3 online"), 2)

    def test_online_ticket_alerts(self) -> None:
        eng = make_eng(self.screen, self.film)
        tomorrow = timezone.localdate() + datetime.timedelta(days=1)
        soon = Showtime.objects.create(
            engagement=eng, starts_at=self._local(tomorrow, 19), online_allowance=10)
        make_order(soon, status="PAID", lines={"adult": 9})
        gone = Showtime.objects.create(
            engagement=eng, starts_at=self._local(tomorrow, 14), is_cancelled=True)
        make_order(gone, status="PAID", square_payment_id="PAY-1")
        make_order(gone, status="FAILED")
        html = self.client.get(reverse("dashboard:home")).content.decode()
        self.assertIn("1 online ticket order needs attention", html)
        self.assertIn("Dune at 7:00 PM is nearly sold out online (9 of 10)", html)
        self.assertIn(
            "Dune at 2:00 PM is cancelled with 1 unrefunded online order", html)


class HomePermissionTests(TestCase):
    def _login(self, perms):
        make_staff(email="limited@example.com", password="pw12345", perms=perms)
        self.client.login(username="limited@example.com", password="pw12345")

    def test_no_permissions_renders_header_only(self) -> None:
        self._login(())
        resp = self.client.get(reverse("dashboard:home"))
        self.assertEqual(resp.status_code, 200)
        html = resp.content.decode()
        self.assertIn("Welcome back", html)
        self.assertIn(
            "You don't have access to any dashboard sections yet. "
            "Ask an administrator for access.",
            html.replace("&#x27;", "'"),
        )
        for label in ("Active Engagements", "Today's Showtimes", "Screens",
                      "Yesterday's Sales"):
            self.assertNotIn(label, html)
        # The home alerts partial; base.html's toast container is always there.
        self.assertNotIn("x-data=\"{ shown: true }\"", html)

    def test_box_office_user_sees_tickets_only(self) -> None:
        from phone.models import Voicemail
        screen = Screen.objects.create(name="Screen 1", capacity=100)
        film = Film.objects.create(title="Dune", runtime_minutes=155)
        make_eng(screen, film, status="DRAFT")
        eng = make_eng(screen, film)
        Voicemail.objects.create(recording_sid="RE1")
        start = timezone.make_aware(datetime.datetime.combine(
            timezone.localdate(), datetime.time(23, 30)))
        st = Showtime.objects.create(engagement=eng, starts_at=start)
        make_order(st, status="FAILED")
        self._login(("tickets.view_ticketorder", "cinema.view_showtime"))
        html = self.client.get(reverse("dashboard:home")).content.decode()
        self.assertIn("Today's Showtimes", html)
        self.assertIn("1 online ticket order needs attention", html)
        self.assertNotIn("new voicemail", html)
        self.assertNotIn("don't have access", html.replace("&#x27;", "'"))
        self.assertNotIn("draft", html)
        self.assertNotIn("Active Engagements", html)
        self.assertNotIn("Screens", html)
