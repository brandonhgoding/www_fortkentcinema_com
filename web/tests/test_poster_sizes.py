"""Posters are requested at the size they are shown.

The 2026-10-15 audit's Lighthouse run flagged every TMDB poster on the home
page: w500 files (492x750) drawn into a 120px Coming Soon column or a 33px
calendar cell, about 400 KB over what the phone needed. TMDB serves the
same image at w92, w154, w185, w342, w500 and w780, so the fix is to ask
for the right one. w500 stays the ceiling: nothing here may fetch more
than the page did before.
"""

import re
from unittest import mock

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from web.templatetags.posters import poster_srcset, tmdb_size

W500 = "https://image.tmdb.org/t/p/w500/abc123.jpg"


class TmdbSizeFilterTests(TestCase):
    def test_swaps_the_size_segment(self):
        self.assertEqual(
            tmdb_size(W500, "w342"), "https://image.tmdb.org/t/p/w342/abc123.jpg"
        )

    def test_leaves_other_hosts_alone(self):
        self.assertEqual(tmdb_size("/media/poster.jpg", "w342"), "/media/poster.jpg")

    def test_empty_stays_empty(self):
        self.assertEqual(tmdb_size("", "w342"), "")

    def test_srcset_offers_three_sizes_up_to_w500(self):
        srcset = poster_srcset(W500)
        self.assertEqual(
            srcset,
            "https://image.tmdb.org/t/p/w185/abc123.jpg 185w, "
            "https://image.tmdb.org/t/p/w342/abc123.jpg 342w, "
            "https://image.tmdb.org/t/p/w500/abc123.jpg 500w",
        )
        self.assertNotIn("w780", srcset)

    def test_srcset_is_empty_for_non_tmdb_urls(self):
        # So the template can leave the attribute off instead of listing the
        # same file three times.
        self.assertEqual(poster_srcset("/media/poster.jpg"), "")


def movie(**over):
    base = {
        "id": "1",
        "title": "Dune",
        "rating": "PG-13",
        "runtime": "2h 35min",
        "genre": "Sci-fi",
        "poster": W500,
        "youtube_id": "",
        "is_free_for_members": False,
        "showtimes": {
            "2999-01-15": [
                {
                    "time": "6:00 PM",
                    "iso": "2999-01-15T18:00:00-05:00",
                    "captions": "",
                    "captions_label": "",
                }
            ]
        },
    }
    base.update(over)
    return base


def coming(**over):
    base = {
        "id": "2",
        "title": "Arrival",
        "start_date": "2999-02-01",
        "release_date": "February 1",
        "genre": "",
        "poster": W500,
        "films": [{"id": 2, "title": "Arrival", "poster": W500}],
        "description": "",
        "youtube_id": "",
        "is_free_for_members": False,
    }
    base.update(over)
    return base


def img_tags(html, css_class):
    pattern = r'<img[^>]*class="[^"]*\b%s\b[^"]*"[^>]*>' % css_class
    return re.findall(pattern, html, re.S)


@mock.patch("web.views.get_calendar_month", return_value={})
class HomePosterMarkupTests(TestCase):
    def render(self, now_showing=(), coming_soon=()):
        with (
            mock.patch("web.views.get_now_showing", return_value=list(now_showing)),
            mock.patch("web.views.get_coming_soon", return_value=list(coming_soon)),
        ):
            return self.client.get("/").content.decode()

    def test_now_showing_poster_has_a_srcset_and_intrinsic_size(self, _cal):
        html = self.render(now_showing=[movie()])
        (tag,) = img_tags(html, "movie-poster-img")
        self.assertIn('src="https://image.tmdb.org/t/p/w342/abc123.jpg"', tag)
        self.assertIn("/t/p/w185/abc123.jpg 185w", tag)
        self.assertIn("/t/p/w500/abc123.jpg 500w", tag)
        self.assertNotIn("w780", tag)
        # The poster is the card's full width under 1024px (the card caps at
        # 340px) and a clamp(11.5rem, 38%, 15rem) column above it.
        self.assertIn('sizes="(min-width: 1024px) 15rem, 340px"', tag)
        # Intrinsic size of the src candidate, so the slot is reserved
        # before the file arrives (the audit traced the home page's layout
        # shift to this section).
        self.assertIn('width="342"', tag)
        self.assertIn('height="513"', tag)

    def test_coming_soon_poster_is_sized_for_its_120px_column(self, _cal):
        html = self.render(coming_soon=[coming()])
        (tag,) = img_tags(html, "coming-poster-img")
        self.assertIn('src="https://image.tmdb.org/t/p/w185/abc123.jpg"', tag)
        self.assertIn("/t/p/w342/abc123.jpg 342w", tag)
        self.assertIn('sizes="120px"', tag)
        self.assertIn('width="185"', tag)
        self.assertIn('height="278"', tag)

    def test_double_feature_posters_share_the_column(self, _cal):
        films = [
            {"id": 2, "title": "Arrival", "poster": W500},
            {"id": 3, "title": "Dune", "poster": W500.replace("abc123", "def456")},
        ]
        html = self.render(coming_soon=[coming(films=films)])
        tags = img_tags(html, "coming-poster-img--multi")
        self.assertEqual(len(tags), 2)
        for tag in tags:
            self.assertIn('sizes="60px"', tag)
            self.assertIn("185w", tag)

    def test_non_tmdb_poster_renders_without_a_srcset(self, _cal):
        html = self.render(now_showing=[movie(poster="/media/local.jpg")])
        (tag,) = img_tags(html, "movie-poster-img")
        self.assertIn('src="/media/local.jpg"', tag)
        self.assertNotIn("srcset", tag)
        self.assertNotIn("sizes=", tag)

    def test_schema_keeps_the_w500_poster(self, _cal):
        # Google's event guidelines want the large image; only the <img>
        # elements shrink.
        html = self.render(now_showing=[movie()])
        ld = html[html.index('"ScreeningEvent"') :]
        self.assertIn('"image": "https://image.tmdb.org/t/p/w500/abc123.jpg"', ld)


class CalendarPosterMarkupTests(TestCase):
    """The HTMX calendar fragment: ~33px cells (22px on a phone) and a 40px
    key thumbnail, so fixed small sizes rather than a srcset.

    Written after the template change, not before: the calendar edit rode
    along with the home-page ones. It fails if either size is dropped.
    """

    def fragment(self):
        today = timezone.localdate()
        data = {15: [{"id": "1", "title": "Dune", "poster": W500, "youtube_id": ""}]}
        with mock.patch("web.views.get_calendar_month", return_value=data):
            url = reverse("calendar_month", args=[today.year, today.month - 1])
            return self.client.get(url).content.decode()

    def test_cell_thumbnail_is_w92(self):
        (tag,) = img_tags(self.fragment(), "coming-calendar-cell__img")
        self.assertIn('src="https://image.tmdb.org/t/p/w92/abc123.jpg"', tag)

    def test_key_thumbnail_is_w154(self):
        html = self.fragment()
        key = html[html.index("coming-calendar-key__list") :]
        self.assertIn('src="https://image.tmdb.org/t/p/w154/abc123.jpg"', key)
