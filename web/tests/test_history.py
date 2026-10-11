import json
import re
from pathlib import Path

from django.conf import settings
from django.test import TestCase
from django.urls import reverse

from web.constants import FILM_HISTORY_VIDEO, SAVOY_PLAYBILLS


class HistoryPageTests(TestCase):
    def setUp(self) -> None:
        self.response = self.client.get(reverse("history"))
        self.html = self.response.content.decode()

    def test_returns_200_and_uses_templates(self):
        self.assertEqual(self.response.status_code, 200)
        self.assertTemplateUsed(self.response, "base.html")
        self.assertTemplateUsed(self.response, "web/history.html")
        self.assertTemplateUsed(self.response, "partials/playbill.html")

    def test_no_template_comment_leaks_into_page(self):
        # Django's {# #} is single-line only; a multi-line one leaks as text.
        self.assertNotIn("{#", self.html)
        self.assertNotIn("{% comment %}", self.html)

    def test_is_in_the_sitemap_and_nav(self):
        self.assertIn("/history/", self.client.get("/sitemap.xml").content.decode())
        self.assertIn('href="/history/"', self.client.get("/").content.decode())


class SourcingTests(TestCase):
    """The page's whole claim to trustworthiness is that it shows its sources.

    These assert the attribution survives an edit — a future rewrite that
    quietly drops the citation would turn a sourced history into an anonymous
    one, which is exactly the failure this page was built to avoid.
    """

    def setUp(self) -> None:
        self.html = self.client.get(reverse("history")).content.decode()

    def test_credits_the_published_article_and_its_author(self):
        self.assertIn("Ornstein", self.html)
        self.assertIn("Northern Maine Journal", self.html)
        self.assertIn("April/June 2000", self.html)

    def test_credits_the_historical_society_video(self):
        self.assertIn(FILM_HISTORY_VIDEO["youtube_id"], self.html)
        self.assertIn("Historical Society", self.html)

    def test_flags_the_gem_as_uncorroborated(self):
        # The Gem rests on one source. If the hedging is ever edited away,
        # this page starts asserting something we cannot support.
        self.assertIn("the Gem", self.html)
        self.assertIn("corroborate", self.html)

    def test_names_the_people_the_sources_name(self):
        for person in (
            "Burdina Wheelock",
            "Gloria Ouellette",
            "Delsie Charette",
            "Ouellette",
        ):
            self.assertIn(person, self.html)


class PlaybillTests(TestCase):
    def setUp(self) -> None:
        self.html = self.client.get(reverse("history")).content.decode()

    def test_renders_every_playbill(self):
        self.assertEqual(
            self.html.count('class="playbill__sheet"'), len(SAVOY_PLAYBILLS)
        )

    def test_transcribes_the_bill_verbatim(self):
        # The printer's ampersand and quotes are the point; a "tidied" title
        # would mean the recreation had drifted from the sheet.
        self.assertIn("Wheeler &amp; Woolsey", self.html)
        self.assertIn("Hook, Line &amp; Sinker", self.html)
        self.assertIn("Joan Crawford", self.html)
        self.assertIn("All Talking", self.html)

    def test_every_show_row_is_rendered(self):
        rows = sum(len(pb["shows"]) for pb in SAVOY_PLAYBILLS)
        self.assertEqual(self.html.count('class="playbill__day"'), rows)

    def test_a_film_without_a_url_is_not_a_link(self):
        # Every URL is blank today. None may render as an anchor, or the page
        # ships dead links.
        self.assertNotIn('class="playbill__film playbill__film--linked"', self.html)
        self.assertIn('class="playbill__film"', self.html)

    def test_a_film_with_a_url_becomes_a_link(self):
        pb = {
            **SAVOY_PLAYBILLS[0],
            "shows": [
                {
                    **SAVOY_PLAYBILLS[0]["shows"][0],
                    "youtube_url": "https://www.youtube.com/watch?v=abc123",
                }
            ],
        }
        with self.settings():
            from django.template.loader import render_to_string

            html = render_to_string(
                "partials/playbill.html", {"pb": pb, "pbindex": 0}
            )
        self.assertIn('href="https://www.youtube.com/watch?v=abc123"', html)
        self.assertIn("playbill__film--linked", html)
        self.assertIn('rel="noopener noreferrer"', html)


class VideoEmbedTests(TestCase):
    def setUp(self) -> None:
        self.html = self.client.get(reverse("history")).content.decode()

    def test_iframe_src_is_deferred_until_clicked(self):
        # The facade the rest of the site uses: no request to YouTube on load.
        self.assertIn(":src=", self.html)
        self.assertNotIn(
            f'src="https://www.youtube-nocookie.com/embed/'
            f'{FILM_HISTORY_VIDEO["youtube_id"]}',
            self.html,
        )

    def test_uses_the_nocookie_host(self):
        self.assertIn("youtube-nocookie.com", self.html)

    def test_offers_a_plain_link_when_the_embed_fails(self):
        self.assertIn(
            f'https://www.youtube.com/watch?v={FILM_HISTORY_VIDEO["youtube_id"]}',
            self.html,
        )

    def test_describes_what_the_video_actually_is(self):
        # It is an exhibit walkthrough, not archival footage. Saying so before
        # someone commits 26 minutes is the honest framing.
        self.assertIn(FILM_HISTORY_VIDEO["duration"], self.html)
        self.assertIn("exhibit", self.html)


class SheetVariationTests(TestCase):
    """The six sheets are not uniform and the recreation must not flatten them.

    The printer used double quotes some weeks and single others, left one
    title unquoted, led one row with the film instead of the star, and dropped
    the "in" on another. Those are the artifacts; normalising them would make
    this a stylish approximation rather than a transcription.
    """

    def setUp(self) -> None:
        self.html = self.client.get(reverse("history")).content.decode()

    def test_all_six_sheets_are_present(self):
        self.assertEqual(len(SAVOY_PLAYBILLS), 6)
        self.assertEqual(
            self.html.count('class="playbill__sheet"'), len(SAVOY_PLAYBILLS)
        )

    def test_double_quoted_titles_keep_double_quotes(self):
        # April 6: "REDUCING". July 8: "L'Enigmatique Monsieur Parkes".
        self.assertIn("&ldquo;Reducing&rdquo;", self.html)
        self.assertIn("Enigmatique", self.html)

    def test_single_quoted_titles_keep_single_quotes(self):
        self.assertIn("&lsquo;Beau Ideal&rsquo;", self.html)

    def test_the_unquoted_title_stays_unquoted(self):
        # June 24: DADDY LONG LEGS, set without quote marks at all.
        self.assertIn("Daddy Long Legs", self.html)
        self.assertNotIn("&lsquo;Daddy Long Legs&rsquo;", self.html)

    def test_the_title_first_row_has_no_star_and_credits_below(self):
        # April 9: 'Cohens & Kellys in Africa' / With Geo. Sidney & Chas. Murray
        self.assertIn("Cohens &amp; Kellys in Africa", self.html)
        self.assertIn("With Geo. Sidney &amp; Chas. Murray", self.html)

    def test_all_talking_appears_only_on_the_april_sheets(self):
        # The tag vanishes after April 18, 1931 — a real, datable detail the
        # page draws attention to. If a later transcription adds it to a May
        # or June sheet, that claim silently becomes false.
        tagged = [
            pb["label"] for pb in SAVOY_PLAYBILLS
            if any(s.get("tag") for s in pb["shows"])
        ]
        self.assertEqual(
            tagged,
            ["Week of April 6, 1931", "Week of April 13, 1931"],
        )

    def test_every_film_is_a_1930_or_1931_release_week(self):
        # The dating argument on the page rests on this: six Monday-start
        # weeks that all fit 1931.
        import datetime

        for pb in SAVOY_PLAYBILLS:
            first = datetime.date.fromisoformat(pb["slug"])
            self.assertEqual(first.year, 1931)
            self.assertEqual(first.weekday(), 0, f"{pb['label']} is not a Monday")
            self.assertEqual(len(pb["shows"]), 6)


def jsonld_blocks(html):
    return [
        json.loads(m)
        for m in re.findall(
            r'<script type="application/ld\+json">\s*(.*?)\s*</script>', html, re.S
        )
    ]


def block_of_type(html, wanted):
    for block in jsonld_blocks(html):
        if block.get("@type") == wanted:
            return block
    return None


def headings(html):
    return [
        re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", text)).strip()
        for _, text in re.findall(r"<h([1-6])[^>]*>(.*?)</h\1>", html, re.S)
    ]


def hrefs(html):
    return re.findall(r'<a[^>]+href="([^"]+)"', html)


class HistoryOnPageSeoTests(TestCase):
    """The two on-page signals a search engine weighs hardest: the H1 and the
    heading outline. Both were saying the wrong thing."""

    def setUp(self) -> None:
        self.html = self.client.get(reverse("history")).content.decode()

    def test_h1_names_the_town(self):
        # "Going to the Movies" alone could be any cinema anywhere. The <title>
        # already names Fort Kent; the H1 has to agree with it.
        self.assertEqual(headings(self.html)[0], "Going to the Movies in Fort Kent")

    def test_playbill_wordmarks_are_not_headings(self):
        # The letterhead on each sheet is decoration, not structure. Marked up
        # as <h3> it put six identical "Savoy Theatre" entries into the page's
        # outline, drowning the six real section headings.
        self.assertNotIn("Savoy Theatre", headings(self.html))

    def test_section_headings_are_the_only_h2s(self):
        h2s = re.findall(r"<h2[^>]*>(.*?)</h2>", self.html, re.S)
        self.assertEqual(len(h2s), len(set(h2s)), "duplicate h2 in the outline")


class HistoryStructuredDataTests(TestCase):
    """The page declares og:type=article but emitted no structured data at all.

    Blog posts got BlogPosting and movie pages got Movie/ScreeningEvent; this
    page — the only long-form original writing on the site — was skipped.
    """

    def setUp(self) -> None:
        self.html = self.client.get(reverse("history")).content.decode()

    def test_every_jsonld_block_is_valid_json(self):
        # A trailing comma from a template {% if %} silently kills the whole
        # block, and nothing on the page looks broken when it happens.
        blocks = jsonld_blocks(self.html)
        self.assertGreaterEqual(len(blocks), 3)

    def test_emits_article_jsonld(self):
        article = block_of_type(self.html, "Article")
        self.assertIsNotNone(article, "no Article JSON-LD on the page")
        self.assertEqual(article["headline"], "Going to the Movies in Fort Kent")
        self.assertTrue(article["url"].endswith("/history/"))
        self.assertEqual(article["datePublished"], "2026-08-23")
        self.assertEqual(article["publisher"]["name"], "Fort Kent Cinema")

    def test_article_cites_the_published_source(self):
        # The page's whole claim to trust is that it shows its sources. The
        # machine-readable copy should say so too.
        citation = block_of_type(self.html, "Article")["citation"]
        self.assertIn("Ornstein", citation["author"]["name"])
        self.assertIn("Echoes", citation["isPartOf"]["name"])

    def test_article_names_the_theatres_it_is_about(self):
        # These are the long-tail queries. They appear nowhere in the title,
        # H1 or description — `about` is where they become entities.
        about = block_of_type(self.html, "Article")["about"]
        names = {thing["name"] for thing in about}
        self.assertEqual(
            names,
            {
                "Savoy Theatre",
                "Fort Kent Community Theatre",
                "Fort Kent Drive-In",
                "Century Theater",
            },
        )

    def test_emits_breadcrumb_trail(self):
        crumbs = block_of_type(self.html, "BreadcrumbList")
        self.assertIsNotNone(crumbs, "no BreadcrumbList on the page")
        items = crumbs["itemListElement"]
        self.assertEqual([c["name"] for c in items], ["Home", "History"])
        self.assertEqual([c["position"] for c in items], [1, 2])

    def test_emits_video_object_for_the_society_film(self):
        video = block_of_type(self.html, "VideoObject")
        self.assertIsNotNone(video, "no VideoObject for the Society's film")
        self.assertEqual(video["name"], FILM_HISTORY_VIDEO["title"])
        self.assertIn(FILM_HISTORY_VIDEO["youtube_id"], video["embedUrl"])
        self.assertIn(FILM_HISTORY_VIDEO["youtube_id"], video["thumbnailUrl"])
        self.assertEqual(video["duration"], "PT26M44S")

    def test_video_object_omits_the_upload_date_it_does_not_know(self):
        # We know the year (2019) and nothing more. Padding that to
        # "2019-01-01" would tell Google a date we made up — the same reason
        # BlogPosting omits dateModified.
        self.assertNotIn("uploadDate", block_of_type(self.html, "VideoObject"))


class HistoryInternalLinkingTests(TestCase):
    """Sitewide, exactly one link pointed here: the nav's "More" dropdown.

    That is the failure mode that kept 77 blog posts out of the index. A page
    nothing links to is a page Google will not index.
    """

    def test_footer_links_to_history_from_a_page_that_is_not_home(self):
        # Scoped to the <footer> on purpose. The nav dropdown renders on every
        # page too, so an unscoped "/history/ appears somewhere" assertion
        # passes without the footer link existing at all.
        html = self.client.get("/rentals/").content.decode()
        footer = re.search(r"<footer\b.*?</footer>", html, re.S)
        self.assertIsNotNone(footer, "no footer on the page")
        self.assertIn("/history/", hrefs(footer.group(0)))

    def test_homepage_body_promotes_the_history_page(self):
        response = self.client.get("/")
        self.assertTemplateUsed(response, "partials/cta_history.html")

    def test_homepage_links_to_history_from_more_than_just_the_nav(self):
        count = hrefs(self.client.get("/").content.decode()).count("/history/")
        self.assertGreaterEqual(count, 3, "nav dropdown is still the only link")


class HistorySocialCardTests(TestCase):
    """The page was og:type=article sharing the homepage's generic card.

    Its own card is a crop of the Savoy's newspaper masthead — the one image
    on hand that names the theatre, the street and the town in the artwork
    itself, so it still reads at thumbnail size.
    """

    # Deliberately NOT under static/img/history/: the unmerged
    # feat/history-photos branch gitignores *.jpg in that directory, which
    # would swallow this card the moment it lands.
    CARD = "img/og-history.jpg"

    def setUp(self) -> None:
        self.html = self.client.get(reverse("history")).content.decode()

    def _og_image(self):
        return re.search(
            r'<meta property="og:image" content="([^"]+)"', self.html
        ).group(1)

    def test_og_image_is_the_pages_own_card(self):
        self.assertIn(self.CARD, self._og_image())

    def test_og_image_is_not_the_site_default(self):
        self.assertNotIn("img/og-image.jpg", self._og_image())

    def test_og_image_is_absolute(self):
        # Facebook and X both drop a relative og:image on the floor.
        self.assertTrue(self._og_image().startswith("http"), self._og_image())

    def test_article_jsonld_points_at_the_same_card(self):
        # Two different images for one page is a mixed signal, and the JSON-LD
        # copy was the generic one.
        self.assertIn(self.CARD, block_of_type(self.html, "Article")["image"])

    def test_the_card_file_is_fetchable_and_correctly_sized(self):
        """A crawler that times out fetching the card shows no preview at all."""
        from pathlib import Path

        from django.conf import settings
        from PIL import Image

        path = Path(settings.BASE_DIR) / "static" / self.CARD
        self.assertTrue(path.exists(), f"{path} is missing")
        self.assertLess(path.stat().st_size, 300_000)
        with Image.open(path) as im:
            self.assertEqual(im.size, (1200, 630))

    def test_the_card_carries_no_exif(self):
        """It came off an iPhone with GPS on. Publishing that would put the
        photographer's coordinates in a file anyone can fetch."""
        from pathlib import Path

        from django.conf import settings
        from PIL import Image

        path = Path(settings.BASE_DIR) / "static" / self.CARD
        with Image.open(path) as im:
            self.assertEqual(len(im.getexif()), 0)


class HistoryNavigationTests(TestCase):
    """A 5-7 screen page with no way to move around it, arrow keys that
    turned the playbill from anywhere on the page, and bold text in the link
    colour."""

    def setUp(self):
        self.html = self.client.get(reverse("history")).content.decode()

    def test_contents_links_every_section(self):
        toc = self.html.split('class="history-toc"', 1)[1].split("</nav>", 1)[0]
        targets = re.findall(r'href="#([\w-]+)"', toc)
        self.assertGreaterEqual(len(targets), 6)
        for target in targets:
            self.assertIn(f'id="{target}"', self.html)

    def test_arrow_keys_are_scoped_to_the_carousel(self):
        self.assertNotIn("keydown.left.window", self.html)
        self.assertNotIn("keydown.right.window", self.html)
        self.assertIn("@keydown.left=", self.html)

    def test_bold_text_is_not_link_coloured(self):
        css = (Path(settings.BASE_DIR) / "static/css/HistoryPage.css").read_text()
        rule = css.split(".history-section strong {", 1)[1].split("}", 1)[0]
        self.assertNotIn("gold-light", rule)
        self.assertNotIn("accent", rule)
