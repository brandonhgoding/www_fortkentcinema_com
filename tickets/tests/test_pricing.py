from datetime import datetime, timezone

from django.test import SimpleTestCase

from tickets.pricing import is_matinee, price_table
from web.services.cinema_data import CINEMA_TZ


def eastern(year, month, day, hour=0, minute=0):
    return datetime(year, month, day, hour, minute, tzinfo=CINEMA_TZ)


class PricingTests(SimpleTestCase):
    def test_four_pm_is_a_matinee_four_oh_one_is_not(self):
        self.assertTrue(is_matinee(eastern(2026, 10, 24, 16, 0)))
        self.assertFalse(is_matinee(eastern(2026, 10, 24, 16, 1)))

    def test_evening_prices(self):
        rows = price_table(eastern(2026, 10, 24, 19))
        self.assertEqual([r.unit_cents for r in rows], [800, 700, 600])
        self.assertEqual([r.discount_cents for r in rows], [0, 0, 0])

    def test_matinee_prices_and_discounts(self):
        rows = price_table(eastern(2026, 10, 24, 13))
        self.assertEqual([r.unit_cents for r in rows], [600, 600, 600])
        self.assertEqual([r.discount_cents for r in rows], [200, 100, 0])

    def test_table_order_and_labels(self):
        rows = price_table(eastern(2026, 10, 24, 19))
        self.assertEqual([r.tier for r in rows], ["adult", "senior", "child"])
        self.assertEqual([r.label for r in rows], ["Adult", "Senior", "Child"])

    def test_utc_input_is_judged_in_eastern(self):
        # 20:30 UTC on 24 Oct is 16:30 Eastern: not a matinee.
        self.assertFalse(
            is_matinee(datetime(2026, 10, 24, 20, 30, tzinfo=timezone.utc))
        )
        # 19:30 UTC is 15:30 Eastern.
        self.assertTrue(is_matinee(datetime(2026, 10, 24, 19, 30, tzinfo=timezone.utc)))
