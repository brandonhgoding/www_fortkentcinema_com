"""Cron's entry point for the Thursday email.

Runs at 10:00 and 10:30 Eastern on Thursdays (the second firing resumes an
interrupted first). Without --week-of it refuses to send before 10 AM or on
another day, so a crontab that loses its CRON_TZ cannot send early.
"""

import datetime
import logging

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from cinema.dates import CINEMA_TZ
from newsletter.content import build_context, subject_for
from newsletter.render import render_issue
from newsletter.send import (
    CONNECTION_ERRORS,
    SEND_HOUR,
    NotYet,
    send_issue,
    thursday_for,
)

log = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Send this week's Thursday showtimes email to the mailing list."

    def add_arguments(self, parser):
        parser.add_argument(
            "--week-of",
            help="The Thursday to send for (YYYY-MM-DD). The content is built as "
                 "of 10 AM Eastern that day. Default: today, if it is Thursday "
                 "10 AM or later.",
        )
        parser.add_argument(
            "--dry-run", action="store_true",
            help="Render and print the subject and HTML; write and send nothing.",
        )

    def handle(self, *args, **options):
        now = timezone.now()
        if options["week_of"]:
            week_of = datetime.date.fromisoformat(options["week_of"])
            if week_of.weekday() != 3:
                raise CommandError(f"--week-of {week_of} is not a Thursday")
            # The content clock for an explicit week: that Thursday at send time.
            now = datetime.datetime.combine(
                week_of, datetime.time(SEND_HOUR), tzinfo=CINEMA_TZ
            )
        else:
            try:
                week_of = thursday_for(now)
            except NotYet as not_yet:
                log.info("Thursday email: %s, nothing to do", not_yet.reason)
                self.stdout.write(f"Nothing to do: {not_yet.reason}")
                return

        if options["dry_run"]:
            context = build_context(now)
            if context is None:
                self.stdout.write("Skipped: no showtimes")
                return
            html, _ = render_issue(context)
            self.stdout.write(f"Subject: {subject_for(context['films'])}\n")
            self.stdout.write(html)
            return

        try:
            issue = send_issue(week_of, now)
        except CONNECTION_ERRORS as exc:
            raise CommandError(f"Thursday email {week_of} interrupted: {exc}")
        self.stdout.write(
            f"{issue}: {issue.get_status_display()} "
            f"({issue.sent_count} sent, {issue.failed_count} failed)"
        )
