from django.contrib.sitemaps.views import sitemap
from django.urls import path
from django.views.generic import TemplateView

from website import views as website_views
from website.sitemaps import BlogPostSitemap, BlogStaticSitemap, StaticSitemap

app_name = "website"

sitemaps = {
    "static": StaticSitemap,
    "blog_static": BlogStaticSitemap,
    "blog_posts": BlogPostSitemap,
}

urlpatterns = [
    path(
        "sitemap.xml", sitemap, {"sitemaps": sitemaps}, name="django.contrib.sitemaps.views.sitemap"
    ),
]
