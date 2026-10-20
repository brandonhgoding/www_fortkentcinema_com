from django.core import mail
from django.test import TestCase, override_settings

from tickets.mail import qr_png, send_refund, send_ticket
from tickets.tests.factories import make_order, make_showtime


class TicketEmailTests(TestCase):
    def setUp(self):
        self.st = make_showtime()

    def test_ticket_email_contents_and_qr(self):
        order = make_order(self.st, status="PAID", lines={"adult": 2, "child": 1})
        with override_settings(TICKETS_BASE_URL="https://www.fortkentcinema.com"):
            send_ticket(order)
        self.assertEqual(len(mail.outbox), 1)
        msg = mail.outbox[0]
        self.assertEqual(msg.to, ["ann@example.com"])
        self.assertRegex(
            msg.subject,
            r"^Your tickets: Dune, \w{3} \w{3} \d{1,2} at \d{1,2}:\d{2} [AP]M$",
        )
        self.assertTrue(msg.subject.endswith(" at 7:00 PM"))
        for text in [
            "Hi Ann,",
            order.number,
            "Dune",
            "7:00 PM",
            "Screen 1",
            "2 × Adult $16.00",
            "1 × Child $6.00",
            "Total $22.00",
            "13 Hall Street",
            "Show this at the door, or just give your name.",
            "Tickets are non-refundable unless the show is cancelled.",
            f"https://www.fortkentcinema.com/tickets/order/{order.token}/",
        ]:
            self.assertIn(text, msg.body)
        self.assertNotIn("&amp;", msg.body)
        html = [a for a in msg.alternatives if a[1] == "text/html"][0][0]
        self.assertIn('src="cid:ticket-qr"', html)
        self.assertIn(order.number, html)
        qr = [
            a
            for a in msg.attachments
            if getattr(a, "get_content_type", lambda: "")() == "image/png"
        ]
        self.assertEqual(len(qr), 1)
        self.assertEqual(qr[0]["Content-ID"], "<ticket-qr>")

    def test_qr_png_is_a_png(self):
        self.assertEqual(qr_png("https://x/y")[:8], b"\x89PNG\r\n\x1a\n")

    def test_refund_email(self):
        self.st.is_cancelled = True
        self.st.save()
        order = make_order(self.st, status="REFUNDED", lines={"adult": 2, "child": 1})
        send_refund(order)
        self.assertEqual(len(mail.outbox), 1)
        msg = mail.outbox[0]
        self.assertEqual(msg.to, ["ann@example.com"])
        self.assertRegex(msg.subject, r"^Refunded: Dune, \w{3} \w{3} \d{1,2}$")
        for text in ["Hi Ann,", "cancelled", "$22.00", "within a few days",
                     "(207) 231-5287"]:
            self.assertIn(text, msg.body)

    def test_staff_refund_email_on_a_running_show(self):
        order = make_order(self.st, status="REFUNDED", lines={"adult": 2, "child": 1})
        send_refund(order)
        msg = mail.outbox[0]
        self.assertRegex(msg.subject, r"^Refunded: Dune, \w{3} \w{3} \d{1,2}$")
        day = msg.subject.split(", ", 1)[1]
        self.assertIn(
            f"Your order {order.number} for Dune on {day} has been refunded "
            "by the cinema.",
            msg.body,
        )
        self.assertNotIn("cancelled", msg.body)
        for text in ["$22.00", "within a few days", "(207) 231-5287"]:
            self.assertIn(text, msg.body)
