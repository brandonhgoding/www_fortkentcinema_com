from django.test import TestCase
from django.urls import reverse

from web.constants import SITE_CONFIG


def nav_html(html):
    """Just the <nav> element. Assertions must not stray into the rest of the
    page — /blog/ also appears in the footer, and the trailer overlays use
    x-show legitimately."""
    start = html.index('<nav class="nav"')
    return html[start : html.index("</nav>", start)]


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
        # slot, the same as a link, so this counts menus and links together
        # — that is what makes trading Rentals for Events width-neutral.
        self.assertEqual(len(SITE_CONFIG["navigation"]), 5)

    def test_top_level_order(self):
        labels = [i["label"] for i in SITE_CONFIG["navigation"]]
        self.assertEqual(
            labels,
            ["Now Showing", "Coming Soon", "Membership", "Events", "More"],
        )

    def test_events_holds_the_things_you_turn_up_to(self):
        events = next(
            i for i in SITE_CONFIG["navigation"] if i["label"] == "Events"
        )
        labels = [c["label"] for c in events["children"]]
        # Weekly Open Mic first, then the monthly nights in the order the
        # owner set on 2026-09-23.
        self.assertEqual(labels, ["Open Mic", "Craft Night", "Heckle Night"])

    def test_rentals_moved_under_more_rather_than_out(self):
        # Rentals lost its primary slot to Events; it must still be reachable,
        # because it is a page that sells something.
        more = next(i for i in SITE_CONFIG["navigation"] if i["label"] == "More")
        labels = [c["label"] for c in more["children"]]
        self.assertEqual(
            labels,
            ["Rentals", "Sponsor", "History", "Blog", "Film Vote"],
        )
        self.assertIn("/rentals/", nav_destinations())

    def test_no_destination_was_lost_in_the_reshuffle(self):
        # The reshuffle moves items between levels. Every page that was
        # reachable from the nav must still be, whatever level it sits at.
        for href in (
            "/membership/",
            "/rentals/",
            "/craft-night/",
            "/heckle-night/",
            "/open-mic/",
            "/sponsor/",
            "/history/",
            "/blog/",
            "/vote",
        ):
            self.assertIn(href, nav_destinations())

    def test_dropdown_parents_have_no_href_of_their_own(self):
        # A menu opens; it must not also be a navigable destination. Both
        # "Events" and "More" are menus.
        parents = [i for i in SITE_CONFIG["navigation"] if i.get("children")]
        self.assertEqual(len(parents), 2)
        for parent in parents:
            self.assertNotIn("href", parent, parent["label"])

    def test_vote_href_omits_the_trailing_slash(self):
        # urls.py defines path("vote", ...) bare, unlike every other section
        # page. APPEND_SLASH cannot rescue this one: /vote/ 404s outright.
        self.assertIn("/vote", nav_destinations())
        self.assertNotIn("/vote/", nav_destinations())


class NavigationRenderTests(TestCase):
    def test_every_destination_renders_as_a_crawlable_anchor(self):
        # Dropdown children must be real <a href> in the source, not
        # JavaScript-built, or they drop out of the crawl.
        html = nav_html(self.client.get(reverse("home")).content.decode())
        for href in nav_destinations():
            self.assertIn(f'href="{href}"', html)

    def test_each_dropdown_toggle_is_a_button_carrying_its_aria_state(self):
        html = nav_html(self.client.get(reverse("home")).content.decode())
        self.assertEqual(html.count("nav-dropdown-toggle"), 2)
        self.assertEqual(html.count('aria-haspopup="true"'), 2)
        self.assertIn(":aria-expanded", html)

    def test_each_dropdown_gets_its_own_alpine_scope(self):
        """Two menus on one nav must not share `sub`, or opening either
        opens both."""
        html = nav_html(self.client.get(reverse("home")).content.decode())
        self.assertEqual(html.count('x-data="{ sub: false }"'), 2)

    def test_dropdown_menu_opens_by_class_not_inline_display(self):
        # Alpine's x-show writes inline display:none, which the <=768px
        # media query cannot override to flatten the menu on mobile.
        html = nav_html(self.client.get(reverse("home")).content.decode())
        self.assertIn("nav-dropdown-menu--open", html)
        self.assertNotIn("x-show", html)
