"""A signed Square payment event for a website order, end to end."""

import datetime
from unittest import mock

from audience.models import Member, MembershipTier
from boxoffice.gateway import GatewayError
from boxoffice.tests.fakes import FakeGateway
from boxoffice.tests.test_webhook import KEY, PAID_AT, URL, event, post
from django.core import mail
from django.test import TestCase, override_settings

from join.orders import start
from join.tests.factories import BUYER, make_order, set_variation


@override_settings(SQUARE_WEBHOOK_SIGNATURE_KEY=KEY, SQUARE_WEBHOOK_URL=URL)
class JoinWebhookTests(TestCase):
    def test_signed_event_enters_the_membership_once(self):
        gw = FakeGateway()
        set_variation()
        order = start(MembershipTier.objects.get(slug="individual"), gateway=gw,
                      **BUYER)
        gw.pay(order.square_order_id, "P1", paid_at=PAID_AT)
        with mock.patch("boxoffice.memberships.get_gateway", return_value=gw):
            first = post(self.client, event(order.square_order_id))
            second = post(self.client, event(order.square_order_id))
        self.assertEqual((first.status_code, second.status_code), (200, 200))
        order.refresh_from_db()
        self.assertEqual((order.status, order.square_payment_id), ("PAID", "P1"))
        member = Member.objects.get(email="ann@example.com")
        self.assertEqual((member.terms.count(), order.term, order.sale.source),
                         (1, member.terms.get(), "WEBSITE"))
        self.assertEqual(order.term.started_on, datetime.date(2026, 10, 2))
        self.assertEqual(len(mail.outbox), 1)

    def test_fetch_failure_is_a_503_and_the_order_shows_failed(self):
        set_variation()
        order = make_order(square_order_id="SQ-1")
        failing = FakeGateway(fail_with=GatewayError("down"))
        with mock.patch("boxoffice.memberships.get_gateway", return_value=failing):
            resp = post(self.client, event("SQ-1"))
        order.refresh_from_db()
        self.assertEqual((resp.status_code, order.status), (503, "FAILED"))
