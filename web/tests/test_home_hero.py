"""The home hero shows the next showing; the marquee is the fallback.

With a showing booked this week the first fold is that film: its backdrop,
poster, title, date and time, and a Buy Tickets button to its own checkout
page. With nothing booked the bulb marquee renders as it always has.
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
        label = in_two_days().strftime("%a, %b %-d")
        self.assertIn(f"{label} &middot; 7:00 PM", html)
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

    def test_buy_tickets_goes_to_that_showing(self):
        html = self.home()
        self.assertIn(
            f'<a href="{self.buy_url}" class="btn btn-ticket">Buy Tickets</a>', html
        )
        self.assertIn(
            '<a href="#now-showing" class="btn btn-secondary">All Showtimes</a>', html
        )

    def test_sold_out_online_says_so_and_does_not_link(self):
        # Same rule as the listing chip: the ticket page is not linked once
        # the showing is sold out online, the fold just says so.
        self.st.online_allowance = 1
        self.st.save()
        make_order(self.st, status="PAID")
        html = self.home()
        self.assertIn('<span class="hero-film__note">Sold out online</span>', html)
        self.assertNotIn(f'href="{self.buy_url}"', html)
        self.assertIn(
            '<a href="#now-showing" class="btn btn-ticket">View Showtimes</a>', html
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
