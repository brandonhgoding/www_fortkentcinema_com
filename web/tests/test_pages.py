import datetime
from unittest import mock, skip

from django.test import TestCase
from django.urls import reverse
from django.contrib.staticfiles.finders import find

from blog.models import BlogAuthor, BlogCategory, BlogPost
from web.constants import CINEMA_TZ
from web.tests.test_crawl_and_schema import jsonld


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
        from web.constants import SITE_CONFIG

        labels = [item["label"] for item in SITE_CONFIG["navigation"]]
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
        self.assertIn("fx-dust", html)
        self.assertIn("data-ambient-dust", html)

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
        self.assertIn("ornament", html)          # dividers present
        self.assertIn('data-ambient-dust', html)  # base chrome intact


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


class SilentsSyncedEventTests(TestCase):
    """The one-off /events/ page and its self-expiring homepage CTA.

    The event is not booked as a cinema.Engagement, so nothing else on the site
    knows it exists — these tests are the only thing standing between a wrong
    date and a lobby full of people on the wrong night.
    """

    def url(self):
        return reverse("event_silents_synced")

    def test_page_returns_200_and_uses_its_template(self):
        resp = self.client.get(self.url())
        self.assertEqual(resp.status_code, 200)
        self.assertTemplateUsed(resp, "web/event_silents_synced.html")

    def test_page_carries_the_pitch(self):
        html = self.client.get(self.url()).content.decode()
        for probe in [
            "A Woman of the World",
            "Pearl Jam",
            "Pola Negri",
            "Malcolm St. Clair",
            "Silents Synced",
            "Tuesday, September 1",
            "6:30 PM",
        ]:
            self.assertIn(probe, html, f"{probe} missing from the event page")

    def test_plan_your_night_carries_price_and_doors(self):
        """Both were blank until the theater confirmed them, and the template
        omits whichever is empty — so their presence is worth asserting."""
        html = self.client.get(self.url()).content.decode()
        self.assertIn("$5", html)
        self.assertIn("6:00 PM", html)
        self.assertIn("Doors", html)
        self.assertIn("Admission", html)

    def test_trailer_makes_no_youtube_request_until_clicked(self):
        """The facade is the point: a hardcoded iframe src would pull a
        third-party frame into every pageload of a page whose whole job is to
        load fast for people deciding whether to come out on a Tuesday."""
        html = self.client.get(self.url()).content.decode()
        self.assertIn("event-trailer", html)
        self.assertIn("Watch the trailer", html)
        # The URL appears only inside the Alpine expression, never as a plain
        # src=/href= the browser would fetch on load.
        self.assertNotIn('src="https://www.youtube', html)
        self.assertIn("youtube-nocookie.com/embed/JnRPMubIBY8", html)

    def test_trailer_has_a_watch_on_youtube_escape_hatch(self):
        """An embed can refuse to play for reasons outside our control, and the
        in-frame failure is a dead box with no way out. The link must always be
        present, not conditional on the player working."""
        html = self.client.get(self.url()).content.decode()
        self.assertIn("https://www.youtube.com/watch?v=JnRPMubIBY8", html)
        self.assertIn("Watch on YouTube", html)

    def test_trailer_in_jsonld(self):
        html = self.client.get(self.url()).content.decode()
        trailer = jsonld(html, "ScreeningEvent")["workPresented"]["trailer"]
        self.assertEqual(trailer["@type"], "VideoObject")
        self.assertIn("JnRPMubIBY8", trailer["embedUrl"])

    def test_url_has_no_trailing_slash(self):
        """Detail pages here are slugless-suffix (/movies/<slug>, /blog/<slug>).
        A trailing slash would cost a 301 on every click and every crawl."""
        self.assertEqual(self.url(), "/events/silents-synced-a-woman-of-the-world")

    def test_no_template_comment_leaks_into_page(self):
        html = self.client.get(self.url()).content.decode()
        self.assertNotIn("{#", html)
        self.assertNotIn("{% comment %}", html)

    def test_screening_event_jsonld_matches_the_constant(self):
        """Not booked in the catalog, so this block is the only structured data
        that says the screening exists. An offset-naive startDate is ambiguous
        to every consumer, so the offset must be present."""
        from web.constants import EVENT_SILENTS_SYNCED

        html = self.client.get(self.url()).content.decode()
        block = jsonld(html, "ScreeningEvent")
        self.assertIsNotNone(block, "no ScreeningEvent JSON-LD on the event page")
        self.assertEqual(
            block["startDate"], EVENT_SILENTS_SYNCED["starts_at"].isoformat()
        )
        self.assertIn("-04:00", block["startDate"])
        self.assertEqual(block["workPresented"]["name"], "A Woman of the World")
        self.assertEqual(block["location"]["name"], "Fort Kent Cinema")

    def test_jsonld_advertises_no_price(self):
        """Tickets are door-only. An `offers` block would be a fabricated price
        in a format search engines treat as authoritative."""
        html = self.client.get(self.url()).content.decode()
        self.assertNotIn("offers", jsonld(html, "ScreeningEvent"))

    def test_page_is_in_the_sitemap(self):
        xml = self.client.get("/sitemap.xml").content.decode()
        self.assertIn(self.url(), xml)


class SilentsSyncedCTATests(TestCase):
    """The CTA expires on its own. If this ever stops working the homepage
    advertises a show that already happened."""

    def before(self):
        return datetime.datetime(2026, 8, 20, 12, 0, tzinfo=CINEMA_TZ)

    def after(self):
        return datetime.datetime(2026, 9, 2, 12, 0, tzinfo=CINEMA_TZ)

    @mock.patch("web.views.get_coming_soon", return_value=[])
    @mock.patch("web.views.get_now_showing", return_value=[])
    def test_cta_shows_before_the_event(self, _ns, _cs):
        with mock.patch("django.utils.timezone.now", return_value=self.before()):
            html = self.client.get(reverse("home")).content.decode()
        self.assertIn('class="event-cta"', html)
        self.assertIn(reverse("event_silents_synced"), html)
        self.assertIn("SILENTS SYNCED", html)
        # A $5 ticket is the strongest thing the banner has to say.
        self.assertIn("$5 at the door", html)

    @mock.patch("web.views.get_coming_soon", return_value=[])
    @mock.patch("web.views.get_now_showing", return_value=[])
    def test_cta_disappears_after_the_event(self, _ns, _cs):
        with mock.patch("django.utils.timezone.now", return_value=self.after()):
            html = self.client.get(reverse("home")).content.decode()
        self.assertNotIn('class="event-cta"', html)
        self.assertNotIn(reverse("event_silents_synced"), html)

    @mock.patch("web.views.get_coming_soon", return_value=[])
    @mock.patch("web.views.get_now_showing", return_value=[])
    def test_cta_sits_above_now_showing(self, _ns, _cs):
        """Top slot, where the retired Classic Movie Night CTA lived."""
        with mock.patch("django.utils.timezone.now", return_value=self.before()):
            html = self.client.get(reverse("home")).content.decode()
        self.assertLess(html.index('class="event-cta"'), html.index('id="now-showing"'))

    @mock.patch("web.views.get_coming_soon", return_value=[])
    @mock.patch("web.views.get_now_showing", return_value=[])
    def test_no_orphan_divider_once_the_cta_expires(self, _ns, _cs):
        """The CTA's trailing divider is inside the same guard, so the banner
        and exactly one divider leave together — no stacked pair left behind."""
        with mock.patch("django.utils.timezone.now", return_value=self.before()):
            before = self.client.get(reverse("home")).content.decode()
        with mock.patch("django.utils.timezone.now", return_value=self.after()):
            after = self.client.get(reverse("home")).content.decode()
        self.assertEqual(
            before.count("ornament-divider") - 1, after.count("ornament-divider")
        )

    def test_cta_is_not_hidden_on_phones(self):
        """static/css/home.css hides every other homepage CTA below 600px. This
        one is deliberately exempt — a one-night event needs mobile reach."""
        from pathlib import Path

        from django.conf import settings

        home_css = (
            Path(settings.BASE_DIR) / "static" / "css" / "home.css"
        ).read_text()
        self.assertNotIn(".event-cta", home_css)


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
