"""The Thursday send: one email per active subscriber, safe to re-run, and
resumable after a dropped connection."""

import datetime
import smtplib
from unittest import mock

from django.core import mail
from django.test import TestCase, override_settings
from django.utils import timezone

from audience.models import Subscriber
from newsletter.links import unsubscribe_url
from newsletter.models import Delivery, Issue
from newsletter.send import NotYet, send_issue, thursday_for
from newsletter.tests.fixtures import SEND_TIME, THURSDAY, subscribers, weekend
from web.tests.test_cinema_data import aware

BASE = "https://www.fortkentcinema.com"


def deliveries(*plan):
    """A stand-in for newsletter.send._deliver: each call takes the next item
    of `plan`, an exception to raise or None to really send."""
    steps = list(plan)

    def _deliver(message):
        step = steps.pop(0) if steps else None
        if step is not None:
            raise step
        message.send()

    return mock.patch("newsletter.send._deliver", side_effect=_deliver)


class ThursdayForTests(TestCase):
    def test_thursday_at_ten(self):
        self.assertEqual(thursday_for(SEND_TIME), THURSDAY)

    def test_too_early(self):
        with self.assertRaises(NotYet) as caught:
            thursday_for(aware(2026, 11, 5, 9, 59))
        self.assertEqual(caught.exception.reason, "too early")

    def test_not_thursday(self):
        with self.assertRaises(NotYet) as caught:
            thursday_for(aware(2026, 11, 6, 10, 0))
        self.assertEqual(caught.exception.reason, "not Thursday")


@override_settings(TICKETS_BASE_URL=BASE, DEFAULT_FROM_EMAIL="hello@fortkentcinema.com")
class SendIssueTests(TestCase):
    def setUp(self):
        weekend()
        self.a, self.b = subscribers()

    def test_sends_one_email_per_active_subscriber(self):
        issue = send_issue(THURSDAY, SEND_TIME)
        self.assertEqual(len(mail.outbox), 2)
        self.assertEqual(
            sorted(m.to[0] for m in mail.outbox), ["a@example.com", "b@example.com"]
        )
        self.assertEqual(mail.outbox[0].from_email, "hello@fortkentcinema.com")
        self.assertEqual(mail.outbox[0].subject, "This weekend at the Cinema: Alpha")
        self.assertEqual(issue.status, Issue.Status.SENT)
        self.assertEqual(
            (issue.recipient_count, issue.sent_count, issue.failed_count), (2, 2, 0)
        )
        self.assertIsNotNone(issue.finished_at)
        for delivery in issue.deliveries.all():
            self.assertEqual(delivery.status, Delivery.Status.SENT)
            self.assertIsNotNone(delivery.sent_at)

    def test_one_smtp_connection_for_the_whole_run(self):
        with mock.patch(
            "django.core.mail.backends.locmem.EmailBackend.open", return_value=True
        ) as opened:
            send_issue(THURSDAY, SEND_TIME)
        self.assertEqual(opened.call_count, 1)
        self.assertEqual(len(mail.outbox), 2)

    def test_stamps_use_the_wall_clock_not_the_content_clock(self):
        before = timezone.now()
        issue = send_issue(THURSDAY, SEND_TIME)
        after = timezone.now()
        self.assertTrue(before <= issue.finished_at <= after)
        for delivery in issue.deliveries.all():
            self.assertTrue(before <= delivery.sent_at <= after)

    def test_body_carries_recipients_own_token(self):
        send_issue(THURSDAY, SEND_TIME)
        by_to = {m.to[0]: m for m in mail.outbox}
        html_a = by_to["a@example.com"].alternatives[0][0]
        self.assertIn(unsubscribe_url(self.a), html_a)
        self.assertNotIn(str(self.b.unsubscribe_token), html_a)
        self.assertIn(unsubscribe_url(self.a), by_to["a@example.com"].body)
        self.assertNotIn("{unsubscribe_url}", html_a)
        self.assertEqual(by_to["a@example.com"].alternatives[0][1], "text/html")

    def test_headers(self):
        send_issue(THURSDAY, SEND_TIME)
        message = {m.to[0]: m for m in mail.outbox}["a@example.com"]
        self.assertEqual(
            message.extra_headers["List-Unsubscribe"], f"<{unsubscribe_url(self.a)}>"
        )
        self.assertEqual(
            message.extra_headers["List-Unsubscribe-Post"], "List-Unsubscribe=One-Click"
        )

    def test_second_run_is_noop(self):
        send_issue(THURSDAY, SEND_TIME)
        send_issue(THURSDAY, SEND_TIME)
        self.assertEqual(len(mail.outbox), 2)
        self.assertEqual(Issue.objects.count(), 1)

    def test_no_showtimes_skips(self):
        from cinema.models import Showtime

        Showtime.objects.all().delete()
        issue = send_issue(THURSDAY, SEND_TIME)
        self.assertEqual(issue.status, Issue.Status.SKIPPED)
        self.assertEqual(issue.skip_reason, "no showtimes")
        self.assertIsNotNone(issue.finished_at)
        self.assertEqual(issue.deliveries.count(), 0)
        self.assertEqual(mail.outbox, [])

    def test_recipient_refusal_marks_failed_and_continues(self):
        refused = smtplib.SMTPRecipientsRefused(
            {"a@example.com": (550, b"no such user")}
        )
        with deliveries(refused):
            issue = send_issue(THURSDAY, SEND_TIME)
        self.assertEqual(len(mail.outbox), 1)
        failed = issue.deliveries.get(status=Delivery.Status.FAILED)
        self.assertNotIn(failed.subscriber.email, [m.to[0] for m in mail.outbox])
        self.assertIn("no such user", failed.error)
        self.assertEqual(issue.status, Issue.Status.SENT)
        self.assertEqual((issue.sent_count, issue.failed_count), (1, 1))

    def test_connection_error_leaves_pending_and_resumes(self):
        with deliveries(None, OSError("connection dropped")):
            with self.assertRaises(OSError):
                send_issue(THURSDAY, SEND_TIME)
        issue = Issue.objects.get()
        self.assertEqual(issue.status, Issue.Status.SENDING)
        self.assertEqual(issue.sent_count, 1)
        pending = issue.deliveries.filter(status=Delivery.Status.PENDING)
        self.assertEqual(pending.count(), 1)
        self.assertEqual(len(mail.outbox), 1)
        later = SEND_TIME + datetime.timedelta(minutes=30)
        issue = send_issue(THURSDAY, later)
        self.assertEqual(len(mail.outbox), 2)
        self.assertEqual(issue.status, Issue.Status.SENT)
        self.assertEqual((issue.sent_count, issue.failed_count), (2, 0))

    def test_connection_error_before_any_send_marks_failed(self):
        with deliveries(OSError("refused")):
            with self.assertRaises(OSError):
                send_issue(THURSDAY, SEND_TIME)
        issue = Issue.objects.get()
        self.assertEqual(issue.status, Issue.Status.FAILED)
        self.assertEqual(issue.sent_count, 0)
        issue = send_issue(THURSDAY, SEND_TIME)
        self.assertEqual(issue.status, Issue.Status.SENT)
        self.assertEqual(len(mail.outbox), 2)

    def test_resume_picks_up_new_subscriber(self):
        with deliveries(None, OSError("dropped")):
            with self.assertRaises(OSError):
                send_issue(THURSDAY, SEND_TIME)
        Subscriber.objects.record("late@example.com", source="site")
        issue = send_issue(THURSDAY, SEND_TIME + datetime.timedelta(minutes=30))
        late = [m for m in mail.outbox if m.to == ["late@example.com"]]
        self.assertEqual(len(late), 1)
        self.assertEqual(late[0].subject, issue.subject)
        self.assertEqual(issue.recipient_count, 3)

    def test_resume_closes_fully_sent_issue(self):
        issue = Issue.objects.create(
            week_of=THURSDAY, subject="s", html="<p>{unsubscribe_url}</p>", text="t"
        )
        for sub in (self.a, self.b):
            Delivery.objects.create(
                issue=issue, subscriber=sub, status=Delivery.Status.SENT,
                sent_at=SEND_TIME,
            )
        issue = send_issue(THURSDAY, SEND_TIME)
        self.assertEqual(mail.outbox, [])
        self.assertEqual(issue.status, Issue.Status.SENT)
        self.assertEqual((issue.recipient_count, issue.sent_count), (2, 2))

    def test_body_not_rerendered_on_resume(self):
        from cinema.models import Showtime

        with deliveries(None, OSError("dropped")):
            with self.assertRaises(OSError):
                send_issue(THURSDAY, SEND_TIME)
        stored = Issue.objects.get().html
        run = Showtime.objects.get().engagement
        Showtime.objects.create(
            engagement=run, screen=run.screen, starts_at=aware(2026, 11, 7, 15, 0)
        )
        send_issue(THURSDAY, SEND_TIME + datetime.timedelta(minutes=30))
        late = mail.outbox[-1]
        sub = Subscriber.objects.get(email=late.to[0])
        self.assertEqual(
            late.alternatives[0][0],
            stored.replace("{unsubscribe_url}", unsubscribe_url(sub)),
        )
        self.assertNotIn("3:00 PM", late.alternatives[0][0])
