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

from blog.models import BlogAuthor, BlogCategory, BlogPost
from web.constants import SITE_CONFIG, TICKET_PRICES

SECTION_MARKERS = (
    "hero",
    "now-showing",
    "membership",
    "coming-soon",
    "get-involved",
    "from-the-booth",
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
        "showtimes": {"2999-01-15": [{"time": "6:00 PM", "captions": "", "captions_label": ""}, {"time": "9:00 PM", "captions": "", "captions_label": ""}]},
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
                if c.startswith("home-section--")
            ]
            self.assertEqual(found, [ground], section_id)
            grounds.append(ground)
        for above, below in zip(grounds, grounds[1:]):
            self.assertNotEqual(above, below)


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

    def test_footer_says_the_box_office_opens_before_showtime(self):
        footer = self.footer()
        minutes = SITE_CONFIG["box_office"]["opens_before_show_minutes"]
        self.assertIn(
            f'<p class="footer-box-office">Box office opens {minutes} minutes '
            "before showtime</p>",
            footer,
        )

    def test_box_office_line_sits_under_the_address_and_phone(self):
        # A single line in the brand column since 2026-10-13, not a column
        # of its own (the owner's call).
        footer = self.footer()
        self.assertNotIn("footer-hours", footer)
        self.assertNotIn("Box Office Hours", footer)
        self.assertLess(footer.index("</address>"), footer.index("footer-box-office"))
        brand = footer[footer.index('class="footer-brand"') :]
        self.assertIn("footer-box-office", brand[: brand.index('class="footer-column')])

    def test_no_fixed_weekly_hours_remain(self):
        footer = self.footer()
        self.assertNotIn("footer-hours-row", footer)
        self.assertNotIn("Wednesday", footer)
        self.assertNotIn("hours", SITE_CONFIG)

    def test_hours_are_sitewide_not_just_the_home_page(self):
        self.assertIn("footer-box-office", self.footer(reverse("membership")))


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

    def test_telephone_is_e164(self):
        """schema.org and Google's validator expect the international form;
        the display form stays on the page."""
        self.assertEqual(self.theater()["telephone"], "+12072315287")

    def test_e164_and_display_phone_are_the_same_number(self):
        cinema = SITE_CONFIG["cinema"]
        self.assertEqual(
            cinema["phone_e164"], "+1" + re.sub(r"\D", "", cinema["phone"])
        )

    def test_price_range_is_the_real_ticket_range(self):
        """"$$" is a vague tier; the page states real prices."""
        with mock.patch.dict(TICKET_PRICES, member=3, adult=9):
            self.assertEqual(self.theater()["priceRange"], "$3 - $9")

    def test_logo_is_an_absolute_png_that_ships(self):
        logo = self.theater()["logo"]
        self.assertRegex(logo, r"^https?://.+\.png$")
        name = logo.rsplit("/static/", 1)[1]
        self.assertTrue((Path(settings.BASE_DIR) / "static" / name).exists())


class TelLinkTests(TestCase):
    """Every tel: link dials SITE_CONFIG's number. They were typed by hand on
    six pages, and the footer built its own by stripping punctuation, which
    left off the country code."""

    PAGES = ["/", "/rentals/", "/heckle-night/", "/open-mic/",
             "/no-such-page/"]

    @mock.patch("web.views.get_calendar_month", return_value={})
    @mock.patch("web.views.get_coming_soon", return_value=[])
    @mock.patch("web.views.get_now_showing", return_value=[])
    def test_every_tel_link_comes_from_the_config(self, *_):
        with mock.patch.dict(SITE_CONFIG["cinema"], phone_e164="+19995550100",
                             phone="(999) 555-0100"):
            for path in self.PAGES:
                with self.subTest(path=path):
                    html = self.client.get(path).content.decode()
                    links = re.findall(r'href="tel:([^"]*)"', html)
                    self.assertTrue(links, "no tel: link")
                    self.assertEqual(set(links), {"+19995550100"})
                    self.assertNotIn("231-5287", html)


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


class GetInvolvedTests(TestCase):
    """Open mic, Heckle Night and advertising share one section and one
    card shape.

    The section is titled "Be part of the show"; its id stays get-involved.
    The vote and gift-card cards left it on 2026-10-13 (the owner's call):
    the vote has its footer link, and Heckle Night took the free slot.
    """

    def section(self):
        html = self.client.get(reverse("home")).content.decode()
        self.assertEqual(html.count('id="get-involved"'), 1)
        start = html.index('id="get-involved"')
        return html[start : html.index("</section>", start)]

    def card(self, card_class):
        section = self.section()
        card = section[section.index(card_class) :]
        return card[: card.index("</article>")]

    def test_heading_and_cards_row(self):
        section = self.section()
        self.assertRegex(section, r'<h2 class="section-title"[^>]*>Be part of the show</h2>')
        self.assertIn('class="home-cards"', section)

    def test_advertise_card_is_third_and_has_no_link_yet(self):
        # Added 2026-10-13; its page comes later, so for now it advertises
        # without sending anyone anywhere.
        section = self.section()
        self.assertLess(section.index("heckle-night-cta"), section.index("advertise-cta"))
        card = self.card("advertise-cta")
        self.assertIn("Advertise with us", card)
        self.assertNotIn("<a ", card)

    def test_cards_are_open_mic_then_heckle_night(self):
        from cinema.models import Poll, PollStatus

        # An open round no longer puts a vote card here.
        Poll.objects.create(title="Round One", status=PollStatus.OPEN)
        section = self.section()
        self.assertEqual(section.count("home-card "), 3)
        self.assertLess(section.index("open-mic-cta"), section.index("heckle-night-cta"))
        self.assertNotIn("vote-cta", section)
        self.assertNotIn("gift-card-cta", section)

    def test_no_ticket_button_in_get_involved(self):
        self.assertNotIn("btn-ticket", self.section())

    def test_open_mic_card_copy(self):
        card = self.card("open-mic-cta")
        for text in ("Take center stage", "Every Monday", "Open Mic", "How to sign up &rarr;"):
            self.assertIn(text, card)

    PICTURES = (
        ("open-mic-cta", "take-center-stage"),
        ("heckle-night-cta", "talk-back-to-the-screen"),
        ("advertise-cta", "your-ad-here"),
    )

    def test_each_card_leads_with_its_picture(self):
        """Art first, like the From the booth cards. Decorative (alt="")
        because the title under it says the same thing."""
        for card_class, image in self.PICTURES:
            card = self.card(card_class)
            self.assertIn(f"img/involved/{image}.jpg", card)
            self.assertLess(card.index("home-card__media"), card.index("home-card__eyebrow"))
            self.assertRegex(card, r'<img [^>]*alt=""')

    def test_the_pictures_ship(self):
        from django.contrib.staticfiles import finders

        for _, image in self.PICTURES:
            self.assertIsNotNone(finders.find(f"img/involved/{image}.jpg"), image)

    def test_heckle_night_card_agrees_with_the_page_and_links_to_it(self):
        from web.constants import HECKLE_NIGHT

        card = self.card("heckle-night-cta")
        self.assertIn("Heckle Night &middot; Third Friday of the month", card)
        self.assertIn("Talk back to the screen", card)
        self.assertIn(f"${HECKLE_NIGHT['general_price']} at the door", card)
        self.assertIn("free for members", card)
        self.assertIn(f"Starts at {HECKLE_NIGHT['start_label']}", card)
        self.assertIn(f'href="{reverse("heckle_night")}"', card)
        self.assertIn("See what&rsquo;s next &rarr;", card)



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


class ScreeningEventSchemaTests(TestCase):
    """The home page says what is playing, not only that the cinema exists.

    One schema.org ScreeningEvent per upcoming showtime the Now Showing
    section renders, inside an @graph so the existing jsonld() helpers,
    which call .get("@type") on every block, keep working.
    """

    def setUp(self):
        from cinema.models import Engagement, EngagementFilm, Film, Screen, Showtime

        self.screen = Screen.objects.create(name="Screen 1", capacity=100)
        self.film = Film.objects.create(
            title="Dune", rating="PG-13", poster_url="http://p/d.jpg"
        )
        self.today = datetime.date.today()
        self.eng = Engagement.objects.create(
            screen=self.screen,
            start_date=self.today - datetime.timedelta(days=1),
            end_date=self.today + datetime.timedelta(days=2),
            status="CONFIRMED",
        )
        EngagementFilm.objects.create(engagement=self.eng, film=self.film, position=1)
        self.Showtime = Showtime

    def showtime(self, day_offset, hour):
        from django.utils import timezone

        d = self.today + datetime.timedelta(days=day_offset)
        return self.Showtime.objects.create(
            engagement=self.eng,
            starts_at=timezone.make_aware(datetime.datetime(d.year, d.month, d.day, hour)),
        )

    def events(self):
        html = self.client.get(reverse("home")).content.decode()
        for raw in re.findall(
            r'<script type="application/ld\+json">\s*(.*?)\s*</script>', html, re.S
        ):
            block = json.loads(raw)
            if "@graph" in block:
                return [n for n in block["@graph"] if n.get("@type") == "ScreeningEvent"]
        return None

    def test_one_event_per_upcoming_showtime_with_the_visible_facts(self):
        from web.constants import TICKET_PRICES
        from web.services.cinema_data import CINEMA_TZ

        first = self.showtime(1, 16)
        self.showtime(1, 19)
        self.showtime(2, 19)
        events = self.events()
        self.assertIsNotNone(events, "no @graph block on the home page")
        self.assertEqual(len(events), 3)
        ev = events[0]
        self.assertEqual(ev["name"], "Dune at Fort Kent Cinema")
        self.assertEqual(ev["startDate"], first.starts_at.astimezone(CINEMA_TZ).isoformat())
        self.assertEqual(ev["location"]["@id"], "https://www.fortkentcinema.com/#theater")
        self.assertEqual(ev["location"]["address"]["streetAddress"],
                         SITE_CONFIG["cinema"]["address"]["street"])
        self.assertEqual(ev["workPresented"]["name"], "Dune")
        self.assertEqual(ev["workPresented"]["url"],
                         f"http://testserver/movies/{self.film.slug}")
        self.assertEqual(ev["workPresented"]["image"], "http://p/d.jpg")
        self.assertEqual(ev["workPresented"]["contentRating"], "PG-13")
        self.assertEqual(ev["offers"]["lowPrice"], str(TICKET_PRICES["member"]))
        self.assertEqual(ev["offers"]["highPrice"], str(TICKET_PRICES["adult"]))
        self.assertEqual(ev["offers"]["priceCurrency"], "USD")

    def test_past_showtimes_of_a_running_engagement_are_not_events(self):
        """Advertising a screening that already happened is wrong, and the
        chips do not show it either."""
        self.showtime(-1, 19)
        self.showtime(1, 19)
        self.assertEqual(len(self.events()), 1)

    def test_theater_block_carries_the_id_the_events_point_at(self):
        html = self.client.get(reverse("home")).content.decode()
        self.assertIn('"@id": "https://www.fortkentcinema.com/#theater"',
                      html.split("@graph")[0])

    @mock.patch("web.views.get_coming_soon", return_value=[])
    @mock.patch("web.views.get_now_showing", return_value=[])
    def test_no_block_when_nothing_is_booked(self, _ns, _cs):
        self.assertIsNone(self.events())

    @mock.patch("web.views.get_coming_soon", return_value=[])
    @mock.patch("web.views.get_now_showing")
    def test_showtimes_without_an_iso_start_are_skipped_not_fatal(self, ns, _cs):
        """Older fixtures and callers hand the view time dicts with no iso;
        an event with no startDate is worse than no event."""
        ns.return_value = [movie()]
        self.assertEqual(self.client.get(reverse("home")).status_code, 200)
        self.assertIsNone(self.events())


class TheaterFormerNameTests(TestCase):
    """Showtime directories still carry the old name, "The Century Theater",
    and the building is still called that in town. The site says so on the
    history page; the MovieTheater block says it too, so a machine can tie
    the two names to one business instead of guessing they are neighbours."""

    def theater(self):
        html = self.client.get("/").content.decode()
        for raw in re.findall(
            r'<script type="application/ld\+json">\s*(.*?)\s*</script>', html, re.S
        ):
            block = json.loads(raw)
            if block.get("@type") == "MovieTheater":
                return block
        self.fail("no MovieTheater block")

    def test_former_name_is_an_alternate_name(self):
        self.assertEqual(self.theater()["alternateName"], "The Century Theater")

    def test_the_history_page_says_it_in_visible_text(self):
        """Structured data may only state what a visitor can read."""
        html = self.client.get(reverse("history")).content.decode()
        self.assertIn("Century", main_content(html))
        self.assertIn("Fort Kent Cinema", main_content(html))
