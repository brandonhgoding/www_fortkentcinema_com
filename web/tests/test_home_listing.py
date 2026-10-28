"""The hero is the listing.

The Now Showing section is gone: the film hero carries the whole week's
showtimes, the trailer, the ticket line and the Now Showing anchor, and
the mailing-list form moves to the foot of Coming Soon. In a week with
nothing booked the marquee stays and the empty state keeps a slim section
of its own under the same anchor, so that page does not change.
"""

import datetime
import re
from unittest import mock

from cinema.models import Language, Translation
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from web.tests.test_home_hero import SQUARE_ON, HeroBase, in_two_days


def section(html, section_id):
    at = html.index('id="%s"' % section_id)
    start = html.rindex("<section", 0, at)
    return html[start : html.index("</section>", at) + len("</section>")]


@override_settings(**SQUARE_ON)
class HeroIsTheListingTests(HeroBase):
    def setUp(self):
        self.st = self.booked()

    def test_the_film_hero_carries_the_now_showing_anchor(self):
        html = self.home()
        self.assertEqual(html.count('id="now-showing"'), 1)
        self.assertIn('<section class="hero hero--film" id="now-showing"', html)
        self.assertNotIn('class="now-showing', html)
        self.assertNotIn("section-title", section(html, "now-showing"))

    def test_the_grid_and_the_schedule_list_are_gone(self):
        html = self.home()
        for marker in (
            'class="movies-grid"',
            'class="schedule-list"',
            'class="date-nav"',
            'class="movie-card"',
            'class="schedule-card"',
            "ns_dates",
        ):
            self.assertNotIn(marker, html, marker)

    def test_no_button_points_at_the_listing_any_more(self):
        hero = self.hero()
        self.assertNotIn('href="#now-showing"', hero)
        self.assertNotIn("hero-cta", hero)

    def test_ticket_line_sits_under_the_dates_in_the_panel(self):
        hero = self.hero()
        self.assertEqual(hero.count('<p class="ticket-info">'), 1)
        dates = hero.index('class="hero-film__dates"')
        line = hero.index('<p class="ticket-info">')
        self.assertLess(dates, line)
        self.assertLess(line, hero.index("</article>"))
        self.assertIn("Buy online from the showtimes above", hero)

    def test_three_dates_show_without_a_toggle(self):
        for day in (3, 4):
            self.st.engagement.showtimes.create(
                screen=self.st.screen,
                starts_at=in_two_days(19) + datetime.timedelta(days=day - 2),
            )
        hero = self.hero()
        self.assertEqual(hero.count('<div class="hero-film__row"'), 3)
        self.assertNotIn("hero-film__more", hero)
        self.assertNotIn('x-show="expanded"', hero)

    def test_rows_past_the_third_fold_behind_a_toggle(self):
        eng = self.st.engagement
        eng.end_date = timezone.localdate() + datetime.timedelta(days=8)
        eng.save()
        for day in range(3, 9):
            eng.showtimes.create(
                screen=self.st.screen,
                starts_at=in_two_days(19) + datetime.timedelta(days=day - 2),
            )
        hero = self.hero()
        rows = re.findall(r'<div class="hero-film__row"[^>]*>', hero)
        self.assertEqual(len(rows), 7)
        self.assertTrue(all('x-show="expanded"' not in r for r in rows[:3]), rows[:3])
        self.assertTrue(
            all('x-show="expanded"' in r and "x-cloak" in r for r in rows[3:]), rows[3:]
        )
        self.assertIn(
            '<button class="hero-film__more" type="button" '
            '@click="expanded = !expanded" :aria-expanded="expanded">',
            hero,
        )
        self.assertIn("Show all 7 dates", hero)
        self.assertIn("Show fewer dates", hero)
        # Every panel has its own `expanded`.
        self.assertIn('x-data="{ expanded: false }"', hero)

    def test_folded_rows_show_without_javascript(self):
        html = self.home()
        noscript = re.search(
            r"<noscript>(.*?)</noscript>", section(html, "now-showing"), re.S
        )
        self.assertIsNotNone(noscript)
        self.assertIn(".hero-film__row[x-cloak]", noscript.group(1))
        self.assertNotIn("overlay", noscript.group(1))

    def test_language_label_joins_the_meta_line(self):
        eng = self.st.engagement
        eng.language = Language.FRENCH
        eng.translation = Translation.SUBTITLED
        eng.save()
        hero = self.hero()
        meta = re.search(r'<p class="hero-film__meta">.*?</p>', hero, re.S).group(0)
        self.assertIn(
            '<span class="hero-film__lang">French · English subtitles</span>', meta
        )

    def test_plain_english_has_no_language_span(self):
        self.assertNotIn("hero-film__lang", self.hero())

    def test_free_for_members_is_a_ribbon_on_the_poster(self):
        eng = self.st.engagement
        eng.is_free_for_members = True
        eng.save()
        hero = self.hero()
        wrap = re.search(
            r'<div class="hero-film__poster-wrap.*?</div>', hero, re.S
        ).group(0)
        self.assertIn('<span class="hero-film__ribbon">Free for Members</span>', wrap)

    def test_no_ribbon_when_not_free(self):
        self.assertNotIn("Free for Members", self.hero())

    def test_signup_moves_to_the_foot_of_coming_soon(self):
        html = self.home()
        self.assertEqual(
            re.findall(r'name="location" value="([^"]+)"', html), ["home_showtimes"]
        )
        coming = section(html, "coming-soon")
        self.assertIn('class="list-signup"', coming)
        self.assertLess(
            coming.index("coming-calendar-container"),
            coming.index('class="list-signup"'),
        )
        # The form keeps its Thursday promise; the empty week's lead is different.
        self.assertIn("every Thursday", coming)
        self.assertNotIn("Get an email the moment new runs are booked.", coming)

    def test_old_context_is_gone(self):
        ctx = self.client.get(reverse("home")).context
        for key in (
            "now_showing",
            "ns_dates",
            "ns_dates_json",
            "ns_labels_json",
            "ns_today_index",
        ):
            self.assertNotIn(key, ctx)

    def test_screening_events_come_from_the_hero_films(self):
        self.st.engagement.showtimes.create(
            screen=self.st.screen, starts_at=in_two_days(21)
        )
        html = self.home()
        self.assertEqual(html.count('"@type": "ScreeningEvent"'), 2)
        ld = html[html.index('"ScreeningEvent"') :]
        self.assertIn('"name": "Dune"', ld)
        self.assertIn('"image": "https://image.tmdb.org/t/p/w500/p.jpg"', ld)


@override_settings(**SQUARE_ON)
class HeroTrailerTests(HeroBase):
    def setUp(self):
        self.st = self.booked()
        film = self.st.engagement.primary_film
        film.youtube_id = "yt1"
        film.save()

    def test_poster_opens_the_trailer(self):
        hero = self.hero()
        self.assertIn('x-data="{ film: 0, trailer: null }"', hero)
        wrap = re.search(
            r'<div class="hero-film__poster-wrap hero-film__poster-wrap--playable"'
            r"[^>]*>",
            hero,
        ).group(0)
        self.assertIn('role="button"', wrap)
        self.assertIn('tabindex="0"', wrap)
        self.assertIn('aria-label="Watch Dune trailer"', wrap)
        self.assertIn(
            """@click="trailer = { title: 'Dune', youtube_id: 'yt1' }\"""", wrap
        )
        self.assertIn('data-track="trailer_play"', wrap)
        self.assertIn('class="hero-film__play"', hero)

    def test_a_text_link_offers_the_trailer_too(self):
        hero = self.hero()
        self.assertIn('<button class="hero-film__trailer" type="button"', hero)
        self.assertIn("Watch trailer", hero)

    def test_the_dialog_lives_in_the_hero(self):
        html = self.home()
        hero = section(html, "now-showing")
        self.assertEqual(html.count('class="now-trailer-overlay"'), 1)
        self.assertIn('class="now-trailer-overlay"', hero)
        self.assertIn('role="dialog" aria-modal="true"', hero)
        self.assertIn('class="now-trailer-close"', hero)

    def test_no_trailer_means_no_button(self):
        film = self.st.engagement.primary_film
        film.youtube_id = ""
        film.save()
        hero = self.hero()
        self.assertNotIn("poster-wrap--playable", hero)
        self.assertNotIn("Watch trailer", hero)
        self.assertNotIn("hero-film__play", hero)


@mock.patch("web.views.get_coming_soon", return_value=[])
class NothingBookedTests(TestCase):
    """The marquee week: unchanged, with the empty state in its own section."""

    def home(self):
        return self.client.get(reverse("home")).content.decode()

    def test_marquee_then_the_empty_state_under_the_anchor(self, _cs):
        html = self.home()
        self.assertIn('<section class="hero" data-neon data-cursor-bulbs>', html)
        self.assertEqual(html.count('id="now-showing"'), 1)
        empty = section(html, "now-showing")
        self.assertIn("home-section--raised", empty)
        self.assertIn('<div class="no-showtimes">', empty)
        self.assertIn("No showtimes available.", empty)
        self.assertNotIn("section-title", empty)
        self.assertNotIn("ticket-info", html)
        self.assertLess(html.index('class="hero"'), html.index('id="now-showing"'))
        self.assertLess(html.index('id="now-showing"'), html.index('id="membership"'))

    def test_signup_stays_in_the_empty_state(self, _cs):
        html = self.home()
        self.assertEqual(
            re.findall(r'name="location" value="([^"]+)"', html), ["home_empty"]
        )
        self.assertLess(
            html.index('class="list-signup"'), html.index('class="no-showtimes__links"')
        )
        self.assertNotIn('class="list-signup"', section(html, "coming-soon"))

    def test_the_marquee_button_still_reaches_it(self, _cs):
        html = self.home()
        self.assertIn('<a href="#now-showing" class="btn btn-ticket">', html)
