"""Craft Cinema Night — /craft-night/.

Two things on this page are computed rather than typed, and both are here
for the same reason: a hand-maintained version of either goes stale in
public without anything breaking.

  * The DATES are "last Tuesday of the month", a rule the calendar answers.
  * The FILM on each date is read from the schedule, so the page and Now
    Showing cannot disagree about what plays that Tuesday.

The case that matters most is the ordinary one: the last Tuesday of the
month is usually further out than we book, so most listed nights have no
film. That is not an error state and the page must still render the date.
"""

import datetime
from unittest import mock

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from cinema.models import Engagement, EngagementFilm, Film, Screen, Showtime
from web.constants import CRAFT_NIGHT, CRAFT_NIGHT_FAQ
from web.services.craft_night import (
    get_craft_nights,
    last_tuesday,
    upcoming_nights,
)


def aware(d, hh, mm=0):
    return timezone.make_aware(datetime.datetime(d.year, d.month, d.day, hh, mm))


class LastTuesdayTests(TestCase):
    def test_known_months(self):
        # Hand-checked against a calendar. September 2026 is the interesting
        # one: it both starts and ends on a Tuesday, so an off-by-one in the
        # week walk shows up here.
        self.assertEqual(last_tuesday(2026, 9), datetime.date(2026, 9, 29))
        self.assertEqual(last_tuesday(2026, 10), datetime.date(2026, 10, 27))
        self.assertEqual(last_tuesday(2026, 11), datetime.date(2026, 11, 24))
        self.assertEqual(last_tuesday(2026, 12), datetime.date(2026, 12, 29))
        self.assertEqual(last_tuesday(2027, 2), datetime.date(2027, 2, 23))

    def test_always_a_tuesday_and_in_the_last_week(self):
        for year in (2026, 2027, 2028):
            for month in range(1, 13):
                night = last_tuesday(year, month)
                self.assertEqual(night.weekday(), 1, night)
                # Nothing later in the month is also a Tuesday.
                later = night + datetime.timedelta(days=7)
                self.assertNotEqual(later.month, night.month, night)


class UpcomingNightsTests(TestCase):
    def test_today_counts_as_upcoming(self):
        """A 6:30 show is still ahead of you at noon."""
        nights = upcoming_nights(3, today=datetime.date(2026, 9, 29))
        self.assertEqual(nights[0], datetime.date(2026, 9, 29))

    def test_rolls_to_next_month_once_past(self):
        nights = upcoming_nights(3, today=datetime.date(2026, 9, 30))
        self.assertEqual(
            nights,
            [
                datetime.date(2026, 10, 27),
                datetime.date(2026, 11, 24),
                datetime.date(2026, 12, 29),
            ],
        )

    def test_crosses_the_year_boundary(self):
        nights = upcoming_nights(2, today=datetime.date(2026, 12, 30))
        self.assertEqual(
            nights,
            [datetime.date(2027, 1, 26), datetime.date(2027, 2, 23)],
        )

    def test_returns_exactly_what_was_asked_for(self):
        self.assertEqual(len(upcoming_nights(6, today=datetime.date(2026, 9, 1))), 6)


class CraftNightLineupTests(TestCase):
    """What plays, read from the schedule rather than configured."""

    def setUp(self):
        self.screen = Screen.objects.create(name="The Savoy", capacity=100)
        self.today = datetime.date(2026, 9, 21)
        self.night = datetime.date(2026, 9, 29)

    def book(self, title, date, *, hour=18, minute=30, status="CONFIRMED",
             cancelled=False, listed=True):
        film = Film.objects.create(title=title, runtime_minutes=102, rating="PG")
        engagement = Engagement.objects.create(
            screen=self.screen,
            start_date=date,
            end_date=date,
            status=status,
            show_in_main_listings=listed,
        )
        EngagementFilm.objects.create(engagement=engagement, film=film, position=1)
        Showtime.objects.create(
            engagement=engagement,
            screen=self.screen,
            starts_at=aware(date, hour, minute),
            is_cancelled=cancelled,
        )
        return film

    def nights(self):
        return get_craft_nights(3, today=self.today)

    def test_booked_night_carries_its_film(self):
        self.book("The Wild Robot", self.night)
        first = self.nights()[0]
        self.assertEqual(first["date"], self.night)
        self.assertEqual(first["film"]["title"], "The Wild Robot")
        self.assertEqual(first["film"]["rating"], "PG")

    def test_unbooked_night_still_appears(self):
        """The normal state. We book weeks ahead; the date is further out."""
        rows = self.nights()
        self.assertEqual(len(rows), 3)
        self.assertTrue(all(row["film"] is None for row in rows))
        self.assertEqual(rows[0]["label"], "Tuesday, September 29")

    def test_matinee_is_not_the_craft_night_film(self):
        """A 1pm showing on the same Tuesday is a different show."""
        self.book("Matinee Only", self.night, hour=13)
        self.assertIsNone(self.nights()[0]["film"])

    def test_evening_is_a_floor_not_an_exact_time(self):
        """A show that shifted to 7:00 is still the evening show."""
        self.book("Moved To Seven", self.night, hour=19, minute=0)
        first = self.nights()[0]
        self.assertEqual(first["film"]["title"], "Moved To Seven")
        # The page shows the real start, not the advertised 6:30.
        self.assertEqual(first["film"]["time"], "7:00 PM")

    def test_cancelled_showtime_is_not_a_lineup(self):
        self.book("Cancelled", self.night, cancelled=True)
        self.assertIsNone(self.nights()[0]["film"])

    def test_draft_engagement_is_not_a_lineup(self):
        self.book("Not Confirmed Yet", self.night, status="DRAFT")
        self.assertIsNone(self.nights()[0]["film"])

    def test_hidden_engagement_is_not_a_lineup(self):
        self.book("Private Event", self.night, listed=False)
        self.assertIsNone(self.nights()[0]["film"])

    def test_showtime_on_another_day_is_ignored(self):
        self.book("Wrong Night", self.night - datetime.timedelta(days=1))
        self.assertIsNone(self.nights()[0]["film"])

    def test_query_count_does_not_grow_with_the_number_of_nights(self):
        """Bucketed in Python. Per-date filtering would be N queries.

        The absolute count is not the point and would be brittle; that
        doubling the list does not move it is.
        """
        self.book("The Wild Robot", self.night)
        with self.assertNumQueries(3):
            get_craft_nights(3, today=self.today)
        with self.assertNumQueries(3):
            get_craft_nights(6, today=self.today)


class CraftNightPageTests(TestCase):
    def setUp(self):
        self.response = self.client.get(reverse("craft_night"))

    def test_renders(self):
        self.assertEqual(self.response.status_code, 200)

    def test_url_is_craft_night(self):
        self.assertEqual(reverse("craft_night"), "/craft-night/")

    def test_names_the_partner(self):
        self.assertContains(self.response, CRAFT_NIGHT["partner"])
        self.assertContains(self.response, CRAFT_NIGHT["partner_url"])

    def test_states_both_prices(self):
        """A page that prices only the member rate reads members-only."""
        content = self.response.content.decode()
        self.assertIn(f"${CRAFT_NIGHT['member_price']}", content)
        self.assertIn(f"${CRAFT_NIGHT['general_price']}", content)

    def test_every_faq_answer_is_visible_on_the_page(self):
        """FAQPage markup whose answers are not on the page is penalised."""
        content = self.response.content.decode()
        for faq in CRAFT_NIGHT_FAQ:
            self.assertIn(faq["question"], content)

    def test_faq_markup_is_present(self):
        self.assertContains(self.response, '"@type": "FAQPage"')

    def test_lists_the_upcoming_dates(self):
        self.assertEqual(
            len(self.response.context["nights"]), CRAFT_NIGHT["months_ahead"]
        )

    def test_next_night_is_the_first_one(self):
        ctx = self.response.context
        self.assertEqual(ctx["next_night"], ctx["nights"][0])

    def test_in_the_sitemap(self):
        sitemap = self.client.get("/sitemap.xml").content.decode()
        self.assertIn("/craft-night/", sitemap)

    def test_in_the_nav(self):
        self.assertContains(self.response, "/craft-night/")


class PartnerLogoTests(TestCase):
    """The logo is optional, and the page has to be right without it.

    Rivertown sent us their mark, and CRAFT_NIGHT["partner_logo"] points
    at our copy of it. Blanking it has to leave a correct page, so both
    states are tested and the blank one stays supported.
    """

    def get(self, **overrides):
        config = {**CRAFT_NIGHT, **overrides}
        with mock.patch("web.views.CRAFT_NIGHT", config):
            return self.client.get(reverse("craft_night"))

    def test_no_logo_still_names_the_partner(self):
        response = self.get(partner_logo="")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, CRAFT_NIGHT["partner"])
        self.assertNotContains(response, "craft-partner__logo")

    def test_logo_renders_when_configured(self):
        response = self.get(partner_logo="img/og-image.jpg")
        self.assertContains(response, "craft-partner__logo")
        self.assertContains(response, CRAFT_NIGHT["partner_logo_alt"])

    def test_logo_links_to_the_partner_site(self):
        response = self.get(partner_logo="img/og-image.jpg")
        self.assertContains(response, CRAFT_NIGHT["partner_url"])

    def test_we_do_not_hotlink_their_logo(self):
        """The asset must be ours to serve, not fetched off their site."""
        self.assertFalse(CRAFT_NIGHT["partner_logo"].startswith("http"))

    def test_configured_logo_file_exists(self):
        """A typo in the path would 500 the page under manifest storage."""
        from django.contrib.staticfiles import finders

        self.assertIsNotNone(finders.find(CRAFT_NIGHT["partner_logo"]))
