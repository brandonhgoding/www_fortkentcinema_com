"""manage.py send_weekly_email: the cron entry point."""

from io import StringIO
from unittest import mock

from django.core import mail
from django.core.management import CommandError, call_command
from django.test import TestCase, override_settings

from newsletter.models import Issue
from newsletter.tests.fixtures import subscribers, weekend
from web.tests.test_cinema_data import aware


def run(*args):
    out = StringIO()
    call_command("send_weekly_email", *args, stdout=out)
    return out.getvalue()


@override_settings(TICKETS_BASE_URL="https://www.fortkentcinema.com")
class CommandTests(TestCase):
    def setUp(self):
        weekend()
        subscribers()

    def test_dry_run_prints_and_writes_nothing(self):
        out = run("--dry-run", "--week-of", "2026-11-05")
        self.assertIn("Subject: This weekend at the Cinema: Alpha", out)
        self.assertIn("<!doctype html>", out)
        self.assertEqual(Issue.objects.count(), 0)
        self.assertEqual(mail.outbox, [])

    def test_non_thursday_week_of_is_an_error(self):
        with self.assertRaises(CommandError):
            run("--week-of", "2026-11-06")

    def test_outside_window_exits_quietly(self):
        with mock.patch(
            "newsletter.management.commands.send_weekly_email.timezone.now",
            return_value=aware(2026, 11, 6, 10, 0),
        ):
            with self.assertLogs("newsletter", "INFO") as logs:
                run()
        self.assertTrue(any("not Thursday" in line for line in logs.output))
        self.assertEqual(Issue.objects.count(), 0)
        self.assertEqual(mail.outbox, [])

    def test_sends_on_thursday_at_ten(self):
        with mock.patch(
            "newsletter.management.commands.send_weekly_email.timezone.now",
            return_value=aware(2026, 11, 5, 10, 0),
        ):
            out = run()
        self.assertEqual(len(mail.outbox), 2)
        self.assertIn("2 sent, 0 failed", out)

    def test_sends_for_week_of(self):
        out = run("--week-of", "2026-11-05")
        self.assertEqual(len(mail.outbox), 2)
        self.assertIn("Sent", out)

    def test_dry_run_without_showtimes_says_skipped(self):
        from cinema.models import Showtime

        Showtime.objects.all().delete()
        out = run("--dry-run", "--week-of", "2026-11-05")
        self.assertIn("Skipped: no showtimes", out)
