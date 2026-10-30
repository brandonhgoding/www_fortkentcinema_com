"""The two email bodies render the same showtimes, every ticket link, and the
unsubscribe placeholder."""

import datetime

from django.test import SimpleTestCase

from newsletter.render import render_issue

BUY = "https://www.fortkentcinema.com/tickets/7/"


def context(**over):
    ctx = {
        "films": [
            {
                "title": "Alpha", "poster": "http://p/a.jpg", "rating": "PG",
                "runtime": "1h 40min", "is_free_for_members": False,
                "days": [
                    {
                        "label": "Thursday, Nov 5",
                        "times": [
                            {"time": "10:15 AM", "ticket_url": BUY,
                             "sold_out": False, "in_person": False},
                            {"time": "7:00 PM", "ticket_url": "",
                             "sold_out": True, "in_person": False},
                        ],
                    },
                    {
                        "label": "Friday, Nov 6",
                        "times": [
                            {"time": "7:00 PM", "ticket_url": "",
                             "sold_out": False, "in_person": True},
                            {"time": "9:30 PM", "ticket_url": "",
                             "sold_out": False, "in_person": False},
                        ],
                    },
                ],
            },
            {
                "title": "Beta", "poster": "", "rating": "", "runtime": "",
                "is_free_for_members": True,
                "days": [{"label": "Saturday, Nov 7", "times": [
                    {"time": "11:00 AM", "ticket_url": "",
                     "sold_out": False, "in_person": False}]}],
            },
        ],
        "coming_soon": [
            {"title": "Gamma", "poster": "http://p/g.jpg", "opens": "Fri, Nov 13"},
            {"title": "Delta", "poster": "", "opens": "Fri, Nov 20"},
        ],
        "coming_soon_url": "https://www.fortkentcinema.com/#coming-soon",
        "post": {"title": "Projector news", "subtitle": "A new lamp",
                 "url": "https://www.fortkentcinema.com/blog/a-new-lamp"},
        "site_url": "https://www.fortkentcinema.com",
        "cinema": {
            "name": "Fort Kent Cinema", "phone": "(207) 231-5287",
            "address": {"street": "13 Hall Street", "city": "Fort Kent",
                        "state": "ME", "zip": "04743"},
        },
        "ticket_prices": {"adult": 8, "senior": 7, "child": 6, "matinee": 6,
                          "member": 4, "matinee_until": datetime.time(16, 0)},
        "unsubscribe_url": "{unsubscribe_url}",
    }
    ctx.update(over)
    return ctx


class RenderTests(SimpleTestCase):
    def test_html_has_every_state_and_the_placeholder(self):
        html, _ = render_issue(context())
        self.assertIn(f'href="{BUY}"', html)
        self.assertIn("Sold out online", html)
        self.assertIn("In-person purchase only", html)
        self.assertIn('href="{unsubscribe_url}"', html)
        self.assertIn("Alpha", html)
        self.assertIn("Beta", html)
        self.assertIn("Free for Members", html)
        self.assertIn("Coming Soon", html)
        self.assertIn("Gamma", html)
        self.assertIn("Opens Fri, Nov 13", html)
        self.assertIn("Projector news", html)
        self.assertIn('<img src="http://p/a.jpg"', html)
        self.assertIn("$4 members", html)
        self.assertIn("13 Hall Street", html)

    def test_text_names_every_showtime_the_html_does(self):
        _, text = render_issue(context())
        for time in ("10:15 AM", "7:00 PM", "9:30 PM", "11:00 AM"):
            self.assertIn(time, text)
        self.assertIn(f"\n{BUY}\n", text)
        self.assertIn("Sold out online", text)
        self.assertIn("In-person purchase only", text)
        self.assertIn("{unsubscribe_url}", text)
        self.assertIn("Projector news", text)
        self.assertIn("Gamma", text)
        self.assertNotIn("<", text)

    def test_html_escapes_titles_and_text_does_not(self):
        films = context()["films"]
        films[0]["title"] = "Tom & Jerry"
        html, text = render_issue(context(films=films))
        self.assertIn("Tom &amp; Jerry", html)
        self.assertIn("Tom & Jerry", text)

    def test_no_post_section_without_post(self):
        html, text = render_issue(context(post=None))
        self.assertNotIn("From the Booth", html)
        self.assertNotIn("From the Booth", text)

    def test_no_coming_soon_section_when_empty(self):
        html, text = render_issue(context(coming_soon=[]))
        self.assertNotIn("Coming Soon", html)
        self.assertNotIn("Coming Soon", text)
