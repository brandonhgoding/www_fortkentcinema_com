import datetime
import html as html_lib
from unittest import mock

from accounts.tests.factories import make_user
from audience.models import Member, MembershipTier
from boxoffice.gateway import GatewayError
from boxoffice.tests.fakes import FakeGateway
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from join.models import MembershipOrder
from join.tests.factories import BUYER, make_order, set_variation
from join.tests.helpers import paid_order


def text(response) -> str:
    return html_lib.unescape(response.content.decode())


def age(order, minutes: int) -> None:
    MembershipOrder.objects.filter(pk=order.pk).update(
        created_at=timezone.now() - datetime.timedelta(minutes=minutes))


class ViewTestCase(TestCase):
    def setUp(self):
        self.gw = FakeGateway()
        patcher = mock.patch("join.views.get_gateway", return_value=self.gw)
        self.get_gateway = patcher.start()
        self.addCleanup(patcher.stop)
        set_variation()

    def get(self, slug) -> str:
        response = self.client.get(reverse("join:start", args=[slug]))
        self.assertEqual(response.status_code, 200)
        return text(response)

    def post(self, slug, **over):
        data = {**BUYER, "website": ""}
        data.update(over)
        return self.client.post(reverse("join:start", args=[slug]), data)

    def page(self, order) -> str:
        response = self.client.get(reverse("join:order", args=[order.token]))
        self.assertEqual(response.status_code, 200)
        return text(response)


class JoinPageTests(ViewTestCase):
    def test_join_page_shows_tier_and_form(self):
        html = self.get("individual")
        for s in ["Individual", "$60", 'name="first_name"', 'name="last_name"',
                  'name="email"', "Pay $60 on Square", "come straight back here",
                  'content="noindex, nofollow"']:
            self.assertIn(s, html)
        self.assertNotIn('name="phone"', html)
        self.assertNotIn(">Join<", html)  # the card's own button stays off here

    def test_unlisted_or_unknown_tier_404(self):
        MembershipTier.objects.filter(slug="individual").update(
            show_on_membership_page=False)
        self.assertEqual(
            self.client.get(reverse("join:start", args=["individual"])).status_code,
            404)
        self.assertEqual(
            self.client.get(reverse("join:start", args=["nope"])).status_code, 404)

    def test_tier_without_variation_shows_box_office_sentence(self):
        MembershipTier.objects.filter(slug="individual").update(square_variation_id="")
        html = self.get("individual")
        self.assertIn("This tier isn't sold online. Join at the box office before "
                      "any show.", html)
        self.assertNotIn('name="email"', html)

    def test_square_off_shows_unavailable_sentence(self):
        self.get_gateway.return_value = None
        with mock.patch("join.views.square_enabled", return_value=False):
            html = self.get("individual")
        self.assertIn("Online membership sign-up isn't available right now. Join at "
                      "the box office before any show.", html)
        self.assertNotIn('name="email"', html)

    def test_signed_in_member_is_prefilled(self):
        Member.objects.create(first_name="Marguerite", last_name="Ouellette",
                              email="m.o@example.com")
        self.client.force_login(make_user("m.o@example.com", "pw12345", is_staff=False))
        html = self.get("individual")
        for s in ['value="Marguerite"', 'value="Ouellette"', 'value="m.o@example.com"']:
            self.assertIn(s, html)

    def test_signed_in_non_member_gets_only_the_email(self):
        self.client.force_login(make_user("new@example.com", "pw12345", is_staff=False))
        html = self.get("individual")
        self.assertIn('value="new@example.com"', html)


class JoinPostTests(ViewTestCase):
    def test_post_redirects_to_square(self):
        resp = self.post("individual")
        self.assertEqual((resp.status_code, resp["Location"]),
                         (303, "https://square.link/u/1"))
        order = MembershipOrder.objects.get()
        self.assertEqual((order.status, order.email, order.tier.slug),
                         ("PENDING", "ann@example.com", "individual"))

    def test_post_invalid_email_rerenders(self):
        resp = self.post("individual", email="not-an-email")
        self.assertEqual(resp.status_code, 200)
        self.assertIn("Enter a valid email address.", text(resp))
        self.assertEqual(MembershipOrder.objects.count(), 0)

    def test_honeypot(self):
        resp = self.post("individual", website="http://spam")
        self.assertEqual((resp.status_code, resp["Location"]),
                         (303, reverse("join:start", args=["individual"])))
        self.assertEqual((MembershipOrder.objects.count(), self.gw.calls), (0, []))

    def test_post_gateway_failure_message(self):
        self.gw.fail_with = GatewayError("boom")
        self.assertIn("We couldn't start checkout. Please try again, or join at the "
                      "box office.", text(self.post("individual")))

    def test_post_square_off_shows_sentence_and_saves_nothing(self):
        self.get_gateway.return_value = None
        with mock.patch("join.views.square_enabled", return_value=False):
            resp = self.post("individual")
        self.assertIn("isn't available right now", text(resp))
        self.assertEqual(MembershipOrder.objects.count(), 0)

    def test_post_tier_without_variation_is_refused(self):
        MembershipTier.objects.filter(slug="individual").update(square_variation_id="")
        resp = self.post("individual")
        self.assertIn("This tier isn't sold online.", text(resp))
        self.assertEqual(MembershipOrder.objects.count(), 0)


@override_settings(GA_MEASUREMENT_ID="G-TESTID123")
class OrderPageTests(ViewTestCase):
    def test_paid_first_term(self):
        order = paid_order()
        html = self.page(order)
        for s in ["Payment received", "Welcome, Ann", "Individual membership",
                  "Your membership runs Oct 26, 2026 through Oct 25, 2027.",
                  "There's no card to carry. Give your name at the box office.",
                  "Create an account with ann@example.com", 'href="/register"',
                  "'purchase'", "value: 60", 'content="noindex, nofollow"']:
            self.assertIn(s, html)
        self.assertNotIn("You're renewed", html)

    def test_paid_renewal_for_the_signed_in_member(self):
        order = paid_order(earlier_term=True)
        self.client.force_login(make_user("ann@example.com", "pw12345", is_staff=False))
        html = self.page(order)
        self.assertIn("You're renewed", html)
        self.assertIn('href="/dashboard/"', html)
        self.assertNotIn("Create an account", html)

    def test_pending_refreshes_then_waits(self):
        order = make_order(square_checkout_url="https://square.link/u/9")
        html = self.page(order)
        self.assertIn("Confirming your payment", html)
        self.assertIn('http-equiv="refresh" content="4"', html)
        age(order, 3)
        html = self.page(order)
        self.assertIn("Still waiting", html)
        self.assertIn('href="https://square.link/u/9"', html)
        self.assertNotIn('http-equiv="refresh"', html)
        self.assertNotIn("'purchase'", html)

    def test_failed_and_abandoned(self):
        failed = make_order(status="FAILED", error="Current term never expires")
        self.assertIn("Payment received. We're finishing your membership and will "
                      "email you.", self.page(failed))
        abandoned = make_order(status="ABANDONED")
        html = self.page(abandoned)
        self.assertIn("This checkout didn't start.", html)
        self.assertIn(reverse("join:start", args=["individual"]), html)

    def test_order_page_is_never_cached(self):
        resp = self.client.get(reverse("join:order", args=[make_order().token]))
        self.assertIn("no-cache", resp["Cache-Control"])

    def test_bad_token_404(self):
        self.assertEqual(
            self.client.get(reverse("join:order", args=["nope"])).status_code, 404)

    def test_order_page_renders_with_square_off(self):
        self.get_gateway.return_value = None
        self.assertIn("Welcome, Ann", self.page(paid_order()))

    def test_order_page_recovers_after_sixty_seconds(self):
        order = make_order()
        MembershipOrder.objects.filter(pk=order.pk).update(
            created_at=timezone.now() - datetime.timedelta(seconds=61))
        with mock.patch("join.views.recover_pending") as recover:
            self.client.get(reverse("join:order", args=[order.token]))
        recover.assert_called_once()
        self.assertIs(recover.call_args.kwargs["gateway"], self.gw)

    def test_young_pending_does_not_ask_square(self):
        order = make_order()
        with mock.patch("join.views.recover_pending") as recover:
            self.client.get(reverse("join:order", args=[order.token]))
        recover.assert_not_called()
