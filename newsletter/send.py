"""The Thursday send. One Issue per week, one Delivery per recipient, and a
run that can die anywhere and be re-run without anyone getting two emails."""

from __future__ import annotations

import datetime
import logging
import smtplib

from django.conf import settings
from django.core import mail
from django.core.mail import EmailMultiAlternatives
from django.utils import timezone

from audience.models import Subscriber
from cinema.dates import CINEMA_TZ
from newsletter.content import build_context, subject_for
from newsletter.links import unsubscribe_url
from newsletter.models import UNSUBSCRIBE_PLACEHOLDER, Delivery, Issue
from newsletter.render import render_issue

log = logging.getLogger(__name__)

SEND_HOUR = 10
# One address bounced at submission: note it and carry on. Anything else from
# the SMTP library, or the socket, is the connection: stop and let cron resume.
RECIPIENT_ERRORS = (smtplib.SMTPRecipientsRefused, smtplib.SMTPDataError)
CONNECTION_ERRORS = (smtplib.SMTPException, OSError)
ERROR_MAX_LENGTH = 1000


class NotYet(Exception):
    """Not Thursday 10 AM Eastern yet; `reason` says which."""

    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(reason)


def thursday_for(now: datetime.datetime) -> datetime.date:
    """The Thursday `now` belongs to, or NotYet before 10 AM or on another day."""
    local = now.astimezone(CINEMA_TZ)
    if local.weekday() != 3:
        raise NotYet("not Thursday")
    if local.hour < SEND_HOUR:
        raise NotYet("too early")
    return local.date()


def render_for(issue: Issue, now: datetime.datetime) -> bool:
    """Fill the Issue's bodies once. False when there is nothing to send: the
    Issue is then SKIPPED, unless deliveries already exist (a resumed run
    keeps its stored copy, so this cannot happen)."""
    if issue.html:
        return True
    context = build_context(now)
    if context is None:
        if not issue.deliveries.exists():
            issue.status = Issue.Status.SKIPPED
            issue.skip_reason = "no showtimes"
            issue.finished_at = now
            issue.save(update_fields=["status", "skip_reason", "finished_at"])
        return False
    issue.html, issue.text = render_issue(context)
    issue.subject = subject_for(context["films"])
    issue.save(update_fields=["html", "text", "subject"])
    return True


def message_for(issue: Issue, delivery: Delivery, connection) -> EmailMultiAlternatives:
    url = unsubscribe_url(delivery.subscriber)
    message = EmailMultiAlternatives(
        subject=issue.subject,
        body=issue.text.replace(UNSUBSCRIBE_PLACEHOLDER, url),
        from_email=settings.DEFAULT_FROM_EMAIL,
        to=[delivery.subscriber.email],
        connection=connection,
        headers={
            "List-Unsubscribe": f"<{url}>",
            "List-Unsubscribe-Post": "List-Unsubscribe=One-Click",
        },
    )
    message.attach_alternative(
        issue.html.replace(UNSUBSCRIBE_PLACEHOLDER, url), "text/html"
    )
    return message


def _deliver(message: EmailMultiAlternatives) -> None:
    message.send()


def _recount(issue: Issue, now: datetime.datetime, *, final: bool) -> None:
    rows = issue.deliveries
    issue.recipient_count = rows.count()
    issue.sent_count = rows.filter(status=Delivery.Status.SENT).count()
    issue.failed_count = rows.filter(status=Delivery.Status.FAILED).count()
    if final:
        issue.status = Issue.Status.SENT
        issue.finished_at = now
    else:
        issue.status = (
            Issue.Status.FAILED if issue.sent_count == 0 else Issue.Status.SENDING
        )
    issue.save()


def send_issue(week_of: datetime.date, now: datetime.datetime | None = None) -> Issue:
    """Send (or resume) the week's email to every active subscriber."""
    if now is None:
        now = timezone.now()
    issue, _ = Issue.objects.get_or_create(week_of=week_of)
    if issue.is_done:
        log.info("Thursday email %s already %s", week_of, issue.status)
        return issue
    if not render_for(issue, now):
        log.info("Thursday email %s skipped: %s", week_of, issue.skip_reason)
        return issue

    Delivery.objects.bulk_create(
        [Delivery(issue=issue, subscriber=s) for s in Subscriber.objects.active()],
        ignore_conflicts=True,
    )
    issue.status = Issue.Status.SENDING
    issue.recipient_count = issue.deliveries.count()
    issue.save(update_fields=["status", "recipient_count"])

    pending = issue.deliveries.filter(status=Delivery.Status.PENDING).select_related(
        "subscriber"
    )
    connection = mail.get_connection()
    try:
        for delivery in pending:
            message = message_for(issue, delivery, connection)
            try:
                _deliver(message)
            except RECIPIENT_ERRORS as exc:
                delivery.status = Delivery.Status.FAILED
                delivery.error = str(exc)[:ERROR_MAX_LENGTH]
                delivery.save(update_fields=["status", "error"])
                continue
            except CONNECTION_ERRORS:
                _recount(issue, now, final=False)
                log.error(
                    "Thursday email %s interrupted after %d of %d; cron will resume",
                    week_of, issue.sent_count, issue.recipient_count,
                )
                raise
            delivery.status = Delivery.Status.SENT
            delivery.sent_at = now
            delivery.save(update_fields=["status", "sent_at"])
    finally:
        connection.close()

    _recount(issue, now, final=True)
    if issue.failed_count:
        log.error(
            "Thursday email %s: %d of %d deliveries failed",
            week_of, issue.failed_count, issue.recipient_count,
        )
    return issue
