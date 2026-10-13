"""Open Mic — /open-mic/.

The one computed thing is the next date, and the interesting edge is a
Monday evening: before 9 PM the next open mic is tonight, after it is next
week. The rest holds the page to the facts the owner decided, and to the
home-page band that has advertised the same night since the React port.
"""

import datetime

from django.test import TestCase
from django.urls import reverse

from web.constants import OPEN_MIC, OPEN_MIC_FAQ
from web.services.open_mic import upcoming_nights
from web.services.showtimes import CINEMA_TZ


def at(y, m, d, hh=12, mm=0):
    return datetime.datetime(y, m, d, hh, mm, tzinfo=CINEMA_TZ)


class UpcomingNightsTests(TestCase):
    def test_midweek_points_at_the_coming_monday(self):
        # Wednesday 2026-09-23 -> Monday 2026-09-28.
        self.assertEqual(
            upcoming_nights(1, now=at(2026, 9, 23)),
            [datetime.date(2026, 9, 28)],
        )

    def test_monday_before_the_finish_is_tonight(self):
        self.assertEqual(
            upcoming_nights(1, now=at(2026, 9, 28, 20, 59)),
            [datetime.date(2026, 9, 28)],
        )

    def test_monday_after_the_finish_is_next_week(self):
        self.assertEqual(
            upcoming_nights(1, now=at(2026, 9, 28, 21, 0)),
            [datetime.date(2026, 10, 5)],
        )

    def test_sunday_night_is_tomorrow(self):
        self.assertEqual(
            upcoming_nights(1, now=at(2026, 9, 27, 23, 30)),
            [datetime.date(2026, 9, 28)],
        )

    def test_the_monday_is_the_cinemas_monday_not_utc(self):
        # 01:30 UTC on a Tuesday is still 9:30 PM Monday in Fort Kent:
        # tonight's is over, so next week's is next.
        utc = datetime.datetime(2026, 9, 29, 1, 30, tzinfo=datetime.timezone.utc)
        self.assertEqual(upcoming_nights(1, now=utc), [datetime.date(2026, 10, 5)])

    def test_every_night_is_a_monday_a_week_apart(self):
        nights = upcoming_nights(10, now=at(2026, 12, 30))
        for night in nights:
            self.assertEqual(night.weekday(), OPEN_MIC["weekday"])
        for a, b in zip(nights, nights[1:]):
            self.assertEqual((b - a).days, 7)


class ConfigTests(TestCase):
    def test_end_label_and_end_time_agree(self):
        self.assertEqual(
            datetime.datetime.strptime(OPEN_MIC["end_label"], "%I:%M %p").time(),
            OPEN_MIC["end_time"],
        )


class OpenMicPageTests(TestCase):
    def setUp(self):
        self.response = self.client.get(reverse("open_mic"))

    def test_renders(self):
        self.assertEqual(self.response.status_code, 200)

    def test_url(self):
        self.assertEqual(reverse("open_mic"), "/open-mic/")

    def test_states_the_decided_facts(self):
        for fact in (
            "Monday",
            "6:30 PM",
            "9:00 PM",
            "Century auditorium",
            "Karaoke",
            "original music",
            "comedy",
            "sign-up sheet",
            "Free",
            "All ages",
            "PG",
        ):
            self.assertContains(self.response, fact)

    def test_every_faq_answer_is_on_the_page(self):
        """FAQPage markup whose answers aren't visible is penalised."""
        for faq in OPEN_MIC_FAQ:
            self.assertContains(self.response, faq["question"], count=2)

    def test_no_price_is_quoted(self):
        # Free to perform and to watch; a stray "$" means a copied price.
        body = self.response.content.decode()
        main = body[body.index('class="openmic-page"') :]
        self.assertNotIn("$", main)

    def test_in_the_sitemap(self):
        self.assertContains(self.client.get("/sitemap.xml"), "/open-mic/")


class HomeBandAgreesTests(TestCase):
    """The home page has advertised this night since the React port."""

    def test_card_matches_the_page_and_links_to_it(self):
        html = self.client.get(reverse("home")).content.decode()
        card = html[html.index("open-mic-cta") :]
        card = card[: card.index("</article>")]
        self.assertIn(f"Every {OPEN_MIC['day_label']}", card)
        self.assertIn(
            f"Doors open at {OPEN_MIC['doors_label']} and the first act goes up at "
            f"{OPEN_MIC['start_label']}.",
            card,
        )
        self.assertIn("in the Century auditorium", card)
        self.assertIn("free and all ages", card)
        self.assertIn("Open Mic", card)
        self.assertIn("How to sign up &rarr;", card)
        self.assertIn(f'href="{reverse("open_mic")}"', card)
        self.assertNotIn("data-track", card)
