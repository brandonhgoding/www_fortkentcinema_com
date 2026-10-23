import datetime
from decimal import Decimal

from django.test import TestCase
from django.utils import timezone

from accounts.models import User
from audience.dates import month_bounds
from audience.models import FreeAdmission, Member, MembershipTerm, MembershipTier


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


def give_term(member, slug="cinema-supporter", started=None, expires=None):
    tier = MembershipTier.objects.get(slug=slug)
    today = timezone.localdate()
    return MembershipTerm.objects.create(
        member=member,
        tier=tier,
        started_on=started or today - datetime.timedelta(days=30),
        expires_on=expires or today + datetime.timedelta(days=300),
        price_paid=Decimal("120.00"),
    )


class MonthBoundsTests(TestCase):
    def test_a_31_day_month(self) -> None:
        self.assertEqual(
            month_bounds(2026, 8),
            (datetime.date(2026, 8, 1), datetime.date(2026, 8, 31)),
        )

    def test_a_30_day_month(self) -> None:
        self.assertEqual(
            month_bounds(2026, 9),
            (datetime.date(2026, 9, 1), datetime.date(2026, 9, 30)),
        )

    def test_february_in_a_leap_year(self) -> None:
        self.assertEqual(
            month_bounds(2028, 2),
            (datetime.date(2028, 2, 1), datetime.date(2028, 2, 29)),
        )

    def test_february_in_a_common_year(self) -> None:
        self.assertEqual(
            month_bounds(2026, 2),
            (datetime.date(2026, 2, 1), datetime.date(2026, 2, 28)),
        )

    def test_december_does_not_overflow_the_year(self) -> None:
        self.assertEqual(
            month_bounds(2026, 12),
            (datetime.date(2026, 12, 1), datetime.date(2026, 12, 31)),
        )


class AllowanceTests(TestCase):
    def setUp(self) -> None:
        self.member = make_member()

    def test_comes_from_the_current_terms_tier(self) -> None:
        give_term(self.member, "cinema-supporter")
        self.assertEqual(self.member.free_admission_allowance, 1)

    def test_family_plus_gets_four(self) -> None:
        give_term(self.member, "family-plus")
        self.assertEqual(self.member.free_admission_allowance, 4)

    def test_a_tier_that_grants_none(self) -> None:
        give_term(self.member, "individual")
        self.assertEqual(self.member.free_admission_allowance, 0)

    def test_a_member_with_no_term_at_all(self) -> None:
        self.assertEqual(self.member.free_admission_allowance, 0)

    def test_a_lapsed_member_gets_nothing(self) -> None:
        """The benefit came with the membership, and the membership is over."""
        today = timezone.localdate()
        give_term(
            self.member,
            "family-plus",
            started=today - datetime.timedelta(days=400),
            expires=today - datetime.timedelta(days=35),
        )
        self.assertEqual(self.member.free_admission_allowance, 0)


class UsageInMonthTests(TestCase):
    def setUp(self) -> None:
        self.member = make_member()
        give_term(self.member, "family-plus")

    def redeem(self, year, month, day) -> None:
        FreeAdmission.objects.create(
            member=self.member, redeemed_on=datetime.date(year, month, day)
        )

    def test_counts_only_that_month(self) -> None:
        self.redeem(2026, 9, 2)
        self.redeem(2026, 9, 20)
        self.redeem(2026, 8, 15)
        self.assertEqual(self.member.free_admissions_in(2026, 9), 2)

    def test_the_last_day_of_the_previous_month_does_not_count(self) -> None:
        """The boundary most likely to be got wrong."""
        self.redeem(2026, 8, 31)
        self.assertEqual(self.member.free_admissions_in(2026, 9), 0)
        self.assertEqual(self.member.free_admissions_in(2026, 8), 1)

    def test_the_first_day_of_the_month_counts(self) -> None:
        self.redeem(2026, 9, 1)
        self.assertEqual(self.member.free_admissions_in(2026, 9), 1)

    def test_the_last_day_of_the_month_counts(self) -> None:
        self.redeem(2026, 9, 30)
        self.assertEqual(self.member.free_admissions_in(2026, 9), 1)

    def test_a_month_with_none(self) -> None:
        self.assertEqual(self.member.free_admissions_in(2026, 9), 0)

    def test_another_members_redemptions_do_not_count(self) -> None:
        other = make_member("Solange", "Pelletier", "s.p@example.com")
        FreeAdmission.objects.create(
            member=other, redeemed_on=datetime.date(2026, 9, 5)
        )
        self.assertEqual(self.member.free_admissions_in(2026, 9), 0)

    def test_usage_is_not_capped_by_the_allowance(self) -> None:
        for day in range(1, 7):
            self.redeem(2026, 9, day)
        self.assertEqual(self.member.free_admissions_in(2026, 9), 6)
        self.assertEqual(self.member.free_admission_allowance, 4)
