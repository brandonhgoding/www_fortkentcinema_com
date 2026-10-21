from django.core.checks import Warning
from django.core.checks.registry import registry
from django.test import SimpleTestCase, override_settings

from phone.checks import check_twilio_settings

PROXY = {"SECURE_PROXY_SSL_HEADER": ("HTTP_X_FORWARDED_PROTO", "https")}


@override_settings(DEBUG=False, SECURE_PROXY_SSL_HEADER=None)
class TwilioCheckTests(SimpleTestCase):
    """A token with the rest half-set is reported once, at startup and by
    ``manage.py check``: the states a solo deploy drifts into."""

    def test_is_registered(self) -> None:
        self.assertIn(check_twilio_settings, registry.registered_checks)

    @override_settings(
        TWILIO_AUTH_TOKEN="tok", TWILIO_ACCOUNT_SID="AC1", TWILIO_WEBHOOK_BASE_URL=""
    )
    def test_no_base_url_and_no_proxy_headers_warns(self) -> None:
        [message] = check_twilio_settings(app_configs=None)
        self.assertIsInstance(message, Warning)
        self.assertEqual(message.id, "phone.W001")
        self.assertIn("TWILIO_WEBHOOK_BASE_URL", message.msg)

    @override_settings(
        TWILIO_AUTH_TOKEN="tok",
        TWILIO_ACCOUNT_SID="",
        TWILIO_WEBHOOK_BASE_URL="https://www.fortkentcinema.com",
    )
    def test_blank_account_sid_warns(self) -> None:
        [message] = check_twilio_settings(app_configs=None)
        self.assertEqual(message.id, "phone.W002")
        self.assertIn("TWILIO_ACCOUNT_SID", message.msg)

    @override_settings(
        TWILIO_AUTH_TOKEN="tok",
        TWILIO_ACCOUNT_SID="AC1",
        TWILIO_WEBHOOK_BASE_URL="https://www.fortkentcinema.com",
    )
    def test_pinned_base_url_is_quiet(self) -> None:
        self.assertEqual(check_twilio_settings(app_configs=None), [])

    @override_settings(
        TWILIO_AUTH_TOKEN="tok",
        TWILIO_ACCOUNT_SID="AC1",
        TWILIO_WEBHOOK_BASE_URL="",
        **PROXY,
    )
    def test_proxy_headers_are_quiet(self) -> None:
        self.assertEqual(check_twilio_settings(app_configs=None), [])

    @override_settings(
        DEBUG=True,
        TWILIO_AUTH_TOKEN="tok",
        TWILIO_ACCOUNT_SID="AC1",
        TWILIO_WEBHOOK_BASE_URL="",
    )
    def test_runserver_rebuilds_its_own_url_so_debug_is_quiet(self) -> None:
        self.assertEqual(check_twilio_settings(app_configs=None), [])

    @override_settings(
        TWILIO_AUTH_TOKEN="", TWILIO_ACCOUNT_SID="", TWILIO_WEBHOOK_BASE_URL=""
    )
    def test_blank_token_is_the_off_switch_not_a_warning(self) -> None:
        self.assertEqual(check_twilio_settings(app_configs=None), [])

    @override_settings(
        TWILIO_AUTH_TOKEN="tok", TWILIO_ACCOUNT_SID="", TWILIO_WEBHOOK_BASE_URL=""
    )
    def test_both_problems_are_both_reported(self) -> None:
        ids = [m.id for m in check_twilio_settings(app_configs=None)]
        self.assertEqual(ids, ["phone.W001", "phone.W002"])
