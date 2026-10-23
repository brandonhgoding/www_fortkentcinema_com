"""The ledger and the catalog link rows are visible in the admin, read-only."""

from accounts.tests.factories import make_user
from boxoffice.models import SaleLine, SquareItem, SquareVariation
from boxoffice.tests.test_pull import make_eng
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone


class LedgerAdminTests(TestCase):
    def setUp(self) -> None:
        user = make_user(
            email="admin@example.com", password="pw", is_staff=True, is_superuser=True
        )
        self.client.force_login(user)
        eng = make_eng()
        self.item = SquareItem.objects.create(
            engagement=eng, name="Dune", square_id="item-1"
        )
        self.variation = SquareVariation.objects.create(
            item=self.item,
            square_id="var-1",
            sku="fkc-eng-1-adult",
            tier="adult",
            name="Adult",
            price_cents=800,
            ordinal=0,
        )
        day = timezone.localdate()
        self.line = SaleLine.objects.create(
            order_id="O1",
            line_uid="L1",
            business_date=day,
            show_date=day,
            closed_at=timezone.now(),
            item_name="Dune",
            variation_name="Adult",
            quantity=2,
            gross_cents=1600,
            variation=self.variation,
            engagement=eng,
        )

    def test_changelists_load(self) -> None:
        for name, needle in (
            ("saleline", "Dune"),
            ("squareitem", "item-1"),
            ("squarevariation", "fkc-eng-1-adult"),
        ):
            with self.subTest(model=name):
                response = self.client.get(
                    reverse(f"admin:boxoffice_{name}_changelist")
                )
                self.assertEqual(response.status_code, 200)
                self.assertContains(response, needle)

    def test_rows_are_read_only(self) -> None:
        for name in ("saleline", "squareitem", "squarevariation"):
            with self.subTest(model=name):
                response = self.client.get(reverse(f"admin:boxoffice_{name}_add"))
                self.assertEqual(response.status_code, 403)
