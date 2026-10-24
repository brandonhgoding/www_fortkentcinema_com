"""
URL configuration for fortkentcinema project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.2/topics/http/urls/
"""

from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from accounts.forms import EmailAuthenticationForm, EmailPasswordResetForm
from accounts.views import LockoutClearingPasswordResetConfirmView
from django.contrib.auth.views import (
    LoginView,
    LogoutView,
    PasswordResetCompleteView,
    PasswordResetDoneView,
    PasswordResetView,
)
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
    path(
        "password-reset",
        PasswordResetView.as_view(
            form_class=EmailPasswordResetForm,
            template_name="dashboard/password_reset_form.html",
            email_template_name="dashboard/password_reset_email.txt",
            subject_template_name="dashboard/password_reset_subject.txt",
            success_url="/password-reset/sent",
        ),
        name="password_reset",
    ),
    path(
        "password-reset/sent",
        PasswordResetDoneView.as_view(
            template_name="dashboard/password_reset_sent.html"
        ),
        name="password_reset_sent",
    ),
    path(
        "password-reset/<uidb64>/<token>",
        LockoutClearingPasswordResetConfirmView.as_view(
            template_name="dashboard/password_reset_confirm.html",
            success_url="/password-reset/done",
        ),
        name="password_reset_confirm",
    ),
    path(
        "password-reset/done",
        PasswordResetCompleteView.as_view(
            template_name="dashboard/password_reset_done.html"
        ),
        name="password_reset_complete",
    ),
    path("dashboard/", include("dashboard.urls")),
    path("phone/", include("phone.urls")),
    path("boxoffice/", include("boxoffice.urls")),
    path("tickets/", include("tickets.urls")),
    *legacy_urlpatterns,
    path("", include("web.urls")),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
