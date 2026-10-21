import datetime
from unittest.mock import patch

from cinema.models import EngagementFilm, Film, Screen
from django.test import TestCase
from phone.speech import hours_and_prices_speech, showtimes_speech
from web.constants import SITE_CONFIG, TICKET_PRICES

from .helpers import add_showtime, at, make_engagement

SUNDAY = datetime.date(2026, 10, 4)


class ShowtimesSpeechTests(TestCase):
    def setUp(self) -> None:
        self.hamnet = make_engagement(
            "Hamnet", SUNDAY, SUNDAY + datetime.timedelta(days=7)
        )

    def test_reads_todays_shows_grouped_by_title_in_eastern_time(self) -> None:
        # A second screen, because (screen, starts_at) is unique.
        weapons = make_engagement(
            "Weapons",
            SUNDAY,
            SUNDAY,
            screen=Screen.objects.create(name="Screen 2", capacity=40),
            is_free_for_members=True,
        )
        add_showtime(self.hamnet, at(2026, 10, 4, 16))
        add_showtime(self.hamnet, at(2026, 10, 4, 19, 15))
        add_showtime(weapons, at(2026, 10, 4, 19, 15))

        self.assertEqual(
            showtimes_speech(now=at(2026, 10, 4, 12)),
            "Today's showtimes: Hamnet at 4:00 PM and 7:15 PM. "
            "Weapons, free for members, at 7:15 PM.",
        )

    def test_a_double_feature_is_read_with_and_not_plus(self) -> None:
        # Engagement.title joins films with " + " for the listings; Polly
        # would read that as "plus" or drop it.
        for position, title in ((2, "Weapons"), (3, "Sinners")):
            EngagementFilm.objects.create(
                engagement=self.hamnet,
                film=Film.objects.create(title=title),
                position=position,
            )
        add_showtime(self.hamnet, at(2026, 10, 4, 19))
        self.assertEqual(
            showtimes_speech(now=at(2026, 10, 4, 12)),
            "Today's showtimes: Hamnet, Weapons, and Sinners at 7:00 PM.",
        )

    def test_a_display_title_is_read_as_written(self) -> None:
        self.hamnet.display_title = "Halloween Double Feature"
        self.hamnet.save()
        EngagementFilm.objects.create(
            engagement=self.hamnet,
            film=Film.objects.create(title="Weapons"),
            position=2,
        )
        add_showtime(self.hamnet, at(2026, 10, 4, 19))
        self.assertEqual(
            showtimes_speech(now=at(2026, 10, 4, 12)),
            "Today's showtimes: Halloween Double Feature at 7:00 PM.",
        )

    def test_leaves_out_shows_that_already_started(self) -> None:
        add_showtime(self.hamnet, at(2026, 10, 4, 16))
        add_showtime(self.hamnet, at(2026, 10, 4, 19, 15))
        self.assertEqual(
            showtimes_speech(now=at(2026, 10, 4, 17)),
            "Today's showtimes: Hamnet at 7:15 PM.",
        )

    def test_a_show_starting_this_minute_is_still_read(self) -> None:
        # Doors are open and trailers rolling: a caller at 7:15 for the
        # 7:15 still wants to hear it. Pins the >= in the query.
        add_showtime(self.hamnet, at(2026, 10, 4, 19, 15))
        self.assertEqual(
            showtimes_speech(now=at(2026, 10, 4, 19, 15)),
            "Today's showtimes: Hamnet at 7:15 PM.",
        )

    def test_a_midnight_show_belongs_to_tomorrow(self) -> None:
        # 12:00 AM is the first minute of the next Eastern day, so at 11:50
        # PM it is read as tomorrow's. A late-night caller may mean
        # "tonight"; this pins today's rule so a change is deliberate.
        add_showtime(self.hamnet, at(2026, 10, 5, 0, 0))
        self.assertEqual(
            showtimes_speech(now=at(2026, 10, 4, 23, 50)),
            "There are no shows today. Our next showtimes are tomorrow: "
            "Hamnet at 12:00 AM.",
        )

    def test_no_shows_today_reads_the_next_day_with_showtimes(self) -> None:
        add_showtime(self.hamnet, at(2026, 10, 9, 18, 30))
        add_showtime(self.hamnet, at(2026, 10, 9, 21))
        add_showtime(self.hamnet, at(2026, 10, 10, 14))  # a later day: not read
        self.assertEqual(
            showtimes_speech(now=at(2026, 10, 4, 12)),
            "There are no shows today. Our next showtimes are Friday, October 9: "
            "Hamnet at 6:30 PM and 9:00 PM.",
        )

    def test_next_day_is_tomorrow(self) -> None:
        add_showtime(self.hamnet, at(2026, 10, 5, 19))
        self.assertEqual(
            showtimes_speech(now=at(2026, 10, 4, 12)),
            "There are no shows today. Our next showtimes are tomorrow: "
            "Hamnet at 7:00 PM.",
        )

    def test_all_of_todays_shows_have_started(self) -> None:
        add_showtime(self.hamnet, at(2026, 10, 4, 16))
        add_showtime(self.hamnet, at(2026, 10, 5, 19))
        self.assertTrue(
            showtimes_speech(now=at(2026, 10, 4, 20)).startswith(
                "There are no more shows today. Our next showtimes are tomorrow"
            )
        )

    def test_late_evening_utc_rollover_stays_on_the_eastern_day(self) -> None:
        # 11:30 PM Eastern is already the next day in UTC.
        add_showtime(self.hamnet, at(2026, 10, 4, 23, 30))
        self.assertEqual(
            showtimes_speech(now=at(2026, 10, 4, 22)),
            "Today's showtimes: Hamnet at 11:30 PM.",
        )

    def test_nothing_scheduled_at_all(self) -> None:
        self.assertEqual(
            showtimes_speech(now=at(2026, 10, 4, 12)),
            "There are no shows today. We don't have any upcoming showtimes "
            "scheduled yet. Please check fort kent cinema dot com for updates.",
        )

    def test_skips_cancelled_draft_and_hidden_runs(self) -> None:
        add_showtime(self.hamnet, at(2026, 10, 4, 16), is_cancelled=True)
        draft = make_engagement("Draft Film", SUNDAY, SUNDAY, status="DRAFT")
        add_showtime(draft, at(2026, 10, 4, 17))
        hidden = make_engagement(
            "Private Event", SUNDAY, SUNDAY, show_in_main_listings=False
        )
        add_showtime(hidden, at(2026, 10, 4, 18))

        speech = showtimes_speech(now=at(2026, 10, 4, 12))
        self.assertTrue(speech.startswith("There are no shows today."))
        for title in ("Hamnet", "Draft Film", "Private Event"):
            self.assertNotIn(title, speech)


# Fixed values, so this pins the wording rather than today's prices and hours:
# a reprice in web/constants.py shouldn't fail the suite.
BOX_OFFICE = {"opens_before_show_minutes": 45}
PRICES = {
    "adult": 8,
    "senior": 7,
    "child": 6,
    "matinee": 5,
    "member": 4,
    "matinee_until": datetime.time(16, 0),
}


class HoursAndPricesSpeechTests(TestCase):
    @patch.dict(TICKET_PRICES, PRICES)
    @patch.dict(SITE_CONFIG, {"box_office": BOX_OFFICE})
    def test_reads_hours_and_every_price(self) -> None:
        self.assertEqual(
            hours_and_prices_speech(),
            "We're at 13 Hall Street in Fort Kent, and the box office opens "
            "45 minutes before every show. "
            "Tickets are $8 for adults, $7 for seniors, and $6 for children. "
            "Matinees, for shows starting at 4:00 PM or earlier, are $5. "
            "Members pay $4 for any show, and some shows are free for members. "
            "You can also buy tickets ahead of time at fort kent cinema dot com.",
        )

    def test_says_tickets_are_sold_online(self) -> None:
        self.assertIn(
            "buy tickets ahead of time at fort kent cinema dot com.",
            hours_and_prices_speech(),
        )

    def test_reads_the_live_prices(self) -> None:
        speech = hours_and_prices_speech()
        self.assertIn(f"${TICKET_PRICES['adult']} for adults", speech)
        self.assertIn(f"are ${TICKET_PRICES['matinee']}.", speech)
