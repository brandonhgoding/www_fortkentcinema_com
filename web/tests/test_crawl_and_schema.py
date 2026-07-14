"""Crawl leaks and the remaining structured data.

The calendar was an unbounded crawl trap: /calendar/1900/0/ returned 200, and the
fragment carries prev/next links, so a crawler could walk ~120,000 URLs of thin
content. It's a bare fragment with no <head>, so it can't carry a robots meta —
the X-Robots-Tag header is the only mechanism available.
"""

import datetime
import json
import re

from blog.models import BlogAuthor, BlogCategory, BlogPost
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from web.constants import MEMBERSHIP_FAQ


def jsonld(html, type_):
    for raw in re.findall(
        r'<script type="application/ld\+json">\s*(.*?)\s*</script>', html, re.S
    ):
        block = json.loads(raw)
        if block.get("@type") == type_:
            return block
    return None


class CalendarCrawlTrapTests(TestCase):
    def this_year(self):
        return timezone.localdate().year

    def test_calendar_sends_noindex_nofollow(self):
        """No <head> to put a robots meta in, so the header is the only option.
        `nofollow` is what stops Google walking prev/next forever."""
        resp = self.client.get(f"/calendar/{self.this_year()}/6/")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp["X-Robots-Tag"], "noindex, nofollow")

    def test_real_pages_are_not_noindexed(self):
        for name in ["home", "membership", "blog_list"]:
            resp = self.client.get(reverse(name))
            self.assertNotIn("X-Robots-Tag", resp)

    def test_years_far_in_the_past_404(self):
        """/calendar/1900/0/ used to return 200 — the range was MINYEAR..MAXYEAR."""
        self.assertEqual(self.client.get("/calendar/1900/0/").status_code, 404)

    def test_years_far_in_the_future_404(self):
        self.assertEqual(self.client.get("/calendar/2200/0/").status_code, 404)

    def test_nearby_years_still_work(self):
        """A real visitor browsing a month or two either way must not hit a 404."""
        for year in (self.this_year() - 1, self.this_year(), self.this_year() + 1):
            self.assertEqual(
                self.client.get(f"/calendar/{year}/0/").status_code, 200, f"year {year}"
            )

    def test_invalid_month_still_404s(self):
        self.assertEqual(
            self.client.get(f"/calendar/{self.this_year()}/12/").status_code, 404
        )


class RobotsTxtTests(TestCase):
    def robots(self):
        return self.client.get("/robots.txt").content.decode()

    def test_private_areas_disallowed(self):
        body = self.robots()
        for path in ["/admin/", "/api/", "/dashboard/", "/login", "/logout/"]:
            self.assertIn(f"Disallow: {path}", body)

    def test_calendar_is_not_disallowed(self):
        """Deliberate. A disallowed URL is never fetched, so Google would never
        SEE the X-Robots-Tag noindex on calendar URLs it already holds. Disallow
        and noindex defeat each other here."""
        self.assertNotIn("Disallow: /calendar", self.robots())

    def test_sitemap_declared(self):
        self.assertIn("Sitemap:", self.robots())


class OgImageTests(TestCase):
    def test_og_image_is_small_enough_to_actually_be_fetched(self):
        """It was a 5760x3844 camera original at 3.5MB. Crawlers time out on
        that, so link previews were simply failing."""
        from pathlib import Path

        from django.conf import settings
        from PIL import Image

        path = Path(settings.BASE_DIR) / "static" / "img" / "og-image.jpg"
        size = path.stat().st_size
        self.assertLess(size, 300_000, f"og-image is {size:,} bytes")

        with Image.open(path) as im:
            self.assertEqual(im.size, (1200, 630))


class FaviconTests(TestCase):
    def test_apple_touch_icon_is_a_png_not_an_svg(self):
        """iOS does not support SVG for apple-touch-icon. Pointing it at
        favicon.svg gave iPhone home-screen bookmarks a blank icon."""
        html = self.client.get(reverse("home")).content.decode()
        tag = re.search(r'<link[^>]+rel="apple-touch-icon"[^>]*>', html).group(0)
        self.assertIn(".png", tag)
        self.assertNotIn(".svg", tag)
        self.assertIn('sizes="180x180"', tag)

    def test_apple_touch_icon_is_180x180_square_and_opaque(self):
        """iOS masks the icon itself, so it must be full-bleed and have no alpha —
        transparent corners get filled with black."""
        from pathlib import Path

        from django.conf import settings
        from PIL import Image

        path = Path(settings.BASE_DIR) / "static" / "img" / "apple-touch-icon.png"
        with Image.open(path) as im:
            self.assertEqual(im.size, (180, 180))
            self.assertEqual(im.mode, "RGB", "must be opaque — no alpha channel")

    def test_png_favicon_fallbacks_exist(self):
        html = self.client.get(reverse("home")).content.decode()
        self.assertIn('sizes="32x32"', html)
        self.assertIn('sizes="16x16"', html)
        self.assertIn('type="image/svg+xml"', html)  # modern browsers still get the SVG


class BlogPostingSchemaTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        author = BlogAuthor.objects.create(first_name="Brandon", last_name="Goding")
        cat = BlogCategory.objects.create(name="Reviews")
        cls.post = BlogPost.objects.create(
            title="A Review of Something",
            subtitle="It was good",
            author=author,
            category=cat,
            post_date=datetime.date(2026, 3, 23),
            content="...",
        )

    def schema(self):
        html = self.client.get(f"/blog/{self.post.slug}").content.decode()
        return jsonld(html, "BlogPosting")

    def test_emits_blogposting(self):
        s = self.schema()
        self.assertIsNotNone(s, "no BlogPosting JSON-LD")
        self.assertEqual(s["headline"], "A Review of Something")
        self.assertEqual(s["datePublished"], "2026-03-23")
        self.assertEqual(s["author"]["name"], "Brandon Goding")
        self.assertEqual(s["articleSection"], "Reviews")

    def test_no_fabricated_datemodified(self):
        """BlogPost has no updated_at field. Emitting post_date as dateModified
        would tell Google an edited post was last touched the day it went up."""
        self.assertNotIn("dateModified", self.schema())


class FaqSchemaTests(TestCase):
    def schema(self):
        html = self.client.get(reverse("membership")).content.decode()
        return jsonld(html, "FAQPage")

    def test_emits_faqpage_with_every_question(self):
        s = self.schema()
        self.assertIsNotNone(s, "no FAQPage JSON-LD")
        self.assertEqual(len(s["mainEntity"]), len(MEMBERSHIP_FAQ))

    def test_answers_match_the_visible_page(self):
        """Google penalises FAQ markup whose answers aren't on the page."""
        from django.utils.html import escape

        html = self.client.get(reverse("membership")).content.decode()
        for q in self.schema()["mainEntity"]:
            self.assertEqual(q["@type"], "Question")
            # The rendered page escapes apostrophes (&#x27;), the JSON-LD doesn't.
            self.assertIn(escape(q["acceptedAnswer"]["text"]), html)
            self.assertIn(escape(q["name"]), html)


class ClassicsTitleTests(TestCase):
    def test_falls_back_when_nothing_scheduled(self):
        html = self.client.get(reverse("classics")).content.decode()
        self.assertIn(
            "<title>Classic Movie Night — Fort Kent Cinema</title>", html
        )

    def test_names_the_scheduled_film(self):
        from cinema.models import Engagement, EngagementFilm, Film, Screen, Showtime

        screen = Screen.objects.create(name="Screen 1", capacity=100)
        film = Film.objects.create(title="Carnival of Souls", poster_url="https://x/p.jpg")
        today = timezone.localdate()
        eng = Engagement.objects.create(
            screen=screen,
            start_date=today,
            end_date=today + datetime.timedelta(days=2),
            status="CONFIRMED",
            kind="CLASSIC",
        )
        EngagementFilm.objects.create(engagement=eng, film=film, position=0)
        Showtime.objects.create(
            engagement=eng,
            screen=screen,
            starts_at=timezone.now() + datetime.timedelta(days=1),
        )

        html = self.client.get(reverse("classics")).content.decode()
        self.assertIn("Carnival of Souls — Classic Movie Night", html)
