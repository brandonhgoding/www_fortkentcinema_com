import csv
import datetime
import io
import json
from unittest import mock
from zoneinfo import ZoneInfo

from boxoffice.tests.fakes import FakeGateway
from django.contrib.auth import get_user_model
from django.core import mail
from django.test import TestCase
from django.urls import reverse
from tickets.models import TicketOrder
from tickets.tests.factories import make_order, make_showtime
from dashboard.tests.helpers import make_staff

User = get_user_model()
TZ = ZoneInfo("America/New_York")


def toast(resp) -> dict:
    return json.loads(resp["HX-Trigger"])["dashboard-toast"]


class DoorListTestCase(TestCase):
    def setUp(self) -> None:
        self.staff = make_staff(
            username="sam", password="pw12345", first_name="Sam"
        )
        self.client.login(username="sam", password="pw12345")
        self.st = make_showtime()
        self.url = reverse("dashboard:showtime_orders", args=[self.st.pk])

    def paid(self, name="Ann Lee", payment="P1", **over) -> TicketOrder:
        return make_order(
            self.st,
            status="PAID",
            name=name,
            square_payment_id=payment,
            **over,
        )

    def row_names(self, html: str, names) -> list[str]:
        found = [(html.find(n), n) for n in names if html.find(n) != -1]
        return [n for _, n in sorted(found)]


class StaffOnlyTests(TestCase):
    def test_requires_staff_everywhere(self) -> None:
        st = make_showtime()
        order = make_order(st, status="PAID", square_payment_id="P1")
        gets = [
            reverse("dashboard:showtime_orders", args=[st.pk]),
            reverse("dashboard:showtime_orders_export", args=[st.pk]),
        ]
        posts = [
            reverse("dashboard:showtime_allowance", args=[st.pk]),
            reverse("dashboard:showtime_refund_all", args=[st.pk]),
            reverse("dashboard:ticket_order_arrive", args=[order.pk]),
            reverse("dashboard:ticket_order_unarrive", args=[order.pk]),
            reverse("dashboard:ticket_order_retry", args=[order.pk]),
            reverse("dashboard:ticket_order_refund", args=[order.pk]),
        ]
        with mock.patch("dashboard.ticket_views.get_gateway") as gw:
            for url in gets:
                self.assertEqual(self.client.get(url).status_code, 302, url)
            for url in posts:
                self.assertEqual(self.client.post(url).status_code, 302, url)
            User.objects.create_user(username="n", password="pw12345")
            self.client.login(username="n", password="pw12345")
            for url in gets:
                self.assertEqual(self.client.get(url).status_code, 403, url)
            for url in posts:
                self.assertEqual(self.client.post(url).status_code, 403, url)
        gw.assert_not_called()
        order.refresh_from_db()
        self.assertEqual(order.status, "PAID")
        self.assertIsNone(order.redeemed_at)


class DoorListTests(DoorListTestCase):
    def test_rows_sorted_by_name_and_only_valid_statuses(self) -> None:
        self.paid("Zed Moss", lines={"adult": 2, "child": 1})
        self.paid("Ann Lee")
        make_order(self.st, status="PENDING", name="Bob Ray")
        make_order(self.st, status="REFUNDED", name="Cy Vance", square_payment_id="P3")
        make_order(self.st, status="FAILED", name="Di Ross")  # never paid
        make_order(
            self.st,
            status="FAILED",
            name="Ed Fox",
            square_payment_id="P5",
            error="Ticket email failed",
        )
        resp = self.client.get(self.url)
        html = resp.content.decode()
        names = ["Ann Lee", "Cy Vance", "Ed Fox", "Zed Moss", "Bob Ray", "Di Ross"]
        # Door order: by last name, the way people say it at the window.
        self.assertEqual(
            self.row_names(html, names), ["Ed Fox", "Ann Lee", "Zed Moss", "Cy Vance"]
        )
        self.assertIn("2 adult, 1 child", html)
        self.assertIn("$22.00", html)
        self.assertIn("status-active", html)
        self.assertIn("status-draft", html)
        self.assertIn("status-cancelled", html)
        self.assertIn("Resend email", html)
        # Arrive on Ann, Ed and Zed; not on the refunded row.
        self.assertEqual(html.count(">Arrive</button>"), 3)

    def test_header_shows_online_count_and_allowance(self) -> None:
        self.paid(lines={"adult": 3})
        html = self.client.get(self.url).content.decode()
        self.assertIn('id="online-count"', html)
        self.assertIn("3 / 50", html)
        self.assertIn('name="online_allowance"', html)
        self.assertIn("0 means in-person purchase only", html)

    def test_view_only_user_sees_door_list_without_actions(self) -> None:
        order = self.paid(lines={"adult": 3})
        self.st.is_cancelled = True
        self.st.save()
        make_staff(username="viewer", perms=("tickets.view_ticketorder",))
        self.client.login(username="viewer", password="pw12345")
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        html = response.content.decode()
        self.assertIn(order.number, html)
        self.assertIn("3 / 50", html)  # the allowance value still printed
        for name in (
            "ticket_order_arrive",
            "ticket_order_refund",
            "showtime_allowance",
            "showtime_refund_all",
        ):
            with self.subTest(name=name):
                args = [self.st.pk if "showtime" in name else order.pk]
                self.assertNotIn(reverse(f"dashboard:{name}", args=args), html)

    def test_search_filters_by_name_or_number(self) -> None:
        ann = self.paid("Ann Lee")
        zed = self.paid("Zed Moss")
        resp = self.client.get(self.url, {"q": "ann"}, HTTP_HX_REQUEST="true")
        html = resp.content.decode()
        self.assertIn("Ann Lee", html)
        self.assertNotIn("Zed Moss", html)
        self.assertNotIn("<html", html)  # rows partial only
        html = self.client.get(self.url, {"q": "moss"}).content.decode()
        self.assertIn("Zed Moss", html)
        self.assertNotIn("Ann Lee", html)
        html = self.client.get(self.url, {"q": zed.number.lower()}).content.decode()
        self.assertIn("Zed Moss", html)
        self.assertNotIn(ann.number, html)

    def test_arrive_and_undo(self) -> None:
        order = self.paid("Ann Lee")
        arrive = reverse("dashboard:ticket_order_arrive", args=[order.pk])
        at = datetime.datetime(2026, 7, 4, 18, 52, tzinfo=TZ)
        with mock.patch("django.utils.timezone.now", return_value=at):
            resp = self.client.post(arrive, HTTP_HX_REQUEST="true")
        html = resp.content.decode()
        self.assertIn(f'id="ticket-order-{order.pk}"', html)
        self.assertIn("Arrived 6:52 PM · Sam", html)
        self.assertIn(">Undo</button>", html)
        order.refresh_from_db()
        self.assertEqual(order.redeemed_by, self.staff)
        self.assertEqual(order.redeemed_at, at)

        resp = self.client.post(
            reverse("dashboard:ticket_order_unarrive", args=[order.pk]),
            HTTP_HX_REQUEST="true",
        )
        self.assertIn(">Arrive</button>", resp.content.decode())
        order.refresh_from_db()
        self.assertIsNone(order.redeemed_at)
        self.assertIsNone(order.redeemed_by)

    def test_arrived_falls_back_to_username(self) -> None:
        make_staff(username="kim", password="pw12345")
        self.client.login(username="kim", password="pw12345")
        order = self.paid()
        resp = self.client.post(
            reverse("dashboard:ticket_order_arrive", args=[order.pk]),
            HTTP_HX_REQUEST="true",
        )
        self.assertIn("· kim", resp.content.decode())

    def test_refunded_order_cannot_arrive(self) -> None:
        order = make_order(self.st, status="REFUNDED", square_payment_id="P1")
        self.client.post(reverse("dashboard:ticket_order_arrive", args=[order.pk]))
        order.refresh_from_db()
        self.assertIsNone(order.redeemed_at)

    def test_arrive_without_htmx_redirects_to_the_list(self) -> None:
        order = self.paid()
        resp = self.client.post(
            reverse("dashboard:ticket_order_arrive", args=[order.pk])
        )
        self.assertRedirects(resp, self.url, fetch_redirect_response=False)

    def test_allowance_inline_edit(self) -> None:
        url = reverse("dashboard:showtime_allowance", args=[self.st.pk])
        resp = self.client.post(url, {"online_allowance": "7"}, HTTP_HX_REQUEST="true")
        self.assertEqual(resp.status_code, 200)
        self.assertIn('id="online-count"', resp.content.decode())
        self.assertIn("0 / 7", resp.content.decode())
        self.st.refresh_from_db()
        self.assertEqual(self.st.online_allowance, 7)

        self.client.post(url, {"online_allowance": ""}, HTTP_HX_REQUEST="true")
        self.st.refresh_from_db()
        self.assertIsNone(self.st.online_allowance)

        for bad in ("x", "-1"):
            with self.subTest(bad=bad):
                resp = self.client.post(
                    url, {"online_allowance": bad}, HTTP_HX_REQUEST="true"
                )
                self.assertEqual(resp.status_code, 400)
                self.assertIn(
                    "Online allowance must be a whole number.", resp.content.decode()
                )
                self.st.refresh_from_db()
                self.assertIsNone(self.st.online_allowance)

    def test_csv_columns_and_formula_neutralising(self) -> None:
        order = self.paid(
            "=HYPERLINK() Fox",
            lines={"adult": 2, "child": 1},
            email="h@example.com",
            paid_at=datetime.datetime(2026, 7, 1, 12, 30, tzinfo=TZ),
        )
        make_order(self.st, status="PENDING", name="Bob Ray")
        resp = self.client.get(
            reverse("dashboard:showtime_orders_export", args=[self.st.pk])
        )
        self.assertEqual(resp["Content-Type"], "text/csv")
        self.assertIn("attachment;", resp["Content-Disposition"])
        rows = list(csv.reader(io.StringIO(resp.content.decode())))
        self.assertEqual(
            rows[0],
            [
                "number",
                "first name",
                "last name",
                "email",
                "phone",
                "adult",
                "senior",
                "child",
                "total",
                "status",
                "paid at",
                "arrived at",
            ],
        )
        self.assertEqual(len(rows), 2)
        self.assertEqual(
            rows[1],
            [
                order.number,
                "'=HYPERLINK()",
                "Fox",
                "h@example.com",
                "207-555-0100",
                "2",
                "0",
                "1",
                "22.00",
                "Paid",
                "2026-07-01 12:30",
                "",
            ],
        )


class RefundAllTests(DoorListTestCase):
    def cancel(self) -> None:
        self.st.is_cancelled = True
        self.st.save()

    def test_refund_all_banner_only_when_cancelled_with_paid_orders(self) -> None:
        refund_all = reverse("dashboard:showtime_refund_all", args=[self.st.pk])
        self.paid("Ann Lee", lines={"adult": 2})
        html = self.client.get(self.url).content.decode()
        self.assertNotIn(refund_all, html)  # not cancelled

        self.cancel()
        make_order(self.st, status="REFUNDED", square_payment_id="P9")
        self.paid("Zed Moss", payment="P2", lines={"child": 1})
        html = self.client.get(self.url).content.decode()
        self.assertIn("alert alertWarning", html)
        self.assertIn(refund_all, html)
        self.assertIn("data-dashboard-confirm", html)
        self.assertIn("Refund 2 orders totalling $22.00", html)

        TicketOrder.objects.filter(status="PAID").update(status="REFUNDED")
        html = self.client.get(self.url).content.decode()
        self.assertNotIn(refund_all, html)

    def test_refund_all_summary_toast(self) -> None:
        self.cancel()
        ann = self.paid("Ann Lee", payment="P1")
        zed = self.paid("Zed Moss", payment="P2")
        fake = FakeGateway(fail_on={"P2"})
        with mock.patch("dashboard.ticket_views.get_gateway", return_value=fake):
            resp = self.client.post(
                reverse("dashboard:showtime_refund_all", args=[self.st.pk]),
                HTTP_HX_REQUEST="true",
            )
        self.assertEqual(
            toast(resp), {"kind": "warning", "message": "1 refunded, 1 failed"}
        )
        self.assertIn('id="door-list"', resp.content.decode())
        ann.refresh_from_db()
        zed.refresh_from_db()
        self.assertEqual(ann.status, "REFUNDED")
        self.assertEqual(zed.status, "PAID")
        self.assertEqual(zed.error, "boom")

    def test_refund_all_refuses_a_showtime_that_is_not_cancelled(self) -> None:
        self.paid("Ann Lee", payment="P1")
        self.paid("Zed Moss", payment="P2")
        url = reverse("dashboard:showtime_refund_all", args=[self.st.pk])
        refused = "This showtime isn't cancelled; nothing was refunded."
        fake = FakeGateway()
        with mock.patch("dashboard.ticket_views.get_gateway", return_value=fake):
            resp = self.client.post(url, HTTP_HX_REQUEST="true")
            self.assertEqual(toast(resp), {"kind": "error", "message": refused})
            self.assertIn('id="door-list"', resp.content.decode())
            resp = self.client.post(url, follow=True)
            self.assertRedirects(resp, self.url)
            self.assertContains(resp, "nothing was refunded")
        self.assertEqual(fake.calls, [])
        self.assertEqual(
            list(TicketOrder.objects.values_list("status", flat=True)),
            ["PAID", "PAID"],
        )

    def test_refund_all_without_failures_and_without_htmx(self) -> None:
        self.cancel()
        self.paid("Ann Lee")
        with mock.patch(
            "dashboard.ticket_views.get_gateway", return_value=FakeGateway()
        ):
            resp = self.client.post(
                reverse("dashboard:showtime_refund_all", args=[self.st.pk]),
                follow=True,
            )
        self.assertRedirects(resp, self.url)
        self.assertContains(resp, "1 refunded")
        self.assertNotContains(resp, "failed")


class RetryAndRefundTests(DoorListTestCase):
    def test_retry_resends_and_refund_single(self) -> None:
        order = make_order(
            self.st,
            status="FAILED",
            square_payment_id="P1",
            error="smtp down",
            email="ed@example.com",
        )
        resp = self.client.post(
            reverse("dashboard:ticket_order_retry", args=[order.pk]),
            HTTP_HX_REQUEST="true",
        )
        order.refresh_from_db()
        self.assertEqual(order.status, "PAID")
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(toast(resp)["kind"], "success")
        html = resp.content.decode()
        self.assertIn(f'id="ticket-order-{order.pk}"', html)
        self.assertNotIn("Resend email", html)

        fake = FakeGateway()
        with mock.patch("dashboard.ticket_views.get_gateway", return_value=fake):
            resp = self.client.post(
                reverse("dashboard:ticket_order_refund", args=[order.pk]),
                HTTP_HX_REQUEST="true",
            )
        order.refresh_from_db()
        self.assertEqual(order.status, "REFUNDED")
        self.assertEqual(fake.calls[0][1]["reason"], "Refunded by staff")
        self.assertEqual(toast(resp)["kind"], "success")
        html = resp.content.decode()
        self.assertIn("status-draft", html)
        self.assertNotIn(">Arrive</button>", html)

    def test_retry_on_an_order_that_needs_nothing_says_so(self) -> None:
        unpaid = make_order(self.st, status="FAILED", error="Square said no")
        paid = self.paid()
        for order in (unpaid, paid):
            with self.subTest(status=order.status):
                with mock.patch("dashboard.ticket_views.resend") as resend:
                    resp = self.client.post(
                        reverse("dashboard:ticket_order_retry", args=[order.pk]),
                        HTTP_HX_REQUEST="true",
                    )
                resend.assert_not_called()
                self.assertEqual(
                    toast(resp), {"kind": "info", "message": "Nothing to resend"}
                )
                self.assertIn(f'id="ticket-order-{order.pk}"', resp.content.decode())
        self.assertEqual(len(mail.outbox), 0)

    def test_refund_on_an_already_refunded_order_says_so(self) -> None:
        order = make_order(self.st, status="REFUNDED", square_payment_id="P1")
        fake = FakeGateway()
        with mock.patch("dashboard.ticket_views.get_gateway", return_value=fake):
            resp = self.client.post(
                reverse("dashboard:ticket_order_refund", args=[order.pk]),
                HTTP_HX_REQUEST="true",
            )
        self.assertEqual(toast(resp), {"kind": "info", "message": "Already refunded"})
        self.assertIn(f'id="ticket-order-{order.pk}"', resp.content.decode())
        self.assertEqual(fake.calls, [])

    def test_failed_refund_keeps_the_row_and_toasts_the_error(self) -> None:
        order = self.paid(payment="P1")
        fake = FakeGateway(fail_on={"P1"})
        with mock.patch("dashboard.ticket_views.get_gateway", return_value=fake):
            resp = self.client.post(
                reverse("dashboard:ticket_order_refund", args=[order.pk]),
                HTTP_HX_REQUEST="true",
            )
        self.assertEqual(toast(resp), {"kind": "error", "message": "boom"})
        order.refresh_from_db()
        self.assertEqual(order.status, "PAID")
