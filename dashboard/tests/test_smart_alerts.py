import datetime
from zoneinfo import ZoneInfo

from cinema.models import Engagement, EngagementFilm, Film, Screen
from dashboard.smart_alerts import build_smart_alerts
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from tickets.alerts import cancelled_with_orders, failures_count, nearly_sold_out
from tickets.tests.factories import make_order, make_showtime


def make_eng(screen, film, *, end, status="CONFIRMED", start=None, title=None):
    eng = Engagement.objects.create(
        screen=screen, start_date=start or datetime.date(2026, 7, 1), end_date=end,
        status=status, display_title=title or "",
    )
    EngagementFilm.objects.create(engagement=eng, film=film, position=1)
    return eng


class BuildSmartAlertsTests(TestCase):
    def setUp(self) -> None:
        self.screen = Screen.objects.create(name="S1", capacity=50)
        self.film = Film.objects.create(title="Dune")
        self.today = datetime.date(2026, 7, 10)

    def test_no_showtimes_tomorrow_only_when_engagements_exist(self) -> None:
        # No engagements -> no alert even if tomorrow empty
        self.assertEqual(build_smart_alerts(Engagement.objects.all(), 0, self.today), [])
        make_eng(self.screen, self.film, end=datetime.date(2026, 7, 20))
        ids = [a["id"] for a in build_smart_alerts(Engagement.objects.all(), 0, self.today)]
        self.assertIn("no-showtimes-tomorrow", ids)

    def test_no_alert_when_tomorrow_has_showtimes(self) -> None:
        make_eng(self.screen, self.film, end=datetime.date(2026, 7, 20))
        ids = [a["id"] for a in build_smart_alerts(Engagement.objects.all(), 3, self.today)]
        self.assertNotIn("no-showtimes-tomorrow", ids)

    def test_ending_soon_boundaries(self) -> None:
        make_eng(self.screen, self.film, end=self.today, title="Ends Today")
        make_eng(self.screen, self.film, end=self.today + datetime.timedelta(days=2), title="Ends Two")
        make_eng(self.screen, self.film, end=self.today + datetime.timedelta(days=3), title="Ends Three")
        make_eng(self.screen, self.film, end=self.today, status="DRAFT", title="Draft One")
        alerts = build_smart_alerts(Engagement.objects.all(), 5, self.today)
        msgs = [a["message"] for a in alerts]
        self.assertIn("Ends Today ends in 0 days", msgs)
        self.assertIn("Ends Two ends in 2 days", msgs)
        self.assertFalse(any("Ends Three" in m for m in msgs))   # +3 excluded
        self.assertFalse(any("Draft One" in m for m in msgs))    # non-CONFIRMED excluded

    def test_ending_soon_singular(self) -> None:
        make_eng(self.screen, self.film, end=self.today + datetime.timedelta(days=1), title="One Day")
        msgs = [a["message"] for a in build_smart_alerts(Engagement.objects.all(), 5, self.today)]
        self.assertIn("One Day ends in 1 day", msgs)  # singular

    def test_draft_count_plural(self) -> None:
        make_eng(self.screen, self.film, end=datetime.date(2026, 7, 20), status="DRAFT")
        make_eng(self.screen, self.film, end=datetime.date(2026, 7, 20), status="DRAFT")
        msgs = [a["message"] for a in build_smart_alerts(Engagement.objects.all(), 5, self.today)]
        self.assertIn("You have 2 draft engagements waiting to be confirmed", msgs)

    def test_draft_count_singular(self) -> None:
        make_eng(self.screen, self.film, end=datetime.date(2026, 7, 20), status="DRAFT")
        msgs = [a["message"] for a in build_smart_alerts(Engagement.objects.all(), 5, self.today)]
        self.assertIn("You have 1 draft engagement waiting to be confirmed", msgs)

    def test_clean_state_no_alerts(self) -> None:
        make_eng(self.screen, self.film, end=datetime.date(2026, 7, 20))  # confirmed, far end
        alerts = build_smart_alerts(Engagement.objects.all(), 5, self.today)
        self.assertEqual(alerts, [])


class SponsorshipAlertRemovedTests(TestCase):
    def setUp(self) -> None:
        self.today = datetime.date(2026, 7, 10)

    def test_rental_alert_alone(self):
        alerts = build_smart_alerts(
            [], 1, self.today, new_rental_inquiries=2, new_voicemails=1
        )
        ids = [a["id"] for a in alerts]
        self.assertIn("new-rental-inquiries", ids)
        self.assertIn("new-voicemails", ids)
        self.assertNotIn("new-sponsorship-inquiries", ids)

    def test_new_inquiries_argument_is_gone(self):
        with self.assertRaises(TypeError):
            build_smart_alerts([], 1, self.today, new_inquiries=1)


class RentalInquiryAlertTests(TestCase):
    def setUp(self) -> None:
        self.today = datetime.date(2026, 7, 10)

    def _message(self, count: int) -> str | None:
        alerts = build_smart_alerts(
            [], 1, self.today, new_rental_inquiries=count
        )
        return next(
            (a["message"] for a in alerts if a["id"] == "new-rental-inquiries"),
            None,
        )

    def test_no_alert_when_there_are_no_new_inquiries(self):
        self.assertIsNone(self._message(0))

    def test_alert_is_singular_for_one(self):
        self.assertEqual(self._message(1), "You have 1 new rental inquiry")

    def test_alert_is_plural_for_many(self):
        self.assertEqual(self._message(3), "You have 3 new rental inquiries")

    def test_alert_links_to_the_new_inquiries(self):
        alerts = build_smart_alerts([], 1, self.today, new_rental_inquiries=1)
        alert = next(a for a in alerts if a["id"] == "new-rental-inquiries")
        self.assertEqual(
            alert["url"], reverse("dashboard:rental_inquiries") + "?status=NEW"
        )


class VoicemailAlertTests(TestCase):
    def setUp(self) -> None:
        self.today = datetime.date(2026, 7, 10)

    def _message(self, count: int) -> str | None:
        alerts = build_smart_alerts([], 1, self.today, new_voicemails=count)
        return next((a["message"] for a in alerts if a["id"] == "new-voicemails"), None)

    def test_no_alert_without_new_voicemails(self):
        self.assertIsNone(self._message(0))

    def test_alert_is_singular_for_one(self):
        self.assertEqual(self._message(1), "You have 1 new voicemail")

    def test_alert_is_plural_for_many(self):
        self.assertEqual(self._message(2), "You have 2 new voicemails")

    def test_alert_links_to_the_new_voicemails(self):
        alerts = build_smart_alerts([], 1, self.today, new_voicemails=1)
        alert = next(a for a in alerts if a["id"] == "new-voicemails")
        self.assertEqual(
            alert["url"], reverse("dashboard:voicemails") + "?status=NEW"
        )

    def _square_ids(self, **kwargs) -> list[str]:
        alerts = build_smart_alerts([], 1, self.today, **kwargs)
        return [a["id"] for a in alerts if a["id"].startswith("square")]

    def test_square_alerts(self) -> None:
        ids = self._square_ids(square_pull_status="FAILED", square_sync_failures=2)
        self.assertIn("square-pull-failed", ids)
        self.assertIn("square-sync-failed", ids)
        missing = build_smart_alerts(
            [], 1, self.today, square_pull_status="MISSING")
        self.assertEqual(missing[0]["message"], "No Square sales pull ran yesterday")
        self.assertEqual(self._square_ids(square_pull_status=None), [])
        self.assertEqual(self._square_ids(square_pull_status="OK"), [])

    def test_incomplete_pull_names_the_online_orders(self) -> None:
        incomplete = build_smart_alerts(
            [], 1, self.today, square_pull_status="INCOMPLETE")
        self.assertEqual(
            [(a["id"], a["type"], a["message"]) for a in incomplete],
            [("square-pull-incomplete", "warning",
              "Yesterday's Square sales pull missed paid online ticket orders")])

    def test_square_sync_failed_message_pluralises(self) -> None:
        one = build_smart_alerts([], 1, self.today, square_sync_failures=1)
        self.assertEqual(one[0]["message"], "1 run failed to sync to Square")
        two = build_smart_alerts([], 1, self.today, square_sync_failures=2)
        self.assertEqual(two[0]["message"], "2 runs failed to sync to Square")

    def test_square_membership_failed_pluralises(self) -> None:
        one = build_smart_alerts([], 1, self.today, square_membership_failures=1)
        self.assertIn(
            "1 Square membership sale needs attention", [a["message"] for a in one])
        two = build_smart_alerts([], 1, self.today, square_membership_failures=2)
        self.assertIn(
            "2 Square membership sales need attention", [a["message"] for a in two])
        self.assertNotIn("square-membership-failed", self._square_ids())


class AdInquiryAlertTests(TestCase):
    def setUp(self) -> None:
        self.today = datetime.date(2026, 7, 10)

    def _alert(self, count: int) -> dict | None:
        alerts = build_smart_alerts([], 1, self.today, new_ad_inquiries=count)
        return next((a for a in alerts if a["id"] == "new-ad-inquiries"), None)

    def test_zero_is_silent(self):
        self.assertIsNone(self._alert(0))

    def test_singular_and_plural(self):
        self.assertEqual(self._alert(1)["message"], "You have 1 new ad inquiry")
        self.assertEqual(self._alert(2)["message"], "You have 2 new ad inquiries")

    def test_links_to_the_list(self):
        self.assertEqual(self._alert(1)["url"], reverse("dashboard:ad_inquiries"))


class TicketAlertQueryTests(TestCase):
    def setUp(self) -> None:
        self.now = timezone.now()

    def test_failures_count_counts_failed_with_or_without_payment(self):
        st = make_showtime()
        make_order(st, status="FAILED")
        make_order(st, status="FAILED", square_payment_id="PAY-1")
        make_order(st, status="PAID", square_payment_id="PAY-2")
        make_order(st, status="EXPIRED")
        # A checkout Square never started needs nobody's attention.
        make_order(st, status="ABANDONED", error="down")
        self.assertEqual(failures_count(), 2)

    def test_nearly_sold_out_at_ninety_percent(self):
        # Default allowance: half of a 100-seat screen = 50.
        tomorrow = make_showtime(starts_at=self.now + datetime.timedelta(days=1))
        make_order(tomorrow, status="PAID", lines={"adult": 45})
        self.assertEqual(nearly_sold_out(self.now), [(tomorrow, 45, 50)])

        tomorrow.ticket_orders.get().lines.update(quantity=44)
        self.assertEqual(nearly_sold_out(self.now), [])

    def test_nearly_sold_out_counts_seats_on_hold(self):
        st = make_showtime(starts_at=self.now + datetime.timedelta(days=1))
        make_order(st, status="PAID", lines={"adult": 40})
        make_order(st, status="PENDING", lines={"adult": 5})
        self.assertEqual(nearly_sold_out(self.now), [(st, 45, 50)])

    def test_nearly_sold_out_only_within_two_days(self):
        three_days = make_showtime(starts_at=self.now + datetime.timedelta(days=3))
        two_days = make_showtime(starts_at=self.now + datetime.timedelta(days=2))
        started = make_showtime(starts_at=self.now - datetime.timedelta(minutes=1))
        for st in (three_days, two_days, started):
            make_order(st, status="PAID", lines={"adult": 50})
        self.assertEqual(nearly_sold_out(self.now), [])

    def test_nearly_sold_out_skips_cancelled_and_zero_allowance(self):
        soon = self.now + datetime.timedelta(hours=5)
        cancelled = make_showtime(starts_at=soon, is_cancelled=True)
        make_order(cancelled, status="PAID", lines={"adult": 50})
        make_showtime(starts_at=soon, online_allowance=0)
        self.assertEqual(nearly_sold_out(self.now), [])

    def test_cancelled_with_orders_past_and_future(self):
        past = make_showtime(
            starts_at=self.now - datetime.timedelta(days=3), is_cancelled=True
        )
        make_order(past, status="PAID", square_payment_id="PAY-1")
        make_order(past, status="PAID", square_payment_id="PAY-2")
        make_order(past, status="REFUNDED", square_payment_id="PAY-3")
        future = make_showtime(is_cancelled=True)
        make_order(future, status="FAILED", square_payment_id="PAY-4")
        refunded = make_showtime(is_cancelled=True)
        make_order(refunded, status="REFUNDED", square_payment_id="PAY-5")
        make_order(refunded, status="FAILED")
        live = make_showtime()
        make_order(live, status="PAID", square_payment_id="PAY-6")
        self.assertEqual(
            sorted(cancelled_with_orders(), key=lambda row: row[0].pk),
            [(past, 2), (future, 1)],
        )


class OnlineTicketAlertTests(TestCase):
    def setUp(self) -> None:
        self.today = datetime.date(2026, 7, 10)
        self.showtime = make_showtime(
            starts_at=datetime.datetime(
                2026, 7, 11, 19, 0, tzinfo=ZoneInfo("America/New_York")
            )
        )

    def _alert(self, alert_id: str, **kwargs) -> dict | None:
        alerts = build_smart_alerts([], 1, self.today, **kwargs)
        return next((a for a in alerts if a["id"] == alert_id), None)

    def test_ticket_failures_alert_singular_and_plural(self):
        self.assertIsNone(self._alert("ticket-failures"))
        one = self._alert("ticket-failures", ticket_failures=1)
        self.assertEqual(one["message"], "1 online ticket order needs attention")
        self.assertEqual(one["type"], "warning")
        self.assertEqual(
            one["url"], reverse("dashboard:ticket_orders") + "?status=FAILED"
        )
        two = self._alert("ticket-failures", ticket_failures=2)
        self.assertEqual(two["message"], "2 online ticket orders need attention")

    def test_nearly_sold_out_alert(self):
        alert = self._alert(
            f"nearly-sold-out-{self.showtime.pk}",
            nearly_sold_out=[(self.showtime, 45, 50)],
        )
        self.assertEqual(
            alert["message"], "Dune at 7:00 PM is nearly sold out online (45 of 50)"
        )
        self.assertEqual(alert["type"], "info")
        self.assertEqual(
            alert["url"], reverse("dashboard:showtime_orders", args=[self.showtime.pk])
        )

    def test_cancelled_with_orders_alert_singular_and_plural(self):
        alert_id = f"cancelled-orders-{self.showtime.pk}"
        one = self._alert(alert_id, cancelled_with_orders=[(self.showtime, 1)])
        self.assertEqual(
            one["message"],
            "Dune at 7:00 PM is cancelled with 1 unrefunded online order",
        )
        self.assertEqual(one["type"], "warning")
        self.assertEqual(
            one["url"], reverse("dashboard:showtime_orders", args=[self.showtime.pk])
        )
        two = self._alert(alert_id, cancelled_with_orders=[(self.showtime, 3)])
        self.assertEqual(
            two["message"],
            "Dune at 7:00 PM is cancelled with 3 unrefunded online orders",
        )
