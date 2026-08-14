"""301s for URL structures used by earlier generations of the site.

Google still holds these URLs — the oldest go back to 2022 — and they were
404ing after the Django migration, which stranded years of ranking history and
inbound links. Each pattern matches both the trailing-slash and bare form so a
legacy URL resolves in a single hop rather than bouncing through APPEND_SLASH.

Do not delete these. If a future rewrite changes URLs again, add the redirects
in the same commit.
"""

from django.urls import re_path
from django.views.generic import RedirectView

legacy_urlpatterns = [
    # Blog lived at /fort-kent-cinema-blog/<slug>/. Slugs carried over to the
    # modern /blog/<slug> route unchanged, so this maps 1:1.
    re_path(
        r"^fort-kent-cinema-blog/(?P<slug>[-\w]+)/?$",
        RedirectView.as_view(pattern_name="blog_detail", permanent=True),
        name="legacy_blog_detail",
    ),
    re_path(
        r"^fort-kent-cinema-blog/?$",
        RedirectView.as_view(pattern_name="blog_list", permanent=True),
        name="legacy_blog_list",
    ),
    # /coming-soon/ has no modern page; the homepage carries the section.
    re_path(
        r"^coming-soon/?$",
        RedirectView.as_view(url="/#coming-soon", permanent=True),
        name="legacy_coming_soon",
    ),
    # The old per-movie pages. Re-point these at /movies/<slug> once real
    # per-movie pages exist — until then the homepage is the closest thing.
    re_path(
        r"^archive/(?P<slug>[-\w]+)/?$",
        RedirectView.as_view(url="/", permanent=True),
        name="legacy_archive_detail",
    ),
    re_path(
        r"^archive/?$",
        RedirectView.as_view(url="/", permanent=True),
        name="legacy_archive_index",
    ),
    # Classic Movie Night was discontinued 2026-08-14 and /classics/ removed.
    # The page carried its own ranking history, so it redirects rather than 404s.
    re_path(
        r"^classics/?$",
        RedirectView.as_view(url="/", permanent=True),
        name="legacy_classics",
    ),
    # No modern contact page; address and phone are in the homepage footer.
    re_path(
        r"^contact-fort-kent-cinema/?$",
        RedirectView.as_view(url="/", permanent=True),
        name="legacy_contact",
    ),
]
