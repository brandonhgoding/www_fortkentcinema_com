import datetime

from cinema.models import Engagement, EngagementFilm, Film, Screen
from dashboard.smart_alerts import build_smart_alerts
from django.test import TestCase


def make_eng(screen, film, *, end, status="CONFIRMED", start=None, title=None):
    eng = Engagement.objects.create(
        screen=screen, start_date=start or datetime.date(2026, 7, 1), end_date=end,
        status=status, event_title=title or "",
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
