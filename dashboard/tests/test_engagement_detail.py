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

    def test_status_badge_uses_design_system_pill(self) -> None:
        """Regression: the status badge must carry a modifier the CSS defines.

        It used to be a page-local statusConfirmed class; the dashboard now
        has one status pill, design-system.css's .status-badge, whose
        modifiers are the lower-cased status value.
        """
        eng = make_eng(self.screen, films=[self.film], status="CONFIRMED")
        html = self.client.get(reverse("dashboard:engagement_detail", args=[eng.pk])).content.decode()
        self.assertIn('class="status-badge status-confirmed"', html)
        # Not the raw value, which no rule matches.
        self.assertNotIn("status-CONFIRMED", html)


from cinema.models import Showtime
import datetime as _dt
from django.utils import timezone


class ShowtimeListTests(TestCase):
    def setUp(self) -> None:
        User.objects.create_user(username="s", password="pw12345", is_staff=True)
        self.client.login(username="s", password="pw12345")
        self.screen = Screen.objects.create(name="Screen 1", capacity=100)
        self.film = Film.objects.create(title="Dune", runtime_minutes=155)
        self.eng = make_eng(self.screen, films=[self.film])

    def _url(self, eng):
        return reverse("dashboard:engagement_detail", args=[eng.pk])

    def test_empty_state(self) -> None:
        html = self.client.get(self._url(self.eng)).content.decode()
        self.assertIn("No showtimes scheduled", html)

    def test_lists_showtimes_with_badges(self) -> None:
        aware = timezone.make_aware(_dt.datetime(2026, 7, 4, 19, 0))
        Showtime.objects.create(engagement=self.eng, starts_at=aware, captions="CC")
        Showtime.objects.create(
            engagement=self.eng, starts_at=timezone.make_aware(_dt.datetime(2026, 7, 5, 19, 0)),
            is_cancelled=True)
        html = self.client.get(self._url(self.eng)).content.decode()
        self.assertIn("CC", html)             # captions badge
        self.assertIn("Cancelled", html)      # cancelled badge
        self.assertIn("Active", html)         # active badge


from zoneinfo import ZoneInfo

TZ = ZoneInfo("America/New_York")


class ShowtimeCreateEditTests(TestCase):
    def setUp(self) -> None:
        User.objects.create_user(username="s", password="pw12345", is_staff=True)
        self.client.login(username="s", password="pw12345")
        self.screen = Screen.objects.create(name="Screen 1", capacity=100)
        self.film = Film.objects.create(title="Dune", runtime_minutes=155)
        self.eng = make_eng(self.screen, films=[self.film])

    def test_get_form(self) -> None:
        html = self.client.get(reverse("dashboard:showtime_create", args=[self.eng.pk])).content.decode()
        self.assertIn('id="showtime-form"', html)
        self.assertIn("Create Showtime", html)

    def test_create_combines_tz_aware(self) -> None:
        resp = self.client.post(reverse("dashboard:showtime_create", args=[self.eng.pk]),
                                {"date": "2026-07-04", "time": "19:30", "captions": ""})
        self.assertEqual(resp.status_code, 200)
        st = Showtime.objects.get()
        local = st.starts_at.astimezone(TZ)
        self.assertEqual((local.hour, local.minute), (19, 30))
        self.assertEqual(st.screen_id, self.screen.id)  # defaulted from engagement
        self.assertIn("close-drawer", resp["HX-Trigger"])

    def test_create_overlap_rejected(self) -> None:
        import datetime as d
        from django.utils import timezone
        Showtime.objects.create(engagement=self.eng,
                                starts_at=timezone.make_aware(d.datetime(2026, 7, 4, 19, 0)))
        resp = self.client.post(reverse("dashboard:showtime_create", args=[self.eng.pk]),
                                {"date": "2026-07-04", "time": "20:00", "captions": ""})
        self.assertEqual(Showtime.objects.count(), 1)  # not created
        self.assertIn("overlaps with", resp.content.decode())

    def test_edit_cancel_skips_overlap(self) -> None:
        import datetime as d
        from django.utils import timezone
        a = Showtime.objects.create(engagement=self.eng,
                                    starts_at=timezone.make_aware(d.datetime(2026, 7, 4, 19, 0)))
        # editing 'a' to cancelled must not conflict with itself/others
        resp = self.client.post(reverse("dashboard:showtime_edit", args=[a.pk]),
                                {"date": "2026-07-04", "time": "19:00", "captions": "", "is_cancelled": "on"})
        self.assertEqual(resp.status_code, 200)
        a.refresh_from_db()
        self.assertTrue(a.is_cancelled)


class ShowtimeDeleteTests(TestCase):
    def setUp(self) -> None:
        User.objects.create_user(username="s", password="pw12345", is_staff=True)
        self.client.login(username="s", password="pw12345")
        self.screen = Screen.objects.create(name="Screen 1", capacity=100)
        self.film = Film.objects.create(title="Dune", runtime_minutes=155)
        self.eng = make_eng(self.screen, films=[self.film])

    def test_delete(self) -> None:
        import datetime as d
        from django.utils import timezone
        st = Showtime.objects.create(engagement=self.eng,
                                     starts_at=timezone.make_aware(d.datetime(2026, 7, 4, 19, 0)))
        resp = self.client.post(reverse("dashboard:showtime_delete", args=[st.pk]))
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(Showtime.objects.filter(pk=st.pk).exists())
        self.assertIn("dashboard-toast", resp["HX-Trigger"])


class ShowtimeBulkTests(TestCase):
    def setUp(self) -> None:
        User.objects.create_user(username="s", password="pw12345", is_staff=True)
        self.client.login(username="s", password="pw12345")
        self.screen = Screen.objects.create(name="Screen 1", capacity=100)
        self.film = Film.objects.create(title="Dune", runtime_minutes=100)
        self.eng = make_eng(self.screen, films=[self.film])

    def test_get_bulk_form(self) -> None:
        html = self.client.get(reverse("dashboard:showtime_bulk", args=[self.eng.pk])).content.decode()
        self.assertIn('id="bulk-showtime-form"', html)
        self.assertIn("bulkShowtimeForm", html)

    def test_bulk_creates_grid(self) -> None:
        resp = self.client.post(reverse("dashboard:showtime_bulk", args=[self.eng.pk]),
                                {"start_date": "2026-07-01", "end_date": "2026-07-03",
                                 "times": ["13:00", "19:00"], "captions": ""})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(Showtime.objects.count(), 6)  # 3 days x 2 times
        self.assertIn("close-drawer", resp["HX-Trigger"])

    def test_bulk_rejects_overlap(self) -> None:
        # two times 30 min apart with a 100-min film overlap -> whole batch rejected
        resp = self.client.post(reverse("dashboard:showtime_bulk", args=[self.eng.pk]),
                                {"start_date": "2026-07-01", "end_date": "2026-07-01",
                                 "times": ["19:00", "19:30"], "captions": ""})
        self.assertEqual(Showtime.objects.count(), 0)
        self.assertIn("overlaps with", resp.content.decode())

    def test_bulk_requires_times(self) -> None:
        resp = self.client.post(reverse("dashboard:showtime_bulk", args=[self.eng.pk]),
                                {"start_date": "2026-07-01", "end_date": "2026-07-01",
                                 "times": ["", ""], "captions": ""})
        self.assertEqual(Showtime.objects.count(), 0)
        self.assertIn("at least one time", resp.content.decode().lower())
