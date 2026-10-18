import datetime
from datetime import timedelta
from zoneinfo import ZoneInfo

from boxoffice.models import SquareItem
from django.test import TestCase
from django.utils import timezone

from tickets.availability import (
    Availability,
    check,
    for_showtimes,
    remaining,
    sold,
    variation_ids,
)
from tickets.tests.factories import age, make_live_item, make_order, make_showtime


class AvailabilityTests(TestCase):
    def setUp(self):
        self.st = make_showtime()
        # Real time: orders get a real created_at, and the show is a week out.
        self.now = timezone.now()

    def test_sold_counts_paid_and_young_pending_only(self):
        make_order(self.st, status="PAID", lines={"adult": 2})
        make_order(self.st, status="PENDING", lines={"child": 1})  # young
        old = make_order(self.st, status="PENDING", lines={"senior": 5})
        age(old, minutes=21)
        make_order(self.st, status="EXPIRED", lines={"adult": 5})
        make_order(self.st, status="REFUNDED", lines={"adult": 5})
        make_order(self.st, status="FAILED", lines={"adult": 5})
        make_order(self.st, status="FAILED", lines={"adult": 1}, square_payment_id="P9")
        self.assertEqual(sold(self.st, self.now), 4)

    def test_sold_is_zero_with_no_orders(self):
        self.assertEqual(sold(self.st, self.now), 0)

    def test_sold_ignores_other_showtimes(self):
        other = make_showtime(starts_at=self.st.starts_at + timedelta(hours=3))
        make_order(other, status="PAID", lines={"adult": 2})
        self.assertEqual(sold(self.st, self.now), 0)

    def test_remaining_never_negative(self):
        self.st.online_allowance = 1
        self.st.save()
        make_order(self.st, status="PAID", lines={"adult": 3})
        self.assertEqual(remaining(self.st, self.now), 0)

    def test_remaining_is_allowance_less_sold(self):
        make_order(self.st, status="PAID", lines={"adult": 2, "child": 1})
        self.assertEqual(remaining(self.st, self.now), 47)  # half of 100, less 3

    def test_reason_order(self):
        st, now = self.st, self.now
        # disabled beats everything
        st.is_cancelled = True
        self.assertEqual(check(st, now, square_enabled=False).reason, "disabled")
        st.is_cancelled = False
        # draft run, hidden run
        st.engagement.status = "DRAFT"
        self.assertEqual(check(st, now, square_enabled=True).reason, "not_listed")
        st.engagement.status = "CONFIRMED"
        st.engagement.show_in_main_listings = False
        self.assertEqual(check(st, now, square_enabled=True).reason, "not_listed")
        st.engagement.show_in_main_listings = True
        # cancelled showtime
        st.is_cancelled = True
        self.assertEqual(check(st, now, square_enabled=True).reason, "cancelled")
        st.is_cancelled = False
        # 29 minutes before start is closed, 31 is open
        self.assertEqual(
            check(st, st.starts_at - timedelta(minutes=29), square_enabled=True).reason,
            "cutoff",
        )
        self.assertEqual(
            check(st, st.starts_at - timedelta(minutes=30), square_enabled=True).reason,
            "cutoff",
        )
        self.assertEqual(
            check(st, st.starts_at - timedelta(minutes=31), square_enabled=True).reason,
            "no_item",
        )
        # with a live item but a full allowance
        make_live_item(st.engagement)
        st.online_allowance = 0
        st.save()
        self.assertEqual(check(st, now, square_enabled=True).reason, "sold_out")
        st.online_allowance = None
        st.save()
        result = check(st, now, square_enabled=True)
        self.assertEqual(
            result,
            Availability(
                purchasable=True, reason="", sold=0, remaining=50, allowance=50
            ),
        )

    def test_item_without_square_id_is_no_item(self):
        SquareItem.objects.create(
            engagement=self.st.engagement, square_id=None, name="Dune"
        )
        self.assertEqual(
            check(self.st, self.now, square_enabled=True).reason, "no_item"
        )
        result = for_showtimes([self.st], self.now, square_enabled=True)
        self.assertEqual(result[self.st.pk].reason, "no_item")

    def test_deleted_item_is_no_item(self):
        item = make_live_item(self.st.engagement)
        item.deleted_at = self.now
        item.save()
        self.assertEqual(
            check(self.st, self.now, square_enabled=True).reason, "no_item"
        )

    def test_blocked_showtime_still_reports_counts(self):
        make_order(self.st, status="PAID", lines={"adult": 2})
        result = check(self.st, self.now, square_enabled=False)
        self.assertFalse(result.purchasable)
        self.assertEqual((result.sold, result.remaining, result.allowance), (2, 48, 50))

    def test_cutoff_across_dst_change(self):
        # 1 Nov 2026 1:30 AM EDT (05:30 UTC), the night clocks fall back.
        eastern = ZoneInfo("America/New_York")
        starts_at = datetime.datetime(2026, 11, 1, 1, 30, tzinfo=eastern, fold=0)
        st = make_showtime(starts_at=starts_at)
        make_live_item(st.engagement)
        inside = datetime.datetime(2026, 11, 1, 1, 5, tzinfo=eastern, fold=0)
        outside = datetime.datetime(2026, 11, 1, 0, 55, tzinfo=eastern)
        st.refresh_from_db()
        self.assertEqual(check(st, inside, square_enabled=True).reason, "cutoff")
        self.assertEqual(check(st, outside, square_enabled=True).reason, "")

    def test_for_showtimes_matches_check_and_uses_few_queries(self):
        other = make_showtime(starts_at=self.st.starts_at + timedelta(hours=3))
        make_live_item(self.st.engagement)
        make_order(self.st, status="PAID", lines={"adult": 2})
        make_order(other, status="PAID", lines={"child": 1})
        # Showtimes already loaded: 1 grouped sold count, 2 live items.
        with self.assertNumQueries(2):
            result = for_showtimes([self.st, other], self.now, square_enabled=True)
        self.assertEqual(
            result,
            {
                self.st.pk: check(self.st, self.now, square_enabled=True),
                other.pk: check(other, self.now, square_enabled=True),
            },
        )
        self.assertTrue(result[self.st.pk].purchasable)
        self.assertEqual(result[other.pk].reason, "no_item")
        self.assertEqual(result[other.pk].sold, 1)

    def test_for_showtimes_empty(self):
        with self.assertNumQueries(0):
            self.assertEqual(for_showtimes([], self.now, square_enabled=True), {})

    def test_variation_ids(self):
        make_live_item(self.st.engagement)
        self.assertEqual(
            variation_ids(self.st.engagement),
            {"adult": "var-adult", "senior": "var-senior", "child": "var-child"},
        )

    def test_variation_ids_without_item(self):
        self.assertEqual(variation_ids(self.st.engagement), {})
