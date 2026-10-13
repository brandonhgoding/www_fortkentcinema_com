import html as html_lib
import json
import re
from unittest import mock

from django.test import TestCase
from django.urls import reverse
from django.contrib.staticfiles.finders import find

from blog.models import BlogAuthor, BlogCategory, BlogPost
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
        self.assertNotIn("Twitter/X falls back", html)
        self.assertNotIn("{#", html)
        self.assertNotIn("{% comment %}", html)


class SiteConfigContextTests(TestCase):
    def test_site_config_available_in_templates(self):
        response = self.client.get(reverse("home"))
        self.assertIn("site_config", response.context)
        self.assertEqual(
            response.context["site_config"]["cinema"]["name"], "Fort Kent Cinema"
        )

    def test_navigation_present(self):
        # Blog moved under the "More" dropdown, so labels have to be walked
        # one level deep. See test_nav.py for the structure's own tests.
        from web.constants import SITE_CONFIG

        labels = []
        for item in SITE_CONFIG["navigation"]:
            labels.append(item["label"])
            labels.extend(child["label"] for child in item.get("children", []))
        self.assertIn("Now Showing", labels)
        self.assertIn("Blog", labels)


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

    def test_google_analytics_absent_without_measurement_id(self):
        """The ID moved to GA_MEASUREMENT_ID; it is unset outside production so
        dev and test traffic stay out of the analytics. See test_analytics.py."""
        html = self.client.get(reverse("home")).content.decode()
        self.assertNotIn("googletagmanager.com", html)

    def test_chrome_elements_present(self):
        html = self.client.get(reverse("home")).content.decode()
        self.assertIn('class="skip-link"', html)

    def test_ambient_dust_is_gone(self):
        """The hero's floating dust canvas was removed deliberately: its motes
        were hardcoded rgba(201, 168, 76) — the old design's warm gold, not a
        brand value — and it read as grain over the blue-led hero rather than
        as projector light. Removed in markup (hero.html), CSS (.fx-dust) and
        JS (frontend/effects/init/ambientDust.js, deleted). This asserts it
        stays gone; a reappearance means one of the three came back alone."""
        html = self.client.get(reverse("home")).content.decode()
        self.assertNotIn("fx-dust", html)
        self.assertNotIn("data-ambient-dust", html)

    def test_canonical_uses_request_url(self):
        html = self.client.get(reverse("home")).content.decode()
        self.assertIn('rel="canonical"', html)


class HomeViewDataTests(TestCase):
    @mock.patch("web.views.get_coming_soon", return_value=[])
    @mock.patch("web.views.get_now_showing", return_value=[])
    def test_context_has_movie_lists(self, _ns, _cs):
        resp = self.client.get(reverse("home"))
        self.assertEqual(resp.status_code, 200)
        self.assertIn("now_showing", resp.context)
        self.assertIn("coming_soon", resp.context)

    @mock.patch("web.views.get_coming_soon", return_value=[])
    @mock.patch("web.views.get_now_showing", return_value=[])
    def test_home_meta_overrides(self, _ns, _cs):
        html = self.client.get(reverse("home")).content.decode()
        self.assertIn("Movies in the St. John Valley", html)  # home <title>/og:title

    @mock.patch("web.views.get_coming_soon", return_value=[])
    @mock.patch("web.views.get_now_showing")
    def test_now_showing_renders_movie_and_dates(self, ns, _cs):
        ns.return_value = [{
            "id": "1", "title": "Dune", "rating": "PG-13", "runtime": "2h 35min",
            "genre": "", "poster": "d.jpg", "youtube_id": "abc",
            "is_free_for_members": True,
            "showtimes": {"2999-01-15": [{"time": "6:00 PM", "captions": "", "captions_label": ""}], "2999-01-16": [{"time": "7:00 PM", "captions": "", "captions_label": ""}]},
        }]
        html = self.client.get(reverse("home")).content.decode()
        self.assertIn("now-showing", html)          # section id
        self.assertIn("Dune", html)                  # movie title
        self.assertIn("6:00 PM", html)               # a showtime rendered into DOM
        self.assertIn("7:00 PM", html)               # both dates' times server-rendered
        self.assertIn("Free for Members", html)      # free banner
        self.assertIn('data-spotlight', html)        # spotlight grid hook
        self.assertIn('data-neon', html)             # hero neon hook
        self.assertIn('data-cursor-bulbs', html)     # hero cursor bulbs hook

    @mock.patch("web.views.get_coming_soon", return_value=[])
    @mock.patch("web.views.get_now_showing")
    def test_movie_with_only_past_showtimes_has_no_broken_nav_or_card(self, ns, _cs):
        # A movie whose only showtime is in the past has no upcoming dates:
        # the desktop date-nav must not render (it would be empty/broken),
        # and the phone schedule-list must not render an empty card for it.
        ns.return_value = [{
            "id": "1", "title": "Past Movie", "rating": "PG-13", "runtime": "2h",
            "genre": "", "poster": "p.jpg", "youtube_id": "",
            "is_free_for_members": False,
            "showtimes": {"2000-01-01": [{"time": "6:00 PM", "captions": "", "captions_label": ""}]},
        }]
        html = self.client.get(reverse("home")).content.decode()
        self.assertNotIn("date-nav__current", html)
        self.assertNotIn("Past Movie", html)
        self.assertIn("No showtimes available.", html)


class ComingSoonTests(TestCase):
    @mock.patch("web.views.get_now_showing", return_value=[])
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
        self.assertIn("NOVEMBER 22", html)  # release_date uppercased in template


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
        self.assertIn(f"MAY {y}", html)                        # month_label
        self.assertIn("Wicked", html)                          # a day's movie
        self.assertIn("coming-calendar-cell--has-movie", html)
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

    @mock.patch("web.views.get_coming_soon", return_value=[])
    @mock.patch("web.views.get_now_showing", return_value=[])
    def test_home_has_view_toggle(self, _ns, _cs):
        html = self.client.get(reverse("home")).content.decode()
        self.assertIn("coming-view-toggle", html)
        self.assertIn("coming-calendar-container", html)

    @mock.patch("web.views.get_calendar_month")
    def test_key_lists_each_film_once_with_its_dates(self, m):
        def movie(title, slug=""):
            return {"id": title, "title": title, "slug": slug, "poster": f"{title}.jpg"}

        m.return_value = {
            2: [movie("Verity", "verity")],
            9: [movie("Pan's Labyrinth"), movie("Verity", "verity")],
            15: [movie("Verity", "verity")],
        }
        resp = self.client.get(reverse("calendar_month", args=[self.year, 9]))
        films = resp.context["films"]
        self.assertEqual(
            [(f["title"], f["dates"]) for f in films],
            [("Verity", "Oct 2\u201315"), ("Pan's Labyrinth", "Oct 9")],
        )
        html = resp.content.decode()
        self.assertIn("Showing in October", html)
        # Linked to the film page when there is one, plain text when not.
        self.assertIn(f'href="{reverse("movie_detail", args=["verity"])}">Verity</a>', html)
        self.assertIn("Pan&#x27;s Labyrinth", html)
        self.assertNotIn("Pan&#x27;s Labyrinth</a>", html)
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
        html = resp.content.decode()
        self.assertEqual(html.count("coming-calendar-cell--today"), 1)
        self.assertEqual(html.count("coming-calendar-cell--past"), 11)
        self.assertIn('<span class="sr-only"> (today)</span>', html)

    def test_out_of_range_month_404(self):
        for bad in ("/calendar/2999/12/", "/calendar/2999/13/"):
            self.assertEqual(self.client.get(bad).status_code, 404)


class HomeIntegrationTests(TestCase):
    @mock.patch("web.views.get_coming_soon", return_value=[])
    @mock.patch("web.views.get_now_showing", return_value=[])
    def test_full_home_composition_order(self, _ns, _cs):
        html = self.client.get(reverse("home")).content.decode()
        # The hero, then the five sections below it, each rendered once.
        # (Support is switched off: SHOW_SUPPORT_STRIP.)
        markers = (
            'class="hero"', 'id="now-showing"', 'id="membership"',
            'id="coming-soon"', 'id="get-involved"', 'id="from-the-booth"',
        )
        for marker in markers:
            self.assertEqual(html.count(marker), 1, marker)
            if marker.startswith("id="):
                start = html.rindex("<", 0, html.index(marker))
                self.assertTrue(html.startswith("<section", start), marker)
        order = [html.index(s) for s in markers]
        self.assertEqual(order, sorted(order))
        self.assertIn('class="skip-link"', html)  # base chrome intact


class BlogTeaserTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.author = BlogAuthor.objects.create(
            first_name="Jane", last_name="Doe"
        )
        cls.category = BlogCategory.objects.create(name="News")
        cls.post = BlogPost.objects.create(
            title="Fort Kent Cinema Turns 90",
            subtitle="A look back at the history of the theater",
            author=cls.author,
            category=cls.category,
            content="Nine decades of movies in the St. John Valley.",
            post_date="2026-01-01",
        )

    @mock.patch("web.views.get_coming_soon", return_value=[])
    @mock.patch("web.views.get_now_showing", return_value=[])
    def test_recent_post_renders_on_home(self, _ns, _cs):
        html = self.client.get(reverse("home")).content.decode()
        self.assertIn("Fort Kent Cinema Turns 90", html)

    @mock.patch("web.views.get_coming_soon", return_value=[])
    @mock.patch("web.views.get_now_showing", return_value=[])
    def test_recent_post_renders_as_a_home_card(self, _ns, _cs):
        # The From the booth post cards are home cards, not the /blog/ list
        # card: category and date eyebrow, the title as the link, the
        # subtitle, and a byline.
        html = self.client.get(reverse("home")).content.decode()
        self.assertIn("Fort Kent Cinema Turns 90", html)
        self.assertIn('class="home-card blog-post-card"', html)
        self.assertIn("A look back at the history of the theater", html)
        self.assertIn("By Jane Doe", html)

    @mock.patch("web.views.get_coming_soon", return_value=[])
    @mock.patch("web.views.get_now_showing", return_value=[])
    def test_teaser_shows_three_newest_posts(self, _ns, _cs):
        # From the booth carries the three newest posts, one row of three. Newest first, the rest dropped.
        for i in range(8):
            BlogPost.objects.create(
                title=f"Filler {i}",
                # BlogPost slugs come from the subtitle, not the title.
                subtitle=f"Filler subtitle {i}",
                author=self.author,
                category=self.category,
                content="Body.",
                post_date=f"2026-02-{i + 1:02d}",
            )
        resp = self.client.get(reverse("home"))
        posts = list(resp.context["recent_posts"])
        self.assertEqual(len(posts), 3)
        self.assertEqual(
            [p.title for p in posts],
            [f"Filler {i}" for i in range(7, 4, -1)],
        )
        # The 2026-01-01 post from setUpTestData is the oldest and falls off.
        self.assertNotIn("Fort Kent Cinema Turns 90", [p.title for p in posts])


class MembershipPageTests(TestCase):
    def test_membership_200_and_template(self):
        resp = self.client.get(reverse("membership"))
        self.assertEqual(resp.status_code, 200)
        self.assertTemplateUsed(resp, "web/membership.html")

    def test_renders_tiers_and_faq(self):
        html = self.client.get(reverse("membership")).content.decode()
        self.assertIn("Silver Screen", html)       # a tier name from MEMBERSHIP
        self.assertIn("tier-card", html)
        self.assertIn("membership-faq", html)
        self.assertIn("How long does a membership last?", html)  # a FAQ question
        self.assertIn('id="tiers"', html)          # scroll-to anchor target

    def test_membership_meta(self):
        html = self.client.get(reverse("membership")).content.decode()
        self.assertIn("Membership", html)


class RentalsPageTests(TestCase):
    def test_rentals_200_and_content(self):
        resp = self.client.get(reverse("rentals"))
        self.assertEqual(resp.status_code, 200)
        self.assertTemplateUsed(resp, "web/rentals.html")
        html = resp.content.decode()
        self.assertIn("RENT THE THEATER", html)
        self.assertIn("$225", html)  # base rate
        self.assertIn("rentals-page", html)

    def test_rentals_meta(self):
        html = self.client.get(reverse("rentals")).content.decode()
        self.assertIn("Private Rentals", html)

    def test_rentals_content_sections(self):
        html = self.client.get(reverse("rentals")).content.decode()
        self.assertIn("rental-card--featured", html)
        self.assertIn("PRIVATE SCREENING", html)
        self.assertIn("LICENSED SCREENING", html)
        self.assertIn("QUESTIONS WE GET", html)
        self.assertIn("READY TO BOOK?", html)

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


class StaticAssetsTests(TestCase):
    def test_core_css_present(self):
        for name in ("css/variables.css", "css/global.css", "css/effects.css"):
            self.assertIsNotNone(find(name), f"missing static asset: {name}")

    def test_component_css_present(self):
        # Representative sample of the ported component/page sheets.
        for name in ("css/Hero.css", "css/Nav.css", "css/Footer.css", "css/NowShowing.css"):
            self.assertIsNotNone(find(name), f"missing static asset: {name}")
