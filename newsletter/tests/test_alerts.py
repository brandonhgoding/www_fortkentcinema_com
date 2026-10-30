"""The dashboard alert for a Thursday whose email never went out."""

import datetime

from django.test import TestCase

from newsletter.alerts import last_thursday, missed
from newsletter.models import Issue

THU, FRI, SAT, SUN = (datetime.date(2026, 11, d) for d in (5, 6, 7, 8))
WED = datetime.date(2026, 11, 4)


class LastThursdayTests(TestCase):
    def test_weekend_days_point_at_this_weeks_thursday(self):
        for day in (FRI, SAT, SUN):
            self.assertEqual(last_thursday(day), THU)

    def test_midweek_is_none(self):
        self.assertIsNone(last_thursday(THU))
        self.assertIsNone(last_thursday(WED))


class MissedTests(TestCase):
    def test_missed_without_issue(self):
        self.assertTrue(missed(FRI))

    def test_not_missed_when_sent_or_skipped(self):
        issue = Issue.objects.create(week_of=THU, status=Issue.Status.SENT)
        self.assertFalse(missed(FRI))
        issue.status = Issue.Status.SKIPPED
        issue.save()
        self.assertFalse(missed(SUN))

    def test_missed_when_still_sending(self):
        Issue.objects.create(week_of=THU, status=Issue.Status.SENDING)
        self.assertTrue(missed(FRI))

    def test_not_missed_midweek(self):
        self.assertFalse(missed(WED))
        self.assertFalse(missed(THU))
