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
