from django.contrib.sitemaps import Sitemap
from django.urls import reverse

from blog.models import BlogPost


class StaticViewSitemap(Sitemap):
    changefreq = "weekly"
    priority = 0.7

    def items(self):
        return ["home", "membership", "classics", "rentals", "about", "blog_list"]

    def location(self, name):
        return reverse(name)


class BlogPostSitemap(Sitemap):
    changefreq = "monthly"
    priority = 0.6

    def items(self):
        return BlogPost.objects.all()

    def lastmod(self, obj):
        return obj.post_date
