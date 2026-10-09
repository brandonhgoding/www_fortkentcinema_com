import datetime
import json
from decimal import Decimal
from unittest import mock

from audience.models import Member, MembershipTerm, MembershipTier
from boxoffice.models import MembershipSale
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

User = get_user_model()

UTC = datetime.timezone.utc


def make_sale(**over) -> MembershipSale:
    fields = {
        "order_id": "O1",
        "email": "ann@example.com",
        "display_name": "Ann Lee",
        "error": "boom",
        "status": MembershipSale.Status.FAILED,
        "gross_cents": 6000,
    }
    fields.update(over)
    return MembershipSale.objects.create(**fields)


def make_term(first="Ann", last="Lee") -> MembershipTerm:
    member = Member.objects.create(
        first_name=first, last_name=last, email=f"{first.lower()}@example.com")
    today = timezone.localdate()
    return MembershipTerm.objects.create(
        member=member,
        tier=MembershipTier.objects.get(slug="individual"),
        started_on=today,
        expires_on=today + datetime.timedelta(days=365),
        price_paid=Decimal("60.00"),
    )


class StaffTestCase(TestCase):
    def setUp(self) -> None:
        User.objects.create_user(username="s", password="pw12345", is_staff=True)
        self.client.login(username="s", password="pw12345")


class StaffOnlyTests(TestCase):
    def test_list_and_retry_require_staff(self) -> None:
        sale = make_sale()
        list_url = reverse("dashboard:square_sales")
        retry_url = reverse("dashboard:square_sale_retry", args=[sale.pk])
        self.assertEqual(self.client.get(list_url).status_code, 302)
        self.assertEqual(self.client.post(retry_url).status_code, 302)
        User.objects.create_user(username="n", password="pw12345")
        self.client.login(username="n", password="pw12345")
        self.assertEqual(self.client.get(list_url).status_code, 403)
        with mock.patch("dashboard.membership_sale_views.process_order") as po:
            self.assertEqual(self.client.post(retry_url).status_code, 403)
        po.assert_not_called()


class ListTests(StaffTestCase):
    url = reverse("dashboard:square_sales")

    def test_lists_sales_newest_first_with_status_and_member(self) -> None:
        term = make_term()
        make_sale(
            order_id="OK1", status="OK", error="", term=term, display_name="Ann Lee",
            closed_at=datetime.datetime(2026, 10, 2, 16, tzinfo=UTC))
        make_sale(
            order_id="BAD1", display_name="Bob Roe", email="bob@example.com",
            closed_at=datetime.datetime(2026, 10, 3, 16, tzinfo=UTC))
        html = self.client.get(self.url).content.decode()
        self.assertLess(html.index("Bob Roe"), html.index("Ann Lee"))
        self.assertIn("Needs attention", html)
        self.assertIn("Entered", html)
        self.assertIn(reverse("dashboard:member_detail", args=[term.member.pk]), html)
        self.assertIn("boom", html)
        self.assertIn("$60.00", html)
        self.assertIn("Oct 3, 2026", html)

    def test_ok_sale_whose_term_was_deleted_says_so(self) -> None:
        term = make_term()
        make_sale(order_id="OK1", status="OK", error="", term=term)
        term.delete()
        html = self.client.get(self.url).content.decode()
        self.assertIn("term removed", html)

    def test_retry_only_on_failed_rows(self) -> None:
        failed = make_sale(order_id="F")
        ok = make_sale(order_id="K", status="OK", error="")
        skipped = make_sale(order_id="S", status="SKIPPED", error="")
        html = self.client.get(self.url).content.decode()
        self.assertIn(reverse("dashboard:square_sale_retry", args=[failed.pk]), html)
        self.assertNotIn(reverse("dashboard:square_sale_retry", args=[ok.pk]), html)
        self.assertNotIn(
            reverse("dashboard:square_sale_retry", args=[skipped.pk]), html)

    def test_empty_state(self) -> None:
        html = self.client.get(self.url).content.decode()
        self.assertIn("No Square membership sales yet", html)

    def test_subtitle_counts_failed(self) -> None:
        make_sale(order_id="A")
        html = self.client.get(self.url).content.decode()
        self.assertIn("1 needs attention", html)
        make_sale(order_id="B")
        make_sale(order_id="C", status="OK", error="")
        html = self.client.get(self.url).content.decode()
        self.assertIn("2 need attention", html)


class RetryTests(StaffTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.sale = make_sale()
        self.url = reverse("dashboard:square_sale_retry", args=[self.sale.pk])

    def test_retry_runs_process_order_and_swaps_the_row(self) -> None:
        term = make_term()

        def fake(order_id):
            MembershipSale.objects.filter(order_id=order_id).update(
                status="OK", error="", term=term)

        with mock.patch(
            "dashboard.membership_sale_views.process_order", side_effect=fake
        ) as po:
            resp = self.client.post(self.url, HTTP_HX_REQUEST="true")
        po.assert_called_once_with("O1")
        self.assertEqual(resp.status_code, 200)
        html = resp.content.decode()
        self.assertIn(f'id="square-sale-{self.sale.pk}"', html)
        self.assertIn("Entered", html)
        self.assertNotIn("Retry", html)
        toast = json.loads(resp["HX-Trigger"])["dashboard-toast"]
        self.assertEqual(toast["kind"], "success")
        self.assertEqual(toast["message"], "Entered: Ann Lee")

    def test_retry_that_fails_again_toasts_the_error(self) -> None:
        def fake(order_id):
            MembershipSale.objects.filter(order_id=order_id).update(
                error="still boom")

        with mock.patch(
            "dashboard.membership_sale_views.process_order", side_effect=fake
        ):
            resp = self.client.post(self.url, HTTP_HX_REQUEST="true")
        toast = json.loads(resp["HX-Trigger"])["dashboard-toast"]
        self.assertEqual(toast, {"kind": "error", "message": "still boom"})
        html = resp.content.decode()
        self.assertIn("still boom", html)
        self.assertIn("Retry", html)

    def test_non_htmx_post_redirects_to_the_list(self) -> None:
        with mock.patch("dashboard.membership_sale_views.process_order") as po:
            resp = self.client.post(self.url)
        po.assert_called_once_with("O1")
        self.assertRedirects(
            resp, reverse("dashboard:square_sales"), fetch_redirect_response=False)

    def test_unknown_sale_is_404(self) -> None:
        url = reverse("dashboard:square_sale_retry", args=[self.sale.pk + 99])
        with mock.patch("dashboard.membership_sale_views.process_order") as po:
            resp = self.client.post(url, HTTP_HX_REQUEST="true")
        self.assertEqual(resp.status_code, 404)
        po.assert_not_called()
