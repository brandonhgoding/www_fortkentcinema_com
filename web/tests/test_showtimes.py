import datetime
from django.test import SimpleTestCase
from web.services import showtimes


class ShowtimeDateTests(SimpleTestCase):
    def test_today_eastern_is_iso(self):
        self.assertRegex(showtimes.today_eastern(), r"^\d{4}-\d{2}-\d{2}$")

    def test_format_today_label(self):
        today = showtimes.today_eastern()
        self.assertEqual(showtimes.format_showtime_date(today, today=today), "Today")

    def test_format_long_and_short_weekday(self):
        # 2999-12-31 is a Friday; assert shape, not a hardcoded locale name.
        long = showtimes.format_showtime_date("2999-12-31", today="2000-01-01")
        self.assertRegex(long, r"^[A-Za-z]{4,}, Dec 31$")
        short = showtimes.format_showtime_date("2999-12-31", weekday="short", today="2000-01-01")
        self.assertRegex(short, r"^[A-Za-z]{3}, Dec 31$")
        self.assertNotEqual(short, long)

    def test_upcoming_dates_filters_and_sorts(self):
        today = "2999-01-01"
        st = {"2000-01-01": ["6:00 PM"], "2999-12-31": ["9:00 PM"],
              "2999-06-15": ["3:00 PM"], today: ["7:00 PM"]}
        self.assertEqual(
            showtimes.upcoming_dates(st, today=today),
            [today, "2999-06-15", "2999-12-31"],
        )

    def test_upcoming_dates_bad_input(self):
        for bad in (None, "nope", 123, []):
            self.assertEqual(showtimes.upcoming_dates(bad, today="2000-01-01"), [])
