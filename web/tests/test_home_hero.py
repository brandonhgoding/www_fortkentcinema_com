"""The home hero shows the next showing; the marquee is the fallback.

With a showing booked this week the first fold is that film: its backdrop,
poster, title, and its upcoming showtimes as the shared ticket chips, so the
visitor picks a time on the fold. Other films this week are named under
them. With nothing booked the bulb marquee renders as it always has.
"""

import datetime
import re
from decimal import Decimal
from zoneinfo import ZoneInfo

from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from audience.models import Member, MembershipTerm, MembershipTier

from tickets.tests.factories import make_live_item, make_order, make_showtime
from web.constants import SITE_CONFIG

SQUARE_ON = {
    "SQUARE_ACCESS_TOKEN": "t",
    "SQUARE_LOCATION_ID": "L",
    "SQUARE_TICKET_CATEGORY_ID": "C",
}


def in_two_days(hour=19):
    day = timezone.localdate() + datetime.timedelta(days=2)
    return datetime.datetime.combine(
        day, datetime.time(hour, 0), tzinfo=ZoneInfo("America/New_York")
    )


class HeroBase(TestCase):
    def home(self):
        return self.client.get(reverse("home")).content.decode()

    def hero(self):
        return re.search(
            r'<section class="hero hero--film".*?</section>', self.home(), re.S
        ).group(0)

    def booked(self):
        st = make_showtime(starts_at=in_two_days())
        film = st.engagement.primary_film
        film.rating = "PG-13"
        film.overview = " ".join(f"w{i}" for i in range(40))
        film.poster_url = "https://image.tmdb.org/t/p/w500/p.jpg"
        film.backdrop_url = "https://image.tmdb.org/t/p/w780/b.jpg"
        film.save()
        return st


@override_settings(**SQUARE_ON)
class FilmHeroTests(HeroBase):
    def setUp(self):
        self.st = self.booked()
        make_live_item(self.st.engagement)
        self.buy_url = reverse("tickets:buy", args=[self.st.pk])

    def test_fold_is_the_next_film(self):
        html = self.home()
        self.assertIn('class="hero hero--film"', html)
        self.assertNotIn('class="marquee-title"', html)
        self.assertIn('<h2 class="hero-film__title">Dune</h2>', html)
        self.assertIn('<span class="hero-film__cert">PG-13</span>', html)
        self.assertIn("2h 35min", html)

    def test_cinema_name_stays_the_h1(self):
        html = self.home()
        self.assertIn(
            f'<h1 class="hero-film__lockup">{SITE_CONFIG["cinema"]["name"]}', html
        )

    def test_artwork_loads_early(self):
        html = self.home()
        self.assertIn(
            '<img class="hero-film__backdrop"'
            ' src="https://image.tmdb.org/t/p/w1280/b.jpg" alt="" fetchpriority="high"',
            html,
        )
        self.assertIn(
            '<img class="hero-film__poster"'
            ' src="https://image.tmdb.org/t/p/w500/p.jpg"',
            html,
        )

    def test_description_is_trimmed(self):
        html = self.home()
        lede = re.search(r'<p class="hero-film__lede">([^<]*)</p>', html).group(1)
        self.assertTrue(lede.endswith("w24 …"), lede)
        self.assertNotIn("w25", lede)

    def test_showtimes_are_the_call_to_action(self):
        # The fold offers the film's times, each the same chip the listing
        # uses, instead of one Buy Tickets button to one checkout.
        late = self.st.engagement.showtimes.create(
            screen=self.st.screen, starts_at=in_two_days(21)
        )
        hero = self.hero()
        label = in_two_days().strftime("%a, %b %-d")
        self.assertIn(f'<dt class="hero-film__date">{label}</dt>', hero)
        self.assertIn(
            f'<a class="showtime showtime--buy" href="{self.buy_url}">7:00 PM', hero
        )
        late_url = reverse("tickets:buy", args=[late.pk])
        self.assertIn(
            f'<a class="showtime showtime--buy" href="{late_url}">9:00 PM', hero
        )
        self.assertNotIn("Buy Tickets", hero)
        self.assertIn(
            '<a href="#now-showing" class="btn btn-secondary">All Showtimes</a>', hero
        )
        self.assertIn(
            '<a href="/membership/" class="btn btn-secondary">Join Membership</a>', hero
        )

    def test_rows_stop_at_three_dates(self):
        for days in (3, 4, 5):
            self.st.engagement.showtimes.create(
                screen=self.st.screen,
                starts_at=in_two_days() + datetime.timedelta(days=days - 2),
            )
        hero = self.hero()
        self.assertEqual(hero.count('<dt class="hero-film__date">'), 3)
        fifth = timezone.localdate() + datetime.timedelta(days=5)
        self.assertNotIn(fifth.strftime("%a, %b %-d"), hero)

    def test_sold_out_online_says_so_and_does_not_link(self):
        # Same rule as the listing chip: the ticket page is not linked once
        # the showing is sold out online, the chip just says so, and with
        # nothing left to buy the buttons fall back to the marquee's pair.
        self.st.online_allowance = 1
        self.st.save()
        make_order(self.st, status="PAID")
        hero = self.hero()
        self.assertIn('<span class="showtime__note">Sold out online</span>', hero)
        self.assertNotIn(f'href="{self.buy_url}"', hero)
        self.assertIn(
            '<a href="#now-showing" class="btn btn-ticket">View Showtimes</a>', hero
        )

    def test_member_line_stays(self):
        tier = MembershipTier.objects.get(slug="individual")
        member = Member.objects.create(first_name="A", last_name="B", email="a@b.c")
        MembershipTerm.objects.create(
            member=member, tier=tier, started_on=timezone.localdate(),
            expires_on=timezone.localdate() + datetime.timedelta(days=30),
            price_paid=Decimal("60.00"),
        )
        html = self.home()
        self.assertIn('<span class="hero-members-count">1</span>', html)


@override_settings(**SQUARE_ON)
class AlsoShowingTests(HeroBase):
    def test_other_films_this_week_are_named(self):
        self.st = self.booked()
        make_live_item(self.st.engagement)
        other = make_showtime(starts_at=in_two_days(21))
        film = other.engagement.primary_film
        film.title = "Hocus Pocus"
        film.poster_url = "https://image.tmdb.org/t/p/w500/hp.jpg"
        film.save()
        hero = self.hero()
        strip = re.search(
            r'<div class="hero-film__also">.*?</div>\s*</div>', hero, re.S
        ).group(0)
        self.assertIn("Also showing", strip)
        self.assertIn('<a class="hero-film__also-item" href="#now-showing">', strip)
        self.assertIn('<span class="hero-film__also-title">Hocus Pocus</span>', strip)
        label = in_two_days().strftime("%a, %b %-d")
        self.assertIn(f"{label} &middot; 9:00 PM", strip)
        self.assertIn(
            '<img class="hero-film__also-poster"'
            ' src="https://image.tmdb.org/t/p/w500/hp.jpg" alt=""',
            strip,
        )
        # The other film's times are not offered on the fold: its own card is.
        self.assertNotIn(reverse("tickets:buy", args=[other.pk]), hero)

    def test_alone_means_no_strip(self):
        self.booked()
        self.assertNotIn("Also showing", self.hero())


class FilmHeroWithoutSalesTests(HeroBase):
    def test_square_off_falls_back_to_the_old_buttons(self):
        self.booked()
        html = self.home()
        self.assertIn('class="hero hero--film"', html)
        self.assertIn(
            '<a href="#now-showing" class="btn btn-ticket">View Showtimes</a>', html
        )
        self.assertIn(
            '<a href="/membership/" class="btn btn-secondary">Join Membership</a>', html
        )
        self.assertNotIn("Buy Tickets", html)

    def test_poster_stands_in_for_a_missing_backdrop(self):
        st = self.booked()
        film = st.engagement.primary_film
        film.backdrop_url = ""
        film.save()
        html = self.home()
        self.assertIn(
            '<img class="hero-film__backdrop hero-film__backdrop--poster"'
            ' src="https://image.tmdb.org/t/p/w500/p.jpg"',
            html,
        )

    def test_no_artwork_means_no_image(self):
        st = self.booked()
        film = st.engagement.primary_film
        film.backdrop_url = ""
        film.poster_url = ""
        film.save()
        html = self.home()
        self.assertIn('class="hero hero--film"', html)
        self.assertNotIn('class="hero-film__backdrop', html)
        self.assertNotIn('class="hero-film__poster"', html)


class MarqueeFallbackTests(HeroBase):
    def test_nothing_booked_renders_the_marquee(self):
        html = self.home()
        self.assertNotIn("hero--film", html)
        self.assertIn(
            f'<h1 class="marquee-title">{SITE_CONFIG["cinema"]["name"]}</h1>', html
        )

    def test_a_showing_that_started_does_not_count(self):
        make_showtime(starts_at=timezone.now() - datetime.timedelta(minutes=5))
        html = self.home()
        self.assertNotIn("hero--film", html)
