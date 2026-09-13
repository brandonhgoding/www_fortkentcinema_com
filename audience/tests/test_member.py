import datetime
from decimal import Decimal

from django.db import IntegrityError
from django.test import TestCase
from django.utils import timezone

from audience.models import Member, MembershipTerm, MembershipTier


class MemberFieldTests(TestCase):
    def test_email_is_lowercased_on_save(self) -> None:
        member = Member.objects.create(
            first_name="Ada", last_name="Lovelace", email="  Ada@Example.COM "
        )
        member.refresh_from_db()
        self.assertEqual(member.email, "ada@example.com")

    def test_email_is_unique(self) -> None:
        Member.objects.create(
            first_name="Ada", last_name="Lovelace", email="ada@example.com"
        )
        with self.assertRaises(IntegrityError):
            Member.objects.create(
                first_name="Another", last_name="Ada", email="ada@example.com"
            )

    def test_full_name(self) -> None:
        member = Member(first_name="Ada", last_name="Lovelace")
        self.assertEqual(member.full_name, "Ada Lovelace")

    def test_ordering_is_by_surname(self) -> None:
        Member.objects.create(
            first_name="Zoe", last_name="Adams", email="z@example.com"
        )
        Member.objects.create(
            first_name="Amy", last_name="Baker", email="a@example.com"
        )
        self.assertEqual(
            [m.last_name for m in Member.objects.all()], ["Adams", "Baker"]
        )

    def test_phone_and_notes_are_optional(self) -> None:
        member = Member.objects.create(
            first_name="Ada", last_name="Lovelace", email="ada@example.com"
        )
        self.assertEqual(member.phone, "")
        self.assertEqual(member.notes, "")


class MembershipTermTests(TestCase):
    def setUp(self) -> None:
        self.member = Member.objects.create(
            first_name="Ada", last_name="Lovelace", email="ada@example.com"
        )
        self.tier = MembershipTier.objects.get(slug="individual")

    def _term(self, **kwargs) -> MembershipTerm:
        defaults = {
            "member": self.member,
            "tier": self.tier,
            "started_on": datetime.date(2026, 1, 1),
            "expires_on": datetime.date(2027, 1, 1),
            "price_paid": Decimal("60.00"),
        }
        return MembershipTerm.objects.create(**{**defaults, **kwargs})

    def test_terms_are_reachable_from_the_member(self) -> None:
        term = self._term()
        self.assertEqual(list(self.member.terms.all()), [term])

    def test_terms_are_newest_first(self) -> None:
        older = self._term(started_on=datetime.date(2025, 1, 1))
        newer = self._term(started_on=datetime.date(2026, 1, 1))
        self.assertEqual(list(self.member.terms.all()), [newer, older])

    def test_deleting_a_member_deletes_their_terms(self) -> None:
        self._term()
        self.member.delete()
        self.assertEqual(MembershipTerm.objects.count(), 0)

    def test_default_expiry_is_start_plus_the_tier_duration(self) -> None:
        self.assertEqual(
            MembershipTerm.default_expiry(datetime.date(2026, 9, 11), 12),
            datetime.date(2027, 9, 11),
        )


class DerivedStatusTests(TestCase):
    def setUp(self) -> None:
        self.member = Member.objects.create(
            first_name="Ada", last_name="Lovelace", email="ada@example.com"
        )
        self.today = timezone.localdate()
        self.tier = MembershipTier.objects.get(slug="individual")

    def _term(self, start_offset: int, end_offset: int) -> MembershipTerm:
        return MembershipTerm.objects.create(
            member=self.member,
            tier=self.tier,
            started_on=self.today + datetime.timedelta(days=start_offset),
            expires_on=self.today + datetime.timedelta(days=end_offset),
            price_paid=Decimal("60.00"),
        )

    def test_no_terms_means_lapsed(self) -> None:
        self.assertIsNone(self.member.current_term)
        self.assertFalse(self.member.is_active)
        self.assertEqual(self.member.status, "lapsed")

    def test_active_on_the_first_day(self) -> None:
        self._term(0, 365)
        self.assertTrue(self.member.is_active)

    def test_active_on_the_expiry_date_itself(self) -> None:
        # Inclusive: the membership is good THROUGH expires_on.
        self._term(-365, 0)
        self.assertTrue(self.member.is_active)

    def test_lapsed_the_day_after_expiry(self) -> None:
        self._term(-366, -1)
        self.assertFalse(self.member.is_active)
        self.assertEqual(self.member.status, "lapsed")

    def test_expiring_soon_within_thirty_days(self) -> None:
        self._term(-335, 29)
        self.assertEqual(self.member.status, "expiring")

    def test_not_expiring_soon_at_thirty_one_days(self) -> None:
        self._term(-334, 31)
        self.assertEqual(self.member.status, "active")

    def test_a_renewal_makes_a_lapsed_member_active_again(self) -> None:
        old = self._term(-800, -400)
        new = self._term(-10, 355)
        self.member.refresh_from_db()
        self.assertTrue(self.member.is_active)
        self.assertEqual(self.member.current_term, new)
        self.assertNotEqual(self.member.current_term, old)

    def test_term_knows_whether_it_is_current(self) -> None:
        self.assertTrue(self._term(-1, 1).is_current)
        self.assertFalse(self._term(-10, -5).is_current)


class MemberManagerTests(TestCase):
    def setUp(self) -> None:
        self.today = timezone.localdate()
        self.tier = MembershipTier.objects.get(slug="individual")
        self.active = Member.objects.create(
            first_name="Cur", last_name="Rent", email="current@example.com"
        )
        MembershipTerm.objects.create(
            member=self.active,
            tier=self.tier,
            started_on=self.today - datetime.timedelta(days=10),
            expires_on=self.today + datetime.timedelta(days=10),
            price_paid=Decimal("60.00"),
        )
        self.lapsed = Member.objects.create(
            first_name="Ex", last_name="Pired", email="lapsed@example.com"
        )
        MembershipTerm.objects.create(
            member=self.lapsed,
            tier=self.tier,
            started_on=self.today - datetime.timedelta(days=400),
            expires_on=self.today - datetime.timedelta(days=35),
            price_paid=Decimal("60.00"),
        )
        self.never = Member.objects.create(
            first_name="No", last_name="Terms", email="never@example.com"
        )

    def test_active_returns_only_covered_members(self) -> None:
        self.assertEqual(list(Member.objects.active()), [self.active])

    def test_lapsed_includes_members_with_no_terms(self) -> None:
        self.assertEqual(
            sorted(m.email for m in Member.objects.lapsed()),
            ["lapsed@example.com", "never@example.com"],
        )

    def test_active_and_lapsed_partition_the_roster(self) -> None:
        self.assertEqual(
            Member.objects.active().count() + Member.objects.lapsed().count(),
            Member.objects.count(),
        )

    def test_a_member_with_two_terms_is_not_listed_twice(self) -> None:
        MembershipTerm.objects.create(
            member=self.active,
            tier=self.tier,
            started_on=self.today - datetime.timedelta(days=5),
            expires_on=self.today + datetime.timedelta(days=20),
            price_paid=Decimal("60.00"),
        )
        self.assertEqual(Member.objects.active().count(), 1)
