from unittest.mock import patch

from django.test import TestCase, override_settings
from django.urls import reverse
from phone.models import CallLog, Voicemail
from twilio.request_validator import RequestValidator

from .helpers import TOKEN, post_signed

CALL = {"CallSid": "CA123", "From": "+12075550100"}
WEBHOOKS = (
    "incoming_call",
    "menu",
    "voicemail_recorded",
    "voicemail_status",
    "voicemail_transcribed",
)
PROXY = override_settings(
    SECURE_PROXY_SSL_HEADER=("HTTP_X_FORWARDED_PROTO", "https"),
    USE_X_FORWARDED_HOST=True,
    ALLOWED_HOSTS=["www.fortkentcinema.com", "testserver"],
)


@override_settings(TWILIO_AUTH_TOKEN=TOKEN, TWILIO_WEBHOOK_BASE_URL="")
class SignatureTests(TestCase):
    def setUp(self) -> None:
        # Rejections are logged by design; keep them out of test output.
        self.logger = self.enterContext(patch("phone.decorators.logger"))

    def test_every_webhook_rejects_a_missing_signature(self) -> None:
        for name in WEBHOOKS:
            with self.subTest(name):
                response = self.client.post(reverse(f"phone:{name}"), CALL)
                self.assertEqual(response.status_code, 403)

    def test_every_webhook_rejects_a_forged_signature(self) -> None:
        for name in WEBHOOKS:
            with self.subTest(name):
                response = self.client.post(
                    reverse(f"phone:{name}"), CALL, HTTP_X_TWILIO_SIGNATURE="forged"
                )
                self.assertEqual(response.status_code, 403)

    def test_rejects_tampered_params(self) -> None:
        path = reverse("phone:voicemail_recorded")
        signature = RequestValidator(TOKEN).compute_signature(
            f"http://testserver{path}", {**CALL, "RecordingSid": "RE1"}
        )
        response = self.client.post(
            path, {**CALL, "RecordingSid": "RE2"}, HTTP_X_TWILIO_SIGNATURE=signature
        )
        self.assertEqual(response.status_code, 403)
        self.assertFalse(Voicemail.objects.exists())
        self.logger.warning.assert_called_once()

    def test_rejected_request_has_no_side_effects(self) -> None:
        self.client.post(reverse("phone:incoming_call"), CALL)
        self.assertFalse(CallLog.objects.exists())

    def test_query_string_is_part_of_the_signature(self) -> None:
        path = reverse("phone:menu")
        response = post_signed(
            self.client,
            path + "?attempt=2",
            CALL,
            url=f"http://testserver{path}?attempt=1",
        )
        self.assertEqual(response.status_code, 403)

    @override_settings(TWILIO_AUTH_TOKEN="")
    def test_missing_token_fails_closed(self) -> None:
        response = post_signed(self.client, reverse("phone:incoming_call"), CALL)
        self.assertEqual(response.status_code, 403)

    def test_get_is_not_allowed(self) -> None:
        self.assertEqual(
            self.client.get(reverse("phone:incoming_call")).status_code, 405
        )

    def test_csrf_is_exempt(self) -> None:
        self.client = self.client_class(enforce_csrf_checks=True)
        response = post_signed(self.client, reverse("phone:incoming_call"), CALL)
        self.assertEqual(response.status_code, 200)


@override_settings(TWILIO_AUTH_TOKEN=TOKEN, TWILIO_WEBHOOK_BASE_URL="")
class ReverseProxyTests(TestCase):
    """nginx terminates TLS, so Django sees plain HTTP from 127.0.0.1 while
    Twilio signed https://www.fortkentcinema.com/... ."""

    path = "/phone/voice/"
    public_url = "https://www.fortkentcinema.com/phone/voice/"
    forwarded = {
        "HTTP_X_FORWARDED_PROTO": "https",
        "HTTP_X_FORWARDED_HOST": "www.fortkentcinema.com",
    }

    def setUp(self) -> None:
        self.enterContext(patch("phone.decorators.logger"))

    @PROXY
    def test_accepts_the_public_https_url_via_forwarded_headers(self) -> None:
        response = post_signed(
            self.client, self.path, CALL, url=self.public_url, **self.forwarded
        )
        self.assertEqual(response.status_code, 200)

    def test_without_proxy_settings_the_public_signature_fails(self) -> None:
        # What production would do if USE_PROXY_HEADERS were left off.
        response = post_signed(
            self.client, self.path, CALL, url=self.public_url, **self.forwarded
        )
        self.assertEqual(response.status_code, 403)

    @override_settings(TWILIO_WEBHOOK_BASE_URL="https://www.fortkentcinema.com/")
    def test_base_url_setting_pins_the_signed_url(self) -> None:
        response = post_signed(self.client, self.path, CALL, url=self.public_url)
        self.assertEqual(response.status_code, 200)
