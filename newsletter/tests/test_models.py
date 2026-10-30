import datetime

from django.db import IntegrityError
from django.test import TestCase

from audience.models import Subscriber
from newsletter.models import Delivery, Issue


class IssueTests(TestCase):
    def test_defaults(self):
        issue = Issue.objects.create(week_of=datetime.date(2026, 11, 5))
        self.assertEqual(issue.status, Issue.Status.SENDING)
        self.assertFalse(issue.is_done)
        self.assertEqual(
            (issue.recipient_count, issue.sent_count, issue.failed_count), (0, 0, 0)
        )

    def test_is_done_for_sent_and_skipped(self):
        for status in (Issue.Status.SENT, Issue.Status.SKIPPED):
            self.assertTrue(
                Issue(week_of=datetime.date(2026, 11, 5), status=status).is_done
            )

    def test_week_of_unique(self):
        Issue.objects.create(week_of=datetime.date(2026, 11, 5))
        with self.assertRaises(IntegrityError):
            Issue.objects.create(week_of=datetime.date(2026, 11, 5))

    def test_preview_html_replaces_placeholder(self):
        issue = Issue(
            week_of=datetime.date(2026, 11, 5),
            html='<a href="{unsubscribe_url}">x</a>',
        )
        self.assertEqual(issue.preview_html, '<a href="#">x</a>')


class DeliveryTests(TestCase):
    def test_one_delivery_per_subscriber_per_issue(self):
        issue = Issue.objects.create(week_of=datetime.date(2026, 11, 5))
        sub, _ = Subscriber.objects.record("a@example.com", source="site")
        Delivery.objects.create(issue=issue, subscriber=sub)
        with self.assertRaises(IntegrityError):
            Delivery.objects.create(issue=issue, subscriber=sub)
