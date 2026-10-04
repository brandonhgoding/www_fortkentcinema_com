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


class InquiryAlertTests(TestCase):
    def setUp(self) -> None:
        self.today = datetime.date(2026, 7, 10)

    def test_no_alert_when_there_are_no_new_inquiries(self):
        ids = [
            a["id"]
            for a in build_smart_alerts([], 1, self.today, new_inquiries=0)
        ]
        self.assertNotIn("new-sponsorship-inquiries", ids)

    def test_alert_is_singular_for_one(self):
        alerts = build_smart_alerts([], 1, self.today, new_inquiries=1)
        message = next(
            a["message"] for a in alerts if a["id"] == "new-sponsorship-inquiries"
        )
        self.assertEqual(message, "You have 1 new sponsorship inquiry")

    def test_alert_is_plural_for_many(self):
        alerts = build_smart_alerts([], 1, self.today, new_inquiries=3)
        message = next(
            a["message"] for a in alerts if a["id"] == "new-sponsorship-inquiries"
        )
        self.assertEqual(message, "You have 3 new sponsorship inquiries")

    def test_existing_callers_without_the_argument_still_work(self):
        # The new parameter has a default, so every existing call site and the
        # pre-existing tests above keep working unchanged.
        self.assertEqual(build_smart_alerts([], 1, self.today), [])


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
