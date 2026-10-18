import datetime
from zoneinfo import ZoneInfo

from django.test import TestCase, override_settings
from django.utils import timezone

from tickets.spec import base_url, checkout_spec
from tickets.tests.factories import make_order, make_showtime

WEBHOOK_URL = "https://www.fortkentcinema.com/boxoffice/square/webhook/"


class CheckoutSpecTests(TestCase):
    def setUp(self):
        day = timezone.localdate() + datetime.timedelta(days=7)
        self.matinee_st = make_showtime(
            starts_at=datetime.datetime.combine(
                day, datetime.time(13, 0), tzinfo=ZoneInfo("America/New_York")
            )
        )

    def test_spec_lines_prices_and_urls(self):
        with override_settings(
            TICKETS_BASE_URL="https://www.fortkentcinema.com",
            DEFAULT_FROM_EMAIL="info@fortkentcinema.com",
        ):
            # Out of tier order, to prove the lines come back in SQUARE_TIERS order.
            order = make_order(
                self.matinee_st,
                lines={"child": 1, "adult": 2},
                email="ann@example.com",
                phone="207-555-0100",
            )
            spec = checkout_spec(order, {"adult": "va", "senior": "vs", "child": "vc"})
        self.assertEqual(
            [
                (line.variation_id, line.name, line.quantity, line.unit_cents)
                + (line.discount_cents,)
                for line in spec.lines
            ],
            [("va", "Adult", 2, 600, 400), ("vc", "Child", 1, 600, 0)],
        )
        self.assertEqual(
            spec.redirect_url,
            f"https://www.fortkentcinema.com/tickets/order/{order.token}/",
        )
        self.assertEqual(spec.reference, order.number)
        self.assertEqual(spec.idempotency_key, order.token)
        self.assertEqual(spec.showtime_id, self.matinee_st.pk)
        self.assertEqual(spec.buyer_email, "ann@example.com")
        self.assertEqual(spec.buyer_phone, "207-555-0100")
        self.assertEqual(spec.support_email, "info@fortkentcinema.com")

    def test_base_url_prefers_tickets_setting_without_trailing_slash(self):
        with override_settings(
            TICKETS_BASE_URL="https://tickets.example.com/",
            SQUARE_WEBHOOK_URL="https://www.fortkentcinema.com/boxoffice/x/",
        ):
            self.assertEqual(base_url(), "https://tickets.example.com")

    def test_base_url_falls_back_to_webhook_host(self):
        with override_settings(
            TICKETS_BASE_URL="",
            SQUARE_WEBHOOK_URL=WEBHOOK_URL,
        ):
            self.assertEqual(base_url(), "https://www.fortkentcinema.com")

    def test_base_url_empty_without_either_setting(self):
        with override_settings(TICKETS_BASE_URL="", SQUARE_WEBHOOK_URL=""):
            self.assertEqual(base_url(), "")
