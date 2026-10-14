"""The static sitemap's hand-maintained <lastmod> dates."""

import datetime
import re

from django.test import TestCase


class StaticSitemapLastmodTests(TestCase):
    """The static sitemap carried no <lastmod> at all, so nothing told Google
    that a page it already had a copy of was worth re-fetching.

    The dates are hand-maintained, which means the risk is not that they are
    wrong today but that they rot. These tests are the guard rail.
    """

    def _urls(self):
        xml = self.client.get("/sitemap.xml").content.decode()
        return dict(
            re.findall(
                r"<url><loc>(.*?)</loc>.*?<lastmod>(.*?)</lastmod>", xml
            )
        )

    def test_every_static_page_has_a_maintained_date(self):
        """Adding a page to items() without dating it is the way this decays:
        the page ships with no lastmod and nobody notices."""
        from web.sitemaps import STATIC_PAGE_LASTMOD, StaticViewSitemap

        undated = [
            name
            for name in StaticViewSitemap().items()
            if name not in STATIC_PAGE_LASTMOD
        ]
        self.assertEqual(
            undated, [], f"add these to STATIC_PAGE_LASTMOD: {undated}"
        )

    def test_no_date_is_in_the_future(self):
        """A future date is the clearest possible tell that these are being
        set by hand rather than observed, and it is what makes Google stop
        trusting lastmod across the whole site."""
        from web.sitemaps import STATIC_PAGE_LASTMOD

        today = datetime.date.today()
        ahead = {
            name: date
            for name, date in STATIC_PAGE_LASTMOD.items()
            if date > today
        }
        self.assertEqual(ahead, {}, f"dated in the future: {ahead}")

    def test_the_sitemap_actually_emits_them(self):
        urls = self._urls()
        rentals = [u for u in urls if u.endswith("/rentals/")]
        self.assertEqual(len(rentals), 1, "rentals missing from the sitemap")
        self.assertTrue(urls[rentals[0]], "rentals has an empty lastmod")

    def test_a_data_driven_page_beats_its_template_date(self):
        """/blog/ moves when a post lands, with nobody touching the template.
        A fixed date would go stale the same day."""
        from blog.models import BlogAuthor, BlogCategory, BlogPost
        from web.sitemaps import STATIC_PAGE_LASTMOD, StaticViewSitemap

        future = datetime.date.today()
        BlogPost.objects.create(
            title="A new post",
            post_date=future,
            content="x",
            author=BlogAuthor.objects.create(
                first_name="Brandon", last_name="Goding"
            ),
            category=BlogCategory.objects.create(name="News"),
        )
        self.assertEqual(StaticViewSitemap().lastmod("blog_list"), future)
        self.assertGreater(future, STATIC_PAGE_LASTMOD["blog_list"])
