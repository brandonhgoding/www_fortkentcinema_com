import base64
import datetime
import hashlib
import hmac
import json
from unittest import mock

from audience.models import Member, MembershipTier
from boxoffice.gateway import OrderData, OrderLine, Recipient
from boxoffice.models import MembershipSale
from boxoffice.tests.fakes import FakeGateway
from django.http import HttpResponse
from django.test import TestCase, override_settings
from django.urls import reverse
from tickets.tests.factories import make_order, make_showtime

KEY = "test-signature-key"
URL = "https://www.fortkentcinema.com/boxoffice/square/webhook/"
INDIVIDUAL = "LUXWXSDRQGNENE7XDBXPNYXY"
# The first tender's time: 23:12 Eastern on 2 October.
PAID_AT = datetime.datetime(2026, 10, 3, 3, 12, tzinfo=datetime.timezone.utc)


def sign(body: str, url: str = URL) -> str:
    digest = hmac.new(KEY.encode(), (url + body).encode(), hashlib.sha256).digest()
    return base64.b64encode(digest).decode()


def post(client, payload: dict, *, signature: str | None = "valid") -> HttpResponse:
    body = json.dumps(payload)
    return post_raw(client, body, signature=signature)


def post_raw(client, body: str, *, signature: str | None = "valid") -> HttpResponse:
    extra = {}
    if signature is not None:
        extra["HTTP_X_SQUARE_HMACSHA256_SIGNATURE"] = (
            sign(body) if signature == "valid" else signature)
    return client.post(reverse("boxoffice:square_webhook"), data=body,
                       content_type="application/json", **extra)


def event(order_id="O1", status="COMPLETED", type="payment.updated",
          amount: int | None = None) -> dict:
    payment = {"id": "P1", "order_id": order_id, "status": status,
               "created_at": "2026-10-03T03:12:00.000Z"}
    if order_id is None:
        del payment["order_id"]
    if amount is not None:
        payment["amount_money"] = {"amount": amount, "currency": "USD"}
    return {
        "type": type,
        "event_id": "E1",
        "data": {"type": "payment", "id": "P1", "object": {"payment": payment}},
    }


class WebhookTestCase(TestCase):
    def setUp(self):
        self.logger = self.enterContext(patch_logger())
        self.process = self.enterContext(
            mock.patch("boxoffice.views.process_order"))


def patch_logger():
    return mock.patch("boxoffice.decorators.logger")


@override_settings(SQUARE_WEBHOOK_SIGNATURE_KEY=KEY, SQUARE_WEBHOOK_URL=URL)
class SignatureTests(WebhookTestCase):
    def assertRejected(self, resp):
        self.assertEqual(resp.status_code, 403)
        self.process.assert_not_called()

    def test_missing_signature_is_403_with_no_side_effects(self):
        self.assertRejected(post(self.client, event(), signature=None))

    def test_forged_signature_is_403(self):
        self.assertRejected(post(self.client, event(), signature="forged"))
        self.logger.warning.assert_called_once()
        self.logger.error.assert_not_called()

    def test_non_utf8_body_is_403(self):
        resp = self.client.post(
            reverse("boxoffice:square_webhook"),
            data=b'\xff{"type": "order.updated"}',
            content_type="application/json",
            HTTP_X_SQUARE_HMACSHA256_SIGNATURE="anything")
        self.assertRejected(resp)
        self.logger.warning.assert_called_once()

    def test_tampered_body_is_403(self):
        signed = sign(json.dumps(event("O1")))
        self.assertRejected(post(self.client, event("O2"), signature=signed))

    @override_settings(SQUARE_WEBHOOK_SIGNATURE_KEY="")
    def test_blank_key_is_403(self):
        self.assertRejected(post(self.client, event()))
        self.logger.error.assert_called_once()
        self.logger.warning.assert_not_called()

    @override_settings(SQUARE_WEBHOOK_URL="")
    def test_blank_url_is_403(self):
        self.assertRejected(post(self.client, event()))
        self.logger.error.assert_called_once()
        self.logger.warning.assert_not_called()

    def test_get_is_405(self):
        resp = self.client.get(reverse("boxoffice:square_webhook"))
        self.assertEqual(resp.status_code, 405)
        self.process.assert_not_called()

    def test_signature_is_over_the_registered_url_not_the_request_host(self):
        body = json.dumps(event())
        host_sig = sign(body, "http://testserver/boxoffice/square/webhook/")
        self.assertRejected(post_raw(self.client, body, signature=host_sig))
        self.assertEqual(post_raw(self.client, body).status_code, 200)


@override_settings(SQUARE_WEBHOOK_SIGNATURE_KEY=KEY, SQUARE_WEBHOOK_URL=URL)
class DispatchTests(WebhookTestCase):
    def assertIgnored(self, resp):
        self.assertEqual(resp.status_code, 200)
        self.process.assert_not_called()

    def test_completed_payment_updated_is_processed(self):
        resp = post(self.client, event("O9"))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.content, b"")
        self.process.assert_called_once_with("O9")

    def test_completed_payment_created_is_processed(self):
        resp = post(self.client, event("O9", type="payment.created"))
        self.assertEqual(resp.status_code, 200)
        self.process.assert_called_once_with("O9")

    def test_completed_payment_reaches_tickets(self):
        # The tickets app registers its handler at startup; boxoffice does
        # not import it.
        with mock.patch("tickets.orders.confirm_payment") as cp:
            post(self.client, event(order_id="SQ1"))
        cp.assert_called_once()
        self.assertEqual(cp.call_args.args[:2], ("SQ1", "P1"))
        self.assertEqual(cp.call_args.kwargs,
                         {"paid_at": PAID_AT, "amount_cents": None})

    def test_payment_amount_reaches_tickets(self):
        with mock.patch("tickets.orders.confirm_payment") as cp:
            post(self.client, event(order_id="SQ1", amount=1600))
        self.assertEqual(cp.call_args.kwargs["amount_cents"], 1600)

    def test_payment_for_less_than_the_order_total_is_not_confirmed(self):
        st = make_showtime()
        order = make_order(st, square_order_id="SQ1")
        with self.assertLogs("tickets.orders", "ERROR"):
            resp = post(self.client, event(order_id="SQ1", amount=100))
        self.assertEqual(resp.status_code, 200)
        order.refresh_from_db()
        self.assertEqual(order.status, "PENDING")
        self.assertIn("100", order.error)
        self.process.assert_not_called()

    def test_ticket_order_skips_the_membership_handler(self):
        st = make_showtime()
        make_order(st, square_order_id="SQ1")
        with mock.patch("tickets.orders.confirm_payment", return_value=object()) as cp:
            resp = post(self.client, event(order_id="SQ1"))
        self.assertEqual(resp.status_code, 200)
        self.process.assert_not_called()
        cp.assert_called_once()
        self.assertEqual(cp.call_args.args[:2], ("SQ1", "P1"))

    def test_handler_crash_still_records_the_membership_and_asks_for_retry(self):
        def crash(order_id, payment_id, paid_at, amount_cents):
            raise RuntimeError("tickets down")

        with mock.patch("boxoffice.payment_events._handlers", [crash]), \
                self.assertLogs("boxoffice.payment_events", "ERROR"), \
                self.assertLogs("django.request", "ERROR"):
            resp = post(self.client, event("O9"))
        self.assertEqual(resp.status_code, 503)
        self.process.assert_called_once_with("O9")

    def test_membership_crash_asks_for_retry_instead_of_a_500(self):
        self.process.side_effect = RuntimeError("db down")
        with self.assertLogs("boxoffice.views", "ERROR"), \
                self.assertLogs("django.request", "ERROR"):
            resp = post(self.client, event("O9"))
        self.assertEqual(resp.status_code, 503)

    def test_approved_payment_is_ignored(self):
        self.assertIgnored(post(self.client, event(status="APPROVED")))

    def test_order_updated_is_ignored(self):
        payload = {"type": "order.updated", "event_id": "E1", "data": {
            "type": "order_updated", "id": "O1", "object": {"order_updated": {
                "order_id": "O1", "state": "COMPLETED"}}}}
        self.assertIgnored(post(self.client, payload))

    def test_other_event_types_are_ignored(self):
        self.assertIgnored(post(self.client, event(type="customer.created")))

    def test_payment_without_order_id_is_ignored(self):
        self.assertIgnored(post(self.client, event(order_id=None)))

    def test_malformed_json_is_400(self):
        self.assertEqual(post_raw(self.client, "{not json").status_code, 400)
        self.process.assert_not_called()

    def test_non_object_json_is_400(self):
        self.assertEqual(post_raw(self.client, "[1, 2]").status_code, 400)
        self.process.assert_not_called()

    def test_payload_without_payment_is_400(self):
        resp = post(self.client, {"type": "payment.updated", "data": {"object": {}}})
        self.assertEqual(resp.status_code, 400)
        self.process.assert_not_called()

    def test_payment_without_status_is_400(self):
        payload = event()
        del payload["data"]["object"]["payment"]["status"]
        self.assertEqual(post(self.client, payload).status_code, 400)
        self.process.assert_not_called()

    def test_payment_that_is_not_an_object_is_400(self):
        payload = event()
        payload["data"]["object"]["payment"] = ["P1"]
        self.assertEqual(post(self.client, payload).status_code, 400)
        self.process.assert_not_called()

    def test_non_membership_order_returns_200(self):
        self.process.return_value = None
        self.assertEqual(post(self.client, event("O9")).status_code, 200)

    def test_failed_outcome_still_returns_200(self):
        self.process.return_value = MembershipSale(
            order_id="O9", status="FAILED", error="boom", paid_at=PAID_AT)
        self.assertEqual(post(self.client, event("O9")).status_code, 200)

    def test_fetch_failure_returns_503_so_square_retries(self):
        self.process.return_value = MembershipSale(
            order_id="O9", status="FAILED", paid_at=None,
            error="Could not fetch the order from Square: boom")
        # A 503 is logged as an ERROR; capture it so the test output stays quiet.
        with self.assertLogs("django.request", "ERROR"):
            resp = post(self.client, event("O9"))
        self.assertEqual(resp.status_code, 503)

    def test_attribution_failure_still_returns_200(self):
        self.process.return_value = MembershipSale(
            order_id="O9", status="FAILED", paid_at=PAID_AT,
            error="Ordered 2 memberships; enter by hand")
        self.assertEqual(post(self.client, event("O9")).status_code, 200)

    def test_order_without_payment_time_returns_200(self):
        # Fetched (tier written) but unattributable: a retry cannot fix it.
        self.process.return_value = MembershipSale(
            order_id="O9", status="FAILED", paid_at=None, tier_id=1,
            error="Order has no payment time")
        self.assertEqual(post(self.client, event("O9")).status_code, 200)


@override_settings(SQUARE_WEBHOOK_SIGNATURE_KEY=KEY, SQUARE_WEBHOOK_URL=URL)
class EndToEndTests(TestCase):
    def setUp(self):
        self.enterContext(patch_logger())
        MembershipTier.objects.filter(slug="individual").update(
            square_variation_id=INDIVIDUAL)

    def test_signed_event_pays_a_ticket_order_once(self):
        # No mocks between Square's bytes and the buyer's inbox; the replay
        # Square sends after a slow 200 must not email a second ticket.
        from django.core import mail
        order = make_order(make_showtime(), square_order_id="O1")
        first = post(self.client, event("O1"))
        replay = post(self.client, event("O1"))
        self.assertEqual((first.status_code, replay.status_code), (200, 200))
        order.refresh_from_db()
        self.assertEqual((order.status, order.square_payment_id, order.paid_at),
                         ("PAID", "P1", PAID_AT))
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn(order.number, mail.outbox[0].body)
        self.assertFalse(MembershipSale.objects.exists())

    def test_signed_event_creates_the_member(self):
        gw = FakeGateway()
        gw.orders.append(OrderData(
            order_id="O1", closed_at=None, paid_at=PAID_AT,
            lines=(OrderLine(uid="L1", name="Individual Membership",
                             variation_name="Annual",
                             catalog_object_id=INDIVIDUAL, quantity=1,
                             gross_cents=6000),),
            recipient=Recipient("Ann Lee", "ann@example.com", "+12075550100")))
        with mock.patch("boxoffice.memberships.get_gateway", return_value=gw):
            resp = post(self.client, event("O1"))
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(Member.objects.filter(email="ann@example.com").exists())
        sale = MembershipSale.objects.get(order_id="O1")
        self.assertEqual((sale.status, sale.paid_at), ("OK", PAID_AT))
        self.assertEqual(sale.term.started_on, datetime.date(2026, 10, 2))


REFUNDED_AT = datetime.datetime(2026, 10, 4, 15, 0, tzinfo=datetime.timezone.utc)


def refund_event(payment_id="P1", status="COMPLETED", type="refund.updated",
                 amount: int | None = 1600) -> dict:
    refund = {"id": "R1", "payment_id": payment_id, "order_id": "O1",
              "status": status, "created_at": "2026-10-04T14:59:00.000Z",
              "updated_at": "2026-10-04T15:00:00.000Z"}
    if payment_id is None:
        del refund["payment_id"]
    if amount is not None:
        refund["amount_money"] = {"amount": amount, "currency": "USD"}
    return {
        "type": type,
        "event_id": "E2",
        "data": {"type": "refund", "id": "R1", "object": {"refund": refund}},
    }


def dispute_event(payment_id="P1", state="EVIDENCE_REQUIRED",
                  type="dispute.created", reason="FRAUD") -> dict:
    dispute = {"id": "D1", "state": state, "reason": reason,
               "amount_money": {"amount": 1600, "currency": "USD"},
               "disputed_payment": {"payment_id": payment_id}}
    if payment_id is None:
        del dispute["disputed_payment"]
    return {
        "type": type,
        "event_id": "E3",
        "data": {"type": "dispute", "id": "D1", "object": {"dispute": dispute}},
    }


@override_settings(SQUARE_WEBHOOK_SIGNATURE_KEY=KEY, SQUARE_WEBHOOK_URL=URL)
class ReversalTests(WebhookTestCase):
    """A refund or chargeback made outside the site must still reach the apps
    that issued the ticket, or the buyer keeps a ticket nobody paid for."""

    def setUp(self):
        super().setUp()
        self.refunds = mock.MagicMock(return_value=True)
        self.disputes = mock.MagicMock(return_value=True)
        self.enterContext(mock.patch("boxoffice.payment_events._refund_handlers",
                                     [self.refunds]))
        self.enterContext(mock.patch("boxoffice.payment_events._dispute_handlers",
                                     [self.disputes]))

    def test_completed_refund_reaches_handlers(self):
        resp = post(self.client, refund_event())
        self.assertEqual(resp.status_code, 200)
        self.refunds.assert_called_once_with("P1", "R1", REFUNDED_AT, 1600)
        self.process.assert_not_called()

    def test_refund_created_already_completed_is_processed_too(self):
        post(self.client, refund_event(type="refund.created"))
        self.refunds.assert_called_once()

    def test_pending_refund_is_ignored(self):
        resp = post(self.client, refund_event(status="PENDING"))
        self.assertEqual(resp.status_code, 200)
        self.refunds.assert_not_called()

    def test_refund_without_amount_passes_none(self):
        post(self.client, refund_event(amount=None))
        self.assertEqual(self.refunds.call_args.args[3], None)

    def test_refund_without_payment_id_is_400(self):
        resp = post(self.client, refund_event(payment_id=None))
        self.assertEqual(resp.status_code, 400)
        self.refunds.assert_not_called()

    def test_refund_handler_crash_asks_for_retry(self):
        self.refunds.side_effect = RuntimeError("tickets down")
        with self.assertLogs("boxoffice.payment_events", "ERROR"), \
                self.assertLogs("django.request", "ERROR"):
            resp = post(self.client, refund_event())
        self.assertEqual(resp.status_code, 503)

    def test_unclaimed_refund_is_200(self):
        self.refunds.return_value = False
        self.assertEqual(post(self.client, refund_event()).status_code, 200)

    def test_dispute_created_reaches_handlers(self):
        resp = post(self.client, dispute_event())
        self.assertEqual(resp.status_code, 200)
        self.disputes.assert_called_once_with("P1", "D1", "EVIDENCE_REQUIRED",
                                              "FRAUD")

    def test_dispute_state_change_reaches_handlers(self):
        post(self.client, dispute_event(type="dispute.state.updated", state="LOST"))
        self.disputes.assert_called_once_with("P1", "D1", "LOST", "FRAUD")

    def test_dispute_without_payment_is_400(self):
        resp = post(self.client, dispute_event(payment_id=None))
        self.assertEqual(resp.status_code, 400)
        self.disputes.assert_not_called()


@override_settings(SQUARE_WEBHOOK_SIGNATURE_KEY=KEY, SQUARE_WEBHOOK_URL=URL)
class ReversalEndToEndTests(TestCase):
    def setUp(self):
        self.enterContext(patch_logger())

    def test_signed_refund_event_voids_the_ticket_once(self):
        from django.core import mail
        order = make_order(make_showtime(), status="PAID", square_order_id="O1",
                           square_payment_id="P1", lines={"adult": 2})
        first = post(self.client, refund_event(amount=1600))
        replay = post(self.client, refund_event(amount=1600))
        self.assertEqual((first.status_code, replay.status_code), (200, 200))
        order.refresh_from_db()
        self.assertEqual((order.status, order.refunded_at), ("REFUNDED", REFUNDED_AT))
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].subject[:9], "Refunded:")
