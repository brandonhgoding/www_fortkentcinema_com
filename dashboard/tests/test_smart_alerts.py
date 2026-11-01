import datetime

from cinema.models import Engagement, EngagementFilm, Film, Screen
from dashboard.smart_alerts import build_smart_alerts
from django.test import TestCase
from django.urls import reverse


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

    def test_draft_count(self) -> None:
        make_eng(self.screen, self.film, end=datetime.date(2026, 7, 20), status="DRAFT")
        make_eng(self.screen, self.film, end=datetime.date(2026, 7, 20), status="DRAFT")
        alerts = build_smart_alerts(Engagement.objects.all(), 5, self.today)
        alert = next(a for a in alerts if a["id"] == "draft-engagements")
        self.assertIn("2", alert["message"])

    def test_clean_state_no_alerts(self) -> None:
        make_eng(self.screen, self.film, end=datetime.date(2026, 7, 20))  # confirmed, far end
        alerts = build_smart_alerts(Engagement.objects.all(), 5, self.today)
        self.assertEqual(alerts, [])


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

    def test_alert_carries_the_count(self):
        self.assertIn("3", self._message(3))

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

    def test_alert_carries_the_count(self):
        self.assertIn("2", self._message(2))

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
        self.assertEqual(
            self._square_ids(square_pull_status="MISSING"), ["square-pull-missing"]
        )
        self.assertEqual(self._square_ids(square_pull_status=None), [])
        self.assertEqual(self._square_ids(square_pull_status="OK"), [])

    def test_square_sync_failed_message_carries_the_count(self) -> None:
        alerts = build_smart_alerts([], 1, self.today, square_sync_failures=2)
        alert = next(a for a in alerts if a["id"] == "square-sync-failed")
        self.assertIn("2", alert["message"])


class AdInquiryAlertTests(TestCase):
    def setUp(self) -> None:
        self.today = datetime.date(2026, 7, 10)

    def _alert(self, count: int) -> dict | None:
        alerts = build_smart_alerts([], 1, self.today, new_ad_inquiries=count)
        return next((a for a in alerts if a["id"] == "new-ad-inquiries"), None)

    def test_zero_is_silent(self):
        self.assertIsNone(self._alert(0))

    def test_alert_carries_the_count(self):
        self.assertIn("2", self._alert(2)["message"])

    def test_links_to_the_list(self):
        self.assertEqual(self._alert(1)["url"], reverse("dashboard:ad_inquiries"))


class AlertPermTests(TestCase):
    def test_every_alert_carries_a_perm(self):
        today = datetime.date(2026, 7, 10)
        screen = Screen.objects.create(name="S1", capacity=50)
        film = Film.objects.create(title="Dune")
        engagements = [
            make_eng(screen, film, end=today + datetime.timedelta(days=1)),
            make_eng(screen, film, end=today + datetime.timedelta(days=30),
                     status="DRAFT"),
        ]
        alerts = build_smart_alerts(
            engagements, 0, today,
            new_rental_inquiries=1, new_ad_inquiries=1, new_voicemails=1,
            square_pull_status="FAILED", square_sync_failures=1,
        )
        by_prefix = {
            "no-showtimes-tomorrow": "cinema.view_showtime",
            "ending-soon-": "cinema.view_engagement",
            "draft-engagements": "cinema.view_engagement",
            "new-rental-inquiries": "cinema.view_rentalinquiry",
            "new-ad-inquiries": "cinema.view_adinquiry",
            "new-voicemails": "phone.view_voicemail",
            "square-pull-": "boxoffice.view_salespull",
            "square-sync-failed": "cinema.view_engagement",
        }
        self.assertEqual(len(alerts), 8)
        for alert in alerts:
            expected = next(
                perm for prefix, perm in by_prefix.items()
                if alert["id"].startswith(prefix)
            )
            self.assertEqual(alert["perm"], expected, alert["id"])
