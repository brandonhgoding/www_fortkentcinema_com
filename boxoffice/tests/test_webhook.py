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

KEY = "test-signature-key"
URL = "https://www.fortkentcinema.com/boxoffice/square/webhook/"
INDIVIDUAL = "LUXWXSDRQGNENE7XDBXPNYXY"
CLOSED_AT = datetime.datetime(2026, 10, 2, 19, 12, tzinfo=datetime.timezone.utc)


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


def event(order_id="O1", state="COMPLETED", type="order.updated") -> dict:
    return {
        "type": type,
        "event_id": "E1",
        "data": {
            "type": "order_updated",
            "id": order_id,
            "object": {"order_updated": {
                "order_id": order_id, "state": state,
                "version": 2, "location_id": "LOC"}},
        },
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
    def test_completed_order_is_processed(self):
        resp = post(self.client, event("O9"))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.content, b"")
        self.process.assert_called_once_with("O9")

    def test_other_event_types_are_ignored(self):
        resp = post(self.client, event(type="payment.updated"))
        self.assertEqual(resp.status_code, 200)
        self.process.assert_not_called()

    def test_open_order_is_ignored(self):
        resp = post(self.client, event(state="OPEN"))
        self.assertEqual(resp.status_code, 200)
        self.process.assert_not_called()

    def test_malformed_json_is_400(self):
        self.assertEqual(post_raw(self.client, "{not json").status_code, 400)
        self.process.assert_not_called()

    def test_non_object_json_is_400(self):
        self.assertEqual(post_raw(self.client, "[1, 2]").status_code, 400)
        self.process.assert_not_called()

    def test_payload_without_order_is_400(self):
        resp = post(self.client, {"type": "order.updated", "data": {}})
        self.assertEqual(resp.status_code, 400)
        self.process.assert_not_called()

    def test_failed_outcome_still_returns_200(self):
        self.process.return_value = MembershipSale(
            order_id="O9", status="FAILED", error="boom", closed_at=CLOSED_AT)
        self.assertEqual(post(self.client, event("O9")).status_code, 200)

    def test_fetch_failure_returns_503_so_square_retries(self):
        self.process.return_value = MembershipSale(
            order_id="O9", status="FAILED", closed_at=None,
            error="Could not fetch the order from Square: boom")
        self.assertEqual(post(self.client, event("O9")).status_code, 503)

    def test_attribution_failure_still_returns_200(self):
        self.process.return_value = MembershipSale(
            order_id="O9", status="FAILED", closed_at=CLOSED_AT,
            error="Ordered 2 memberships; enter by hand")
        self.assertEqual(post(self.client, event("O9")).status_code, 200)


@override_settings(SQUARE_WEBHOOK_SIGNATURE_KEY=KEY, SQUARE_WEBHOOK_URL=URL)
class EndToEndTests(TestCase):
    def setUp(self):
        self.enterContext(patch_logger())
        MembershipTier.objects.filter(slug="individual").update(
            square_variation_id=INDIVIDUAL)

    def test_signed_event_creates_the_member(self):
        gw = FakeGateway()
        gw.orders.append(OrderData(
            order_id="O1", closed_at=CLOSED_AT,
            lines=(OrderLine(uid="L1", name="Individual Membership",
                             variation_name="Annual",
                             catalog_object_id=INDIVIDUAL, quantity=1,
                             gross_cents=6000),),
            recipient=Recipient("Ann Lee", "ann@example.com", "+12075550100")))
        with mock.patch("boxoffice.memberships.get_gateway", return_value=gw):
            resp = post(self.client, event("O1"))
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(Member.objects.filter(email="ann@example.com").exists())
        self.assertEqual(MembershipSale.objects.get(order_id="O1").status, "OK")
