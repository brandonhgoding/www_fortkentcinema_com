from blog.models import BlogPost
from cinema.models import Film
from django.contrib.sitemaps import Sitemap
from django.urls import reverse


class StaticViewSitemap(Sitemap):
    changefreq = "weekly"
    priority = 0.7

    def items(self):
        # "about" temporarily removed while the About page is hidden
        return ["home", "membership", "rentals", "blog_list"]

    def location(self, name):
        return reverse(name)


class BlogPostSitemap(Sitemap):
    changefreq = "monthly"
    priority = 0.6

    def items(self):
        return BlogPost.objects.all()

    def lastmod(self, obj):
        return obj.post_date


class FilmSitemap(Sitemap):
    changefreq = "weekly"
    priority = 0.8

    def items(self):
        # Only films we've actually booked. A never-booked film has no showtimes
        # and no run history — nothing but the TMDB blurb — so it has no page.
        return (
            Film.objects.filter(engagements__isnull=False)
            .exclude(slug__isnull=True)
            .distinct()
        )
