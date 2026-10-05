"""Home page structure: section order, showtime chips, hours, empty states.

The audit found four things wrong on the page that carries ~99% of this
site's search clicks:

  * ornament dividers emitted unconditionally, so a self-expiring CTA left
    two of them stacked, and a hidden section left one leading or trailing;
  * showtimes marked up as <button> with no handler anywhere and no online
    ticket path in the project at all;
  * SITE_CONFIG["hours"] rendered in zero templates;
  * empty states that were a flat sentence or a blank void.

The dividers were then removed outright rather than placed correctly, and
the {% section %} tag went with them — with no seam to emit it did nothing
a bare {% include %} does not. Sections are separated by their alternating
grounds. What survives here is the ordering guarantee and a check that the
ornament does not come back.
"""

import datetime
import json
import re
from unittest import mock

from django.test import SimpleTestCase, TestCase
from django.urls import reverse
from django.utils.html import escape

from web.constants import (
    _WEEK,
    OPENING_HOURS_SPECIFICATION,
    SITE_CONFIG,
    SPONSORSHIP_TIERS,
    _expand_days,
)

SECTION_MARKERS = (
    "hero",
    "sponsored-cta",
    "vote-cta",
    "now-showing",
    "open-mic-cta",
    "coming-soon",
    "gift-card-cta",
    "history-cta",
    "sponsor-cta",
    "blog",
)


def main_content(html):
    return html.split('<main id="main-content">', 1)[1].split("</main>", 1)[0]


def section_sequence(html):
    """The order the page's top-level sections appear in."""
    pattern = r'class="(%s)"' % "|".join(SECTION_MARKERS)
    return [m.group(1) for m in re.finditer(pattern, main_content(html))]


def movie(**over):
    base = {
        "id": "1",
        "title": "Dune",
        "rating": "PG-13",
        "runtime": "2h 35min",
        "genre": "Sci-fi",
        "poster": "d.jpg",
        "youtube_id": "abc",
        "is_free_for_members": False,
        "showtimes": {"2999-01-15": ["6:00 PM", "9:00 PM"]},
    }
    base.update(over)
    return base


class SectionCompositionTests(TestCase):
    """The page is a plain list of sections now."""

    def home(self):
        return self.client.get(reverse("home")).content.decode()

    @mock.patch("web.views.get_coming_soon", return_value=[])
    @mock.patch("web.views.get_now_showing", return_value=[])
    def test_section_ornaments_are_gone(self, _ns, _cs):
        """Two decorative devices were removed from between and beneath the
        sections, each in every layer it touched:

          * the ornament divider — partial deleted, .ornament-* rules
            deleted, and the template tag that placed it deleted;
          * the fx-divider chevron under each section subtitle — <svg>
            deleted from three partials, .fx-divider rules deleted, and the
            --fx-draw property that drew its stroke no longer set by
            scrollReveal.js (nothing else consumed it).

        Sections are separated by their alternating grounds. This asserts no
        layer of either device comes back on its own."""
        html = self.home()
        self.assertNotIn("ornament-divider", html)
        self.assertNotIn("ornament-line", html)
        self.assertNotIn("ornament-star", html)
        self.assertNotIn("fx-divider", html)

    @mock.patch("web.views.get_coming_soon", return_value=[])
    @mock.patch("web.views.get_now_showing", return_value=[])
    def test_sections_appear_once_each_in_order(self, _ns, _cs):
        seq = section_sequence(self.home())
        self.assertEqual(seq, sorted(set(seq), key=seq.index),
                         "a section rendered twice: %s" % seq)
        self.assertEqual(seq[0], "hero")

    @mock.patch("web.views.get_coming_soon", return_value=[])
    @mock.patch("web.views.get_now_showing", return_value=[])
    def test_history_and_sponsor_ctas_are_paired(self, _ns, _cs):
        """These two are the page's most similar blocks and were flagged as
        structural twins that read as one templated run. They are laid out
        side by side above 900px, which needs a wrapper element — CSS alone
        cannot pair two sibling <section>s. If the wrapper is lost they fall
        back to stacking, silently, so the nesting is asserted."""
        main = main_content(self.home())
        pair = re.search(
            r'<div class="cta-pair">(.*?)</div>\s*<section class="blog"',
            main, re.S)
        self.assertIsNotNone(pair, "the .cta-pair wrapper is gone")
        self.assertIn("history-cta", pair.group(1))
        self.assertIn("sponsor-cta", pair.group(1))
        self.assertLess(pair.group(1).index("history-cta"),
                        pair.group(1).index("sponsor-cta"))

    @mock.patch("web.views.get_coming_soon", return_value=[])
    @mock.patch("web.views.get_now_showing", return_value=[])
    def test_self_expiring_ctas_appear_only_when_live(self, _ns, _cs):
        """cta_sponsored and cta_vote render nothing between runs/rounds.
        With no seams to place, that needs no coordination — but they still
        have to actually disappear."""
        self.assertNotIn("sponsored-cta", section_sequence(self.home()))
        self.assertNotIn("vote-cta", section_sequence(self.home()))

        banner = {
            "url": "/movies/dune/",
            "eyebrow": "",
            "sponsor": "A.H. Custom Carpentry",
            "admission": "$4",
            "film": {"title": "Dune"},
            "days": [{"date": datetime.date(2999, 1, 15), "times": ["6:00 PM"]}],
        }
        poll = {"title": "Pick the Sunday matinee", "options": {"count": 3}}
        with mock.patch("web.views.sponsored_screening", return_value=banner), \
                mock.patch(
                    "web.views.vote_service.open_polls", return_value=[poll]
                ):
            seq = section_sequence(self.home())
        self.assertIn("sponsored-cta", seq)
        self.assertIn("vote-cta", seq)
        self.assertEqual(seq[0], "hero")


class ShowtimeChipTests(TestCase):
    """There is no online ticket path in this project, so a <button> here
    promised a purchase that cannot happen."""

    @mock.patch("web.views.get_coming_soon", return_value=[])
    @mock.patch("web.views.get_now_showing")
    def test_showtimes_are_spans_not_buttons(self, ns, _cs):
        ns.return_value = [movie()]
        html = self.client.get(reverse("home")).content.decode()
        self.assertNotIn('<button class="showtime"', html)
        # Desktop movie card and the phone schedule card both render the times.
        self.assertGreaterEqual(html.count('<span class="showtime">'), 4)
        self.assertIn('<span class="showtime">6:00 PM</span>', html)

    @mock.patch("web.views.get_coming_soon", return_value=[])
    @mock.patch("web.views.get_now_showing")
    def test_class_name_is_unchanged(self, ns, _cs):
        """The interface with static/css/MovieCard.css."""
        ns.return_value = [movie()]
        html = self.client.get(reverse("home")).content.decode()
        self.assertIn('class="showtime"', html)


class FooterHoursTests(TestCase):
    def footer(self, path="/"):
        html = self.client.get(path).content.decode()
        match = re.search(r"<footer\b.*?</footer>", html, re.S)
        self.assertIsNotNone(match, "no footer on the page")
        return match.group(0)

    def test_hours_render_in_the_footer(self):
        footer = self.footer()
        self.assertIn('class="footer-column footer-hours"', footer)
        self.assertIn('class="footer-heading"', footer)
        for period in SITE_CONFIG["hours"].values():
            self.assertIn(escape(period["days"]), footer)
            self.assertIn(period["open"], footer)
            self.assertIn(period["close"], footer)

    def test_every_period_gets_its_own_row(self):
        footer = self.footer()
        rows = SITE_CONFIG["hours"]
        self.assertEqual(footer.count('class="footer-hours-row"'), len(rows))
        self.assertEqual(footer.count('class="footer-hours-days"'), len(rows))
        self.assertEqual(footer.count('class="footer-hours-time"'), len(rows))

    def test_hours_are_sitewide_not_just_the_home_page(self):
        self.assertIn("footer-hours", self.footer(reverse("membership")))


class OpeningHoursSchemaTests(TestCase):
    """SITE_CONFIG is the single source of truth; base.html reads the derived
    rows rather than restating them."""

    def theater(self, path="/"):
        html = self.client.get(path).content.decode()
        for raw in re.findall(
            r'<script type="application/ld\+json">\s*(.*?)\s*</script>', html, re.S
        ):
            block = json.loads(raw)
            if block.get("@type") == "MovieTheater":
                return block
        self.fail("no MovieTheater block")

    def test_block_is_still_valid_json(self):
        self.assertEqual(self.theater()["@type"], "MovieTheater")

    def test_new_keys_are_present(self):
        block = self.theater()
        for key in ("openingHoursSpecification", "image", "hasMap"):
            self.assertIn(key, block)

    def test_opening_hours_match_the_config(self):
        specs = self.theater()["openingHoursSpecification"]
        self.assertEqual(len(specs), len(SITE_CONFIG["hours"]))
        for spec in specs:
            self.assertEqual(spec["@type"], "OpeningHoursSpecification")
            # 24h ISO, not the "4:00 PM" the config carries for humans.
            self.assertRegex(spec["opens"], r"^\d{2}:\d{2}$")
            self.assertRegex(spec["closes"], r"^\d{2}:\d{2}$")
        # Derived from SITE_CONFIG rather than restated here, so changing the
        # hours doesn't fail this test; _expand_days is pinned separately.
        self.assertEqual(
            [
                {k: spec[k] for k in ("dayOfWeek", "opens", "closes")}
                for spec in specs
            ],
            OPENING_HOURS_SPECIFICATION,
        )
        for spec in specs:
            for day in spec["dayOfWeek"]:
                self.assertIn(day, _WEEK)


    def test_has_map_points_at_the_configured_address(self):
        self.assertIn("Hall+Street", self.theater()["hasMap"])

    def test_image_is_absolute(self):
        self.assertRegex(self.theater()["image"], r"^https?://")


class ExpandDaysTests(SimpleTestCase):
    def test_range(self):
        self.assertEqual(
            _expand_days("Monday - Thursday"),
            ["Monday", "Tuesday", "Wednesday", "Thursday"],
        )

    def test_range_wraps_the_week(self):
        self.assertEqual(
            _expand_days("Saturday - Monday"), ["Saturday", "Sunday", "Monday"]
        )

    def test_single_day(self):
        self.assertEqual(_expand_days("Friday"), ["Friday"])

    def test_days_joined_with_ampersand(self):
        self.assertEqual(_expand_days("Saturday & Sunday"), ["Saturday", "Sunday"])

    def test_days_and_ranges_joined_with_commas(self):
        self.assertEqual(
            _expand_days("Monday, Wednesday - Friday"),
            ["Monday", "Wednesday", "Thursday", "Friday"],
        )

    def test_misspelt_day_raises(self):
        with self.assertRaises(ValueError):
            _expand_days("Saturday & Sundy")

class EmptyStateTests(TestCase):
    @mock.patch("web.views.get_coming_soon", return_value=[])
    @mock.patch("web.views.get_now_showing", return_value=[])
    def test_now_showing_empty_state_offers_somewhere_to_go(self, _ns, _cs):
        html = self.client.get(reverse("home")).content.decode()
        empty = re.search(
            r'<div class="no-showtimes">.*?</div>', html, re.S
        ).group(0)
        self.assertIn("No showtimes available.", empty)
        self.assertIn(SITE_CONFIG["social"]["facebook"], empty)
        self.assertIn("/membership/", empty)
        self.assertIn("/history/", empty)
        self.assertIn("#coming-soon", empty)

    @mock.patch("web.views.get_coming_soon", return_value=[])
    @mock.patch("web.views.get_now_showing", return_value=[])
    def test_coming_soon_empty_state_is_not_a_blank_void(self, _ns, _cs):
        html = self.client.get(reverse("home")).content.decode()
        self.assertIn('class="coming-empty"', html)
        empty = html.split('class="coming-empty"', 1)[1].split("</div>", 1)[0]
        self.assertIn(SITE_CONFIG["social"]["facebook"], empty)
        self.assertIn(reverse("blog_list"), empty)

    @mock.patch("web.views.get_coming_soon")
    @mock.patch("web.views.get_now_showing")
    def test_empty_states_stay_out_of_the_way_when_there_is_content(self, ns, cs):
        ns.return_value = [movie()]
        cs.return_value = [
            {
                "id": "5",
                "title": "Wicked",
                "release_date": "November 22",
                "genre": "",
                "poster": "w.jpg",
                "youtube_id": "",
                "films": [],
                "is_free_for_members": False,
                "start_date": "2999-11-22",
            }
        ]
        html = self.client.get(reverse("home")).content.decode()
        self.assertNotIn("no-showtimes", html)
        self.assertNotIn("coming-empty", html)


class SponsorCtaCopyTests(TestCase):
    """The homepage sponsor CTA has to stay true with nobody maintaining it."""

    def home(self):
        return self.client.get(reverse("home")).content.decode()

    def body(self):
        html = self.home()
        start = html.index('class="sponsor-cta__body"')
        return html[start:html.index("</p>", start)]

    def test_it_names_no_sponsor_and_no_film(self):
        """It used to open with a worked example — "A.H. Custom Carpentry
        covered the cost of bringing The Wild Robot to Fort Kent". That is a
        real, approved sponsorship and it still leads /sponsor/, which is
        where a case study belongs.

        Here it was written in the past tense about one finished booking, so
        it went stale the moment that run ended and only a human remembering
        to edit the home page could fix it. The copy is now the presenting
        tier itself, which is true of whoever signs next."""
        body = self.body()
        self.assertNotIn("A.H. Custom Carpentry", body)
        self.assertNotIn("Wild Robot", body)

    def test_the_sponsor_page_keeps_its_named_example(self):
        """Generalising the teaser must not have touched the case study."""
        html = self.client.get(reverse("sponsor")).content.decode()
        self.assertIn("A.H. Custom Carpentry", html)
        self.assertIn("The Wild Robot", html)

    def test_the_price_is_the_cheapest_tier(self):
        cheapest = min(t["price"] for t in SPONSORSHIP_TIERS)
        self.assertEqual(cheapest, 299)  # guards the fixture, not the render
        self.assertIn("From $%d." % cheapest, self.body())

    def test_the_price_tracks_the_tiers_rather_than_being_typed(self):
        """Repricing the cheapest tier has to move the home page with it."""
        repriced = [dict(t) for t in SPONSORSHIP_TIERS]
        repriced[0] = {**repriced[0], "price": 349}
        with mock.patch("web.views.SPONSORSHIP_TIERS", repriced):
            body = self.body()
        self.assertIn("From $349.", body)
        self.assertNotIn("$299", body)

    def test_every_promise_maps_to_the_presenting_tier(self):
        """Each clause in the body is an entry in SPONSORSHIP_TIERS[0].
        If a perk is dropped from the tier, this copy is now overselling."""
        includes = " ".join(SPONSORSHIP_TIERS[0]["includes"]).lower()
        for perk in ("big screen before the film", "posts"):
            self.assertIn(perk, includes)
        body = self.body().lower()
        self.assertIn("big screen", body)
        self.assertIn("before the lights go down", body)
        self.assertIn("post", body)
        # There is no marquee on the building. The credit a sponsor buys is
        # the screen itself, and the copy must not promise street signage.
        self.assertNotIn("marquee", body)
