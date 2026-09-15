import datetime

from django.contrib.auth.models import User
from django.test import TestCase
from django.utils import timezone

from audience.models import FreeAdmission, Member


def make_member(first="Marguerite", last="Ouellette", email="m.o@example.com"):
    return Member.objects.create(
        first_name=first, last_name=last, email=email
    )


class FreeAdmissionTests(TestCase):
    def setUp(self) -> None:
        self.member = make_member()

    def test_redeemed_on_defaults_to_today(self) -> None:
        admission = FreeAdmission.objects.create(member=self.member)
        self.assertEqual(admission.redeemed_on, timezone.localdate())

    def test_reverse_accessor(self) -> None:
        FreeAdmission.objects.create(member=self.member)
        self.assertEqual(self.member.free_admissions.count(), 1)

    def test_ordering_is_newest_first(self) -> None:
        for day in (3, 1, 2):
            FreeAdmission.objects.create(
                member=self.member, redeemed_on=datetime.date(2026, 9, day)
            )
        self.assertEqual(
            [a.redeemed_on.day for a in self.member.free_admissions.all()],
            [3, 2, 1],
        )

    def test_note_is_optional(self) -> None:
        self.assertEqual(FreeAdmission.objects.create(member=self.member).note, "")

    def test_nothing_stops_exceeding_the_allowance(self) -> None:
        """The allowance is a policy the UI warns about, not a constraint."""
        today = timezone.localdate()
        for _ in range(5):
            FreeAdmission.objects.create(member=self.member, redeemed_on=today)
        self.assertEqual(self.member.free_admissions.count(), 5)

    def test_deleting_the_member_deletes_their_redemptions(self) -> None:
        FreeAdmission.objects.create(member=self.member)
        self.member.delete()
        self.assertEqual(FreeAdmission.objects.count(), 0)


class RecordedByTests(TestCase):
    def setUp(self) -> None:
        self.member = make_member()
        self.staff = User.objects.create_user(
            username="bgoding", password="pw12345", is_staff=True
        )

    def test_records_who_gave_it(self) -> None:
        admission = FreeAdmission.objects.create(
            member=self.member, recorded_by=self.staff
        )
        admission.refresh_from_db()
        self.assertEqual(admission.recorded_by, self.staff)

    def test_deleting_the_staff_account_keeps_the_record(self) -> None:
        """Losing an employee must not erase what they did."""
        admission = FreeAdmission.objects.create(
            member=self.member, recorded_by=self.staff
        )
        self.staff.delete()
        admission.refresh_from_db()
        self.assertIsNone(admission.recorded_by)
        self.assertEqual(FreeAdmission.objects.count(), 1)

    def test_recorded_by_is_optional(self) -> None:
        self.assertIsNone(
            FreeAdmission.objects.create(member=self.member).recorded_by
        )
