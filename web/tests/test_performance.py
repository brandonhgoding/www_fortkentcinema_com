"""Core Web Vitals regressions.

The site measured LCP 3.9s / FCP 3.0s on mobile, with 0 "good" URLs in Search
Console. The cause was not images — CLS was already 0.00. It was CSS:

  - global.css line 1 did `@import url(<google fonts>)`, and line 2 imported
    variables.css. A CSS @import can't be DISCOVERED until the importing sheet
    has downloaded and parsed, so this put a 4-level-deep chain into two
    third-party hosts on the critical path. Worst single blocker: 911ms.
  - 15 separate render-blocking stylesheets. The bytes were trivial (~25KB);
    the ROUND TRIPS were the cost, especially over HTTP/1.1.

These tests lock in the fixes. They are cheap to keep passing and the failure
mode they prevent is invisible until someone runs Lighthouse months later.
"""

import re
from pathlib import Path

from django.conf import settings
from django.test import TestCase
from django.urls import reverse

CSS_DIR = Path(settings.BASE_DIR) / "static" / "css"
BUNDLE = CSS_DIR / "bundle.css"


def stylesheet_links(html):
    return re.findall(r'<link[^>]+rel="stylesheet"[^>]*href="([^"]+)"', html)


class SingleStylesheetTests(TestCase):
    def test_public_pages_link_exactly_one_stylesheet(self):
        """15 render-blocking stylesheets cost ~1,680ms. Adding a per-page
        <link> back would silently undo this — add it to
        frontend/styles/main.css instead."""
        for name in ["home", "membership", "rentals", "blog_list"]:
            html = self.client.get(reverse(name)).content.decode()
            links = stylesheet_links(html)
            self.assertEqual(
                len(links), 1, f"{name} links {len(links)} stylesheets: {links}"
            )
            self.assertIn("bundle", links[0])

    def test_no_third_party_font_host_anywhere(self):
        """Self-hosted. A reintroduced Google Fonts link puts two cross-origin
        hosts back on the critical path."""
        for name in ["home", "blog_list"]:
            html = self.client.get(reverse(name)).content.decode()
            self.assertNotIn("fonts.googleapis.com", html)
            self.assertNotIn("fonts.gstatic.com", html)

    def test_preconnects_to_poster_hosts(self):
        html = self.client.get(reverse("home")).content.decode()
        self.assertIn('rel="preconnect" href="https://image.tmdb.org"', html)

    def test_above_the_fold_fonts_are_preloaded(self):
        """Without these the browser can't discover a font until it has parsed the
        CSS, so it paints in the fallback and then swaps, and that reflow is a
        layout shift.

        Oswald is deliberately not here — it sets the /history/ playbills only,
        below the fold on one route. Nor are the italic and latin-ext subsets,
        which unicode-range gates behind characters most pages never use."""
        html = self.client.get(reverse("home")).content.decode()
        preloads = re.findall(r'<link[^>]+rel="preload"[^>]+>', html)
        self.assertEqual(len(preloads), 3, "expected the 3 latin faces preloaded")
        for family in ["eb-garamond", "cabin-latin", "cabin-condensed-400"]:
            self.assertTrue(
                any(family in p for p in preloads), f"{family} not preloaded"
            )
        for family in ["oswald", "italic", "latin-ext"]:
            self.assertFalse(
                any(family in p for p in preloads), f"{family} should not preload"
            )

    def test_font_preloads_are_crossorigin(self):
        """Required even same-origin; without it the browser fetches each font
        twice — once for the preload, once for the actual use."""
        html = self.client.get(reverse("home")).content.decode()
        for p in re.findall(r'<link[^>]+rel="preload"[^>]+>', html):
            self.assertIn("crossorigin", p)
            self.assertIn('as="font"', p)


class BundleTests(TestCase):
    """The built artefact. `npm run build` regenerates it."""

    def setUp(self):
        if not BUNDLE.exists():
            self.skipTest("bundle.css not built — run `npm run build` in frontend/")
        self.css = BUNDLE.read_text()

    def test_bundle_has_no_import(self):
        """An @import in the bundle would recreate the render-blocking chain the
        whole change exists to remove."""
        self.assertNotIn("@import", self.css)

    def test_bundle_has_no_third_party_urls(self):
        self.assertNotIn("fonts.googleapis.com", self.css)
        self.assertNotIn("fonts.gstatic.com", self.css)

    def test_bundle_contains_rules_from_every_source_sheet(self):
        """A smoke check that the cascade order held and nothing was dropped."""
        for probe in [
            "--color-gold",  # variables.css
            "@font-face",  # fonts.css
            ".nav-logo",  # Nav.css
            ".footer",  # Footer.css
            ".hero",  # Hero.css
            ".movie-card",  # MovieCard.css
            ".coming-",  # ComingSoon.css
            ".home-card",  # HomeSections.css
            ".tier-card",  # TierCard.css
            ".movie-page",  # MoviePage.css
            ".blog-pagination",  # BlogListPage.css
            ".thanks-title",  # global.css (appended)
        ]:
            self.assertIn(probe, self.css, f"{probe} missing from bundle")

    def test_bundle_carries_the_home_vocabulary_and_not_the_old_pair(self):
        """HomeSections.css is in the bundle; the retired CTA grid is not."""
        for probe in (".home-card", ".home-section--accent", ".btn-member"):
            self.assertIn(probe, self.css, f"{probe} missing from bundle")
        self.assertNotIn(".cta-pair", self.css)
        self.assertNotIn("--color-ornament-gold", self.css)

    def test_fonts_are_self_hosted_and_relative(self):
        """The url() refs must stay relative so collectstatic can rewrite them to
        hashed filenames. esbuild's --external:*.woff2 is what preserves this;
        without it esbuild inlines the fonts and Django never sees them."""
        refs = re.findall(r"url\((\.\./fonts/[^)]+\.woff2)\)", self.css)
        self.assertGreater(len(refs), 0, "no self-hosted font references")
        for ref in refs:
            name = ref.replace("../fonts/", "")
            self.assertTrue(
                (Path(settings.BASE_DIR) / "static" / "fonts" / name).exists(),
                f"bundle references a font that isn't in static/fonts/: {name}",
            )

    def test_fonts_use_display_swap(self):
        """Without swap the text is invisible until the font arrives."""
        faces = self.css.count("@font-face")
        swaps = self.css.count("font-display:swap") + self.css.count(
            "font-display: swap"
        )
        self.assertEqual(swaps, faces, "every @font-face needs font-display: swap")

    def test_no_duplicate_font_files(self):
        """These are VARIABLE fonts — one file covers a weight range. Naming the
        same bytes once per weight made the browser download them up to 4 times
        (font payload went 158KB -> 235KB before this was caught). Each @font-face
        must declare a weight RANGE and share the file."""
        import hashlib

        fonts_dir = Path(settings.BASE_DIR) / "static" / "fonts"
        digests = {}
        for f in fonts_dir.glob("*.woff2"):
            h = hashlib.md5(f.read_bytes()).hexdigest()
            digests.setdefault(h, []).append(f.name)
        dupes = {h: names for h, names in digests.items() if len(names) > 1}
        self.assertEqual(dupes, {}, f"byte-identical font files: {dupes}")


class SourceCssTests(TestCase):
    def test_no_import_in_any_source_stylesheet(self):
        """This is the bug. global.css shipped with two of them for years."""
        offenders = []
        for f in CSS_DIR.glob("*.css"):
            if re.search(r"\.[0-9a-f]{12}\.css$", f.name) or f.name == "bundle.css":
                continue
            body = re.sub(r"/\*.*?\*/", "", f.read_text(), flags=re.S)
            if "@import" in body:
                offenders.append(f.name)
        self.assertEqual(offenders, [], f"@import found in: {offenders}")


class ImageLoadingTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        import datetime

        from cinema.models import Engagement, EngagementFilm, Film, Screen
        from django.utils import timezone

        cls.screen = Screen.objects.create(name="Screen 1", capacity=100)
        today = timezone.localdate()

        # Two now-showing films: the first poster is above the fold, the second isn't.
        cls.films = []
        for i in range(2):
            film = Film.objects.create(
                title=f"Poster Test {i}", poster_url=f"https://image.tmdb.org/p{i}.jpg"
            )
            eng = Engagement.objects.create(
                screen=cls.screen,
                start_date=today,
                end_date=today + datetime.timedelta(days=3),
                status="CONFIRMED",
            )
            EngagementFilm.objects.create(engagement=eng, film=film, position=0)
            from cinema.models import Showtime

            Showtime.objects.create(
                engagement=eng,
                screen=cls.screen,
                starts_at=timezone.now() + datetime.timedelta(days=1, hours=i),
            )
            cls.films.append(film)

    def test_first_now_showing_poster_is_eager_and_prioritised(self):
        """Lazy-loading an above-the-fold image DELAYS LCP — the opposite of the
        goal."""
        html = self.client.get(reverse("home")).content.decode()
        posters = re.findall(r"<img[^>]+movie-poster-img[^>]*>", html)
        self.assertGreaterEqual(len(posters), 2)
        self.assertIn('fetchpriority="high"', posters[0])
        self.assertNotIn('loading="lazy"', posters[0])

    def test_subsequent_now_showing_posters_are_lazy(self):
        html = self.client.get(reverse("home")).content.decode()
        posters = re.findall(r"<img[^>]+movie-poster-img[^>]*>", html)
        self.assertIn('loading="lazy"', posters[1])

    def test_movie_page_poster_is_not_lazy(self):
        """It is that page's LCP element."""
        film = self.films[0]
        html = self.client.get(f"/movies/{film.slug}").content.decode()
        poster = re.search(r"<img[^>]+movie-page-poster-img[^>]*>", html).group(0)
        self.assertIn('fetchpriority="high"', poster)
        self.assertNotIn('loading="lazy"', poster)


class CacheHeaderTests(TestCase):
    def test_static_assets_cached_for_a_year(self):
        """Assets are content-hashed, so a changed file gets a new URL and can
        never be served stale."""
        self.assertEqual(settings.WHITENOISE_MAX_AGE, 31536000)
