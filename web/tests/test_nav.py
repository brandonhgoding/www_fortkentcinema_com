import re
from pathlib import Path

from django.conf import settings
from django.test import TestCase
from django.urls import reverse

from web.constants import SITE_CONFIG


def nav_html(html):
    """Just the <nav> element. Assertions must not stray into the rest of the
    page — /blog/ also appears in the footer, and the trailer overlays use
    x-show legitimately."""
    start = html.index('<nav class="nav"')
    return html[start : html.index("</nav>", start)]


def footer_html(html):
    """Just the <footer> element."""
    start = html.index("<footer")
    return html[start : html.index("</footer>", start)]


def footer_destinations():
    return [item["href"] for item in SITE_CONFIG["footer_navigation"]]


def nav_destinations():
    """Every href in the nav, flattened across the dropdown."""
    hrefs = []
    for item in SITE_CONFIG["navigation"]:
        if item.get("children"):
            hrefs.extend(child["href"] for child in item["children"])
        else:
            hrefs.append(item["href"])
    return hrefs


class NavigationConfigTests(TestCase):
    def test_five_top_level_items_is_the_ceiling(self):
        # The nav collapses to a hamburger at 768px, and a sixth top-level
        # item is what strained the 768-900px range. A dropdown occupies one
        # slot, the same as a link, so this counts menus and links together.
        self.assertLessEqual(len(SITE_CONFIG["navigation"]), 5)

    def test_nav_row_is_empty(self):
        # The owner's call on 2026-10-31: Now Showing, Buy Ad Space and Rent
        # the Cinema all left the nav. The bar is the logo and the Become a
        # Member button; advertising and rentals are footer links.
        self.assertEqual(SITE_CONFIG["navigation"], [])

    def test_membership_is_the_nav_button_not_a_link(self):
        # The owner's call on 2026-10-13: Membership leaves the link row and
        # becomes a "Become a Member" button on the right.
        self.assertEqual(
            SITE_CONFIG["nav_cta"],
            {"label": "Become a Member", "href": "/membership/"},
        )
        self.assertNotIn("/membership/", nav_destinations())

    def test_footer_holds_what_left_more(self):
        labels = [i["label"] for i in SITE_CONFIG["footer_navigation"]]
        # Alphabetical, the owner's call on 2026-10-13. The rentals and
        # advertising labels match the nav and the page titles, so Google
        # sees one name per page wherever it is linked.
        self.assertEqual(
            labels,
            [
                "Buy Ad Space",
                "Century Theatre in Fort Kent",
                "From the Booth",
                "Rent the Cinema",
            ],
        )

    def test_footer_does_not_send_visitors_to_the_staff_sign_in(self):
        # Only staff sign in since the member portal went (2026-10-31).
        html = footer_html(self.client.get("/").content.decode())
        self.assertNotIn('href="/login"', html)

    def test_rentals_link_lives_in_the_footer(self):
        # The owner's call on 2026-10-14: /rentals/ had no internal link
        # after /sponsor/ was removed, so it joins the Explore column.
        html = footer_html(self.client.get("/").content.decode())
        self.assertIn('href="/rentals/"', html)

    def test_advertise_link_lives_in_the_footer(self):
        html = footer_html(self.client.get("/").content.decode())
        self.assertIn('href="/advertise/"', html)

    def test_footer_events_column_is_kept_empty_for_now(self):
        # Heckle Night left it on 2026-10-13 and Craft Night was deleted the
        # same day. The owner kept the heading to fill later; until then it
        # has no links and no empty <ul>.
        self.assertEqual(SITE_CONFIG["footer_events"], [])
        html = footer_html(self.client.get("/").content.decode())
        events = html[html.index(">Events</h2>") :]
        events = events[: events.index("</nav>")]
        self.assertNotIn("<ul", events)


class NavigationRenderTests(TestCase):
    def test_every_destination_renders_as_a_crawlable_anchor(self):
        # Dropdown children must be real <a href> in the source, not
        # JavaScript-built, or they drop out of the crawl.
        html = nav_html(self.client.get(reverse("home")).content.decode())
        for href in nav_destinations():
            self.assertIn(f'href="{href}"', html)

    def test_footer_links_render_as_crawlable_anchors_on_every_page(self):
        for path in ("/", "/rentals/"):
            html = footer_html(self.client.get(path).content.decode())
            for href in footer_destinations():
                self.assertIn(f'href="{href}"', html, path)

    def test_become_a_member_is_a_button_styled_link_last_in_the_row(self):
        for path in ("/", "/rentals/"):
            html = nav_html(self.client.get(path).content.decode())
            self.assertIn('href="/membership/"', html, path)
            self.assertIn("btn btn-primary nav-cta", html, path)
            # Last in the row, so it sits at the right edge.
            last_li = html.rindex("<li")
            self.assertIn('href="/membership/"', html[last_li:], path)

    def test_rentals_and_advertise_are_not_in_the_nav(self):
        # Removed from the nav on 2026-10-31; the footer still links both.
        for path in ("/", "/rentals/", "/advertise/", "/blog/"):
            html = nav_html(self.client.get(path).content.decode())
            self.assertNotIn('href="/advertise/"', html, path)
            self.assertNotIn('href="/rentals/"', html, path)

    def test_nav_labels_never_wrap(self):
        # Three links plus the button is enough that between 769 and about
        # 840px "Buy Ad Space" and "Rent the Cinema" broke onto two lines
        # (the bar is a flex row with no nowrap on the links, only on the
        # button). Pin the rule on the source sheet; bundle.css is built
        # from it.
        css = (Path(settings.BASE_DIR) / "static" / "css" / "Nav.css").read_text()
        rule = re.search(r"\n\.nav-link \{(.*?)\}", css, re.S)
        self.assertIsNotNone(rule, ".nav-link rule missing from Nav.css")
        self.assertIn("white-space: nowrap", rule.group(1))
