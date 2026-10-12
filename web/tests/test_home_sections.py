"""Home page structure: section order, showtime chips, hours, empty states.

The audit found four things wrong on the page that carries ~99% of this
site's search clicks:

  * ornament dividers emitted unconditionally, so a self-expiring CTA left
    two of them stacked, and a hidden section left one leading or trailing;
  * showtimes marked up as <button> with no handler anywhere and no online
    ticket path in the project at all;
  * SITE_CONFIG["hours"] rendered in zero templates (since replaced by
    "opens before every show" — the fixed hours contradicted the schedule);
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

from django.test import TestCase
from django.urls import reverse

from web.constants import SITE_CONFIG, SPONSORSHIP_TIERS

SECTION_MARKERS = (
    "hero",
    "sponsored-cta",
    "now-showing",
    "coming-soon",
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
        self.assertNotIn("vote-cta", main_content(self.home()))

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
            html = self.home()
        seq = section_sequence(html)
        self.assertIn("sponsored-cta", seq)
        self.assertIn("vote-cta", main_content(html))
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
    """The box office has no fixed weekly hours: it opens ahead of each show.

    A fixed table (Wednesday - Thursday, Saturday & Sunday) contradicted the
    schedule beside it — Friday Heckle Night, Tuesday shows, an 11 AM Saturday
    matinee — so the footer now says the one thing that is always true.
    """

    def footer(self, path="/"):
        html = self.client.get(path).content.decode()
        match = re.search(r"<footer\b.*?</footer>", html, re.S)
        self.assertIsNotNone(match, "no footer on the page")
        return match.group(0)

    def test_footer_says_the_box_office_opens_before_every_show(self):
        footer = self.footer()
        self.assertIn('class="footer-column footer-hours"', footer)
        minutes = SITE_CONFIG["box_office"]["opens_before_show_minutes"]
        self.assertIn(f"{minutes} minutes before every show", footer)

    def test_footer_points_at_the_showtimes(self):
        self.assertIn('href="/#now-showing"', self.footer())

    def test_no_fixed_weekly_hours_remain(self):
        footer = self.footer()
        self.assertNotIn("footer-hours-row", footer)
        self.assertNotIn("Wednesday", footer)
        self.assertNotIn("hours", SITE_CONFIG)

    def test_hours_are_sitewide_not_just_the_home_page(self):
        self.assertIn("footer-hours", self.footer(reverse("membership")))


class TheaterSchemaTests(TestCase):
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
        for key in ("image", "hasMap"):
            self.assertIn(key, block)

    def test_no_fixed_opening_hours_are_published(self):
        """Google shows openingHoursSpecification as "Closed" on every other
        day, and show nights fall on those days. Better no hours than wrong
        ones."""
        self.assertNotIn("openingHoursSpecification", self.theater())

    def test_has_map_points_at_the_configured_address(self):
        self.assertIn("Hall+Street", self.theater()["hasMap"])

    def test_image_is_absolute(self):
        self.assertRegex(self.theater()["image"], r"^https?://")


class EmptyStateTests(TestCase):
    @mock.patch("web.views.get_coming_soon", return_value=[])
    @mock.patch("web.views.get_now_showing", return_value=[])
    def test_now_showing_empty_state_offers_somewhere_to_go(self, _ns, _cs):
        html = self.client.get(reverse("home")).content.decode()
        # Through the links list: the signup form's honeypot has its own </div>.
        empty = re.search(
            r'<div class="no-showtimes">.*?</ul>', html, re.S
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


class GetInvolvedTests(TestCase):
    """Vote, open mic and gift card share one section and one card shape."""

    def section(self):
        html = self.client.get(reverse("home")).content.decode()
        self.assertEqual(html.count('id="get-involved"'), 1)
        start = html.index('id="get-involved"')
        return html[start : html.index("</section>", start)]

    def open_poll(self):
        from cinema.models import Poll, PollStatus

        Poll.objects.create(title="Round One", status=PollStatus.OPEN)

    def test_heading_and_cards_row(self):
        section = self.section()
        self.assertRegex(section, r'<h2 class="section-title"[^>]*>Get involved</h2>')
        self.assertIn('class="home-cards"', section)

    def test_cards_in_order_vote_open_mic_gift_card(self):
        self.open_poll()
        section = self.section()
        positions = [
            section.index(m) for m in ("vote-cta", "open-mic-cta", "gift-card-cta")
        ]
        self.assertEqual(positions, sorted(positions))
        self.assertEqual(section.count("home-card "), 3)

    def test_without_an_open_round_two_cards_remain(self):
        section = self.section()
        self.assertNotIn("vote-cta", section)
        self.assertLess(section.index("open-mic-cta"), section.index("gift-card-cta"))

    def test_no_ticket_button_in_get_involved(self):
        self.open_poll()
        self.assertNotIn("btn-ticket", self.section())

    def test_open_mic_card_copy(self):
        section = self.section()
        for text in ("Every Monday", "Open Mic", "How to sign up &rarr;"):
            self.assertIn(text, section)

    def test_gift_card_copy_and_new_window(self):
        section = self.section()
        card = section[section.index("gift-card-cta") :]
        self.assertIn("Give the gift of cinema", card)
        self.assertIn("An e-gift card for a night at the movies.", card)
        self.assertIn("Buy an e-gift card &rarr;", card)
        self.assertIn('target="_blank"', card)
        self.assertIn('data-track="giftcard_click"', card)
        self.assertRegex(card, r'aria-label="[^"]*opens in new window')
