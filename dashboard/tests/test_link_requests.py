"""Staff side of membership link requests: the list, marking done, the alert."""

import datetime

from accounts.tests.factories import make_user
from audience.models import LinkRequestStatus, MembershipLinkRequest
from dashboard.smart_alerts import build_smart_alerts
from dashboard.tests.helpers import make_staff
from django.test import TestCase
from django.urls import reverse

LIST = "dashboard:membership_link_requests"


def ask(email="nobody@example.com", first="Marguerite", last="Ouellette"):
    user = make_user(email, "pw12345", is_staff=False)
    return MembershipLinkRequest.objects.create(
        user=user, first_name=first, last_name=last
    )


class LinkRequestListTests(TestCase):
    def setUp(self) -> None:
        make_staff(email="staffer@example.com", password="pw12345")
        self.client.login(username="staffer@example.com", password="pw12345")

    def test_lists_name_account_email_and_roster_search(self) -> None:
        ask()
        html = self.client.get(reverse(LIST)).content.decode()
        self.assertIn("Marguerite Ouellette", html)
        self.assertIn("nobody@example.com", html)
        self.assertIn(reverse("dashboard:members") + "?q=Ouellette", html)
        self.assertIn("1 open request", html)

    def test_empty_state(self) -> None:
        html = self.client.get(reverse(LIST)).content.decode()
        self.assertIn("No link requests", html)

    def test_status_filter(self) -> None:
        ask()
        done = ask(email="done@example.com", first="Finished", last="Already")
        done.status = LinkRequestStatus.DONE
        done.save()
        html = self.client.get(reverse(LIST) + "?status=NEW").content.decode()
        self.assertIn("Marguerite", html)
        self.assertNotIn("Finished", html)
        html = self.client.get(reverse(LIST)).content.decode()
        self.assertIn("Finished", html)

    def test_mark_done(self) -> None:
        request = ask()
        resp = self.client.post(
            reverse("dashboard:membership_link_request_status", args=[request.pk]),
            {"status": LinkRequestStatus.DONE},
        )
        self.assertRedirects(resp, reverse(LIST))
        request.refresh_from_db()
        self.assertEqual(request.status, LinkRequestStatus.DONE)
        self.assertIsNotNone(request.resolved_at)

    def test_reopen_clears_resolved_at(self) -> None:
        request = ask()
        request.mark_done()
        self.client.post(
            reverse("dashboard:membership_link_request_status", args=[request.pk]),
            {"status": LinkRequestStatus.NEW},
        )
        request.refresh_from_db()
        self.assertEqual(request.status, LinkRequestStatus.NEW)
        self.assertIsNone(request.resolved_at)

    def test_home_alert_counts_open_requests(self) -> None:
        ask()
        ask(email="two@example.com")
        resp = self.client.get(reverse("dashboard:home"))
        alert = next(
            a for a in resp.context["alerts"] if a["id"] == "new-link-requests"
        )
        self.assertEqual(alert["message"], "You have 2 membership link requests")
        self.assertEqual(alert["url"], reverse(LIST) + "?status=NEW")


class LinkRequestAlertTests(TestCase):
    def test_alert_singular_and_absent(self) -> None:
        today = datetime.date(2026, 10, 24)
        alerts = build_smart_alerts([], 1, today, new_link_requests=1)
        self.assertEqual(
            [a["message"] for a in alerts], ["You have 1 membership link request"]
        )
        self.assertEqual(alerts[0]["perm"], "audience.view_membershiplinkrequest")
        self.assertEqual(build_smart_alerts([], 1, today, new_link_requests=0), [])
