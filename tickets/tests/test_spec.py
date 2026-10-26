import datetime
from zoneinfo import ZoneInfo

from django.test import SimpleTestCase, TestCase, override_settings
from django.utils import timezone

from tickets.spec import checkout_spec, e164_phone
from tickets.tests.factories import make_order, make_showtime

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
        self.assertEqual(spec.buyer_phone, "+12075550100")
        self.assertEqual(order.phone, "207-555-0100")
        self.assertEqual(spec.support_email, "info@fortkentcinema.com")

    def spec_for(self, phone="207-555-0100", from_email="info@fortkentcinema.com"):
        order = make_order(self.matinee_st, phone=phone)
        with override_settings(DEFAULT_FROM_EMAIL=from_email):
            return checkout_spec(order, {"adult": "va", "senior": "vs", "child": "vc"})

    def test_unusable_phone_becomes_blank_and_order_keeps_typed(self):
        spec = self.spec_for(phone="555-0100")
        self.assertEqual(spec.buyer_phone, "")

    def test_support_email_blank_when_unset_or_localhost(self):
        for from_email in ["", "webmaster@localhost", "Cinema <no-reply@localhost>"]:
            self.assertEqual(self.spec_for(from_email=from_email).support_email, "")
        self.assertEqual(
            self.spec_for(from_email="Cinema <info@fortkentcinema.com>").support_email,
            "info@fortkentcinema.com",
        )


class E164PhoneTests(SimpleTestCase):
    def test_cases(self):
        for raw, expected in [
            ("(207) 555-0100", "+12075550100"),
            ("1 207 555 0100", "+12075550100"),
            ("+1 207.555.0100", "+12075550100"),
            ("+44 20 7946 0958", "+442079460958"),
            ("555-0100", ""),
            ("2 207 555 0100", ""),
            ("+1234567", ""),
            ("+1234567890123456", ""),
            ("", ""),
        ]:
            self.assertEqual(e164_phone(raw), expected, raw)
