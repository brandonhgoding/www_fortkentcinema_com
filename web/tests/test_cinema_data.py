import datetime

from cinema.models import Engagement, EngagementFilm, Film, Screen, Showtime
from django.test import TestCase
from django.utils import timezone

from web.services.cinema_data import (
    _format_runtime,
    get_calendar_month,
    get_coming_soon,
)


def make_screen():
    return Screen.objects.create(name="Screen 1", capacity=100)


def make_film(title="Dune", **kw):
    return Film.objects.create(title=title, **kw)


def make_engagement(screen, films, *, start, end, status="CONFIRMED", kind="REGULAR",
                    show=True, display_title="", free_for_members=False):
    eng = Engagement.objects.create(
        screen=screen, start_date=start, end_date=end, status=status, kind=kind,
        show_in_main_listings=show, display_title=display_title,
        is_free_for_members=free_for_members,
    )
    for i, f in enumerate(films, start=1):
        EngagementFilm.objects.create(engagement=eng, film=f, position=i)
    return eng


def aware(y, mo, d, hh, mm=0):
    return timezone.make_aware(datetime.datetime(y, mo, d, hh, mm))


class FormatRuntimeTests(TestCase):
    def test_format(self) -> None:
        self.assertEqual(_format_runtime(None), "")
        self.assertEqual(_format_runtime(0), "")
        self.assertEqual(_format_runtime(40), "40min")
        self.assertEqual(_format_runtime(60), "1h")
        self.assertEqual(_format_runtime(100), "1h 40min")


class ComingSoonTests(TestCase):
    def setUp(self) -> None:
        self.screen = make_screen()
        self.today = timezone.localdate()
        self.a = make_film("Alpha", runtime_minutes=90, synopsis="a-syn",
                           poster_url="http://p/a.jpg", youtube_id="yta")
        self.b = make_film("Beta", runtime_minutes=100, poster_url="http://p/b.jpg")

    def _future(self, films, days=3, **kw):
        s = self.today + datetime.timedelta(days=days)
        return make_engagement(self.screen, films, start=s, end=s + datetime.timedelta(days=2), **kw)

    def test_future_returned(self) -> None:
        self._future([self.a])
        out = get_coming_soon()
        self.assertEqual(len(out), 1)
        m = out[0]
        self.assertEqual(m["title"], "Alpha")
        self.assertEqual(m["genre"], "")
        self.assertEqual(m["poster"], "http://p/a.jpg")
        self.assertEqual(m["description"], "a-syn")
        self.assertEqual(m["youtube_id"], "yta")
        self.assertEqual(
            m["films"],
            [{"id": self.a.id, "title": "Alpha", "poster": "http://p/a.jpg"}],
        )
        self.assertEqual(m["start_date"], (self.today + datetime.timedelta(days=3)).isoformat())

    def test_classic_included(self) -> None:
        # Classic Movie Night was discontinued and /classics/ removed, so a
        # leftover CLASSIC engagement has to surface here or it is invisible.
        self._future([self.a], kind="CLASSIC")
        out = get_coming_soon()
        self.assertEqual([m["title"] for m in out], ["Alpha"])

    def test_dedup_by_film_set(self) -> None:
        self._future([self.a], days=3)
        self._future([self.a], days=5)   # same film -> deduped
        self._future([self.a, self.b], days=6, kind="DOUBLE_FEATURE")  # distinct set -> kept
        out = get_coming_soon()
        self.assertEqual(len(out), 2)
        # the single-Alpha runs collapse to one; the double feature survives as its own set
        self.assertEqual(sorted(m["title"] for m in out), ["Alpha", "Alpha + Beta"])

    def test_release_date_format(self) -> None:
        s = self.today + datetime.timedelta(days=3)
        self._future([self.a], days=3)
        expected = s.strftime("%B %-d")
        self.assertEqual(get_coming_soon()[0]["release_date"], expected)


class CalendarMonthTests(TestCase):
    def setUp(self) -> None:
        self.screen = make_screen()
        self.film = make_film("Dune", poster_url="http://p/d.jpg", youtube_id="yt1")
        self.eng = make_engagement(self.screen, [self.film],
                                   start=datetime.date(2026, 6, 1), end=datetime.date(2026, 6, 30))

    def test_groups_by_local_day(self) -> None:
        Showtime.objects.create(engagement=self.eng, starts_at=aware(2026, 6, 4, 13, 0))
        Showtime.objects.create(engagement=self.eng, starts_at=aware(2026, 6, 4, 19, 0))  # same day, dedup by title
        Showtime.objects.create(engagement=self.eng, starts_at=aware(2026, 6, 10, 19, 0))
        data = get_calendar_month(2026, 5)  # month 5 == June (0-based)
        self.assertEqual(sorted(data.keys()), [4, 10])
        self.assertEqual(len(data[4]), 1)  # deduped per day by title
        self.assertEqual(data[4][0]["title"], "Dune")
        self.assertEqual(data[4][0]["poster"], "http://p/d.jpg")
        self.assertEqual(data[4][0]["youtube_id"], "yt1")

    def test_late_night_local_day(self) -> None:
        # 23:00 local on the 15th stays on the 15th (not the 16th UTC)
        Showtime.objects.create(engagement=self.eng, starts_at=aware(2026, 6, 15, 23, 0))
        data = get_calendar_month(2026, 5)
        self.assertIn(15, data)

    def test_empty_month(self) -> None:
        self.assertEqual(get_calendar_month(2026, 0), {})  # January, no showtimes

    def test_unannounced_runs_stay_off_the_calendar(self) -> None:
        # A draft or cancelled booking keeps its showtimes un-cancelled, so
        # the showtime flag alone would publish it.
        for status, day in [("DRAFT", 5), ("CANCELLED", 6)]:
            eng = make_engagement(self.screen, [make_film(status)], status=status,
                                  start=datetime.date(2026, 6, 1),
                                  end=datetime.date(2026, 6, 30))
            Showtime.objects.create(engagement=eng, starts_at=aware(2026, 6, day, 19))
        self.assertEqual(get_calendar_month(2026, 5), {})

    def test_ended_runs_stay_on_past_months(self) -> None:
        self.eng.status = "ENDED"
        self.eng.save()
        Showtime.objects.create(engagement=self.eng, starts_at=aware(2026, 6, 4, 19, 0))
        self.assertIn(4, get_calendar_month(2026, 5))


class ComingSoonScheduleTests(TestCase):
    """Each Coming Soon card carries `upcoming`: its runs' not-yet-started
    showtimes grouped by local date, in the chip shape the hero uses, so the
    card can sell tickets for a run beyond the hero's week."""

    def setUp(self) -> None:
        self.screen = make_screen()
        self.today = timezone.localdate()
        self.film = make_film("Alpha")

    def _run(self, days, length=2):
        start = self.today + datetime.timedelta(days=days)
        return make_engagement(self.screen, [self.film], start=start,
                               end=start + datetime.timedelta(days=length))

    def _showtime(self, eng, days, hour, **kw):
        day = self.today + datetime.timedelta(days=days)
        when = timezone.make_aware(datetime.datetime.combine(day, datetime.time(hour)))
        return Showtime.objects.create(engagement=eng, starts_at=when, **kw)

    def test_rows_grouped_by_local_date_in_order(self) -> None:
        eng = self._run(10)
        late = self._showtime(eng, 11, 19)
        first = self._showtime(eng, 10, 13)
        second = self._showtime(eng, 10, 19, captions="OC")
        (card,) = get_coming_soon()
        d10 = (self.today + datetime.timedelta(days=10)).isoformat()
        d11 = (self.today + datetime.timedelta(days=11)).isoformat()
        self.assertEqual([row["key"] for row in card["upcoming"]], [d10, d11])
        self.assertEqual(
            [t["showtime_id"] for t in card["upcoming"][0]["times"]],
            [first.pk, second.pk],
        )
        self.assertEqual(
            [t["showtime_id"] for t in card["upcoming"][1]["times"]], [late.pk]
        )
        oc = card["upcoming"][0]["times"][1]
        self.assertEqual(oc["time"], "7:00 PM")
        self.assertEqual(oc["captions"], "OC")
        self.assertEqual(oc["captions_label"], "Open Captions")
        self.assertTrue(oc["iso"].startswith(d10))

    def test_deduped_runs_merge_their_showtimes_onto_the_one_card(self) -> None:
        early = self._run(3)
        later = self._run(20)
        a = self._showtime(early, 3, 19)
        b = self._showtime(later, 20, 19)
        (card,) = get_coming_soon()
        self.assertEqual(
            [t["showtime_id"] for row in card["upcoming"] for t in row["times"]],
            [a.pk, b.pk],
        )

    def test_cancelled_showtimes_are_left_out(self) -> None:
        eng = self._run(10)
        self._showtime(eng, 10, 19, is_cancelled=True)
        kept = self._showtime(eng, 11, 19)
        (card,) = get_coming_soon()
        self.assertEqual(
            [t["showtime_id"] for row in card["upcoming"] for t in row["times"]],
            [kept.pk],
        )

    def test_a_run_hidden_from_the_listings_has_no_schedule(self) -> None:
        # The card was always shown for a hidden run; its showtimes are not
        # listed anywhere (the ticket page 404s them), so no chips either.
        start = self.today + datetime.timedelta(days=10)
        eng = make_engagement(self.screen, [self.film], start=start,
                              end=start + datetime.timedelta(days=2), show=False)
        self._showtime(eng, 10, 19)
        (card,) = get_coming_soon()
        self.assertEqual(card["upcoming"], [])

    def test_a_run_with_no_showtimes_has_an_empty_schedule(self) -> None:
        self._run(10)
        (card,) = get_coming_soon()
        self.assertEqual(card["upcoming"], [])

    def test_showtimes_already_started_are_left_out(self) -> None:
        # The run starts tomorrow, but a showtime stamped in the past (a
        # dashboard slip) must not be offered for sale.
        eng = self._run(1)
        past = Showtime.objects.create(
            engagement=eng, starts_at=timezone.now() - datetime.timedelta(hours=1)
        )
        kept = self._showtime(eng, 1, 19)
        (card,) = get_coming_soon()
        ids = [t["showtime_id"] for row in card["upcoming"] for t in row["times"]]
        self.assertEqual(ids, [kept.pk])
        self.assertNotIn(past.pk, ids)


class CalendarMonthTimesTests(TestCase):
    """Each day's film entry on the calendar carries `times`: that day's
    showtimes for the film in the chip shape, so a poster can open the
    day's times. Cancelled showtimes and runs hidden from the main listings
    get none, as on the Coming Soon card."""

    def setUp(self) -> None:
        self.screen = make_screen()
        self.film = make_film("Dune")
        self.eng = make_engagement(self.screen, [self.film],
                                   start=datetime.date(2026, 6, 1),
                                   end=datetime.date(2026, 6, 30))

    def _day(self, d):
        return get_calendar_month(2026, 5)[d]

    def test_times_of_the_day_in_order(self) -> None:
        late = Showtime.objects.create(
            engagement=self.eng, starts_at=aware(2026, 6, 4, 19)
        )
        early = Showtime.objects.create(
            engagement=self.eng, starts_at=aware(2026, 6, 4, 13), captions="OC"
        )
        (movie,) = self._day(4)
        self.assertEqual(
            [t["showtime_id"] for t in movie["times"]], [early.pk, late.pk]
        )
        self.assertEqual(movie["times"][0]["time"], "1:00 PM")
        self.assertEqual(movie["times"][0]["captions"], "OC")
        self.assertEqual(movie["times"][0]["captions_label"], "Open Captions")

    def test_two_runs_of_one_title_merge_their_times_on_the_day(self) -> None:
        other = make_engagement(self.screen, [self.film],
                                start=datetime.date(2026, 6, 1),
                                end=datetime.date(2026, 6, 30))
        a = Showtime.objects.create(
            engagement=self.eng, starts_at=aware(2026, 6, 4, 13)
        )
        b = Showtime.objects.create(
            engagement=other, starts_at=aware(2026, 6, 4, 19)
        )
        (movie,) = self._day(4)
        self.assertEqual([t["showtime_id"] for t in movie["times"]], [a.pk, b.pk])

    def test_cancelled_showtimes_are_left_out(self) -> None:
        Showtime.objects.create(
            engagement=self.eng, starts_at=aware(2026, 6, 4, 13), is_cancelled=True
        )
        kept = Showtime.objects.create(
            engagement=self.eng, starts_at=aware(2026, 6, 4, 19)
        )
        (movie,) = self._day(4)
        self.assertEqual([t["showtime_id"] for t in movie["times"]], [kept.pk])

    def test_a_hidden_run_is_on_the_calendar_with_no_times(self) -> None:
        self.eng.show_in_main_listings = False
        self.eng.save()
        Showtime.objects.create(engagement=self.eng, starts_at=aware(2026, 6, 4, 19))
        (movie,) = self._day(4)
        self.assertEqual(movie["title"], "Dune")
        self.assertEqual(movie["times"], [])
