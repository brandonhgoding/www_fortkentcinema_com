"""
URL configuration for fortkentcinema project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.2/topics/http/urls/
"""

from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.contrib.sitemaps.views import sitemap
from django.urls import include, path
from django.views.generic import TemplateView

from web.sitemaps import BlogPostSitemap, StaticViewSitemap

sitemaps = {"static": StaticViewSitemap, "posts": BlogPostSitemap}

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/", include("blog.urls")),
    path("blog/", include("blog.urls_site")),
    path(
        "sitemap.xml",
        sitemap,
        {"sitemaps": sitemaps},
        name="django.contrib.sitemaps.views.sitemap",
    ),
    path(
        "robots.txt",
        TemplateView.as_view(template_name="robots.txt", content_type="text/plain"),
        name="robots",
    ),
    path("dashboard/", include("dashboard.urls")),
    path("", include("web.urls")),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
