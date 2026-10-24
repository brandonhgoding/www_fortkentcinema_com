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


def footer_item(href):
    return next(i for i in SITE_CONFIG["footer_navigation"] if i["href"] == href)


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

    def test_top_level_order(self):
        # The owner's call on 2026-10-14: the nav names the pages they want
        # Google to offer as sitelinks, in this order. Coming Soon stays a
        # home-page section; it is an anchor, and Google won't sitelink a
        # fragment of the page it is already showing.
        self.assertEqual(
            SITE_CONFIG["navigation"],
            [
                {"label": "Now Showing", "href": "#now-showing"},
                {"label": "Buy Ad Space", "href": "/advertise/"},
                {"label": "Rent the Cinema", "href": "/rentals/"},
            ],
        )

    def test_membership_is_the_nav_button_not_a_link(self):
        # The owner's call on 2026-10-13: Membership leaves the link row and
        # becomes a "Become a Member" button on the right.
        self.assertEqual(
            SITE_CONFIG["nav_cta"],
            {"label": "Become a Member", "href": "/membership/"},
        )
        self.assertNotIn("/membership/", nav_destinations())

    def test_events_menu_is_gone(self):
        # Taken out of the nav on 2026-10-13 with no new home decided yet.
        labels = [i["label"] for i in SITE_CONFIG["navigation"]]
        self.assertNotIn("Events", labels)
        for href in ("/open-mic/", "/heckle-night/"):
            self.assertNotIn(href, nav_destinations())

    def test_more_menu_is_gone(self):
        # The owner emptied "More" on 2026-10-13: Blog, Film Vote and
        # History went to the footer. (Rentals left with them and came back
        # as a top-level link on 2026-10-14.)
        labels = [i["label"] for i in SITE_CONFIG["navigation"]]
        self.assertNotIn("More", labels)
        for href in ("/blog/", "/vote", "/history/", "/sponsor/"):
            self.assertNotIn(href, nav_destinations())

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
                "Member sign in",
                "Rent the Cinema",
                "You Choose",
            ],
        )

    def test_footer_links_member_sign_in(self):
        item = footer_item("/login")
        self.assertEqual(item["label"], "Member sign in")
        self.assertEqual(item["note"], "See your membership")
        html = footer_html(self.client.get("/").content.decode())
        self.assertIn('href="/login"', html)
        self.assertIn("Member sign in", html)

    def test_rentals_link_lives_in_the_footer(self):
        # The owner's call on 2026-10-14: /rentals/ had no internal link
        # after /sponsor/ was removed, so it joins the Explore column.
        rentals = footer_item("/rentals/")
        self.assertEqual(rentals["label"], "Rent the Cinema")
        self.assertEqual(rentals["note"], "Rent the whole theater")
        html = footer_html(self.client.get("/").content.decode())
        self.assertIn('href="/rentals/"', html)

    def test_advertise_link_lives_in_the_footer(self):
        item = footer_item("/advertise/")
        self.assertEqual(item["label"], "Buy Ad Space")
        self.assertEqual(item["note"], "Your business on the big screen")
        html = footer_html(self.client.get("/").content.decode())
        self.assertIn('href="/advertise/"', html)

    def test_footer_no_longer_links_sponsor(self):
        # Removed 2026-10-13 with no new home decided.
        for path in ("/", "/rentals/"):
            html = footer_html(self.client.get(path).content.decode())
            self.assertNotIn('href="/sponsor/"', html, path)

    def test_blog_link_names_the_blog_by_its_title(self):
        # "From the Booth" alone doesn't say it's a blog, so the footer gives
        # it a subtitle on its own line, inside the same link.
        blog = footer_item("/blog/")
        self.assertEqual(blog["href"], "/blog/")
        self.assertEqual(blog["note"], "The Fort Kent Cinema Blog")

    def test_footer_events_column_is_kept_empty_for_now(self):
        # Heckle Night left it on 2026-10-13 and Craft Night was deleted the
        # same day. The owner kept the heading to fill later; until then it
        # has no links and no empty <ul>.
        self.assertEqual(SITE_CONFIG["footer_events"], [])
        html = footer_html(self.client.get("/").content.decode())
        events = html[html.index(">Events</h2>") :]
        events = events[: events.index("</nav>")]
        self.assertNotIn("<ul", events)

    def test_history_link_is_titled_for_the_theatre(self):
        history = footer_item("/history/")
        self.assertEqual(history["href"], "/history/")
        self.assertEqual(history["note"], "A brief, semi-accurate history")

    def test_vote_link_says_what_the_vote_is_for(self):
        vote = footer_item("/vote")
        self.assertEqual(vote["href"], "/vote")
        self.assertEqual(vote["label"], "You Choose")
        self.assertEqual(vote["note"], "Vote to help us pick the films")

    def test_vote_href_omits_the_trailing_slash(self):
        # urls.py defines path("vote", ...) bare, unlike every other section
        # page. APPEND_SLASH cannot rescue this one: /vote/ 404s outright.
        self.assertIn("/vote", footer_destinations())
        self.assertNotIn("/vote/", footer_destinations())


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
            link = html[html.index('href="/blog/"') :]
            link = link[: link.index("</a>")]
            self.assertIn("From the Booth", link, path)
            self.assertIn('<span class="footer-link-note">The Fort Kent Cinema Blog</span>', link, path)

    def test_become_a_member_is_a_button_styled_link_last_in_the_row(self):
        for path in ("/", "/rentals/"):
            html = nav_html(self.client.get(path).content.decode())
            self.assertIn('href="/membership/"', html, path)
            self.assertIn("Become a Member", html, path)
            self.assertIn("btn btn-primary nav-cta", html, path)
            # Last in the row, so it sits at the right edge.
            last_li = html.rindex("<li")
            self.assertIn('href="/membership/"', html[last_li:], path)

    def test_rentals_and_advertise_are_linked_from_the_nav_on_every_page(self):
        # Sitelink candidates: Google weights a main-nav link over a footer
        # one, and the anchor text is what it leans on for the label.
        for path in ("/", "/rentals/", "/advertise/", "/blog/"):
            html = nav_html(self.client.get(path).content.decode())
            self.assertIn('href="/advertise/"', html, path)
            self.assertIn('href="/rentals/"', html, path)
            self.assertIn(">Buy Ad Space</a>", html, path)
            self.assertIn(">Rent the Cinema</a>", html, path)

    def test_coming_soon_left_the_nav(self):
        html = nav_html(self.client.get("/").content.decode())
        self.assertNotIn("#coming-soon", html)
        self.assertNotIn("Coming Soon", html)

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

    def test_no_dropdowns_left(self):
        html = nav_html(self.client.get(reverse("home")).content.decode())
        self.assertNotIn("nav-dropdown-toggle", html)
