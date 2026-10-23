"""
URL configuration for fortkentcinema project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.2/topics/http/urls/
"""

from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from accounts.forms import EmailAuthenticationForm
from django.contrib.auth.views import LoginView, LogoutView
from django.contrib.sitemaps.views import sitemap
from django.urls import include, path
from django.views.generic import TemplateView

from web.redirects import legacy_urlpatterns
from web.sitemaps import (
    BlogPostSitemap,
    PollSitemap,
    StaticViewSitemap,
)
from web.views import LlmsTxtView

sitemaps = {
    "static": StaticViewSitemap,
    "posts": BlogPostSitemap,
    "polls": PollSitemap,
}

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
    path("llms.txt", LlmsTxtView.as_view(), name="llms"),
    path(
        "login",
        LoginView.as_view(
            template_name="dashboard/login.html",
            authentication_form=EmailAuthenticationForm,
        ),
        name="login",
    ),
    path("logout/", LogoutView.as_view(next_page="/login"), name="logout"),
    path("dashboard/", include("dashboard.urls")),
    path("phone/", include("phone.urls")),
    path("boxoffice/", include("boxoffice.urls")),
    path("tickets/", include("tickets.urls")),
    *legacy_urlpatterns,
    path("", include("web.urls")),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
