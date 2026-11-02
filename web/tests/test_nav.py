from django.test import TestCase

from web.constants import SITE_CONFIG


def nav_html(html):
    """Just the <nav> element. Assertions must not stray into the rest of the
    page — the footer carries links too, and the trailer overlays use
    x-show legitimately."""
    start = html.index('<nav class="nav"')
    return html[start : html.index("</nav>", start)]


def footer_html(html):
    """Just the <footer> element."""
    start = html.index("<footer")
    return html[start : html.index("</footer>", start)]


def footer_destinations():
    return [item["href"] for item in SITE_CONFIG["footer_navigation"]]


class NavigationConfigTests(TestCase):
    def test_footer_links_are_alphabetical(self):
        # Alphabetical, the owner's call on 2026-10-13.
        labels = [i["label"] for i in SITE_CONFIG["footer_navigation"]]
        self.assertEqual(labels, sorted(labels))

    def test_rentals_link_lives_in_the_footer(self):
        # The owner's call on 2026-10-14: /rentals/ had no internal link
        # after /sponsor/ was removed, so it joins the Explore column.
        html = footer_html(self.client.get("/").content.decode())
        self.assertIn('href="/rentals/"', html)

    def test_advertise_link_lives_in_the_footer(self):
        html = footer_html(self.client.get("/").content.decode())
        self.assertIn('href="/advertise/"', html)

    def test_footer_and_nav_name_advertise_the_same(self):
        # The owner's call on 2026-11-02: both say "Advertise".
        def label(links):
            return next(i["label"] for i in links if i["href"] == "/advertise/")

        self.assertEqual(label(SITE_CONFIG["footer_navigation"]), "Advertise")
        self.assertEqual(label(SITE_CONFIG["navigation"]), "Advertise")

    def test_advertise_page_and_llms_txt_use_the_same_name(self):
        # Everything says "Advertise" (2026-11-02): the page's title, share
        # title and heading, and its line in llms.txt.
        html = self.client.get("/advertise/").content.decode()
        self.assertIn("<title>Advertise | Fort Kent Cinema</title>", html)
        self.assertIn('content="Advertise | Fort Kent Cinema"', html)
        self.assertIn('<h1 class="advertise-title">ADVERTISE</h1>', html)
        llms = self.client.get("/llms.txt").content.decode()
        self.assertIn("- Advertise, advertising on the big screen", llms)
        self.assertNotIn("Buy Ad Space", html + llms)

    def test_footer_events_column_is_kept_empty_for_now(self):
        # Heckle Night left it on 2026-10-13 and Craft Night was deleted the
        # same day. The owner kept the heading to fill later; until then it
        # has no links and no empty <ul>.
        html = footer_html(self.client.get("/").content.decode())
        events = html[html.index(">Events</h2>") :]
        events = events[: events.index("</nav>")]
        self.assertNotIn("<ul", events)


class NavigationRenderTests(TestCase):
    def test_footer_links_render_as_crawlable_anchors_on_every_page(self):
        for path in ("/", "/rentals/"):
            html = footer_html(self.client.get(path).content.decode())
            for href in footer_destinations():
                self.assertIn(f'href="{href}"', html, path)

    def test_advertise_is_the_one_top_nav_link_on_every_page(self):
        # The owner put Advertise back in the nav on 2026-11-02.
        for path in ("/", "/rentals/", "/advertise/"):
            html = nav_html(self.client.get(path).content.decode())
            self.assertIn('href="/advertise/"', html, path)
            self.assertIn(">Advertise</a>", html, path)
            self.assertEqual(html.count('class="nav-link"'), 1, path)
