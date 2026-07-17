import io
from datetime import date, datetime
from unittest import mock

from cinema.management.commands import backfill_past_films as cmd
from cinema.models import Engagement, EngagementFilm, Film, Screen, Showtime
from django.core.management import call_command
from django.test import TestCase
from django.utils import timezone


class HelperTests(TestCase):
    def test_regular_film_kind(self) -> None:
        entry = {"type": "Film", "notes": ""}
        self.assertEqual(cmd.engagement_kind(entry), Engagement.Kind.REGULAR)

    def test_special_classic_kind(self) -> None:
        entry = {"type": "Special screening", "notes": "Classic re-release"}
        self.assertEqual(cmd.engagement_kind(entry), Engagement.Kind.CLASSIC)

    def test_special_event_kind(self) -> None:
        entry = {"type": "Special screening", "notes": "Interactive event screening"}
        self.assertEqual(cmd.engagement_kind(entry), Engagement.Kind.SPECIAL_EVENT)

    def test_daterange_is_inclusive(self) -> None:
        days = list(cmd.daterange(date(2024, 1, 1), date(2024, 1, 3)))
        self.assertEqual(days, [date(2024, 1, 1), date(2024, 1, 2), date(2024, 1, 3)])

    def test_films_dataset_loaded(self) -> None:
        self.assertEqual(len(cmd.FILMS), 90)
        self.assertEqual(cmd.FILMS[0]["title"], "Despicable Me 4")


class FindFreeSlotTests(TestCase):
    def setUp(self) -> None:
        self.a = Screen.objects.create(name="The Century", capacity=1)
        self.b = Screen.objects.create(name="The Savoy", capacity=1)
        self.screens = [self.a, self.b]

    def _at(self, hour: int) -> datetime:
        return timezone.make_aware(datetime(2024, 1, 1, hour, 0))

    def test_prefers_3pm_on_preferred_screen(self) -> None:
        screen, when = cmd.find_free_slot(set(), date(2024, 1, 1), self.screens, 0)
        self.assertEqual(screen, self.a)
        self.assertEqual(when, self._at(15))

    def test_rotates_preferred_screen(self) -> None:
        screen, when = cmd.find_free_slot(set(), date(2024, 1, 1), self.screens, 1)
        self.assertEqual(screen, self.b)
        self.assertEqual(when, self._at(15))

    def test_falls_back_to_other_screen_at_same_hour(self) -> None:
        taken = {(self.a.id, self._at(15))}
        screen, when = cmd.find_free_slot(taken, date(2024, 1, 1), self.screens, 0)
        self.assertEqual(screen, self.b)
        self.assertEqual(when, self._at(15))

    def test_falls_back_to_later_hour_when_both_screens_taken(self) -> None:
        taken = {(self.a.id, self._at(15)), (self.b.id, self._at(15))}
        screen, when = cmd.find_free_slot(taken, date(2024, 1, 1), self.screens, 0)
        self.assertEqual(screen, self.a)
        self.assertEqual(when, self._at(16))


TMDB_DETAILS = {
    "tmdb_id": 555, "title": "Newish Movie", "release_date": "2024-06-01",
    "overview": "o", "poster_path": "https://img/p.jpg", "backdrop_path": "https://img/b.jpg",
    "runtime": 100, "genres": ["Action"], "imdb_id": "tt555",
}


def _entry(**over):
    base = {
        "title": "Newish Movie", "type": "Film",
        "startDate": "2024-06-01", "endDate": "2024-06-03",
        "daysWithSales": 3, "ticketsSold": 10, "notes": "",
    }
    base.update(over)
    return base


class BackfillHandleTests(TestCase):
    def setUp(self) -> None:
        self.a = Screen.objects.create(name="The Century", capacity=1)
        self.b = Screen.objects.create(name="The Savoy", capacity=1)

    def _mock_service(self, search_results=None, details=TMDB_DETAILS):
        svc = mock.Mock()
        svc.search_films.return_value = (
            [{"tmdb_id": 555, "title": "Newish Movie", "release_date": "2024-06-01"}]
            if search_results is None else search_results
        )
        svc.get_film_details.return_value = details
        return svc

    def _run(self, films, svc, **opts):
        with mock.patch.object(cmd, "FILMS", films), \
             mock.patch.object(cmd, "TMDBService", return_value=svc), \
             mock.patch.object(cmd.time, "sleep"):
            call_command("backfill_past_films", stdout=io.StringIO(), **opts)

    def test_creates_film_engagement_and_showtimes(self) -> None:
        svc = self._mock_service()
        self._run([_entry(ticketsSold=472)], svc)
        film = Film.objects.get(tmdb_id="555")
        eng = Engagement.objects.get()
        self.assertEqual(eng.status, "CONFIRMED")
        self.assertEqual(eng.kind, Engagement.Kind.REGULAR)
        self.assertTrue(eng.show_in_main_listings)
        self.assertEqual(eng.admissions, 472)  # ticketsSold captured
        self.assertEqual(list(eng.films.all()), [film])
        self.assertEqual(Showtime.objects.count(), 3)  # one per date
        for st in Showtime.objects.all():
            self.assertEqual(st.starts_at.astimezone(timezone.get_current_timezone()).hour, 15)

    def test_skips_film_with_existing_engagement(self) -> None:
        film = Film.objects.create(title="Newish Movie")
        eng = Engagement.objects.create(screen=self.a, start_date=date(2024, 6, 1), end_date=date(2024, 6, 3))
        EngagementFilm.objects.create(engagement=eng, film=film, position=1)
        svc = self._mock_service()
        self._run([_entry()], svc)
        svc.search_films.assert_not_called()
        self.assertEqual(Engagement.objects.count(), 1)  # no new engagement
        self.assertEqual(Film.objects.count(), 1)

    def test_title_only_when_no_tmdb_match(self) -> None:
        svc = self._mock_service(search_results=[])
        self._run([_entry(title="Classic Movie (various)")], svc)
        film = Film.objects.get(title="Classic Movie (various)")
        self.assertIsNone(film.tmdb_id)
        self.assertEqual(film.engagements.count(), 1)

    def test_special_screening_is_classic_and_hidden(self) -> None:
        svc = self._mock_service()
        self._run([_entry(type="Special screening", notes="Classic re-release")], svc)
        eng = Engagement.objects.get()
        self.assertEqual(eng.kind, Engagement.Kind.CLASSIC)
        self.assertFalse(eng.show_in_main_listings)

    def test_overlapping_runs_do_not_collide(self) -> None:
        svc = self._mock_service()
        one = _entry(title="Film One")
        two = _entry(title="Film Two")
        # first film -> tmdb 555, second -> 777; same dates, must not clash
        def search(title, *a, **k):
            return ([{"tmdb_id": 777, "title": "Film Two", "release_date": "2024-06-01"}]
                    if title == "Film Two"
                    else [{"tmdb_id": 555, "title": "Film One", "release_date": "2024-06-01"}])
        def details(tmdb_id, *a, **k):
            return {**TMDB_DETAILS, "tmdb_id": tmdb_id, "imdb_id": f"tt{tmdb_id}",
                    "title": "Film Two" if tmdb_id == 777 else "Film One"}
        svc.search_films.side_effect = search
        svc.get_film_details.side_effect = details
        self._run([one, two], svc)
        self.assertEqual(Showtime.objects.count(), 6)  # 3 + 3, no collisions
        # each date has both screens used once at 15:00
        first_day = [s for s in Showtime.objects.all()
                     if s.starts_at.astimezone(timezone.get_current_timezone()).date() == date(2024, 6, 1)]
        self.assertEqual({s.screen_id for s in first_day}, {self.a.id, self.b.id})

    def test_dry_run_writes_nothing(self) -> None:
        svc = self._mock_service()
        self._run([_entry()], svc, dry_run=True)
        self.assertEqual(Film.objects.count(), 0)
        self.assertEqual(Engagement.objects.count(), 0)
        self.assertEqual(Showtime.objects.count(), 0)
        svc.search_films.assert_called_once()  # still looks up to preview the match

    def test_title_only_film_rolled_back_on_failure(self) -> None:
        # A mid-transaction failure rolls back the title-only Film, and the run
        # keeps going rather than aborting the whole command.
        svc = self._mock_service(search_results=[])  # forces title-only path
        with mock.patch.object(cmd.Engagement.objects, "create", side_effect=RuntimeError("boom")):
            self._run([_entry(title="Doomed Run")], svc)  # does not raise
        self.assertEqual(Film.objects.filter(title="Doomed Run").count(), 0)

    def test_one_failed_entry_does_not_abort_run(self) -> None:
        # The first entry blows up; the second must still be backfilled instead of
        # the whole command dying on the first bad film.
        svc = self._mock_service()

        def search(title, *a, **k):
            tmdb = 111 if title == "Bad Movie" else 555
            return [{"tmdb_id": tmdb, "title": title, "release_date": "2024-06-01"}]

        def details(tmdb_id, *a, **k):
            return {**TMDB_DETAILS, "tmdb_id": tmdb_id, "imdb_id": f"tt{tmdb_id}"}

        svc.search_films.side_effect = search
        svc.get_film_details.side_effect = details

        real_slot = cmd.find_free_slot

        def flaky_slot(taken, day, screens, index):
            if index == 0:  # index is the FILMS position -> only the first entry fails
                raise RuntimeError("boom")
            return real_slot(taken, day, screens, index)

        with mock.patch.object(cmd, "find_free_slot", side_effect=flaky_slot):
            self._run([_entry(title="Bad Movie"), _entry(title="Good Movie")], svc)

        # Good entry fully processed despite the first one failing.
        good = Film.objects.get(tmdb_id="555")
        self.assertEqual(good.engagements.count(), 1)
        self.assertEqual(Showtime.objects.count(), 3)
        # Bad entry left no engagement behind.
        self.assertFalse(Engagement.objects.filter(films__tmdb_id="111").exists())
