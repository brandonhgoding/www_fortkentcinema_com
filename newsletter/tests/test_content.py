"""The Thursday email's content: the weekend window, the listing's ticket
states, Coming Soon, the latest post and the subject line."""

import datetime

from django.test import TestCase, override_settings

from blog.models import BlogAuthor, BlogCategory, BlogPost
from cinema.models import Showtime
from newsletter.content import (
    COMING_SOON_CAP,
    build_context,
    day_label,
    opens_label,
    subject_for,
    window_for,
)
from tickets.tests.factories import make_live_item, make_order
from web.tests.test_cinema_data import (
    aware,
    make_engagement,
    make_film,
    make_screen,
)

SQUARE_ON = {
    "SQUARE_ACCESS_TOKEN": "t",
    "SQUARE_LOCATION_ID": "L",
    "SQUARE_TICKET_CATEGORY_ID": "C",
    "TICKETS_BASE_URL": "https://www.fortkentcinema.com",
}

THURSDAY = datetime.date(2026, 11, 5)


class ContentTests(TestCase):
    def setUp(self):
        self.now = aware(2026, 11, 5, 10, 0)
        self.screen = make_screen()
        self.film = make_film("Alpha", poster_url="http://p/a.jpg", rating="PG")
        self.run = make_engagement(
            self.screen, [self.film], start=THURSDAY,
            end=THURSDAY + datetime.timedelta(days=6),
        )

    def showtime(self, day, hour, minute=0, run=None, **over):
        return Showtime.objects.create(
            engagement=run or self.run, screen=self.screen,
            starts_at=aware(2026, 11, day, hour, minute), **over,
        )

    def film_days(self, ctx):
        return [day["label"] for day in ctx["films"][0]["days"]]

    def test_window_for(self):
        self.assertEqual(
            window_for(self.now), (THURSDAY, datetime.date(2026, 11, 8))
        )

    def test_none_without_showtimes(self):
        self.assertIsNone(build_context(self.now))

    def test_window_edges(self):
        self.showtime(4, 23, 59)
        self.showtime(8, 20)
        self.showtime(9, 19)
        ctx = build_context(self.now)
        self.assertEqual(self.film_days(ctx), ["Sunday, Nov 8"])

    def test_thursday_morning_edge(self):
        self.showtime(5, 9, 30)
        self.showtime(5, 10, 15)
        ctx = build_context(self.now)
        self.assertEqual(self.film_days(ctx), ["Thursday, Nov 5"])
        times = ctx["films"][0]["days"][0]["times"]
        self.assertEqual([t["time"] for t in times], ["10:15 AM"])

    def test_cancelled_and_hidden_excluded(self):
        self.showtime(6, 19, is_cancelled=True)
        hidden = make_engagement(
            self.screen, [make_film("Hidden")], start=THURSDAY,
            end=THURSDAY + datetime.timedelta(days=6), show=False,
        )
        self.showtime(6, 21, run=hidden)
        self.assertIsNone(build_context(self.now))

    def test_coming_soon_capped_and_ordered(self):
        self.showtime(6, 19)
        for i in range(4):
            start = datetime.date(2026, 11, 13) + datetime.timedelta(days=7 * i)
            make_engagement(
                self.screen, [make_film(f"Soon {i}")], start=start,
                end=start + datetime.timedelta(days=6),
            )
        ctx = build_context(self.now)
        self.assertEqual(len(ctx["coming_soon"]), COMING_SOON_CAP)
        self.assertEqual(
            [c["title"] for c in ctx["coming_soon"]], ["Soon 0", "Soon 1", "Soon 2"]
        )
        self.assertEqual(ctx["coming_soon"][0]["opens"], "Fri, Nov 13")

    def _post(self, post_date):
        author = BlogAuthor.objects.create(first_name="B", last_name="G")
        category = BlogCategory.objects.create(name="News")
        return BlogPost.objects.create(
            title="Projector news", subtitle="A new lamp", author=author,
            category=category, post_date=post_date, content="...",
            status=BlogPost.Status.PUBLISHED,
        )

    def test_recent_post_included(self):
        self.showtime(6, 19)
        post = self._post(datetime.date(2026, 11, 1))
        ctx = build_context(self.now)
        self.assertEqual(ctx["post"]["title"], "Projector news")
        self.assertEqual(ctx["post"]["subtitle"], "A new lamp")
        self.assertTrue(ctx["post"]["url"].endswith(post.get_absolute_url()))

    def test_old_post_excluded(self):
        self.showtime(6, 19)
        self._post(datetime.date(2026, 10, 27))
        self.assertIsNone(build_context(self.now)["post"])

    @override_settings(**SQUARE_ON)
    def test_ticket_urls_absolute(self):
        st = self.showtime(6, 19)
        make_live_item(self.run)
        ctx = build_context(self.now)
        time = ctx["films"][0]["days"][0]["times"][0]
        self.assertEqual(
            time["ticket_url"], f"https://www.fortkentcinema.com/tickets/{st.pk}/"
        )
        self.assertEqual(ctx["site_url"], "https://www.fortkentcinema.com")
        self.assertEqual(
            ctx["coming_soon_url"], "https://www.fortkentcinema.com/#coming-soon"
        )

    @override_settings(**SQUARE_ON)
    def test_sold_out_film_is_listed(self):
        st = self.showtime(6, 19, online_allowance=1)
        make_live_item(self.run)
        make_order(st, status="PAID")
        ctx = build_context(self.now)
        self.assertEqual([f["title"] for f in ctx["films"]], ["Alpha"])
        time = ctx["films"][0]["days"][0]["times"][0]
        self.assertTrue(time["sold_out"])
        self.assertTrue(time["ticket_url"].endswith(f"/tickets/{st.pk}/"))

    @override_settings(**SQUARE_ON)
    def test_sold_out_renders_as_sold_out_not_buy(self):
        from newsletter.render import render_issue

        st = self.showtime(6, 19, online_allowance=1)
        make_live_item(self.run)
        make_order(st, status="PAID")
        html, text = render_issue(build_context(self.now))
        self.assertIn("Sold out online", html)
        self.assertIn("Sold out online", text)
        self.assertNotIn("Buy</a>", html)
        self.assertNotIn("- Buy:", text)
        self.assertNotIn(f"/tickets/{st.pk}/", html)

    def test_film_fields(self):
        self.showtime(6, 19)
        film = build_context(self.now)["films"][0]
        self.assertEqual(film["poster"], "http://p/a.jpg")
        self.assertEqual(film["rating"], "PG")
        self.assertFalse(film["is_free_for_members"])

    def test_placeholder_and_cinema(self):
        self.showtime(6, 19)
        ctx = build_context(self.now)
        self.assertEqual(ctx["unsubscribe_url"], "{unsubscribe_url}")
        self.assertEqual(ctx["cinema"]["name"], "Fort Kent Cinema")
        self.assertIn("adult", ctx["ticket_prices"])


class LabelTests(TestCase):
    def test_labels(self):
        self.assertEqual(day_label(THURSDAY), "Thursday, Nov 5")
        self.assertEqual(opens_label(datetime.date(2026, 11, 14)), "Sat, Nov 14")

    def test_subject_lines(self):
        base = "This weekend at the Cinema: "
        self.assertEqual(subject_for([{"title": "A"}]), base + "A")
        self.assertEqual(subject_for([{"title": "A"}, {"title": "B"}]), base + "A, B")
        self.assertEqual(
            subject_for([{"title": "A"}, {"title": "B"}, {"title": "C"}]),
            base + "A, B and more",
        )
