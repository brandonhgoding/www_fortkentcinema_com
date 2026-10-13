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
from pathlib import Path
from unittest import mock

from django.conf import settings
from django.test import TestCase
from django.urls import reverse

from django.utils.html import escape

from blog.models import BlogAuthor, BlogCategory, BlogPost
from web.constants import DONATION, SITE_CONFIG, SPONSORSHIP_TIERS

SECTION_MARKERS = (
    "hero",
    "sponsored-cta",
    "now-showing",
    "membership",
    "coming-soon",
    "get-involved",
    "from-the-booth",
    "support",
)


def main_content(html):
    return html.split('<main id="main-content">', 1)[1].split("</main>", 1)[0]


def section_sequence(html):
    """The order the page's top-level sections appear in."""
    pattern = r'(?:class|id)="(%s)"' % "|".join(SECTION_MARKERS)
    seq = [m.group(1) for m in re.finditer(pattern, main_content(html))]
    # coming-soon is both a class and an id on the same <section>
    return [m for i, m in enumerate(seq) if m not in seq[:i]]


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
        self.assertEqual(
            seq, sorted(set(seq), key=seq.index), "a section rendered twice: %s" % seq
        )
        self.assertEqual(seq[0], "hero")

    @mock.patch("web.views.get_coming_soon", return_value=[])
    @mock.patch("web.views.get_now_showing", return_value=[])
    def test_section_order_ends_with_from_the_booth(self, _ns, _cs):
        html = self.home()
        seq = section_sequence(html)
        self.assertEqual(
            seq,
            [
                "hero",
                "now-showing",
                "membership",
                "coming-soon",
                "get-involved",
                "from-the-booth",
            ],
        )
        self.assertNotIn("cta-pair", html)

    @mock.patch("web.views.get_coming_soon", return_value=[])
    @mock.patch("web.views.get_now_showing", return_value=[])
    def test_from_the_booth_is_the_last_section_before_the_footer(self, _ns, _cs):
        main = main_content(self.home())
        last = main.rindex("<section")
        self.assertIn('id="from-the-booth"', main[last : last + 200])

    @mock.patch("web.views.get_coming_soon", return_value=[])
    @mock.patch("web.views.get_now_showing", return_value=[])
    def test_support_strip_is_off(self, _ns, _cs):
        html = self.home()
        self.assertNotIn('id="support"', html)
        self.assertNotIn("Support the Cinema", html)
        self.assertNotIn("sponsor-cta", html)
        self.assertNotIn("donate-cta", html)

    @mock.patch("web.views.SHOW_SUPPORT_STRIP", True)
    @mock.patch("web.views.get_coming_soon", return_value=[])
    @mock.patch("web.views.get_now_showing", return_value=[])
    def test_support_strip_comes_back_last_when_switched_on(self, _ns, _cs):
        seq = section_sequence(self.home())
        self.assertEqual(seq[-2:], ["from-the-booth", "support"])

    @mock.patch("web.views.get_coming_soon", return_value=[])
    @mock.patch("web.views.get_now_showing", return_value=[])
    def test_every_section_has_one_flat_ground(self, _ns, _cs):
        """The class-marker inventory below the hero: each <section> opts into
        the shared .home-section vocabulary with exactly one ground modifier,
        and no two neighbours share a ground."""
        main = main_content(self.home())
        expected = {
            "now-showing": "raised",
            "membership": "accent",
            "coming-soon": "alt",
            "get-involved": "surface",
            "from-the-booth": "alt",
        }
        grounds = []
        for section_id, ground in expected.items():
            at = main.index('id="%s"' % section_id)
            start = main.rindex("<section", 0, at)
            tag = main[start : main.index(">", at)]
            classes = re.search(r'class="([^"]*)"', tag).group(1).split()
            self.assertIn("home-section", classes, section_id)
            found = [
                c[len("home-section--") :]
                for c in classes
                if c.startswith("home-section--") and c != "home-section--slim"
            ]
            self.assertEqual(found, [ground], section_id)
            grounds.append(ground)
        for above, below in zip(grounds, grounds[1:]):
            self.assertNotEqual(above, below)

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
        with (
            mock.patch("web.views.sponsored_screening", return_value=banner),
            mock.patch("web.views.vote_service.open_polls", return_value=[poll]),
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
        empty = re.search(r'<div class="no-showtimes">.*?</ul>', html, re.S).group(0)
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


@mock.patch("web.views.SHOW_SUPPORT_STRIP", True)
class SponsorCtaCopyTests(TestCase):
    """The homepage sponsor link has to stay true with nobody maintaining it."""

    def home(self):
        return self.client.get(reverse("home")).content.decode()

    def body(self):
        """The sponsor link inside Support, as rendered."""
        html = self.home()
        start = html.index('class="sponsor-cta"')
        return html[start : html.index("</a>", start)]

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
        self.assertIn("Sponsor a screening, from $%d &rarr;" % cheapest, self.body())
        self.assertNotIn("sponsor-cta__body", self.home())

    def test_the_price_tracks_the_tiers_rather_than_being_typed(self):
        """Repricing the cheapest tier has to move the home page with it."""
        repriced = [dict(t) for t in SPONSORSHIP_TIERS]
        repriced[0] = {**repriced[0], "price": 349}
        with mock.patch("web.views.SPONSORSHIP_TIERS", repriced):
            body = self.body()
        self.assertIn("from $349 &rarr;", body)
        self.assertNotIn("$299", body)

    def test_it_is_a_tracked_text_link_to_the_sponsor_page(self):
        body = self.body()
        self.assertIn(f'href="{reverse("sponsor")}"', body)
        self.assertIn('data-track="sponsor_click"', body)
        self.assertIn('class="home-link"', body)
        self.assertNotIn("btn-ticket", body)


class FromTheBoothTests(TestCase):
    """Up to three image-led post cards and a way to the rest. The history
    card that used to lead this row is gone; History lives under More."""

    @classmethod
    def setUpTestData(cls):
        cls.author = BlogAuthor.objects.create(first_name="Rick", last_name="Douglas")
        cls.category = BlogCategory.objects.create(name="Rick's Reviews")

    def make_posts(self, n, **over):
        return [
            BlogPost.objects.create(
                title=f"Post {i}",
                subtitle=f"Subtitle {i}",
                author=self.author,
                category=self.category,
                content=f"Body {i}.",
                post_date=f"2026-02-{i + 1:02d}",
                **over,
            )
            for i in range(n)
        ]

    def section(self):
        html = self.client.get(reverse("home")).content.decode()
        self.assertEqual(html.count('id="from-the-booth"'), 1)
        self.assertNotIn('id="our-story"', html)
        start = html.index('id="from-the-booth"')
        return html[html.rindex("<section", 0, start) : html.index("</section>", start)]

    def test_heading_and_lede(self):
        section = self.section()
        self.assertRegex(
            section, r'<h2 class="section-title"[^>]*>From the booth</h2>'
        )
        self.assertIn("Film reviews and notes on running a small-town cinema.", section)

    def test_no_history_card(self):
        self.make_posts(1)
        section = self.section()
        self.assertNotIn("history-cta", section)
        self.assertNotIn("/history/", section)
        self.assertNotIn("A century on this lot", section)

    def test_keeps_the_blog_marker_and_alt_ground(self):
        section = self.section()
        self.assertRegex(section, r'<section[^>]*class="[^"]*\bblog\b')
        self.assertIn("home-section--alt", section)

    def test_five_posts_show_the_newest_three(self):
        self.make_posts(5)
        section = self.section()
        self.assertEqual(section.count('class="home-card blog-post-card"'), 3)
        for shown in ("Post 4", "Post 3", "Post 2"):
            self.assertIn(shown, section)
        for hidden in ("Post 1", "Post 0"):
            self.assertNotIn(hidden, section)
        self.assertLess(section.index("Post 4"), section.index("Post 3"))

    def test_post_card_shape(self):
        post = self.make_posts(1, header_image="blog/headers/post-0.webp")[0]
        section = self.section()
        self.assertIn("Rick&#x27;s Reviews &middot; February 1, 2026", section)
        self.assertRegex(
            section,
            r'<a href="%s" class="blog-post-card__link">Post 0</a>'
            % re.escape(post.get_absolute_url()),
        )
        # One link per card: the title, stretched over the card.
        self.assertEqual(section.count(f'href="{post.get_absolute_url()}"'), 1)
        self.assertIn('<p class="home-card__body">Subtitle 0</p>', section)
        self.assertIn("By Rick Douglas", section)
        # The image is decorative; the title beside it names the post.
        self.assertRegex(
            section,
            r'<img src="%s" alt="" loading="lazy"' % re.escape(post.header_image.url),
        )
        self.assertNotIn("blog-card", section)

    def test_post_without_an_image_keeps_the_media_block(self):
        self.make_posts(1)
        section = self.section()
        self.assertIn('class="blog-post-card__media"', section)
        self.assertNotIn("<img", section)

    def test_all_posts_link_is_a_secondary_button_after_the_cards(self):
        self.make_posts(1)
        section = self.section()
        self.assertRegex(
            section,
            r'<a href="%s" class="btn btn-secondary"[^>]*>\s*All posts'
            % reverse("blog_list"),
        )
        self.assertGreater(section.index("All posts"), section.index("Post 0"))

    def test_without_posts_there_is_no_empty_grid(self):
        section = self.section()
        self.assertIn("All posts", section)
        self.assertNotIn("home-cards", section)
        self.assertNotIn("blog-post-card", section)


@mock.patch("web.views.SHOW_SUPPORT_STRIP", True)
class SupportTests(TestCase):
    def section(self, url=None):
        with mock.patch.dict(
            "web.views.DONATION", {"url": url} if url is not None else {}
        ):
            html = self.client.get(reverse("home")).content.decode()
        self.assertEqual(html.count('id="support"'), 1)
        start = html.index('id="support"')
        return html[start : html.index("</section>", start)]

    def test_label_and_ground(self):
        html = self.client.get(reverse("home")).content.decode()
        tag = html[html.rindex("<section", 0, html.index('id="support"')) :]
        tag = tag[: tag.index(">")]
        self.assertIn("home-section--sunken", tag)
        self.assertIn("home-section--slim", tag)
        self.assertIn("Support the Cinema", self.section())

    def test_sponsor_link(self):
        section = self.section()
        self.assertIn("sponsor-cta", section)
        self.assertIn("Sponsor a screening, from $299 &rarr;", section)

    def test_no_donate_without_a_url(self):
        section = self.section(url="")
        self.assertNotIn("donate-cta", section)
        self.assertNotIn(DONATION["disclaimer"][:20], section)

    def test_donate_link_and_disclaimer_render_together(self):
        section = self.section(url="https://square.link/u/example")
        self.assertIn("donate-cta", section)
        self.assertIn(f'{DONATION["button"]} &rarr;', section)
        self.assertIn('data-track="donate_click"', section)
        self.assertRegex(section, r'aria-label="[^"]*opens in new window')
        self.assertIn(escape(DONATION["disclaimer"]), section)
        self.assertGreater(
            section.index(escape(DONATION["disclaimer"])),
            section.index('data-track="donate_click"'),
        )


class GetInvolvedTests(TestCase):
    """Vote, open mic and gift card share one section and one card shape.

    The section is titled "Be part of the show"; its id stays get-involved.
    """

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
        self.assertRegex(section, r'<h2 class="section-title"[^>]*>Be part of the show</h2>')
        self.assertIn('class="home-cards"', section)

    def test_cards_in_order_vote_open_mic_gift_card(self):
        self.open_poll()
        section = self.section()
        positions = [
            section.index(m) for m in ("vote-cta", "open-mic-cta", "gift-card-cta")
        ]
        self.assertEqual(positions, sorted(positions))
        self.assertEqual(section.count("home-card "), 3)
        self.assertEqual(section.count("open-mic-cta"), 1)
        self.assertEqual(section.count("gift-card-cta"), 1)

    def test_without_an_open_round_two_cards_remain(self):
        section = self.section()
        self.assertNotIn("vote-cta", section)
        self.assertLess(section.index("open-mic-cta"), section.index("gift-card-cta"))

    def test_no_ticket_button_in_get_involved(self):
        self.open_poll()
        self.assertNotIn("btn-ticket", self.section())

    def test_open_mic_card_copy(self):
        section = self.section()
        card = section[section.index("open-mic-cta") :]
        for text in ("Take center stage", "Every Monday", "Open Mic", "How to sign up &rarr;"):
            self.assertIn(text, card)

    def test_each_card_leads_with_its_picture(self):
        """Art first, like the From the booth cards. Decorative (alt="")
        because the title under it says the same thing."""
        self.open_poll()
        section = self.section()
        for card_class, image in (
            ("vote-cta", "you-choose-the-film"),
            ("open-mic-cta", "take-center-stage"),
            ("gift-card-cta", "pay-it-forward"),
        ):
            card = section[section.index(card_class) :]
            card = card[: card.index("</article>")]
            self.assertIn(f"img/involved/{image}.jpg", card)
            self.assertLess(card.index("home-card__media"), card.index("home-card__eyebrow"))
            self.assertRegex(card, r'<img [^>]*alt=""')

    def test_the_pictures_ship(self):
        from django.contrib.staticfiles import finders

        for image in ("you-choose-the-film", "take-center-stage", "pay-it-forward"):
            self.assertIsNotNone(finders.find(f"img/involved/{image}.jpg"), image)

    def test_gift_card_copy_and_new_window(self):
        section = self.section()
        card = section[section.index("gift-card-cta") :]
        self.assertIn("Pay it forward", card)
        self.assertIn("An e-gift card for a night at the movies.", card)
        self.assertIn("Buy an e-gift card &rarr;", card)
        self.assertIn('target="_blank"', card)
        self.assertIn('data-track="giftcard_click"', card)
        self.assertRegex(card, r'aria-label="[^"]*opens in new window')


class HomeTypeAndGroundTests(TestCase):
    """Three heading sizes below the hero, from tokens only, and no ornament
    left on Coming Soon. Read from the source sheets, since the bundle is
    minified."""

    CSS = Path(settings.BASE_DIR) / "static" / "css"

    # Every heading rendered below the hero on the home page, by the sheet
    # that styles it.
    HEADINGS = {
        "global.css": [".section-title"],
        "HomeSections.css": [".home-membership__title", ".home-card__title"],
        "MovieCard.css": [".movie-title"],
        "MovieScheduleCard.css": [".schedule-card__title"],
        "ComingSoon.css": [".coming-movie-title"],
        "SponsoredCTA.css": [".sponsored-cta__title"],
    }

    def font_sizes(self, sheet, selector):
        css = re.sub(r"/\*.*?\*/", "", (self.CSS / sheet).read_text(), flags=re.S)
        sizes = []
        for selectors, body in re.findall(r"([^{}]+)\{([^{}]*)\}", css):
            if selector in [s.strip() for s in selectors.split(",")]:
                sizes += re.findall(r"font-size:\s*([^;]+);", body)
        return sizes

    def test_headings_take_only_the_three_tokens(self):
        allowed = {"var(--type-title)", "var(--type-heading)", "var(--type-lead)"}
        for sheet, selectors in self.HEADINGS.items():
            for selector in selectors:
                sizes = self.font_sizes(sheet, selector)
                self.assertTrue(sizes, f"{selector} sets no font-size in {sheet}")
                for size in sizes:
                    self.assertIn(size.strip(), allowed, f"{selector} in {sheet}")

    def test_cards_sit_24px_apart(self):
        """--spacing-md between cards in every card row below the hero, at
        every breakpoint that sets a gap."""
        rows = {
            "HomeSections.css": ".home-cards",
            "NowShowing.css": ".movies-grid",
            "ComingSoon.css": ".coming-movies-grid",
        }
        rows_schedule = ("NowShowing.css", ".schedule-list")
        for sheet, selector in list(rows.items()) + [rows_schedule]:
            css = re.sub(r"/\*.*?\*/", "", (self.CSS / sheet).read_text(), flags=re.S)
            gaps = [
                g.strip()
                for selectors, body in re.findall(r"([^{}]+)\{([^{}]*)\}", css)
                if selector in [x.strip() for x in selectors.split(",")]
                for g in re.findall(r"(?<![-\w])gap:\s*([^;]+);", body)
            ]
            self.assertTrue(gaps, f"{selector} sets no gap in {sheet}")
            for gap in gaps:
                self.assertEqual(gap, "var(--spacing-md)", f"{selector} in {sheet}")

    def test_coming_soon_has_a_flat_ground_and_no_gold_rules(self):
        css = re.sub(
            r"/\*.*?\*/", "", (self.CSS / "ComingSoon.css").read_text(), flags=re.S
        )
        self.assertNotIn("ornament-gold", css)
        # The ground comes from .home-section--alt; the section's own rule may
        # not paint a background or rules over it.
        for selectors, body in re.findall(r"([^{}]+)\{([^{}]*)\}", css):
            if ".coming-soon" in [s.strip() for s in selectors.split(",")]:
                self.assertNotRegex(body, r"\b(background|border)")
