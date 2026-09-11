import datetime
from decimal import Decimal

from django.db import IntegrityError
from django.test import TestCase

from audience.models import Member, MembershipTerm


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

    def _term(self, **kwargs) -> MembershipTerm:
        defaults = {
            "member": self.member,
            "tier": "individual",
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
