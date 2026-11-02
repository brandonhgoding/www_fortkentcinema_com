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
        for path in ("/rentals/", "/advertise/"):
            found = [u for u in urls if u.endswith(path)]
            self.assertEqual(len(found), 1, f"{path} missing from the sitemap")
            self.assertTrue(urls[found[0]], f"{path} has an empty lastmod")

    def test_a_data_driven_page_beats_its_template_date(self):
        """The homepage moves when a run is booked, with nobody touching the
        template. A fixed date would go stale the same day."""
        from cinema.models import Screen
        from dashboard.tests.test_engagements import make_engagement
        from django.utils import timezone
        from web.sitemaps import STATIC_PAGE_LASTMOD, StaticViewSitemap

        today = timezone.localdate()
        make_engagement(
            Screen.objects.create(name="S1", capacity=50), start=today, end=today
        )
        self.assertEqual(StaticViewSitemap().lastmod("home"), today)
        self.assertGreater(today, STATIC_PAGE_LASTMOD["home"])
