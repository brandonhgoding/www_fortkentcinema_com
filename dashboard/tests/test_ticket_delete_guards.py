import json
from unittest import mock

from cinema.models import Engagement, Showtime
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from tickets.models import TicketOrder
from tickets.tests.factories import age, make_order, make_showtime

User = get_user_model()
REFUSED = "Has online orders. Cancel it instead."


def toast(resp) -> dict:
    return json.loads(resp["HX-Trigger"])["dashboard-toast"]


class DeleteGuardTestCase(TestCase):
    def setUp(self) -> None:
        User.objects.create_user(username="sam", password="pw12345", is_staff=True)
        self.client.login(username="sam", password="pw12345")
        self.st = make_showtime()


class ShowtimeDeleteGuardTests(DeleteGuardTestCase):
    def delete(self):
        return self.client.post(reverse("dashboard:showtime_delete", args=[self.st.pk]))

    def test_paid_order_refuses_delete(self) -> None:
        make_order(self.st, status="PAID", square_payment_id="P1")
        resp = self.delete()
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(toast(resp), {"kind": "error", "message": REFUSED})
        self.assertTrue(Showtime.objects.filter(pk=self.st.pk).exists())

    def test_refunded_order_refuses_delete(self) -> None:
        make_order(self.st, status="REFUNDED", square_payment_id="P1")
        self.assertEqual(toast(self.delete())["message"], REFUSED)
        self.assertTrue(Showtime.objects.filter(pk=self.st.pk).exists())

    def test_holding_order_refuses_delete(self) -> None:
        make_order(self.st, status="PENDING")
        self.assertEqual(toast(self.delete())["message"], REFUSED)
        self.assertTrue(Showtime.objects.filter(pk=self.st.pk).exists())

    def test_failed_with_payment_refuses_delete(self) -> None:
        make_order(self.st, status="FAILED", square_payment_id="P1")
        self.assertEqual(toast(self.delete())["message"], REFUSED)
        self.assertTrue(Showtime.objects.filter(pk=self.st.pk).exists())

    def test_dead_orders_are_removed_and_showtime_deleted(self) -> None:
        expired = make_order(self.st, status="EXPIRED")
        stale = make_order(self.st, status="PENDING")
        age(stale, 60 * 24)
        failed = make_order(self.st, status="FAILED")
        resp = self.delete()
        self.assertEqual(toast(resp)["kind"], "success")
        self.assertFalse(Showtime.objects.filter(pk=self.st.pk).exists())
        self.assertFalse(
            TicketOrder.objects.filter(pk__in=[expired.pk, stale.pk, failed.pk]).exists()
        )


class EngagementDeleteGuardTests(DeleteGuardTestCase):
    def delete(self):
        url = reverse("dashboard:engagement_delete", args=[self.st.engagement_id])
        return self.client.post(url + "?tab=CURRENT")

    def test_paid_order_refuses_delete_before_square(self) -> None:
        make_order(self.st, status="PAID", square_payment_id="P1")
        with mock.patch("dashboard.views.delete") as square_delete:
            resp = self.delete()
        square_delete.assert_not_called()
        self.assertEqual(toast(resp), {"kind": "error", "message": REFUSED})
        self.assertTrue(Engagement.objects.filter(pk=self.st.engagement_id).exists())

    def test_expired_order_is_removed_and_engagement_deleted(self) -> None:
        order = make_order(self.st, status="EXPIRED")
        with mock.patch("dashboard.views.delete") as square_delete:
            resp = self.delete()
        square_delete.assert_called_once()
        self.assertEqual(toast(resp)["kind"], "success")
        self.assertFalse(Engagement.objects.filter(pk=self.st.engagement_id).exists())
        self.assertFalse(TicketOrder.objects.filter(pk=order.pk).exists())
