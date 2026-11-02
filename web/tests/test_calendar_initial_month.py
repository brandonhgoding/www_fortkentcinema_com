"""The month the home page's Coming Soon calendar opens on.

The calendar is lazy-loaded from the URL in the container's hx-get, so the
month it opens on is whatever HomeView puts there: the month of the
earliest Coming Soon run, else this month in Fort Kent.
"""

import datetime
from unittest import mock

from django.test import TestCase
from django.urls import reverse

from web.services.showtimes import CINEMA_TZ


def run(start_date):
    return {
        "id": start_date, "title": f"Run {start_date}", "release_date": "",
        "genre": "", "poster": "", "youtube_id": "", "films": [],
        "start_date": start_date,
    }


@mock.patch("web.views.get_hero_films", return_value=[])
class InitialCalendarMonthTests(TestCase):
    def home(self, coming_soon):
        with mock.patch("web.views.get_coming_soon", return_value=coming_soon):
            return self.client.get(reverse("home"))

    def assertOpensOn(self, response, year, month0):
        self.assertEqual(
            (response.context["initial_year"], response.context["initial_month"]),
            (year, month0),
        )
        self.assertContains(
            response, f'hx-get="{reverse("calendar_month", args=[year, month0])}"'
        )

    def this_month(self):
        now = datetime.datetime.now(CINEMA_TZ)
        return now.year, now.month - 1

    def test_opens_on_the_earliest_runs_month(self, _hero):
        # Out of order on purpose: the earliest wins, not the first listed.
        response = self.home([run("2999-03-20"), run("2999-01-15"), run("2999-02-01")])
        self.assertOpensOn(response, 2999, 0)

    def test_runs_without_a_start_date_are_ignored(self, _hero):
        response = self.home([run(""), run("2999-07-04")])
        self.assertOpensOn(response, 2999, 6)

    def test_nothing_coming_opens_on_this_month(self, _hero):
        self.assertOpensOn(self.home([]), *self.this_month())

    def test_an_unreadable_date_falls_back_to_this_month(self, _hero):
        self.assertOpensOn(self.home([run("not-a-date")]), *self.this_month())
