from django.core import mail
from django.test import TestCase, override_settings

from join.mail import send_welcome
from join.tests.helpers import paid_order


@override_settings(TICKETS_BASE_URL="https://www.fortkentcinema.com")
class WelcomeEmailTests(TestCase):
    def test_welcome_email_for_a_first_term(self):
        order = paid_order()
        send_welcome(order)
        msg = mail.outbox[0]
        self.assertEqual((msg.to, msg.subject),
                         (["ann@example.com"], "Welcome to Fort Kent Cinema"))
        for text in [
            "Hi Ann,", "You're a member.", order.number, "Individual membership",
            "Good from Oct 26, 2026 through Oct 25, 2027",
            "Give your name at the box office.",
            "https://www.fortkentcinema.com/register",
            f"https://www.fortkentcinema.com/membership/order/{order.token}/",
            "13 Hall Street",
        ]:
            self.assertIn(text, msg.body)
        self.assertNotIn("&amp;", msg.body)
        self.assertNotIn("Thanks for renewing", msg.body)
        html = [a for a in msg.alternatives if a[1] == "text/html"][0][0]
        self.assertIn(order.number, html)
        self.assertIn("Oct 25, 2027", html)

    def test_welcome_email_for_a_renewal(self):
        order = paid_order(earlier_term=True)
        send_welcome(order)
        msg = mail.outbox[0]
        self.assertEqual(msg.subject, "Your Fort Kent Cinema membership is renewed")
        self.assertIn("Thanks for renewing", msg.body)
        self.assertNotIn("You're a member.", msg.body)
