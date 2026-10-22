import csv
import datetime
import io
from unittest import mock
from zoneinfo import ZoneInfo

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from tickets.tests.factories import make_order, make_showtime
from dashboard.tests.helpers import make_staff

User = get_user_model()
TZ = ZoneInfo("America/New_York")


def at(day: datetime.date, hour: int, minute: int = 0) -> datetime.datetime:
    return datetime.datetime.combine(day, datetime.time(hour, minute), tzinfo=TZ)


class StaffTestCase(TestCase):
    def setUp(self) -> None:
        make_staff(username="sam", password="pw12345")
        self.client.login(username="sam", password="pw12345")
        self.today = timezone.localdate()


class SummaryTests(StaffTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.url = reverse("dashboard:tickets")

    def test_summary_totals_and_grouping(self) -> None:
        early = make_showtime(starts_at=at(self.today, 0, 1))
        late = make_showtime(starts_at=at(self.today, 23, 59))
        later = make_showtime(starts_at=at(self.today + datetime.timedelta(days=3), 19))
        make_order(early, status="PAID", lines={"adult": 2})  # $16
        make_order(early, status="FAILED", square_payment_id="P1", lines={"child": 1})
        make_order(early, status="FAILED", lines={"adult": 5})  # never paid
        make_order(early, status="REFUNDED", lines={"adult": 5})
        make_order(early, status="PENDING", lines={"adult": 5})
        make_order(later, status="PAID", lines={"senior": 3})  # $21

        resp = self.client.get(self.url)

        self.assertEqual(resp.status_code, 200)
        totals = resp.context["totals"]
        self.assertEqual(totals["today"]["tickets"], 3)
        self.assertEqual(totals["today"]["gross_dollars"], 22)
        self.assertEqual(totals["week"]["tickets"], 6)
        self.assertEqual(totals["week"]["gross_dollars"], 43)
        days = resp.context["days"]
        self.assertEqual(
            [d["date"] for d in days], [self.today, later.starts_at.date()]
        )
        self.assertEqual(days[0]["label"], "Today")
        rows = {r["st"].pk: r for d in days for r in d["rows"]}
        self.assertEqual([r["st"].pk for r in days[0]["rows"]], [early.pk, late.pk])
        self.assertEqual(
            (rows[early.pk]["sold"], rows[early.pk]["gross_dollars"]), (3, 22)
        )
        self.assertEqual(
            (rows[late.pk]["sold"], rows[late.pk]["gross_dollars"]), (0, 0)
        )
        self.assertEqual(rows[late.pk]["allowance"], 50)
        self.assertContains(resp, reverse("dashboard:showtime_orders", args=[late.pk]))

    def test_summary_past_tab(self) -> None:
        yesterday = make_showtime(
            starts_at=at(self.today - datetime.timedelta(days=1), 19)
        )
        make_order(yesterday, status="PAID", lines={"adult": 1})

        upcoming = self.client.get(self.url)
        past = self.client.get(self.url, {"tab": "past"})

        def pks(resp):
            return [r["st"].pk for d in resp.context["days"] for r in d["rows"]]

        self.assertNotIn(yesterday.pk, pks(upcoming))
        self.assertEqual(pks(past), [yesterday.pk])
        self.assertEqual(past.context["days"][0]["rows"][0]["sold"], 1)
        self.assertEqual(past.context["tab"], "past")

    def test_past_tab_paginates_newest_first(self) -> None:
        first_day = self.today - datetime.timedelta(days=60)
        showtimes = [
            make_showtime(starts_at=at(first_day + datetime.timedelta(days=i), 19))
            for i in range(51)
        ]
        page1 = self.client.get(self.url, {"tab": "past"})
        page2 = self.client.get(self.url, {"tab": "past", "page": 2})

        def pks(resp):
            return [r["st"].pk for d in resp.context["days"] for r in d["rows"]]

        self.assertEqual(len(pks(page1)), 50)
        self.assertEqual(pks(page1)[0], showtimes[-1].pk)
        self.assertEqual(pks(page2), [showtimes[0].pk])
        self.assertContains(page1, "?tab=past&amp;page=2")


class OrderLogTests(StaffTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.url = reverse("dashboard:ticket_orders")
        self.st = make_showtime()

    def test_order_log_filter_and_pagination(self) -> None:
        failed = make_order(
            self.st, status="FAILED", square_payment_id="P1", error="Email bounced"
        )
        paid = make_order(self.st, status="PAID", square_payment_id="P2")

        resp = self.client.get(self.url, {"status": "FAILED"})

        self.assertEqual(list(resp.context["page_obj"]), [failed])
        self.assertContains(resp, "Email bounced")
        self.assertContains(
            resp, reverse("dashboard:ticket_order_retry", args=[failed.pk])
        )
        self.assertNotContains(
            resp, reverse("dashboard:ticket_order_refund", args=[paid.pk])
        )
        self.assertContains(
            resp, reverse("dashboard:showtime_orders", args=[self.st.pk])
        )

        everything = self.client.get(self.url)
        self.assertEqual(list(everything.context["page_obj"]), [paid, failed])
        self.assertContains(
            everything, reverse("dashboard:ticket_order_refund", args=[paid.pk])
        )

        for _ in range(49):
            make_order(self.st, status="PAID")
        page1 = self.client.get(self.url)
        page2 = self.client.get(self.url, {"page": 2})
        self.assertEqual(page1.context["page_obj"].paginator.num_pages, 2)
        self.assertEqual(len(page1.context["page_obj"]), 50)
        self.assertEqual(list(page2.context["page_obj"]), [failed])

    def test_refund_button_needs_the_refund_permission(self) -> None:
        paid = make_order(self.st, status="PAID", square_payment_id="P2")
        failed = make_order(
            self.st, status="FAILED", square_payment_id="P1", error="Email bounced"
        )
        make_staff(
            username="clerk",
            perms=("tickets.view_ticketorder", "tickets.change_ticketorder"),
        )
        self.client.login(username="clerk", password="pw12345")
        resp = self.client.get(self.url)
        self.assertContains(
            resp, reverse("dashboard:ticket_order_retry", args=[failed.pk])
        )
        self.assertNotContains(
            resp, reverse("dashboard:ticket_order_refund", args=[paid.pk])
        )

    def test_never_started_checkouts_are_listed_quietly(self) -> None:
        order = make_order(self.st, status="ABANDONED", error="Square: down")

        resp = self.client.get(self.url, {"status": "ABANDONED"})

        self.assertEqual(list(resp.context["page_obj"]), [order])
        self.assertContains(resp, "Never started")
        self.assertContains(resp, "Square: down")
        # Grey like Expired, not the red "needs attention" badge.
        self.assertContains(resp, "status-badge status-draft")
        self.assertNotContains(resp, "status-badge status-cancelled")
        self.assertNotContains(
            resp, reverse("dashboard:ticket_order_retry", args=[order.pk])
        )

    def test_unknown_status_shows_everything(self) -> None:
        make_order(self.st, status="PAID")
        resp = self.client.get(self.url, {"status": "BOGUS"})
        self.assertEqual(len(resp.context["page_obj"]), 1)

    def test_retry_from_the_log_returns_a_log_row(self) -> None:
        order = make_order(self.st, status="FAILED", square_payment_id="P1")
        with mock.patch("dashboard.ticket_views.resend", side_effect=lambda o: o):
            resp = self.client.post(
                reverse("dashboard:ticket_order_retry", args=[order.pk]),
                {"row": "log"},
                HTTP_HX_REQUEST="true",
            )
        self.assertTemplateUsed(resp, "dashboard/_ticket_log_row.html")
        with mock.patch("dashboard.ticket_views.resend", side_effect=lambda o: o):
            resp = self.client.post(
                reverse("dashboard:ticket_order_retry", args=[order.pk]),
                {"row": "log"},
            )
        self.assertRedirects(resp, self.url, fetch_redirect_response=False)

    def test_order_log_csv_has_film_and_showtime(self) -> None:
        make_order(
            self.st,
            status="PAID",
            number="FKC-1",
            square_payment_id="P1",
            lines={"adult": 2, "child": 1},
        )
        make_order(self.st, status="EXPIRED", number="FKC-2")

        resp = self.client.get(reverse("dashboard:ticket_orders_export"))

        self.assertEqual(resp["Content-Type"], "text/csv")
        self.assertIn("attachment", resp["Content-Disposition"])
        rows = list(csv.reader(io.StringIO(resp.content.decode())))
        self.assertEqual(
            rows[0],
            [
                "film",
                "showtime",
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
        local = self.st.starts_at.astimezone(TZ)
        by_number = {r[2]: r for r in rows[1:]}
        self.assertEqual(
            by_number["FKC-1"][:3], ["Dune", f"{local:%Y-%m-%d %H:%M}", "FKC-1"]
        )
        self.assertEqual(by_number["FKC-1"][3:5], ["Ann", "Lee"])
        self.assertEqual(by_number["FKC-1"][7:11], ["2", "0", "1", "22.00"])
        self.assertEqual(by_number["FKC-2"][11], "Expired")

        filtered = self.client.get(
            reverse("dashboard:ticket_orders_export"), {"status": "PAID"}
        )
        rows = list(csv.reader(io.StringIO(filtered.content.decode())))
        self.assertEqual([r[2] for r in rows[1:]], ["FKC-1"])


class SidebarAndStaffTests(TestCase):
    def test_sidebar_link_and_staff_only(self) -> None:
        urls = [
            reverse("dashboard:tickets"),
            reverse("dashboard:ticket_orders"),
            reverse("dashboard:ticket_orders_export"),
        ]
        for url in urls:
            self.assertEqual(self.client.get(url).status_code, 302, url)
        User.objects.create_user(username="n", password="pw12345")
        self.client.login(username="n", password="pw12345")
        for url in urls:
            self.assertEqual(self.client.get(url).status_code, 403, url)

        make_staff(username="sam", password="pw12345")
        self.client.login(username="sam", password="pw12345")
        for url in urls[:2]:
            resp = self.client.get(url)
            html = resp.content.decode()
            link = (
                f'<a href="{reverse("dashboard:tickets")}" class="sidebarLink active"'
            )
            self.assertIn(link, html, url)
            self.assertIn("Online tickets</a>", html)
        home = self.client.get(reverse("dashboard:home")).content.decode()
        self.assertLess(home.index("Memberships</a>"), home.index("Online tickets</a>"))
        self.assertLess(home.index("Online tickets</a>"), home.index("Polls</a>"))
