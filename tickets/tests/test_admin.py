from django.test import TestCase
from django.urls import reverse

from accounts.tests.factories import make_user
from tickets.tests.factories import make_order, make_showtime


class TicketOrderAdminTests(TestCase):
    def setUp(self) -> None:
        user = make_user(
            email="admin@example.com",
            password="pw",
            is_staff=True,
            is_superuser=True,
        )
        self.client.force_login(user)
        self.order = make_order(make_showtime(), status="PAID")

    def test_changelist_loads(self) -> None:
        response = self.client.get(reverse("admin:tickets_ticketorder_changelist"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.order.number)

    def test_change_page_loads(self) -> None:
        url = reverse("admin:tickets_ticketorder_change", args=[self.order.pk])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.order.number)
