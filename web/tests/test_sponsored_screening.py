"""The homepage banner for a sponsored screening.

Unlike the retired Silents Synced CTA, this banner does not restate the
booking. The engagement already exists in the catalog, so the dates and
showtimes are read from those rows — the banner and Now Showing cannot
disagree about when the film plays. Only the sponsor's name is configured,
because `cinema.Engagement` has nowhere to record who paid for the run.

The banner therefore expires on the booking's own `end_date`, with no second
date to keep in sync and no follow-up commit to remember.
"""

import datetime
import re
from pathlib import Path
from unittest import mock

from django.conf import settings
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from cinema.models import Engagement, EngagementFilm, Film, Screen, Showtime
from web.views import sponsored_screening

# The suite configures its own run rather than reading web.constants. Between
# sponsored screenings the live SPONSORED_SCREENING is None, and a mechanism
# that only works while a run happens to be booked is a mechanism that stops
# being tested the moment the banner comes down.
CONFIG = {
    "film_slug": "the-land-before-time",
    "sponsor": "AParadis Photography",
    "eyebrow": "Labor Day Weekend",
    "admission": "$4",
}


def make_screen():
    return Screen.objects.create(name="The Savoy", capacity=100)


def aware(d, hh, mm=0):
    return timezone.make_aware(datetime.datetime(d.year, d.month, d.day, hh, mm))


class SponsoredScreeningFixture(TestCase):
    """A three-day run of the configured film with two showtimes a day."""

    #: Overridden by the unconfigured-state tests below.
    config = CONFIG

    def setUp(self):
        patcher = mock.patch("web.views.SPONSORED_SCREENING", self.config)
        patcher.start()
        self.addCleanup(patcher.stop)

        self.screen = make_screen()
        self.film = Film.objects.create(
            title="The Land Before Time",
            runtime_minutes=69,
            rating="G",
            youtube_id="Hmrx8luoec0",
        )
        # The config finds the film by slug; the fixture must match it or
        # every assertion below is testing nothing.
        self.assertEqual(self.film.slug, CONFIG["film_slug"])
        self.today = timezone.localdate()

    def book(self, *, start_offset=0, days=3, status="CONFIRMED", times=(11, 13)):
        start = self.today + datetime.timedelta(days=start_offset)
        end = start + datetime.timedelta(days=days - 1)
        eng = Engagement.objects.create(
            screen=self.screen, start_date=start, end_date=end, status=status
        )
        EngagementFilm.objects.create(engagement=eng, film=self.film, position=1)
        for i in range(days):
            day = start + datetime.timedelta(days=i)
            for hour in times:
                Showtime.objects.create(engagement=eng, starts_at=aware(day, hour))
        return eng

    def home(self):
        with (
            mock.patch("web.views.get_coming_soon", return_value=[]),
            mock.patch("web.views.get_now_showing", return_value=[]),
        ):
            return self.client.get(reverse("home")).content.decode()

    def home_with_schedule(self):
        """The home page with the shipped showtimes branch (a real catalog
        film booked today), rather than the stubbed empty state."""
        return self.client.get(reverse("home")).content.decode()


class SponsoredScreeningLookupTests(SponsoredScreeningFixture):
    def test_returns_the_run_while_it_is_still_playing(self):
        self.book()
        found = sponsored_screening()
        self.assertIsNotNone(found)
        self.assertEqual(found["film"], self.film)
        self.assertEqual(found["sponsor"], "AParadis Photography")
        self.assertEqual(found["admission"], "$4")

    def test_returns_none_once_the_run_has_ended(self):
        """The expiry. Keyed on the booking's end_date, so nobody has to
        remember to take the banner down."""
        self.book(start_offset=-10, days=3)
        self.assertIsNone(sponsored_screening())

    def test_last_day_of_the_run_still_counts(self):
        """An off-by-one here pulls the banner on the morning of the final
        matinee, which is exactly when it is doing the most work."""
        self.book(start_offset=-2, days=3)
        self.assertIsNotNone(sponsored_screening())

    def test_ignores_a_run_that_is_not_confirmed(self):
        self.book(status="DRAFT")
        self.assertIsNone(sponsored_screening())

    def test_returns_none_when_no_film_matches_the_slug(self):
        """Fails safe. `generate_slug` suffixes collisions, so a second Land
        Before Time in the catalog would move the slug — the banner must go
        quiet rather than raise on the homepage."""
        self.film.slug = "the-land-before-time-2"
        self.film.save()
        self.assertIsNone(sponsored_screening())

    def test_groups_every_showtime_by_day_in_order(self):
        self.book()
        days = sponsored_screening()["days"]
        self.assertEqual(len(days), 3)
        self.assertEqual(
            [d["date"] for d in days],
            [self.today + datetime.timedelta(days=i) for i in range(3)],
        )
        for day in days:
            self.assertEqual(day["times"], ["11:00 AM", "1:00 PM"])

    def test_cancelled_showtimes_are_left_out(self):
        eng = self.book()
        eng.showtimes.filter(starts_at__hour=13).update(is_cancelled=True)
        for day in sponsored_screening()["days"]:
            self.assertEqual(day["times"], ["11:00 AM"])


class SponsoredScreeningBannerTests(SponsoredScreeningFixture):
    def test_banner_carries_the_pitch(self):
        self.book()
        html = self.home()
        for probe in [
            "The Land Before Time",
            "AParadis Photography",
            "$4",
            "11:00 AM",
            "1:00 PM",
        ]:
            self.assertIn(probe, html, f"{probe} missing from the banner")

    def test_banner_carries_the_configured_eyebrow(self):
        """The occasion is the hook — a holiday weekend sells a family matinee
        better than the word 'sponsored' does. It is per-screening copy, so it
        lives in the constant rather than in the template."""
        self.book()
        self.assertIn("Labor Day Weekend", self.home())

    def test_eyebrow_falls_back_when_no_occasion_is_configured(self):
        """Not every sponsored run lands on a holiday."""
        self.book()
        with mock.patch("web.views.SPONSORED_SCREENING", {**CONFIG, "eyebrow": ""}):
            html = self.home()
        self.assertIn("Sponsored screening", html)
        self.assertNotIn("Labor Day Weekend", html)

    def test_banner_links_to_the_movie_page(self):
        """The trailer lives there, fed by Film.youtube_id — no reason to
        build a second facade into a homepage banner."""
        self.book()
        self.assertIn(self.film.get_absolute_url(), self.home())

    def test_showtimes_follow_the_catalog(self):
        """The whole point of reading the rows: move a showtime in the
        dashboard and the banner moves with it, with no commit."""
        eng = self.book()
        eng.showtimes.filter(starts_at__hour=13).delete()
        day = self.today + datetime.timedelta(days=1)
        Showtime.objects.create(engagement=eng, starts_at=aware(day, 19))
        html = self.home()
        self.assertIn("7:00 PM", html)
        self.assertNotIn("1:00 PM", html)

    def test_banner_absent_once_the_run_has_ended(self):
        self.book(start_offset=-10, days=3)
        self.assertNotIn("sponsored-cta", self.home())

    def test_banner_absent_when_nothing_is_booked(self):
        self.assertNotIn("sponsored-cta", self.home())

    def test_sponsored_card_is_inside_now_showing(self):
        """The first card of the Now Showing section, ahead of the schedule:
        after the section opens, before its first showtime markup."""
        self.book()
        html = self.home()
        self.assertEqual(html.count('class="sponsored-cta"'), 1)
        start = html.index('id="now-showing"')
        card = html.index('class="sponsored-cta"')
        self.assertLess(start, card)
        # get_now_showing is stubbed empty, so the empty state renders; its
        # own markup is the first thing the card must precede.
        self.assertLess(card, html.index("no-showtimes"))
        self.assertLess(card, html.index('id="membership"'))

    def test_sponsored_card_precedes_the_schedule_when_films_are_showing(self):
        self.book()
        html = self.home_with_schedule()
        card = html.index('class="sponsored-cta"')
        self.assertLess(html.index('id="now-showing"'), card)
        self.assertLess(card, html.index("date-nav"))

    def test_ticket_button_only_in_now_showing(self):
        """The ticket button belongs to Now Showing alone; every other action
        below the hero is a text link."""
        html = self.home()
        hero_end = html.index("</section>", html.index('class="hero"'))
        start = html.index('id="now-showing"')
        end = html.index('id="membership"')
        for match in re.finditer(r"btn-ticket", html[hero_end:]):
            pos = hero_end + match.start()
            self.assertTrue(start < pos < end, "btn-ticket outside Now Showing")

    def test_the_banner_leaves_nothing_behind_when_absent(self):
        """This used to assert that the banner and exactly one ornament
        divider left together, because the partial carried a trailing
        divider inside its own guard. The dividers are gone sitewide, so
        what matters now is simply that no fragment of the banner survives
        the booking it advertised."""
        self.book()
        self.assertIn("sponsored-cta", self.home())
        Engagement.objects.all().delete()
        without = self.home()
        self.assertNotIn("sponsored-cta", without)
        # The banner's own link text, not the sponsor's name. That name used
        # to be permanent copy in cta_sponsor.html further down the page, so
        # asserting on it proved nothing; the teaser has since been
        # generalised and no longer names anyone, but the link text remains
        # the more precise probe — it belongs to the banner alone.
        self.assertNotIn("Showtimes &amp; trailer", without)

    def test_banner_is_not_hidden_on_phones(self):
        """static/css/home.css hides every other homepage CTA below 600px. A
        Labor Day family matinee is exactly the audience that is on a phone,
        so this one is deliberately exempt — same call the retired EventCTA
        made, and for the same reason."""
        home_css = (Path(settings.BASE_DIR) / "static" / "css" / "home.css").read_text()
        self.assertNotIn("sponsored-cta", home_css)

    def test_no_template_comment_leaks_into_page(self):
        self.book()
        html = self.home()
        self.assertNotIn("{#", html)
        self.assertNotIn("{% comment %}", html)


class NoSponsoredScreeningConfiguredTests(SponsoredScreeningFixture):
    """The state between runs, which is what the homepage does most of the year.

    Clearing the constant has to be enough on its own: the booking it pointed
    at is still sitting in the catalog, still CONFIRMED, still playing. Only
    the config is gone.
    """

    config = None

    def test_returns_none_when_nothing_is_configured(self):
        self.book()
        self.assertIsNone(sponsored_screening())

    def test_banner_absent_when_nothing_is_configured(self):
        self.book()
        self.assertNotIn("sponsored-cta", self.home())
