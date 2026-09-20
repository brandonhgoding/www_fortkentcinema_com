from unittest import mock, skip

from django.test import TestCase
from django.urls import reverse
from django.contrib.staticfiles.finders import find

from blog.models import BlogAuthor, BlogCategory, BlogPost


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
            "showtimes": {"2999-01-15": ["6:00 PM"], "2999-01-16": ["7:00 PM"]},
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
            "showtimes": {"2000-01-01": ["6:00 PM"]},
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

    def test_out_of_range_month_404(self):
        for bad in ("/calendar/2999/12/", "/calendar/2999/13/"):
            self.assertEqual(self.client.get(bad).status_code, 404)


class HomeIntegrationTests(TestCase):
    @mock.patch("web.views.get_coming_soon", return_value=[])
    @mock.patch("web.views.get_now_showing", return_value=[])
    def test_full_home_composition_order(self, _ns, _cs):
        html = self.client.get(reverse("home")).content.decode()
        # Sections appear in the SPA's order
        order = [html.index(s) for s in (
            'class="hero"', 'id="now-showing"', 'id="coming-soon"',
        )]
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
    def test_recent_post_uses_shared_blog_card_partial(self, _ns, _cs):
        # Guards the blog_teaser.html refactor onto the shared
        # partials/blog_card.html include: both the post content and the
        # blog-card markup it renders must appear together on the home page.
        html = self.client.get(reverse("home")).content.decode()
        self.assertIn("Fort Kent Cinema Turns 90", html)
        self.assertIn('class="blog-card"', html)
        self.assertIn('class="blog-card-excerpt"', html)

    @mock.patch("web.views.get_coming_soon", return_value=[])
    @mock.patch("web.views.get_now_showing", return_value=[])
    def test_teaser_shows_six_newest_posts(self, _ns, _cs):
        # Six fills the teaser grid evenly at every breakpoint (3/2/1 across),
        # so a row is never left half empty. Newest first, oldest dropped.
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
        self.assertEqual(len(posts), 6)
        self.assertEqual(
            [p.title for p in posts],
            [f"Filler {i}" for i in range(7, 1, -1)],
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
        self.assertIn("POLICIES", html)
        self.assertIn("READY TO BOOK?", html)


@skip("About page temporarily hidden from nav/urls — re-enable when the /about route is restored")
class AboutPageTests(TestCase):
    def test_about_200_and_content(self):
        resp = self.client.get(reverse("about"))
        self.assertEqual(resp.status_code, 200)
        self.assertTemplateUsed(resp, "web/about.html")
        html = resp.content.decode()
        self.assertIn("OUR STORY", html)
        self.assertIn("Savoy", html)     # from the real history copy
        self.assertIn("about-page", html)


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
