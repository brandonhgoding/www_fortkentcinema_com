"""/llms.txt: a plain-language summary for AI assistants.

A young convention, not a standard, but the audit's assistant questions came
back without prices or membership details, and this answers both. Every fact
in it is rendered from the constants the pages read, so the two can't
disagree; these tests hold that, and that every link in it is a real page.
"""

import re
from unittest import mock

from django.test import TestCase

from web.constants import (
    OPEN_MIC,
    SITE_CONFIG,
    TICKET_PRICES,
)


@mock.patch("web.views.get_calendar_month", return_value={})
@mock.patch("web.views.get_coming_soon", return_value=[])
@mock.patch("web.views.get_now_showing", return_value=[])
class LlmsTxtTests(TestCase):
    def get(self):
        response = self.client.get("/llms.txt")
        self.assertEqual(response.status_code, 200)
        return response

    def test_served_as_utf8_plain_text(self, *_):
        self.assertEqual(self.get()["Content-Type"], "text/plain; charset=utf-8")

    def test_starts_with_the_cinema_name_as_h1(self, *_):
        text = self.get().content.decode()
        self.assertTrue(text.startswith(f"# {SITE_CONFIG['cinema']['name']}\n"))

    def test_not_html_escaped(self, *_):
        """It's a .txt rendered by the HTML template engine: "Maine's" must
        not reach an assistant as "Maine&#x27;s"."""
        text = self.get().content.decode()
        self.assertIn(SITE_CONFIG["cinema"]["tagline"], text)
        self.assertNotIn("&#", text)
        self.assertNotIn("&amp;", text)

    def test_prices_come_from_ticket_prices(self, *_):
        with mock.patch.dict(TICKET_PRICES, adult=91, senior=92, child=93,
                             matinee=94, member=95):
            text = self.get().content.decode()
        for price in ("$91", "$92", "$93", "$94", "$95"):
            self.assertIn(price, text)
        self.assertIn("4 PM or earlier", text)

    def test_contact_and_events_come_from_constants(self, *_):
        text = self.get().content.decode()
        cinema = SITE_CONFIG["cinema"]
        self.assertIn(cinema["address"]["street"], text)
        self.assertIn(cinema["phone"], text)
        self.assertIn(SITE_CONFIG["social"]["facebook"], text)
        self.assertIn(OPEN_MIC["start_label"], text)

    def test_gift_cards_are_not_listed(self, *_):
        # The owner took gift cards off the site on 2026-10-14; llms.txt was
        # the last place that named them.
        text = self.get().content.decode()
        self.assertNotIn("squareup.com/gift", text)
        self.assertNotIn("gift card", text.lower())

    def test_advertising_is_listed(self, *_):
        text = self.get().content.decode()
        self.assertIn("## Rentals, advertising", text)
        # Named as the nav and page titles name them.
        self.assertIn("- Rent the Cinema", text)
        self.assertIn("http://testserver/rentals/", text)
        self.assertIn("- Buy Ad Space", text)
        self.assertIn("http://testserver/advertise/", text)

    def test_every_site_link_is_a_live_page(self, *_):
        text = self.get().content.decode()
        paths = set(re.findall(r"https?://testserver(/[^\s)#]*)", text))
        self.assertGreater(len(paths), 7, "expected links to the site's pages")
        for path in sorted(paths):
            with self.subTest(path=path):
                self.assertEqual(self.client.get(path).status_code, 200)

    def test_does_not_promise_per_film_pages(self, *_):
        # /movies/<slug> was retired on 2026-10-14 (it 301s to the home page),
        # so an assistant reading "links to its own page" would send people to
        # a redirect. The home card is now where a film's details live.
        text = self.get().content.decode()
        self.assertNotIn("its own page", text)
        self.assertIn("There are no separate film pages.", text)
        self.assertIn("Each film card on the home page carries its showtimes", text)

    def test_states_the_screens_and_their_seats(self, *_):
        # Directories disagree on the screen count (Cinema Treasures says
        # one, Screendollars two); the owner confirmed two on 2026-10-15,
        # 100 seats each. Rendered from the config so the schema block and
        # this file can't drift apart.
        text = self.get().content.decode()
        screens = SITE_CONFIG["cinema"]["screens"]
        self.assertEqual(len(screens), 2)
        self.assertIn(f"{len(screens)} screens", text)
        for screen in screens:
            self.assertIn(f"{screen['name']} ({screen['seats']} seats)", text)
