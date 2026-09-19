"""Home page structure: dividers, showtime chips, hours and empty states.

The audit found four things wrong on the page that carries ~99% of this
site's search clicks:

  * ornament dividers emitted unconditionally, so a self-expiring CTA left
    two of them stacked, and a hidden section left one leading or trailing;
  * showtimes marked up as <button> with no handler anywhere and no online
    ticket path in the project at all;
  * SITE_CONFIG["hours"] rendered in zero templates;
  * empty states that were a flat sentence or a blank void.
"""

import datetime
import json
import re
from unittest import mock

from django.template import Context, Template
from django.test import TestCase
from django.urls import reverse

from web.constants import SITE_CONFIG

SECTION_MARKERS = (
    "ornament-divider",
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
    """The order the page's top-level sections and dividers appear in."""
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


class SectionTagTests(TestCase):
    """web/templatetags/page_sections.py in isolation."""

    def render(self, body, **ctx):
        return Template("{% load page_sections %}" + body).render(Context(ctx))

    def test_single_section_gets_no_divider(self):
        out = self.render("{% section %}A{% endsection %}")
        self.assertNotIn("ornament-divider", out)
        self.assertIn("A", out)

    def test_divider_sits_between_two_live_sections(self):
        out = self.render(
            "{% section %}A{% endsection %}{% section %}B{% endsection %}"
        )
        self.assertEqual(out.count("ornament-divider"), 1)
        self.assertLess(out.index("A"), out.index("ornament-divider"))
        self.assertLess(out.index("ornament-divider"), out.index("B"))

    def test_empty_section_contributes_no_divider(self):
        out = self.render(
            "{% section %}A{% endsection %}"
            "{% section %}{% if on %}X{% endif %}{% endsection %}"
            "{% section %}B{% endsection %}",
            on=False,
        )
        self.assertEqual(out.count("ornament-divider"), 1)
        self.assertNotIn("X", out)

    def test_page_never_opens_with_a_divider(self):
        out = self.render(
            "{% section %}{% if on %}X{% endif %}{% endsection %}"
            "{% section %}B{% endsection %}",
            on=False,
        )
        self.assertNotIn("ornament-divider", out)

    def test_page_never_ends_with_a_divider(self):
        out = self.render(
            "{% section %}A{% endsection %}"
            "{% section %}{% if on %}X{% endif %}{% endsection %}",
            on=False,
        )
        self.assertNotIn("ornament-divider", out)

    def test_a_sections_own_trailing_divider_is_absorbed(self):
        """cta_sponsored.html and cta_vote.html each tuck a trailing divider
        inside their own {% if %}. That workaround stays where it is — this
        tag has to tolerate it without doubling the seam."""
        out = self.render(
            "{% section %}A{% include 'partials/ornament_divider.html' %}"
            "{% endsection %}{% section %}B{% endsection %}"
        )
        self.assertEqual(out.count("ornament-divider"), 1)


class HomeDividerTests(TestCase):
    """The rendered page, with and without the two self-expiring CTAs."""

    def home(self):
        return self.client.get(reverse("home")).content.decode()

    def assert_well_formed(self, seq):
        self.assertTrue(seq, "no sections rendered")
        self.assertNotEqual(seq[0], "ornament-divider", "page opens with a divider")
        self.assertNotEqual(seq[-1], "ornament-divider", "page ends with a divider")
        for first, second in zip(seq, seq[1:]):
            self.assertFalse(
                first == second == "ornament-divider",
                "two dividers stacked with nothing between them: %s" % seq,
            )

    @mock.patch("web.views.get_coming_soon", return_value=[])
    @mock.patch("web.views.get_now_showing", return_value=[])
    def test_dividers_separate_live_sections_only(self, _ns, _cs):
        seq = section_sequence(self.home())
        self.assert_well_formed(seq)
        dividers = seq.count("ornament-divider")
        self.assertEqual(dividers, len(seq) - dividers - 1)

    @mock.patch("web.views.get_coming_soon", return_value=[])
    @mock.patch("web.views.get_now_showing", return_value=[])
    def test_still_well_formed_with_both_self_expiring_ctas_live(self, _ns, _cs):
        """Both CTAs carry their own trailing divider. Neither may double up."""
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
                    "web.views.vote_service.current_poll", return_value=poll
                ):
            seq = section_sequence(self.home())
        self.assertIn("sponsored-cta", seq)
        self.assertIn("vote-cta", seq)
        self.assert_well_formed(seq)

    @mock.patch("web.views.get_coming_soon", return_value=[])
    @mock.patch("web.views.get_now_showing", return_value=[])
    def test_each_live_cta_adds_exactly_one_divider(self, _ns, _cs):
        plain = self.home().count("ornament-divider")
        poll = {"title": "Pick the Sunday matinee", "options": {"count": 3}}
        with mock.patch("web.views.vote_service.current_poll", return_value=poll):
            with_vote = self.home().count("ornament-divider")
        self.assertEqual(with_vote, plain + 1)


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
            self.assertIn(period["days"], footer)
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
        weekday = specs[0]
        self.assertEqual(
            weekday["dayOfWeek"], ["Monday", "Tuesday", "Wednesday", "Thursday"]
        )
        self.assertEqual(weekday["opens"], "16:00")
        self.assertEqual(weekday["closes"], "21:00")
        self.assertEqual(specs[1]["dayOfWeek"], ["Friday", "Saturday", "Sunday"])
        self.assertEqual(specs[1]["opens"], "14:00")
        self.assertEqual(specs[1]["closes"], "22:00")

    def test_has_map_points_at_the_configured_address(self):
        self.assertIn("Hall+Street", self.theater()["hasMap"])

    def test_image_is_absolute(self):
        self.assertRegex(self.theater()["image"], r"^https?://")


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
