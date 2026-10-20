from boxoffice.checks import check_square_settings
from django.core.checks import Warning
from django.core.checks.registry import registry
from django.test import SimpleTestCase, override_settings


class SquareSettingsCheckTests(SimpleTestCase):
    """A token with a blank id or a bad environment is reported once, at
    startup and by ``manage.py check``, rather than on every page view."""

    def test_is_registered(self) -> None:
        self.assertIn(check_square_settings, registry.registered_checks)

    @override_settings(SQUARE_ACCESS_TOKEN="tok", SQUARE_LOCATION_ID="",
                       SQUARE_TICKET_CATEGORY_ID="C")
    def test_token_with_blank_id_warns(self) -> None:
        [message] = check_square_settings(app_configs=None)
        self.assertIsInstance(message, Warning)
        self.assertEqual(message.id, "boxoffice.W001")
        self.assertIn("SQUARE_LOCATION_ID is blank", message.msg)

    @override_settings(SQUARE_ACCESS_TOKEN="tok", SQUARE_LOCATION_ID="L",
                       SQUARE_TICKET_CATEGORY_ID="C", SQUARE_ENVIRONMENT="prod")
    def test_bad_environment_warns(self) -> None:
        [message] = check_square_settings(app_configs=None)
        self.assertIn("SQUARE_ENVIRONMENT", message.msg)

    @override_settings(SQUARE_ACCESS_TOKEN="tok", SQUARE_LOCATION_ID="L",
                       SQUARE_TICKET_CATEGORY_ID="C", SQUARE_ENVIRONMENT="sandbox")
    def test_fully_configured_is_quiet(self) -> None:
        self.assertEqual(check_square_settings(app_configs=None), [])

    @override_settings(SQUARE_ACCESS_TOKEN="", SQUARE_LOCATION_ID="",
                       SQUARE_TICKET_CATEGORY_ID="")
    def test_blank_token_is_the_off_switch_not_a_warning(self) -> None:
        self.assertEqual(check_square_settings(app_configs=None), [])
