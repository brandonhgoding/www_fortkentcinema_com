from django.test import TestCase, override_settings

from join.spec import checkout_spec
from join.tests.factories import make_order, set_variation


class CheckoutSpecTests(TestCase):
    @override_settings(
        TICKETS_BASE_URL="https://www.fortkentcinema.com/",
        DEFAULT_FROM_EMAIL="Fort Kent Cinema <hello@fortkentcinema.com>",
    )
    def test_spec_has_one_explicitly_priced_line_and_no_showtime(self):
        set_variation()
        order = make_order(square_customer_id="C-3")
        spec = checkout_spec(order)
        line = spec.lines[0]
        self.assertEqual(
            (len(spec.lines), line.variation_id, line.name, line.quantity,
             line.unit_cents, line.discount_cents),
            (1, "VAR-IND", "Individual", 1, 6000, 0))
        self.assertEqual(
            (spec.reference, spec.buyer_email, spec.buyer_phone, spec.customer_id,
             spec.showtime_id, spec.idempotency_key),
            (order.number, "ann@example.com", "", "C-3", None, order.token))
        self.assertEqual(
            spec.redirect_url,
            f"https://www.fortkentcinema.com/membership/order/{order.token}/")
        self.assertEqual(spec.support_email, "hello@fortkentcinema.com")
