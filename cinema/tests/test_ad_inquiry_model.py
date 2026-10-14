from cinema.models import AdInquiry, AdType, InquiryStatus
from django.test import TestCase


class AdInquiryModelTests(TestCase):
    def test_defaults(self):
        row = AdInquiry.objects.create(
            business_name="Rock's Diner", contact_name="Pat", email="pat@example.com"
        )
        self.assertEqual(row.ad_type, AdType.UNSURE)
        self.assertEqual(row.status, InquiryStatus.NEW)
        self.assertEqual(row.phone, "")
        self.assertEqual(row.message, "")
        self.assertIsNone(row.ip)
        self.assertEqual(str(row), "Rock's Diner (New)")

    def test_newest_first(self):
        first = AdInquiry.objects.create(
            business_name="A", contact_name="a", email="a@example.com"
        )
        second = AdInquiry.objects.create(
            business_name="B", contact_name="b", email="b@example.com"
        )
        self.assertEqual(list(AdInquiry.objects.all()), [second, first])

    def test_ad_type_labels(self):
        self.assertEqual(
            AdType.choices,
            [
                ("SLIDE", "Pre-show slide"),
                ("VIDEO", "Video spot"),
                ("UNSURE", "Not sure yet"),
            ],
        )
