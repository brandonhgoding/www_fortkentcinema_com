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
    def test_four_primary_items_are_visible_before_the_dropdown(self):
        # The nav collapses to a hamburger at 768px; more than four primary
        # links is what strained the 768-900px range.
        primary = [
            i["label"] for i in SITE_CONFIG["navigation"] if not i.get("children")
        ]
        self.assertEqual(
            primary, ["Now Showing", "Coming Soon", "Membership", "Rentals"]
        )

    def test_secondary_pages_live_under_a_single_more_parent(self):
        parents = [i for i in SITE_CONFIG["navigation"] if i.get("children")]
        self.assertEqual(len(parents), 1)
        self.assertEqual(parents[0]["label"], "More")
        labels = [c["label"] for c in parents[0]["children"]]
        self.assertEqual(labels, ["Sponsor", "History", "Blog", "Film Vote"])

    def test_dropdown_parent_has_no_href_of_its_own(self):
        # "More" opens a menu; it must not be a navigable destination.
        parent = next(i for i in SITE_CONFIG["navigation"] if i.get("children"))
        self.assertNotIn("href", parent)

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

    def test_more_toggle_is_a_button_carrying_its_aria_state(self):
        html = nav_html(self.client.get(reverse("home")).content.decode())
        self.assertIn("nav-dropdown-toggle", html)
        self.assertIn('aria-haspopup="true"', html)
        self.assertIn(":aria-expanded", html)

    def test_dropdown_menu_opens_by_class_not_inline_display(self):
        # Alpine's x-show writes inline display:none, which the <=768px
        # media query cannot override to flatten the menu on mobile.
        html = nav_html(self.client.get(reverse("home")).content.decode())
        self.assertIn("nav-dropdown-menu--open", html)
        self.assertNotIn("x-show", html)
