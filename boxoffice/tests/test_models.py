import datetime

from audience.models import Member, MembershipTerm, MembershipTier
from boxoffice.models import (
    MembershipSale,
    SaleLine,
    SalesPull,
    SquareItem,
    SquareVariation,
)
from cinema.models import Engagement, Screen
from django.db import IntegrityError, transaction
from django.test import TestCase
from django.utils import timezone


def make_eng(**over):
    screen = Screen.objects.get_or_create(name="Screen 1", capacity=50)[0]
    defaults = dict(
        screen=screen,
        start_date=datetime.date(2026, 10, 9),
        end_date=datetime.date(2026, 10, 15),
        status="CONFIRMED",
    )
    defaults.update(over)
    return Engagement.objects.create(**defaults)


def make_item(engagement, square_id="A", **over):
    return SquareItem.objects.create(
        engagement=engagement, square_id=square_id, version=1, name="X", **over
    )


class SquareItemTests(TestCase):
    def test_two_live_items_for_one_engagement_refused(self) -> None:
        eng = make_eng()
        make_item(eng, "A")
        with self.assertRaises(IntegrityError), transaction.atomic():
            make_item(eng, "B")

    def test_deleted_item_does_not_block_a_new_live_one(self) -> None:
        eng = make_eng()
        make_item(eng, "A", deleted_at=timezone.now())
        make_item(eng, "B")
        self.assertEqual(eng.square_items.count(), 2)

    def test_deleting_engagement_keeps_item_row(self) -> None:
        eng = make_eng()
        item = make_item(eng, "A")
        eng.delete()
        item.refresh_from_db()
        self.assertIsNone(item.engagement)


class SquareVariationTests(TestCase):
    def test_one_variation_per_tier(self) -> None:
        item = make_item(make_eng())
        SquareVariation.objects.create(
            item=item, square_id="V1", sku="fkc-eng-1-adult",
            tier="adult", name="Adult", price_cents=800, ordinal=0,
        )
        with self.assertRaises(IntegrityError), transaction.atomic():
            SquareVariation.objects.create(
                item=item, square_id="V2", sku="fkc-eng-1-adult-2",
                tier="adult", name="Adult", price_cents=800, ordinal=1,
            )


class SaleLineTests(TestCase):
    def test_order_line_is_unique(self) -> None:
        kwargs = dict(
            order_id="O1", line_uid="L1", business_date=datetime.date(2026, 10, 9),
            closed_at=timezone.now(), item_name="Dune", quantity=1, gross_cents=800,
        )
        SaleLine.objects.create(**kwargs)
        with self.assertRaises(IntegrityError), transaction.atomic():
            SaleLine.objects.create(**kwargs)


class SalesPullTests(TestCase):
    def test_status_choices(self) -> None:
        self.assertEqual(SalesPull.Status.OK, "OK")
        self.assertEqual(SalesPull.Status.FAILED, "FAILED")


class MembershipSaleTests(TestCase):
    def test_order_id_is_unique(self) -> None:
        MembershipSale.objects.create(
            order_id="O1", status=MembershipSale.Status.FAILED
        )
        with self.assertRaises(IntegrityError):
            MembershipSale.objects.create(
                order_id="O1", status=MembershipSale.Status.FAILED
            )

    def test_deleting_the_term_keeps_the_sale(self) -> None:
        tier = MembershipTier.objects.get(slug="individual")
        member = Member.objects.create(first_name="A", last_name="B", email="a@b.c")
        term = MembershipTerm.objects.create(
            member=member,
            tier=tier,
            started_on=datetime.date(2026, 10, 2),
            expires_on=datetime.date(2027, 10, 1),
            price_paid=60,
        )
        sale = MembershipSale.objects.create(
            order_id="O1", tier=tier, term=term, status=MembershipSale.Status.OK
        )
        term.delete()
        sale.refresh_from_db()
        self.assertIsNone(sale.term)

    def test_purchase_date_is_the_eastern_day(self) -> None:
        sale = MembershipSale(
            order_id="O1",
            closed_at=datetime.datetime(2026, 10, 3, 3, 12, tzinfo=datetime.UTC),
        )
        self.assertEqual(sale.purchase_date, datetime.date(2026, 10, 2))
        self.assertIsNone(MembershipSale(order_id="O2").purchase_date)
