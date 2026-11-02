import datetime

from cinema.models import Engagement
from django.contrib.sitemaps import Sitemap
from django.db.models import Max
from django.urls import reverse
from django.utils import timezone

# When each hand-authored page's content last actually changed.
#
# Maintained by hand, and deliberately so — every way of deriving it is worse.
# A template's mtime is reset by checkout, so it would announce that the whole
# site changed on every deploy. Shelling out to `git log` needs history the
# deployed tree may not carry, and costs a subprocess per URL per crawl.
#
# Google drops `lastmod` as a signal for a whole site once it catches that
# site's dates disagreeing with its content, so a merely plausible date is
# worse than no date. Bump an entry when you change what the page *says* —
# not when you restyle it, and never to make it look fresh.
STATIC_PAGE_LASTMOD = {
    "home": datetime.date(2026, 8, 25),
    "rentals": datetime.date(2026, 7, 13),
    "advertise": datetime.date(2026, 11, 2),
}


class StaticViewSitemap(Sitemap):
    changefreq = "weekly"
    priority = 0.7

    def items(self):
        return [
            "home",
            "rentals",
            "advertise",
        ]

    def location(self, name):
        return reverse(name)

    def lastmod(self, name):
        """The later of when the page was edited and when its content moved.

        The homepage is a window onto rows that change with nobody touching
        the template — a new booking moves it — so a fixed date goes stale
        the moment one lands. The rest are prose, and
        only move when someone edits them.

        Returns None rather than a guess for a page listed in neither place.
        An omitted lastmod is a missing signal; a wrong one discredits the
        dates on every other URL here.
        """
        edited = STATIC_PAGE_LASTMOD.get(name)
        moved = self._content_lastmod(name)
        if edited and moved:
            return max(edited, moved)
        return edited or moved

    def _content_lastmod(self, name):
        """The newest row behind a page, for the pages that have rows."""
        if name == "home":
            # A booking landing is what changes Now Showing and Coming Soon.
            # Engagement has no updated_at, so this misses a later edit to an
            # existing run — understating is the safe direction to be wrong.
            at = Engagement.objects.aggregate(at=Max("created_at"))["at"]
            return timezone.localtime(at).date() if at else None
        return None
