"""The dashboard's Thursday Email page: what went out, to how many, and a
sandboxed preview of the stored body."""

import datetime

from django.test import TestCase
from django.urls import reverse

from audience.models import Subscriber
from dashboard.tests.helpers import make_staff, permissions_except
from newsletter.models import Delivery, Issue

WEEK = datetime.date(2026, 11, 5)


class IssueListTests(TestCase):
    def setUp(self):
        make_staff(email="s@example.com", password="pw12345")
        self.client.login(username="s@example.com", password="pw12345")
        self.url = reverse("dashboard:newsletter_issues")

    def test_requires_login(self):
        self.client.logout()
        self.assertEqual(self.client.get(self.url).status_code, 302)

    def test_requires_permission(self):
        self.client.logout()
        make_staff(
            email="t@example.com", password="pw12345",
            perms=permissions_except("newsletter.view_issue"),
        )
        self.client.login(username="t@example.com", password="pw12345")
        self.assertEqual(self.client.get(self.url).status_code, 403)
        preview = reverse("dashboard:newsletter_issue_preview", args=[1])
        self.assertEqual(self.client.get(preview).status_code, 403)

    def test_empty_state(self):
        self.assertIn("empty-state", self.client.get(self.url).content.decode())

    def test_lists_issues_with_status_and_counts(self):
        Issue.objects.create(
            week_of=WEEK, status=Issue.Status.SENT, subject="s", html="<p>x</p>",
            recipient_count=12, sent_count=11, failed_count=1,
        )
        Issue.objects.create(
            week_of=WEEK - datetime.timedelta(days=7), status=Issue.Status.SKIPPED,
            skip_reason="no showtimes",
        )
        html = self.client.get(self.url).content.decode()
        for needle in ("Nov 5, 2026", "Oct 29, 2026", "Sent", "Skipped",
                       "no showtimes", ">12<", ">11<", ">1<"):
            self.assertIn(needle, html)
        self.assertIn(reverse("dashboard:newsletter_issue_preview", args=[
            Issue.objects.get(week_of=WEEK).pk]), html)

    def test_failed_deliveries_expand(self):
        issue = Issue.objects.create(
            week_of=WEEK, status=Issue.Status.SENT, recipient_count=1, failed_count=1
        )
        sub, _ = Subscriber.objects.record("x@example.com", source="site")
        Delivery.objects.create(
            issue=issue, subscriber=sub, status=Delivery.Status.FAILED,
            error="550 no such user",
        )
        html = self.client.get(self.url).content.decode()
        self.assertIn("<details", html)
        self.assertIn("x@example.com", html)
        self.assertIn("550 no such user", html)

    def test_list_loads_only_failed_deliveries(self):
        from django.db import connection
        from django.test.utils import CaptureQueriesContext

        issue = Issue.objects.create(week_of=WEEK, status=Issue.Status.SENT)
        for i in range(3):
            sub, _ = Subscriber.objects.record(f"ok{i}@example.com", source="site")
            Delivery.objects.create(
                issue=issue, subscriber=sub, status=Delivery.Status.SENT
            )
        with CaptureQueriesContext(connection) as ctx:
            self.client.get(self.url)
        delivery_sql = [
            q["sql"] for q in ctx.captured_queries if "newsletter_delivery" in q["sql"]
        ]
        self.assertTrue(delivery_sql)
        self.assertTrue(all("failed" in sql for sql in delivery_sql), delivery_sql)

    def test_sidebar_link(self):
        html = self.client.get(reverse("dashboard:home")).content.decode()
        self.assertIn(self.url, html)
        self.assertIn("Thursday Email", html)


class IssuePreviewTests(TestCase):
    def setUp(self):
        make_staff(email="s@example.com", password="pw12345")
        self.client.login(username="s@example.com", password="pw12345")

    def test_preview_serves_stored_html_sandboxed(self):
        issue = Issue.objects.create(
            week_of=WEEK, html='<p>hi</p><a href="{unsubscribe_url}">u</a>'
        )
        response = self.client.get(
            reverse("dashboard:newsletter_issue_preview", args=[issue.pk])
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content.decode(), '<p>hi</p><a href="#">u</a>')
        self.assertEqual(response["Content-Security-Policy"], "sandbox")
        self.assertTrue(response["Content-Type"].startswith("text/html"))

    def test_preview_unknown_404(self):
        response = self.client.get(
            reverse("dashboard:newsletter_issue_preview", args=[999999])
        )
        self.assertEqual(response.status_code, 404)
