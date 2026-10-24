from django.test import TestCase
from django.urls import reverse

from cinema.models import RentalInquiry
from dashboard.tests.helpers import make_staff


class InquiryStatusHomeTests(TestCase):
    def test_enum_lives_with_rentals(self):
        from cinema.models import rental_inquiry

        self.assertEqual(
            rental_inquiry.InquiryStatus.__module__, "cinema.models.rental_inquiry"
        )
        self.assertEqual(
            [c for c, _ in rental_inquiry.InquiryStatus.choices],
            ["NEW", "CONTACTED", "WON", "LOST"],
        )

    def test_existing_row_keeps_and_changes_status(self):
        r = RentalInquiry.objects.create(
            contact_name="A", email="a@b.c", status="WON"
        )
        staff = make_staff(
            email="staff@example.com", password="pw"
        )
        self.client.force_login(staff)
        self.client.post(
            reverse("dashboard:rental_inquiry_status", args=[r.pk]),
            {"status": "CONTACTED"},
        )
        r.refresh_from_db()
        self.assertEqual(r.status, "CONTACTED")
