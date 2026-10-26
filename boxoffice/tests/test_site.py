"""The public URL and support address every Square checkout sends along."""

from boxoffice.site import base_url, support_email
from django.test import SimpleTestCase, override_settings

WEBHOOK_URL = "https://www.fortkentcinema.com/boxoffice/square/webhook/"


class BaseUrlTests(SimpleTestCase):
    def test_prefers_tickets_setting_without_trailing_slash(self):
        with override_settings(
            TICKETS_BASE_URL="https://tickets.example.com/",
            SQUARE_WEBHOOK_URL="https://www.fortkentcinema.com/boxoffice/x/",
        ):
            self.assertEqual(base_url(), "https://tickets.example.com")

    def test_falls_back_to_webhook_host(self):
        with override_settings(TICKETS_BASE_URL="", SQUARE_WEBHOOK_URL=WEBHOOK_URL):
            self.assertEqual(base_url(), "https://www.fortkentcinema.com")

    def test_empty_without_either_setting(self):
        with override_settings(TICKETS_BASE_URL="", SQUARE_WEBHOOK_URL=""):
            self.assertEqual(base_url(), "")


class SupportEmailTests(SimpleTestCase):
    def test_blank_when_unset_or_localhost(self):
        for from_email in ["", "webmaster@localhost", "Cinema <no-reply@localhost>"]:
            with override_settings(DEFAULT_FROM_EMAIL=from_email):
                self.assertEqual(support_email(), "")

    def test_address_part_of_a_named_sender(self):
        with override_settings(DEFAULT_FROM_EMAIL="Cinema <info@fortkentcinema.com>"):
            self.assertEqual(support_email(), "info@fortkentcinema.com")
