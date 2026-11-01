"""One timezone for the whole site, defined once."""
import datetime

from django.test import SimpleTestCase

from cinema.dates import business_date, format_showtime


class CinemaDatesTests(SimpleTestCase):
    def test_business_date_in_winter_uses_est(self) -> None:
        # 04:30 UTC on 10 January is 23:30 EST on 9 January (UTC-5).
        when = datetime.datetime(2026, 1, 10, 4, 30, tzinfo=datetime.UTC)
        self.assertEqual(business_date(when), datetime.date(2026, 1, 9))

    def test_business_date_in_summer_uses_edt(self) -> None:
        # 03:30 UTC on 10 July is 23:30 EDT on 9 July (UTC-4).
        when = datetime.datetime(2026, 7, 10, 3, 30, tzinfo=datetime.UTC)
        self.assertEqual(business_date(when), datetime.date(2026, 7, 9))

    def test_format_showtime_is_eastern_without_a_leading_zero(self) -> None:
        # 23:00 UTC on 10 January is 6:00 PM EST.
        when = datetime.datetime(2026, 1, 10, 23, 0, tzinfo=datetime.UTC)
        self.assertEqual(format_showtime(when), "6:00 PM")

    def test_format_showtime_reads_midnight_as_twelve(self) -> None:
        # 04:00 UTC on 10 July is 12:00 AM EDT.
        when = datetime.datetime(2026, 7, 10, 4, 0, tzinfo=datetime.UTC)
        self.assertEqual(format_showtime(when), "12:00 AM")
