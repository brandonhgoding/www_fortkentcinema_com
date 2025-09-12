# myapp/sitemaps.py
from django.contrib.sitemaps import Sitemap
from django.db.models import Max
from django.urls import reverse
from django.utils import timezone

from blog.models import BlogPost
from cinema.models import Film


class CinemaSitemap(Sitemap):
    def get_urls(self, page=1, site=None, protocol=None):
        return super().get_urls(
            page=page, site=type("Site", (), {"domain": "www.fortkentcinema.com"}), protocol="https"
        )


class StaticSitemap(CinemaSitemap):
    changefreq = "weekly"
    priority = 0.8

    def items(self):
        return ["website:index", "website:coming_soon"]

    def location(self, item):
        return reverse(item)


class BlogPostSitemap(CinemaSitemap):
    changefreq = "weekly"
    priority = 0.8
    protocol = "https"  # drop if you want Django to infer

    def items(self):
        return BlogPost.objects.all()

    def lastmod(self, obj):
        # If you later add an updated_at field, return that instead.
        return obj.post_date


class BlogStaticSitemap(CinemaSitemap):
    changefreq = "weekly"
    priority = 0.5
    protocol = "https"

    def items(self):
        # Named URL patterns for your blog index (and any other static views you want in the sitemap)
        return ["website:blog_list"]

    def location(self, item):
        return reverse(item)


class FilmArchiveListSitemap(CinemaSitemap):
    changefreq = "weekly"
    priority = 0.5
    protocol = "https"

    def items(self):
        # Named URL for your archive list page
        return ["website:archive"]

    def location(self, item):
        return reverse(item)


class ArchivedFilmDetailSitemap(CinemaSitemap):
    changefreq = "weekly"
    priority = 0.6
    protocol = "https"

    def items(self):
        now = timezone.now()
        # Match ArchiveListView queryset and annotate last booking end date
        return (
            Film.objects.filter(bookings__booking_end_date__lt=now)
            .annotate(last_end=Max("bookings__booking_end_date"))
            .distinct()
        )

    def lastmod(self, obj):
        # If we have a last booking end date, use it; else None (sitemap omits <lastmod>)
        return getattr(obj, "last_end", None)
