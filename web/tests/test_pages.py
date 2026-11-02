import html as html_lib
import json
import re
from unittest import mock

from django.test import TestCase
from django.urls import reverse

from web.tests.test_home_sections import _time, hero_film

from web.constants import RENTALS_FAQ


class HomePageTests(TestCase):
    def test_home_returns_200(self):
        response = self.client.get(reverse("home"))
        self.assertEqual(response.status_code, 200)

    def test_home_uses_base_and_home_templates(self):
        response = self.client.get(reverse("home"))
        self.assertTemplateUsed(response, "base.html")
        self.assertTemplateUsed(response, "web/home.html")

    def test_no_template_comment_leaks_into_page(self):
        # Django's {# #} comment is single-line only; a multi-line {# #} leaks
        # as literal page text. Guard against that regression.
        html = self.client.get(reverse("home")).content.decode()
        self.assertNotIn("{#", html)
        self.assertNotIn("{% comment %}", html)


class SiteConfigContextTests(TestCase):
    def test_site_config_available_in_templates(self):
        response = self.client.get(reverse("home"))
        self.assertIn("site_config", response.context)
        self.assertEqual(
            response.context["site_config"]["cinema"]["name"], "Fort Kent Cinema"
        )


class BaseChromeTests(TestCase):
    def test_default_meta_and_og(self):
        response = self.client.get(reverse("home"))
        html = response.content.decode()
        self.assertIn('property="og:title"', html)
        self.assertIn('property="og:type"', html)
        self.assertIn('name="twitter:card"', html)

    def test_structured_data_present(self):
        html = self.client.get(reverse("home")).content.decode()
        self.assertIn('"@type": "MovieTheater"', html)
        self.assertIn("13 Hall Street", html)

    def test_chrome_elements_present(self):
        html = self.client.get(reverse("home")).content.decode()
        self.assertIn('class="skip-link"', html)

    def test_canonical_uses_request_url(self):
        html = self.client.get(reverse("home")).content.decode()
        self.assertIn('rel="canonical"', html)


class HomeViewDataTests(TestCase):
    @mock.patch("web.views.get_coming_soon", return_value=[])
    @mock.patch("web.views.get_hero_films", return_value=[])
    def test_context_has_movie_lists(self, _ns, _cs):
        resp = self.client.get(reverse("home"))
        self.assertEqual(resp.status_code, 200)
        self.assertIn("hero_films", resp.context)
        self.assertIn("coming_soon", resp.context)

    @mock.patch("web.views.get_coming_soon", return_value=[])
    @mock.patch("web.views.get_hero_films")
    def test_hero_renders_the_film_and_every_date(self, ns, _cs):
        ns.return_value = [hero_film(
            is_free_for_members=True,
            upcoming=[
                {"key": "2999-01-15",
                 "times": [_time(1, "6:00 PM", "2999-01-15T18:00:00-05:00")]},
                {"key": "2999-01-16",
                 "times": [_time(2, "7:00 PM", "2999-01-16T19:00:00-05:00")]},
            ],
        )]
        html = self.client.get(reverse("home")).content.decode()
        self.assertIn('id="now-showing"', html)          # the anchor, on the hero
        self.assertIn('class="hero hero--film"', html)
        self.assertIn("Dune", html)                      # movie title
        self.assertIn("6:00 PM", html)                   # a showtime rendered into DOM
        self.assertIn("7:00 PM", html)                   # both dates server-rendered
        self.assertIn("Free for Members", html)          # the ribbon
        self.assertIn('data-hero-idle', html)            # hero idle hook


class ComingSoonTests(TestCase):
    @mock.patch("web.views.get_hero_films", return_value=[])
    @mock.patch("web.views.get_coming_soon")
    def test_coming_soon_grid_renders(self, cs, _ns):
        cs.return_value = [{
            "id": "5", "title": "Wicked", "release_date": "November 22",
            "genre": "", "poster": "w.jpg", "youtube_id": "", "films": [],
            "is_free_for_members": False, "start_date": "2999-11-22",
        }]
        html = self.client.get(reverse("home")).content.decode()
        self.assertIn("coming-soon", html)
        self.assertIn("Wicked", html)
        self.assertIn("november 22", html.lower())  # the release date


class CalendarTests(TestCase):
    """These used to use year 2999. The view now bounds the year to +/-2 of today
    (see CalendarMonthView.CALENDAR_YEAR_RANGE) because the old MINYEAR..MAXYEAR
    range let a crawler walk ~120,000 URLs via the fragment's prev/next links.
    A far-future year is now a 404 — correctly — so these use the current year."""

    @property
    def year(self):
        from django.utils import timezone

        return timezone.localdate().year

    @mock.patch("web.views.get_calendar_month", return_value={})
    def test_calendar_fragment_200(self, _m):
        resp = self.client.get(reverse("calendar_month", args=[self.year, 4]))
        self.assertEqual(resp.status_code, 200)
        self.assertTemplateUsed(resp, "partials/calendar_month.html")
        self.assertIn("coming-calendar", resp.content.decode())

    @mock.patch("web.views.get_calendar_month")
    def test_calendar_fragment_renders_movies_and_nav(self, m):
        m.return_value = {4: [{"id": "300", "title": "Wicked",
                               "poster": "w.jpg", "youtube_id": "y"}]}
        y = self.year
        html = self.client.get(reverse("calendar_month", args=[y, 4])).content.decode()
        self.assertIn(f"may {y}", html.lower())                # month_label
        self.assertIn("Wicked", html)                          # a day's movie
        # Next-month nav wraps 0-based month 4 -> 5 (June), same year.
        self.assertIn(reverse("calendar_month", args=[y, 5]), html)
        # Prev-month nav 4 -> 3 (April), same year.
        self.assertIn(reverse("calendar_month", args=[y, 3]), html)

    @mock.patch("web.views.get_calendar_month", return_value={})
    def test_calendar_prev_next_wraps_year(self, _m):
        y = self.year
        # January (0-based month 0) prev is December of the previous year.
        html = self.client.get(reverse("calendar_month", args=[y, 0])).content.decode()
        self.assertIn(reverse("calendar_month", args=[y - 1, 11]), html)
        # December (month 11) next is January of the next year.
        html2 = self.client.get(reverse("calendar_month", args=[y, 11])).content.decode()
        self.assertIn(reverse("calendar_month", args=[y + 1, 0]), html2)

    @mock.patch("web.views.get_calendar_month")
    def test_key_lists_each_film_once_with_its_dates(self, m):
        def movie(title):
            return {"id": title, "title": title, "poster": f"{title}.jpg"}

        m.return_value = {
            2: [movie("Verity")],
            9: [movie("Pan's Labyrinth"), movie("Verity")],
            15: [movie("Verity")],
        }
        resp = self.client.get(reverse("calendar_month", args=[self.year, 9]))
        films = resp.context["films"]
        self.assertEqual(
            [(f["title"], f["dates"]) for f in films],
            [("Verity", "Oct 2\u201315"), ("Pan's Labyrinth", "Oct 9")],
        )
        html = resp.content.decode()
        self.assertIn("Pan&#x27;s Labyrinth", html)
        # Each poster in the grid points at its film in the key.
        self.assertEqual(html.count("film !== 0 }"), 3)
        self.assertEqual(html.count("film !== 1 }"), 1)

    @mock.patch("web.views.get_calendar_month", return_value={})
    def test_empty_month_says_so_in_the_key(self, _m):
        html = self.client.get(
            reverse("calendar_month", args=[self.year, 4])
        ).content.decode()
        self.assertIn("Nothing booked for May yet.", html)
        self.assertNotIn("coming-calendar-key__list", html)

    @mock.patch("web.views.get_calendar_month", return_value={})
    def test_today_is_ringed_and_earlier_days_muted(self, _m):
        import datetime

        with mock.patch(
            "web.views.timezone.localdate", return_value=datetime.date(self.year, 10, 12)
        ):
            resp = self.client.get(reverse("calendar_month", args=[self.year, 9]))
        days = {c["day"]: c for c in resp.context["cells"] if c["day"]}
        self.assertTrue(days[11]["is_past"])
        self.assertTrue(days[12]["is_today"])
        self.assertFalse(days[12]["is_past"])
        self.assertFalse(days[13]["is_past"] or days[13]["is_today"])
        self.assertContains(resp, '<span class="sr-only"> (today)</span>', count=1)

    def test_out_of_range_month_404(self):
        for bad in ("/calendar/2999/12/", "/calendar/2999/13/"):
            self.assertEqual(self.client.get(bad).status_code, 404)


class HomeIntegrationTests(TestCase):
    @mock.patch("web.views.get_coming_soon", return_value=[])
    @mock.patch("web.views.get_hero_films", return_value=[])
    def test_full_home_composition_order(self, _ns, _cs):
        html = self.client.get(reverse("home")).content.decode()
        # The empty-week fold (the hero, carrying #now-showing), then the
        # Coming Soon below it, each rendered once.
        markers = (
            'class="hero hero--empty"', 'id="now-showing"',
            'id="coming-soon"',
        )
        for marker in markers:
            self.assertEqual(html.count(marker), 1, marker)
            if marker.startswith("id="):
                start = html.rindex("<", 0, html.index(marker))
                self.assertTrue(html.startswith("<section", start), marker)
        order = [html.index(s) for s in markers]
        self.assertEqual(order, sorted(order))
        self.assertIn('class="skip-link"', html)  # base chrome intact


class RentalsPageTests(TestCase):
    def test_rentals_200_and_content(self):
        resp = self.client.get(reverse("rentals"))
        self.assertEqual(resp.status_code, 200)
        self.assertTemplateUsed(resp, "web/rentals.html")
        self.assertContains(resp, "$225")  # base rate

    def test_every_rental_term_is_on_the_page(self):
        """The terms used to be a bulleted POLICIES list; they are now
        answers. They are contractual either way, so none may quietly go
        missing behind a template edit."""
        html = html_lib.unescape(self.client.get(reverse("rentals")).content.decode())
        for item in RENTALS_FAQ:
            self.assertIn(item["question"], html)
            self.assertIn(item["answer"], html)

    def test_rentals_emits_faq_schema_matching_the_visible_answers(self):
        """Google penalises FAQ markup whose answers are not on the page, and
        the head block and the visible <dl> are separate template blocks that
        could drift. Both render RENTALS_FAQ."""
        html = self.client.get(reverse("rentals")).content.decode()
        blocks = [
            json.loads(m)
            for m in re.findall(
                r'<script type="application/ld\+json">(.*?)</script>', html, re.S
            )
        ]
        faq = next(b for b in blocks if b.get("@type") == "FAQPage")
        self.assertEqual(
            [q["name"] for q in faq["mainEntity"]],
            [item["question"] for item in RENTALS_FAQ],
        )


class SeoTagTests(TestCase):
    def test_default_og_image_is_static_absolute(self):
        html = self.client.get(reverse("home")).content.decode()
        # default og:image should point at the served static file, not a bare root path
        self.assertIn("/static/img/og-image.jpg", html)
        self.assertNotIn('content="https://www.fortkentcinema.com/og-image.jpg"', html)

    def test_canonical_strips_query_string(self):
        html = self.client.get(reverse("home") + "?utm_source=x").content.decode()
        self.assertNotIn("utm_source", html)          # canonical/og:url must not carry query params
