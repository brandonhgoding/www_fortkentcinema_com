import datetime

from django.test import SimpleTestCase

from audience.dates import add_months


class AddMonthsTests(SimpleTestCase):
    def test_adds_a_year(self) -> None:
        self.assertEqual(
            add_months(datetime.date(2026, 9, 11), 12),
            datetime.date(2027, 9, 11),
        )

    def test_crosses_the_year_boundary(self) -> None:
        self.assertEqual(
            add_months(datetime.date(2026, 11, 30), 3),
            datetime.date(2027, 2, 28),
        )

    def test_clamps_to_the_last_day_of_a_shorter_month(self) -> None:
        # There is no 31st of February; a membership sold on the 31st still
        # has to land on a real date.
        self.assertEqual(
            add_months(datetime.date(2026, 1, 31), 1),
            datetime.date(2026, 2, 28),
        )

    def test_lands_on_a_leap_day(self) -> None:
        self.assertEqual(
            add_months(datetime.date(2028, 1, 31), 1),
            datetime.date(2028, 2, 29),
        )

    def test_zero_months_is_the_same_date(self) -> None:
        self.assertEqual(
            add_months(datetime.date(2026, 9, 11), 0),
            datetime.date(2026, 9, 11),
        )
