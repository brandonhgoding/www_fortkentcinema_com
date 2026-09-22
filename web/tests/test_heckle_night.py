"""Heckle Night — /heckle-night/.

The same two computed things /craft-night/ has, tested for the same reason:
a hand-maintained version of either goes stale in public without anything
breaking.

  * The DATES are "third Friday of the month", a rule the calendar answers.
  * The FILM on each date is read from the schedule, so the page and Now
    Showing cannot disagree about what plays that Friday.

And one thing craft night does not have: a start date. This night has never
run, so the rule on its own would advertise a Friday nobody planned. The
floor is tested from both sides of it, because the interesting bug is the
one where the page starts working correctly only after October.
"""

import datetime

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from django.utils.html import escape

from cinema.models import Engagement, EngagementFilm, Film, Screen, Showtime
from web.constants import CRAFT_NIGHT, HECKLE_NIGHT, HECKLE_NIGHT_FAQ
from web.services.heckle_night import (
    get_heckle_nights,
    third_friday,
    upcoming_nights,
)


def aware(d, hh, mm=0):
    return timezone.make_aware(datetime.datetime(d.year, d.month, d.day, hh, mm))


class ThirdFridayTests(TestCase):
    def test_known_months(self):
        # Hand-checked against a calendar. October 2026 is the one that
        # matters — it is the first night, and the rule has to produce it.
        self.assertEqual(third_friday(2026, 10), datetime.date(2026, 10, 16))
        self.assertEqual(third_friday(2026, 11), datetime.date(2026, 11, 20))
        self.assertEqual(third_friday(2026, 12), datetime.date(2026, 12, 18))
        self.assertEqual(third_friday(2027, 1), datetime.date(2027, 1, 15))

    def test_a_month_starting_on_a_friday_counts_that_friday_as_the_first(self):
        """The off-by-one that makes "third Friday" mean the 22nd.

        January 2027 begins on a Friday: the Fridays are the 1st, 8th,
        15th, 22nd. The third is the 15th. A "the 15th, then walk forward"
        implementation gets this wrong, which is why the rule indexes the
        month's Fridays instead.
        """
        self.assertEqual(datetime.date(2027, 1, 1).weekday(), 4)
        self.assertEqual(third_friday(2027, 1), datetime.date(2027, 1, 15))

    def test_always_a_friday_with_exactly_two_fridays_before_it(self):
        for year in (2026, 2027, 2028):
            for month in range(1, 13):
                night = third_friday(year, month)
                self.assertEqual(night.weekday(), 4, night)
                # Two Fridays earlier is still this month; three is not.
                self.assertEqual(
                    (night - datetime.timedelta(days=14)).month, night.month, night
                )
                self.assertNotEqual(
                    (night - datetime.timedelta(days=21)).month, night.month, night
                )


class StartDateTests(TestCase):
    """Nothing before HECKLE_NIGHT["starts_on"] is a heckle night."""

    def test_the_first_night_is_the_configured_start(self):
        nights = upcoming_nights(3, today=datetime.date(2026, 9, 22))
        self.assertEqual(nights[0], HECKLE_NIGHT["starts_on"])

    def test_earlier_third_fridays_are_not_advertised(self):
        """September 18 2026 is a third Friday. It is not a heckle night."""
        self.assertEqual(third_friday(2026, 9), datetime.date(2026, 9, 18))
        nights = upcoming_nights(6, today=datetime.date(2026, 9, 1))
        self.assertNotIn(datetime.date(2026, 9, 18), nights)
        self.assertEqual(nights[0], datetime.date(2026, 10, 16))

    def test_the_floor_stops_binding_once_the_night_is_running(self):
        nights = upcoming_nights(2, today=datetime.date(2027, 3, 1))
        self.assertEqual(
            nights, [datetime.date(2027, 3, 19), datetime.date(2027, 4, 16)]
        )

    def test_the_start_date_is_a_date_the_rule_actually_produces(self):
        """Otherwise the page silently skips the night it was opened for.

        starts_on is a floor, not an override: a start date the rule does
        not generate would be passed over for the next real third Friday,
        and nobody would be told. Guarding it here means the constant and
        the rule cannot drift apart quietly.
        """
        start = HECKLE_NIGHT["starts_on"]
        self.assertEqual(third_friday(start.year, start.month), start)


class UpcomingNightsTests(TestCase):
    def test_today_counts_as_upcoming(self):
        """A 7:00 PM show is still ahead of you at noon."""
        nights = upcoming_nights(3, today=datetime.date(2026, 10, 16))
        self.assertEqual(nights[0], datetime.date(2026, 10, 16))

    def test_rolls_to_next_month_once_past(self):
        nights = upcoming_nights(3, today=datetime.date(2026, 10, 17))
        self.assertEqual(
            nights,
            [
                datetime.date(2026, 11, 20),
                datetime.date(2026, 12, 18),
                datetime.date(2027, 1, 15),
            ],
        )

    def test_crosses_the_year_boundary(self):
        nights = upcoming_nights(2, today=datetime.date(2026, 12, 19))
        self.assertEqual(
            nights, [datetime.date(2027, 1, 15), datetime.date(2027, 2, 19)]
        )

    def test_returns_exactly_what_was_asked_for(self):
        self.assertEqual(len(upcoming_nights(6, today=datetime.date(2027, 5, 1))), 6)


class HeckleNightLineupTests(TestCase):
    """What plays, read from the schedule rather than configured."""

    def setUp(self):
        self.screen = Screen.objects.create(name="The Savoy", capacity=100)
        self.today = datetime.date(2026, 10, 1)
        self.night = datetime.date(2026, 10, 16)

    def book(self, title, date, *, hour=19, minute=0, status="CONFIRMED",
             cancelled=False, listed=True, kind=Engagement.Kind.SPECIAL_EVENT):
        """A Heckle Night booking by default — a SPECIAL_EVENT.

        `kind` is a parameter rather than a constant because the whole
        point of the lineup query is which kinds it refuses.
        """
        film = Film.objects.create(title=title, runtime_minutes=79, rating="NR")
        engagement = Engagement.objects.create(
            screen=self.screen,
            start_date=date,
            end_date=date,
            status=status,
            kind=kind,
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
        return get_heckle_nights(3, today=self.today)

    def test_booked_night_carries_its_film(self):
        self.book("Plan 9 From Outer Space", self.night)
        first = self.nights()[0]
        self.assertEqual(first["date"], self.night)
        self.assertEqual(first["film"]["title"], "Plan 9 From Outer Space")
        self.assertEqual(first["film"]["time"], "7:00 PM")

    def test_unbooked_night_still_appears(self):
        """The normal state. We book weeks ahead; the date is further out."""
        rows = self.nights()
        self.assertEqual(len(rows), 3)
        self.assertTrue(all(row["film"] is None for row in rows))
        self.assertEqual(rows[0]["label"], "Friday, October 16")

    def test_matinee_is_not_the_heckle_night_film(self):
        """A 1pm showing on the same Friday is a different show."""
        self.book("Matinee Only", self.night, hour=13)
        self.assertIsNone(self.nights()[0]["film"])

    def test_evening_is_a_floor_not_an_exact_time(self):
        """A show that shifted to 7:30 is still the evening show."""
        self.book("Moved Late", self.night, hour=19, minute=30)
        first = self.nights()[0]
        self.assertEqual(first["film"]["title"], "Moved Late")
        # The page shows the real start, not the advertised 7:00.
        self.assertEqual(first["film"]["time"], "7:30 PM")

    def test_cancelled_showtime_is_not_a_lineup(self):
        self.book("Cancelled", self.night, cancelled=True)
        self.assertIsNone(self.nights()[0]["film"])

    def test_draft_engagement_is_not_a_lineup(self):
        self.book("Not Confirmed Yet", self.night, status="DRAFT")
        self.assertIsNone(self.nights()[0]["film"])

    def test_showtime_on_another_day_is_ignored(self):
        self.book("Wrong Night", self.night - datetime.timedelta(days=1))
        self.assertIsNone(self.nights()[0]["film"])

    def test_the_regular_friday_feature_is_not_heckle_night(self):
        """The bug this filter exists to prevent.

        A first-run feature in the Friday evening slot is a normal
        screening. Announcing it here would invite a paying room to shout
        at a film we licensed, which is a different and much worse night.
        """
        self.book("First Run Feature", self.night, kind=Engagement.Kind.REGULAR)
        self.assertIsNone(self.nights()[0]["film"])

    def test_a_special_event_is(self):
        self.book("Plan 9 From Outer Space", self.night)
        self.assertEqual(
            self.nights()[0]["film"]["title"], "Plan 9 From Outer Space"
        )

    def test_no_other_kind_counts_either(self):
        """CLASSIC and DOUBLE_FEATURE are near misses, and still misses.

        A Heckle Night booking has one kind. A night booked as something
        else reads "Not booked yet" on the page — visibly wrong, and
        fixable — rather than quietly adopting the wrong film.
        """
        for kind in (Engagement.Kind.CLASSIC, Engagement.Kind.DOUBLE_FEATURE):
            with self.subTest(kind=kind):
                Engagement.objects.all().delete()
                self.book("Close But Not It", self.night, kind=kind)
                self.assertIsNone(self.nights()[0]["film"])

    def test_a_private_event_is_still_not_advertised(self):
        """show_in_main_listings now carries the privacy guard alone.

        Private bookings are special events too. Unticking that box is
        how one is marked private, and this page must not undo that.
        """
        self.book("Someone's Birthday Party", self.night, listed=False)
        self.assertIsNone(self.nights()[0]["film"])

    def test_the_regular_feature_does_not_win_over_the_event(self):
        """Both on the same Friday evening, which is the realistic case:
        one screen runs the first-run feature, the other runs this."""
        self.book("First Run Feature", self.night, hour=19,
                  kind=Engagement.Kind.REGULAR)
        self.book("Robot Monster", self.night, hour=19, minute=30)
        self.assertEqual(self.nights()[0]["film"]["title"], "Robot Monster")

    def test_query_count_does_not_grow_with_the_number_of_nights(self):
        """Bucketed in Python. Per-date filtering would be N queries.

        The absolute count is not the point and would be brittle; that
        doubling the list does not move it is.
        """
        self.book("Plan 9 From Outer Space", self.night)
        with self.assertNumQueries(3):
            get_heckle_nights(3, today=self.today)
        with self.assertNumQueries(3):
            get_heckle_nights(6, today=self.today)


class HeckleNightPageTests(TestCase):
    def setUp(self):
        self.response = self.client.get(reverse("heckle_night"))

    def test_renders(self):
        self.assertEqual(self.response.status_code, 200)

    def test_url_is_heckle_night(self):
        self.assertEqual(reverse("heckle_night"), "/heckle-night/")

    def test_states_the_door_price(self):
        self.assertContains(self.response, f"${HECKLE_NIGHT['general_price']}")

    def test_members_come_in_free(self):
        """Free is the headline, so it has to be on the page as a word."""
        self.assertTrue(HECKLE_NIGHT["members_free"])
        content = self.response.content.decode()
        self.assertIn("Free", content)
        self.assertIn("free for members", content.lower())

    def test_the_free_night_does_not_spend_a_monthly_allowance(self):
        """The answer the box office needs, and the one the code implies.

        Engagement.is_free_for_members is a badge; audience.FreeAdmission
        is a separate allowance drawn down only when staff record a
        redemption. Nothing here records one, so a member keeps whatever
        their tier gives them — and the page has to say so, or the counter
        improvises.
        """
        self.assertContains(self.response, "monthly free admission")

    def test_members_are_pointed_at_the_membership_page(self):
        """A free rate is an argument for joining; it should link."""
        self.assertContains(self.response, reverse("membership"))

    def test_the_door_price_is_the_member_evening_rate(self):
        """$4 reads as "the member rate, for everybody" on the page.

        That sentence is only true while evening admission is $8 less the
        $4 /membership/ promises. If those move, this number is part of
        the same repricing — see the note on HECKLE_NIGHT["general_price"].
        """
        self.assertEqual(
            HECKLE_NIGHT["general_price"],
            CRAFT_NIGHT["general_price"] - CRAFT_NIGHT["member_price"],
        )

    def test_states_who_the_night_is_for(self):
        """In a small town this is the question that decides the evening."""
        self.assertContains(self.response, HECKLE_NIGHT["audience"])

    def test_the_one_rule_is_on_the_page(self):
        """Everything else about this night is negotiable; this is not."""
        self.assertContains(self.response, "Heckle the movie, not each other")

    def test_every_faq_question_is_visible_on_the_page(self):
        """FAQPage markup whose answers are not on the page is penalised.

        escape() because half these questions are written the way someone
        would say them out loud — "I'm not funny", "Can I just watch" — and
        the apostrophes land as &#x27; in the rendered page.
        """
        content = self.response.content.decode()
        for faq in HECKLE_NIGHT_FAQ:
            self.assertIn(escape(faq["question"]), content)
            self.assertIn(escape(faq["answer"]), content)

    def test_faq_markup_is_present(self):
        self.assertContains(self.response, '"@type": "FAQPage"')

    def test_lists_the_upcoming_dates(self):
        self.assertEqual(
            len(self.response.context["nights"]), HECKLE_NIGHT["months_ahead"]
        )

    def test_next_night_is_the_first_one(self):
        ctx = self.response.context
        self.assertEqual(ctx["next_night"], ctx["nights"][0])

    def test_in_the_sitemap(self):
        sitemap = self.client.get("/sitemap.xml").content.decode()
        self.assertIn("/heckle-night/", sitemap)

    def test_in_the_nav(self):
        self.assertContains(self.response, "/heckle-night/")


class MstThreeKTests(TestCase):
    """The premise is theirs; the name and the show are not.

    MST3K is named once, as an explanation, and the FAQ disclaims any
    affiliation. What must never appear is the mark used AS ours — in the
    title, the URL, or the page metadata.
    """

    def setUp(self):
        self.content = self.client.get(reverse("heckle_night")).content.decode()

    def test_the_night_is_not_named_after_them(self):
        """Their name must never be what this night is CALLED.

        Checked against the three places that name a page — <title>,
        og:title and the <h1> — rather than the whole head, because the
        head also carries the FAQ as JSON-LD, and the question that
        disclaims the affiliation has to be allowed to say who it means.
        """
        head = self.content[: self.content.index("</head>")]
        for tag in (
            head[head.index("<title>") : head.index("</title>")],
            head[head.index('property="og:title"') :][:200],
            self.content[self.content.index("<h1") :][:200],
        ):
            self.assertNotIn("Mystery Science", tag)
            self.assertNotIn("MST3K", tag)

    def test_they_are_named_only_as_an_explanation(self):
        """Twice in the visible page, and both uses earn their place.

        Once in the body ("if you've seen it, you know how this works")
        and once in the FAQ question that disclaims the affiliation. The
        head is excluded because the FAQ renders there a second time as
        JSON-LD, which is the same two uses, not new ones. A third use in
        the body would be the page leaning on someone else's mark.
        """
        body = self.content[self.content.index("</head>") :]
        self.assertEqual(body.count("Mystery Science Theater 3000"), 2)
        self.assertNotIn("MST3K", self.content)

    def test_the_url_is_ours(self):
        self.assertNotIn("mst", reverse("heckle_night"))

    def test_the_page_disclaims_affiliation(self):
        self.assertIn("not affiliated with them", self.content)
