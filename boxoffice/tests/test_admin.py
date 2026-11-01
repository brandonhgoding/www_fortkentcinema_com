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
            email="admin@example.com",
            password="pw",
            is_staff=True,
            is_superuser=True,
        )
        self.client.force_login(user)
        eng = make_eng()
        self.item = SquareItem.objects.create(engagement=eng, name="Dune",
                                              square_id="item-1")
        self.variation = SquareVariation.objects.create(
            item=self.item, square_id="var-1", sku="fkc-eng-1-adult", tier="adult",
            name="Adult", price_cents=800, ordinal=0)
        day = timezone.localdate()
        self.line = SaleLine.objects.create(
            order_id="O1", line_uid="L1", business_date=day,
            closed_at=timezone.now(), item_name="Dune", variation_name="Adult",
            quantity=2, gross_cents=1600, variation=self.variation, engagement=eng)

    def test_changelists_load(self) -> None:
        for name, needle in (("saleline", "Dune"), ("squareitem", "item-1"),
                             ("squarevariation", "fkc-eng-1-adult")):
            with self.subTest(model=name):
                response = self.client.get(
                    reverse(f"admin:boxoffice_{name}_changelist"))
                self.assertEqual(response.status_code, 200)
                self.assertContains(response, needle)

    def test_rows_are_read_only(self) -> None:
        for name in ("saleline", "squareitem", "squarevariation"):
            with self.subTest(model=name):
                response = self.client.get(reverse(f"admin:boxoffice_{name}_add"))
                self.assertEqual(response.status_code, 403)

    def test_rows_cannot_be_changed(self) -> None:
        line_url = reverse("admin:boxoffice_saleline_change", args=[self.line.pk])
        self.assertEqual(self.client.post(line_url, {"quantity": "9"}).status_code, 403)
        self.line.refresh_from_db()
        self.assertEqual(self.line.quantity, 2)

    def test_rows_cannot_be_deleted(self) -> None:
        # A deleted SquareItem link row would orphan its item in Square.
        for name, obj in (("saleline", self.line), ("squareitem", self.item),
                          ("squarevariation", self.variation)):
            with self.subTest(model=name):
                url = reverse(f"admin:boxoffice_{name}_delete", args=[obj.pk])
                self.assertEqual(self.client.post(url, {"post": "yes"}).status_code,
                                 403)
                self.assertTrue(type(obj).objects.filter(pk=obj.pk).exists())

    def test_bulk_delete_action_is_refused(self) -> None:
        for name, obj in (("saleline", self.line), ("squareitem", self.item),
                          ("squarevariation", self.variation)):
            with self.subTest(model=name):
                self.client.post(
                    reverse(f"admin:boxoffice_{name}_changelist"),
                    {"action": "delete_selected", "_selected_action": [obj.pk],
                     "post": "yes"})
                self.assertTrue(type(obj).objects.filter(pk=obj.pk).exists())
