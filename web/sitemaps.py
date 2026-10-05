import datetime

from audience.models import MembershipBenefit, MembershipTier
from blog.models import BlogPost
from cinema.models import Engagement, Film, Poll, PollStatus
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
    # The FAQ's "which films are free for members" answer. The tier cards
    # are rows, dated by _content_lastmod below.
    "membership": datetime.date(2026, 9, 20),
    "rentals": datetime.date(2026, 7, 13),
    "craft_night": datetime.date(2026, 9, 21),
    "heckle_night": datetime.date(2026, 9, 22),
    "open_mic": datetime.date(2026, 9, 23),
    "sponsor": datetime.date(2026, 8, 26),
    "history": datetime.date(2026, 8, 25),
    "blog_list": datetime.date(2026, 7, 13),
    "vote": datetime.date(2026, 8, 20),
}


class StaticViewSitemap(Sitemap):
    changefreq = "weekly"
    priority = 0.7

    def items(self):
        return [
            "home",
            "membership",
            "rentals",
            "craft_night",
            "heckle_night",
            "open_mic",
            "sponsor",
            "history",
            "blog_list",
            "vote",
        ]

    def location(self, name):
        return reverse(name)

    def lastmod(self, name):
        """The later of when the page was edited and when its content moved.

        Three of these are windows onto rows that change with nobody touching
        the template — a new post moves /blog/, a new booking moves the
        homepage, a price or perk edit moves /membership/ — so a fixed date
        goes stale the moment any of them happens. The rest are prose, and
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
        if name == "blog_list":
            return BlogPost.objects.published().aggregate(at=Max("post_date"))["at"]
        if name == "home":
            # A booking landing is what changes Now Showing and Coming Soon.
            # Engagement has no updated_at, so this misses a later edit to an
            # existing run — understating is the safe direction to be wrong.
            at = Engagement.objects.aggregate(at=Max("created_at"))["at"]
            return timezone.localtime(at).date() if at else None
        if name == "membership":
            # Every tier, retired ones included: retiring one takes its card
            # off the page. Perks only count while a listed tier carries
            # them. Deleting a row leaves no timestamp behind, so a deletion
            # alone is missed — understating again.
            stamps = [
                MembershipTier.objects.aggregate(at=Max("updated_at"))["at"],
                MembershipBenefit.objects.filter(
                    membershiptier__show_on_membership_page=True
                ).aggregate(at=Max("updated_at"))["at"],
            ]
            at = max((s for s in stamps if s), default=None)
            return timezone.localtime(at).date() if at else None
        return None


class BlogPostSitemap(Sitemap):
    changefreq = "monthly"
    priority = 0.6

    def items(self):
        return BlogPost.objects.published()

    def lastmod(self, obj):
        return obj.post_date


class FilmSitemap(Sitemap):
    changefreq = "weekly"
    priority = 0.8

    def items(self):
        # Only films we've actually booked. A never-booked film has no showtimes
        # and no run history — nothing but the TMDB blurb — so it has no page.
        return Film.objects.with_page().exclude(slug__isnull=True)


class PollSitemap(Sitemap):
    changefreq = "monthly"
    priority = 0.5

    def items(self):
        # Only decided rounds. A draft is not public, and an open round is
        # reached from /vote, which is already in the sitemap.
        return Poll.objects.filter(
            status__in=(PollStatus.CLOSED, PollStatus.ANNOUNCED)
        )

    def location(self, obj):
        return reverse("vote_archive", kwargs={"slug": obj.slug})
