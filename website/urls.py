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
    path("fort-kent-cinema-blog/", website_views.BlogListView.as_view(), name="blog_list"),
    path(
        "fort-kent-cinema-blog/<slug:slug>/",
        website_views.BlogDetailView.as_view(),
        name="blog_detail",
    ),
    path(
        "fort-kent-cinema-membership/",
        TemplateView.as_view(template_name="website/membership_page.html"),
        name="membership",
    ),
    path("contact-fort-kent-cinema/", website_views.contact_view, name="contact"),
    path(
        "sitemap.xml", sitemap, {"sitemaps": sitemaps}, name="django.contrib.sitemaps.views.sitemap"
    ),
]
