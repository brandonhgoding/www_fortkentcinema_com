import datetime
import html as html_lib
from unittest import mock
from zoneinfo import ZoneInfo

from boxoffice.gateway import GatewayError
from boxoffice.tests.fakes import FakeGateway
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from tickets.forms import BuyForm
from tickets.models import TicketOrder
from tickets.orders import start
from tickets.tests.factories import age, make_live_item, make_order, make_showtime

BUYER = {"name": "Ann Lee", "email": "ann@example.com", "phone": "207-555-0100"}


def matinee_start() -> datetime.datetime:
    day = timezone.localdate() + datetime.timedelta(days=7)
    return datetime.datetime.combine(
        day, datetime.time(14, 0), tzinfo=ZoneInfo("America/New_York")
    )


def text(response) -> str:
    """The response body with entities decoded, so copy reads as written."""
    return html_lib.unescape(response.content.decode())


class ViewTestCase(TestCase):
    def setUp(self):
        self.gw = FakeGateway()
        patcher = mock.patch("tickets.views.get_gateway", return_value=self.gw)
        self.get_gateway = patcher.start()
        self.addCleanup(patcher.stop)
        self.st = make_showtime()  # 19:00 a week out: evening prices
        make_live_item(self.st.engagement)

    def get(self, showtime) -> str:
        response = self.client.get(reverse("tickets:buy", args=[showtime.pk]))
        self.assertEqual(response.status_code, 200)
        return text(response)

    def post(self, showtime, **over):
        data = {"adult": 0, "senior": 0, "child": 0, **BUYER, "website": ""}
        data.update(over)
        return self.client.post(reverse("tickets:buy", args=[showtime.pk]), data)


class BuyFormTests(TestCase):
    def form(self, **over):
        data = {"adult": 1, "senior": 0, "child": 0, **BUYER}
        data.update(over)
        return BuyForm(data)

    def test_quantities(self):
        form = self.form(adult=2, child=1)
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.quantities(), {"adult": 2, "senior": 0, "child": 1})

    def test_phone_rules(self):
        for phone in ["(207) 555-0100", "+1 207.555.0100", "5550100"]:
            self.assertTrue(self.form(phone=phone).is_valid(), phone)
        for phone in ["555-010", "call me maybe", "207-555-0100 x12", "1" * 21]:
            self.assertIn("phone", self.form(phone=phone).errors, phone)

    def test_over_twenty_is_invalid(self):
        self.assertTrue(self.form(adult=20).is_valid())
        for tier in ["adult", "senior", "child"]:
            self.assertIn(tier, self.form(**{tier: 21}).errors, tier)

    def test_honeypot(self):
        self.assertTrue(self.form(website="x").is_bot)
        self.assertFalse(self.form().is_bot)


class BuyPageTests(ViewTestCase):
    def test_unlisted_runs_are_not_found(self):
        hidden = make_showtime()
        make_live_item(hidden.engagement, prefix="h-")
        hidden.engagement.show_in_main_listings = False
        hidden.engagement.save()
        draft = make_showtime()
        make_live_item(draft.engagement, prefix="d-")
        draft.engagement.status = "DRAFT"
        draft.engagement.save()
        for showtime in [hidden, draft]:
            url = reverse("tickets:buy", args=[showtime.pk])
            self.assertEqual(self.client.get(url).status_code, 404)
            self.assertEqual(self.post(showtime, adult=1).status_code, 404)
            self.get_gateway.return_value = None
            self.assertEqual(self.client.get(url).status_code, 404)
            self.get_gateway.return_value = self.gw
        self.assertFalse(TicketOrder.objects.exists())

    def test_buy_page_lists_prices_and_matinee(self):
        matinee_st = make_showtime(starts_at=matinee_start())
        make_live_item(matinee_st.engagement, prefix="m-")
        html = self.get(matinee_st)
        self.assertIn("Dune", html)
        self.assertIn("$6", html)
        self.assertIn("Matinee", html)
        self.assertIn("Members pay $4 at the door", html)
        self.assertIn("2h 35min", html)
        self.assertIn("Continue to payment", html)

    def test_evening_prices_and_no_matinee(self):
        html = self.get(self.st)
        self.assertIn("$8", html)
        self.assertIn("$7", html)
        self.assertNotIn("Matinee", html)
        self.assertNotIn("left online", html)

    def test_few_left_shows_count(self):
        self.st.online_allowance = 3
        self.st.save()
        self.assertIn("3 left online", self.get(self.st))

    def test_captions_note(self):
        self.st.captions = "OC"
        self.st.save()
        self.assertIn("open captions", self.get(self.st))

    def test_closed_sentences(self):
        door = "Online tickets aren't available for this show. Buy at the door."
        not_on_sale = "This showtime isn't on sale."

        self.get_gateway.return_value = None
        self.assertIn(door, self.get(self.st))
        self.get_gateway.return_value = self.gw

        no_item = make_showtime()
        self.assertIn(door, self.get(no_item))

        cancelled = make_showtime(is_cancelled=True)
        make_live_item(cancelled.engagement, prefix="c-")
        self.assertIn(not_on_sale, self.get(cancelled))

        soon = make_showtime(starts_at=timezone.now() + datetime.timedelta(minutes=10))
        make_live_item(soon.engagement, prefix="s-")
        self.assertIn(
            "Online sales for this show have closed. "
            "Tickets are still available at the door.",
            self.get(soon),
        )

        self.st.online_allowance = 0
        self.st.save()
        html = self.get(self.st)
        self.assertIn(
            "Sold out online. Tickets may still be available at the door.", html
        )
        self.assertNotIn("Continue to payment", html)

        response = self.client.get(reverse("tickets:buy", args=[999]))
        self.assertEqual(response.status_code, 404)

    def test_bad_token_404_and_noindex(self):
        response = self.client.get(reverse("tickets:order", args=["nope"]))
        self.assertEqual(response.status_code, 404)
        self.assertIn("noindex", self.get(self.st))


class BuyPostTests(ViewTestCase):
    def test_post_all_zero(self):
        r = self.post(self.st, adult=0, senior=0, child=0)
        self.assertIn("Pick at least one ticket.", text(r))
        self.assertEqual(TicketOrder.objects.count(), 0)

    def test_post_bad_phone_and_email(self):
        r = self.post(self.st, adult=1, phone="nope", email="not-an-email")
        self.assertIn("Enter a valid email address.", text(r))
        self.assertIn("Enter a phone number", text(r))
        self.assertEqual(TicketOrder.objects.count(), 0)

    def test_post_over_remaining_is_refused(self):
        self.st.online_allowance = 1
        self.st.save()
        r = self.post(self.st, adult=2)
        self.assertEqual(r.status_code, 200)
        self.assertIn("Sold out online", text(r))
        self.assertEqual(TicketOrder.objects.count(), 0)

    def test_post_negative_is_invalid(self):
        r = self.post(self.st, adult=-1)
        self.assertIn("greater than or equal to 0", text(r))
        self.assertEqual(TicketOrder.objects.count(), 0)

    def test_honeypot(self):
        r = self.post(self.st, adult=1, website="x")
        self.assertEqual(r.status_code, 303)
        self.assertEqual(r["Location"], reverse("tickets:buy", args=[self.st.pk]))
        self.assertEqual(TicketOrder.objects.count(), 0)

    def test_post_redirects_to_square(self):
        r = self.post(self.st, adult=2, child=1)
        self.assertEqual(r.status_code, 303)
        self.assertTrue(r["Location"].startswith("https://square.link/"))
        order = TicketOrder.objects.get()
        self.assertEqual(order.total_cents, 2200)
        self.assertEqual((order.name, order.phone), ("Ann Lee", "207-555-0100"))

    def test_post_gateway_failure_message(self):
        self.get_gateway.return_value = FakeGateway(fail_with=GatewayError("x"))
        r = self.post(self.st, adult=1)
        self.assertIn(
            "We couldn't start checkout. Please try again, or buy at the door.", text(r)
        )
        self.assertEqual(TicketOrder.objects.get().status, "FAILED")

    def test_post_when_closed_is_refused(self):
        self.get_gateway.return_value = None
        r = self.post(self.st, adult=1)
        self.assertIn(
            "Online tickets aren't available for this show. Buy at the door.", text(r)
        )
        self.assertEqual(TicketOrder.objects.count(), 0)

    def test_post_unknown_showtime_404(self):
        r = self.client.post(reverse("tickets:buy", args=[999]), {"adult": 1})
        self.assertEqual(r.status_code, 404)


class OrderPageTests(ViewTestCase):
    def page(self, order):
        response = self.client.get(reverse("tickets:order", args=[order.token]))
        self.assertEqual(response.status_code, 200)
        return text(response)

    def test_order_states(self):
        paid = make_order(self.st, status="PAID", square_payment_id="P1")
        html = self.page(paid)
        self.assertIn("Payment received", html)
        self.assertIn(paid.number, html)
        self.assertIn(reverse("tickets:order_qr", args=[paid.token]), html)
        self.assertIn("Show this at the door, or just give your name.", html)
        self.assertIn("noindex", html)

        mail_failed = make_order(self.st, status="FAILED", square_payment_id="P2")
        self.assertIn("Payment received", self.page(mail_failed))

        pending = make_order(
            self.st, square_checkout_url="https://square.link/u/9", square_order_id="S9"
        )
        html = self.page(pending)
        self.assertIn("Confirming your payment", html)
        self.assertIn('http-equiv="refresh" content="4"', html)

        age(pending, 3)
        html = self.page(pending)
        self.assertIn("Still waiting. Check your email for the ticket", html)
        self.assertIn("Return to payment", html)
        self.assertIn('href="https://square.link/u/9"', html)
        self.assertNotIn('http-equiv="refresh"', html)

        expired = make_order(self.st, status="EXPIRED")
        html = self.page(expired)
        self.assertIn("This checkout expired before payment.", html)
        self.assertIn(reverse("tickets:buy", args=[self.st.pk]), html)

        refunded = make_order(
            self.st,
            status="REFUNDED",
            refunded_at=datetime.datetime(2026, 10, 20, 15, tzinfo=datetime.UTC),
        )
        self.assertIn("This order was refunded on Tue Oct 20.", self.page(refunded))

        failed = make_order(self.st, status="FAILED", error="x")
        self.assertIn("This checkout did not start.", self.page(failed))

    def test_order_states_are_pure(self):
        from tickets.views import order_state

        now = timezone.now()
        order = TicketOrder(status="PENDING", created_at=now)
        self.assertEqual(order_state(order, now), "pending")
        order.created_at = now - datetime.timedelta(minutes=2, seconds=1)
        self.assertEqual(order_state(order, now), "waiting")
        for status, state in [
            ("PAID", "paid"),
            ("EXPIRED", "expired"),
            ("REFUNDED", "refunded"),
            ("FAILED", "failed"),
        ]:
            self.assertEqual(order_state(TicketOrder(status=status), now), state)
        paid_but_no_email = TicketOrder(status="FAILED", square_payment_id="P1")
        self.assertEqual(order_state(paid_but_no_email, now), "paid")

    def test_order_page_recovers_after_sixty_seconds(self):
        order = start(
            self.st,
            quantities={"adult": 1},
            now=timezone.now(),
            gateway=self.gw,
            **BUYER,
        )
        self.gw.pay(order.square_order_id)
        age(order, 2)
        self.assertIn("Payment received", self.page(order))
        order.refresh_from_db()
        self.assertEqual(order.status, "PAID")

    def test_young_pending_does_not_ask_square(self):
        order = make_order(self.st, square_order_id="S1")
        self.page(order)
        self.get_gateway.assert_not_called()

    def test_qr_png(self):
        paid = make_order(self.st, status="PAID", square_payment_id="P1")
        r = self.client.get(reverse("tickets:order_qr", args=[paid.token]))
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r["Content-Type"], "image/png")
        self.assertEqual(r["Cache-Control"], "private, max-age=86400")
        self.assertTrue(r.content.startswith(b"\x89PNG"))

        mail_failed = make_order(self.st, status="FAILED", square_payment_id="P2")
        r = self.client.get(reverse("tickets:order_qr", args=[mail_failed.token]))
        self.assertEqual(r.status_code, 200)

        for order in [make_order(self.st), make_order(self.st, status="REFUNDED")]:
            r = self.client.get(reverse("tickets:order_qr", args=[order.token]))
            self.assertEqual(r.status_code, 404)
        r = self.client.get(reverse("tickets:order_qr", args=["nope"]))
        self.assertEqual(r.status_code, 404)
