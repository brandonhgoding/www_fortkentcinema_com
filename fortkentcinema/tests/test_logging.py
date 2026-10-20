"""The on-call story: errors reach the owner by email, and every line is timed."""
import io
import logging
from unittest import mock

from django.core import mail
from django.test import SimpleTestCase, override_settings


def root_console_handler() -> logging.Handler:
    for handler in logging.getLogger().handlers:
        if handler.name == "console":
            return handler
    raise AssertionError("no console handler on the root logger")


class LoggingTests(SimpleTestCase):
    @override_settings(ADMINS=[("Owner", "owner@example.com")])
    def test_errors_from_any_logger_are_mailed_to_admins(self) -> None:
        # The console copy would land in the test output; swallow it.
        with mock.patch.object(root_console_handler(), "stream", io.StringIO()):
            logging.getLogger("tickets.orders").error("Ticket email failed for FK-1")

        self.assertEqual(len(mail.outbox), 1)
        message = mail.outbox[0]
        self.assertEqual(message.to, ["owner@example.com"])
        self.assertTrue(message.subject.startswith("[Fort Kent Cinema] ERROR"),
                        message.subject)
        self.assertIn("Ticket email failed for FK-1", message.body)

    @override_settings(ADMINS=[("Owner", "owner@example.com")])
    def test_warnings_are_not_mailed(self) -> None:
        logging.getLogger("boxoffice.pull").warning("Could not check order")

        self.assertEqual(mail.outbox, [])

    def test_console_lines_carry_a_timestamp_and_the_logger(self) -> None:
        record = logging.LogRecord(
            "boxoffice.pull", logging.WARNING, __file__, 1, "Pull failed", (), None)

        line = root_console_handler().format(record)

        self.assertRegex(line, r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}")
        self.assertIn("WARNING boxoffice.pull: Pull failed", line)
