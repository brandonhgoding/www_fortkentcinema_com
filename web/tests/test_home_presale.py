"""The Graduate pre-sale challenge banner on the home page (2026-10-17).

The owner needs 50 tickets sold by October 24 to book the film. The banner
is a Square checkout link; it sits between the hero and Now Showing, and
hides itself the day after the deadline so nobody has to remember to pull
it. The image is all type, and at phone widths that type is about 5px tall,
so the facts are repeated as real text under it.
"""

import datetime
from pathlib import Path
from unittest import mock

from django.conf import settings
from django.test import TestCase
from django.urls import reverse

from web.constants import PRESALE_CHALLENGE
from web.services.presale import active_presale

SQUARE = "https://square.link/u/EYztfLV6"
DEADLINE = datetime.date(2026, 10, 24)


class ActivePresaleTests(TestCase):
    def test_deadline_is_october_24(self):
        self.assertEqual(PRESALE_CHALLENGE["deadline"], DEADLINE)
        self.assertEqual(PRESALE_CHALLENGE["url"], SQUARE)

    def test_live_before_the_deadline(self):
        self.assertIsNotNone(active_presale(datetime.date(2026, 10, 17)))

    def test_live_on_the_deadline_day(self):
        self.assertIsNotNone(active_presale(DEADLINE))

    def test_gone_the_day_after(self):
        self.assertIsNone(active_presale(datetime.date(2026, 10, 25)))


@mock.patch("web.views.get_coming_soon", return_value=[])
@mock.patch("web.views.get_now_showing", return_value=[])
class HomePresaleBannerTests(TestCase):
    def home(self, today="2026-10-17"):
        with mock.patch("web.views.today_eastern", return_value=today):
            return self.client.get(reverse("home")).content.decode()

    def section(self, today="2026-10-17"):
        html = self.home(today)
        start = html.index('id="presale"')
        return html[start:html.index("</section>", start)]

    def test_banner_links_to_the_square_checkout(self, *_):
        html = self.home()
        self.assertEqual(html.count('id="presale"'), 1)
        section = self.section()
        self.assertIn(f'href="{SQUARE}"', section)
        self.assertIn('target="_blank"', section)
        # The site's convention for every external link.
        self.assertIn('rel="noopener noreferrer"', section)
        self.assertIn('data-track="presale_click"', section)

    def test_new_tab_and_square_are_announced(self, *_):
        """WCAG G201: a link that opens a new window says so. The visible
        line names Square; the sr-only span says the tab opens."""
        section = self.section()
        self.assertIn("Checkout on Square", section)
        self.assertIn("opens in a new tab", section)
        self.assertIn('class="sr-only"', section)

    def test_hero_points_at_the_banner_while_it_is_live(self, *_):
        """The hero fills the viewport and its button scrolls to Now
        Showing, straight past the banner. A line under the hero buttons
        sends people to it, and goes when the banner goes."""
        html = self.home()
        hero = html[html.index('class="hero"'):html.index('id="presale"')]
        self.assertIn('href="#presale"', hero)
        self.assertIn("The Graduate", hero)
        self.assertIn('data-track="presale_click"', hero)
        gone = self.home("2026-10-25")
        self.assertNotIn('href="#presale"', gone)

    def test_banner_sits_between_the_hero_and_now_showing(self, *_):
        html = self.home()
        hero = html.index('class="hero"')
        presale = html.index('id="presale"')
        now_showing = html.index('id="now-showing"')
        self.assertLess(hero, presale)
        self.assertLess(presale, now_showing)

    def test_the_facts_are_real_text_not_only_pixels(self, *_):
        section = self.section()
        for fact in (
            "The Graduate", "50 tickets", "Saturday, October 24", "$8",
            "Thanksgiving", "7:30", "refund", "pick your showtime at checkout",
        ):
            self.assertIn(fact, section, fact)
        # The handwritten quote is the one human line on the poster and is
        # unreadable on a phone, so it is real text too.
        self.assertIn("My father insists", section)

    def test_alt_is_short_and_leaves_the_facts_to_the_text(self, *_):
        """The alt is the image link's accessible name. The facts sit in the
        heading and paragraph right after it, so a long alt would read the
        pitch out twice; it describes the poster instead."""
        import re
        alt = re.search(r'alt="([^"]*)"', self.section()).group(1)
        self.assertIn("The Graduate", alt)
        self.assertNotIn("50 tickets", alt)
        self.assertLess(len(alt.split()), 20, alt)

    def test_heading_leads_with_the_ask_not_the_title(self, *_):
        section = self.section()
        h2 = section[section.index("<h2"):section.index("</h2>")]
        self.assertIn("Help bring", h2)
        self.assertIn("The Graduate", h2)

    def test_image_is_lazy_sized_and_served_as_webp(self, *_):
        html = self.home()
        start = html.index('id="presale"')
        section = html[start:html.index("</section>", start)]
        self.assertIn('loading="lazy"', section)
        self.assertIn('decoding="async"', section)
        self.assertRegex(section, r'<img[^>]*\swidth="\d+"[^>]*\sheight="\d+"')
        self.assertIn('type="image/webp"', section)
        self.assertIn("graduate-presale", section)

    def test_banner_shows_on_the_deadline_day(self, *_):
        self.assertIn('id="presale"', self.home("2026-10-24"))

    def test_banner_is_gone_the_day_after(self, *_):
        html = self.home("2026-10-25")
        self.assertNotIn('id="presale"', html)
        self.assertNotIn(SQUARE, html)
        self.assertNotIn("graduate-presale", html)


class PresaleAssetsTests(TestCase):
    def test_banner_images_are_committed(self):
        img = Path(settings.BASE_DIR) / "static" / "img"
        for name in (
            "graduate-presale-1400.webp",
            "graduate-presale-2800.webp",
            "graduate-presale-1400.jpg",
        ):
            path = img / name
            self.assertTrue(path.exists(), name)
            # The source PNG is 2MB; nothing here should come close.
            self.assertLess(path.stat().st_size, 600_000, name)
