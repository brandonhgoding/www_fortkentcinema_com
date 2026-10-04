import datetime
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
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

    def test_same_start_date_orders_the_later_entry_first(self) -> None:
        """A tiebreaker, so "newest first" never depends on the database."""
        first = self._term(started_on=datetime.date(2026, 1, 1))
        second = self._term(started_on=datetime.date(2026, 1, 1))
        self.assertEqual(list(self.member.terms.all()), [second, first])

    def test_expiry_before_start_is_invalid(self) -> None:
        term = MembershipTerm(
            member=self.member,
            tier=self.tier,
            started_on=datetime.date(2026, 1, 2),
            expires_on=datetime.date(2026, 1, 1),
            price_paid=Decimal("60.00"),
        )
        with self.assertRaises(ValidationError) as caught:
            term.full_clean()
        self.assertIn("expires_on", caught.exception.message_dict)

    def test_a_one_day_term_is_valid(self) -> None:
        MembershipTerm(
            member=self.member,
            tier=self.tier,
            started_on=datetime.date(2026, 1, 1),
            expires_on=datetime.date(2026, 1, 1),
            price_paid=Decimal("0.00"),
        ).full_clean()

    def test_negative_price_paid_is_invalid(self) -> None:
        term = MembershipTerm(
            member=self.member,
            tier=self.tier,
            started_on=datetime.date(2026, 1, 1),
            expires_on=datetime.date(2026, 12, 31),
            price_paid=Decimal("-1.00"),
        )
        with self.assertRaises(ValidationError) as caught:
            term.full_clean()
        self.assertIn("price_paid", caught.exception.message_dict)

    def test_the_database_refuses_expiry_before_start(self) -> None:
        with self.assertRaises(IntegrityError), transaction.atomic():
            self._term(
                started_on=datetime.date(2026, 1, 2),
                expires_on=datetime.date(2026, 1, 1),
            )

    def test_the_database_refuses_a_negative_price(self) -> None:
        with self.assertRaises(IntegrityError), transaction.atomic():
            self._term(price_paid=Decimal("-1.00"))

    def test_deleting_a_member_deletes_their_terms(self) -> None:
        self._term()
        self.member.delete()
        self.assertEqual(MembershipTerm.objects.count(), 0)

    def test_default_expiry_is_the_day_before_the_anniversary(self) -> None:
        # expires_on is inclusive, so 12 months from 11 Sep is through
        # 10 Sep — not 11 Sep, which would be twelve months and a day.
        self.assertEqual(
            MembershipTerm.default_expiry(datetime.date(2026, 9, 11), 12),
            datetime.date(2027, 9, 10),
        )

    def test_default_expiry_across_a_short_february(self) -> None:
        self.assertEqual(
            MembershipTerm.default_expiry(datetime.date(2026, 3, 1), 12),
            datetime.date(2027, 2, 28),
        )


class EndOfTimeTests(TestCase):
    """Terms at or near date.max — a typo'd year, or a deliberate "forever"."""

    def setUp(self) -> None:
        self.member = Member.objects.create(
            first_name="Ada", last_name="Lovelace", email="ada@example.com"
        )
        self.tier = MembershipTier.objects.get(slug="individual")

    def test_default_expiry_can_be_the_last_representable_day(self) -> None:
        self.assertEqual(
            MembershipTerm.default_expiry(datetime.date(9999, 1, 1), 12),
            datetime.date.max,
        )

    def test_default_expiry_past_the_last_day_is_an_overflow(self) -> None:
        with self.assertRaises(OverflowError):
            MembershipTerm.default_expiry(datetime.date(9999, 6, 1), 12)

    def test_cover_running_to_date_max_does_not_crash_the_status(self) -> None:
        today = timezone.localdate()
        for start, end in [
            (today - datetime.timedelta(days=10), datetime.date.max),
            (today - datetime.timedelta(days=5), today + datetime.timedelta(days=50)),
        ]:
            MembershipTerm.objects.create(
                member=self.member, tier=self.tier, started_on=start,
                expires_on=end, price_paid=Decimal("60.00"),
            )
        self.assertEqual(self.member.covered_through, datetime.date.max)
        self.assertEqual(self.member.status, "active")


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

    def test_an_early_renewal_is_not_expiring_soon(self) -> None:
        """Cover runs on into the renewal, so the member is not about to
        lapse, and the date that matters is the renewal's expiry."""
        self._term(-345, 20)
        self._term(21, 385)
        self.assertEqual(self.member.status, "active")
        self.assertEqual(
            self.member.covered_through,
            self.today + datetime.timedelta(days=385),
        )

    def test_an_overlapping_renewal_extends_cover(self) -> None:
        self._term(-345, 20)
        self._term(10, 375)
        self.assertEqual(self.member.status, "active")

    def test_cover_follows_a_chain_of_renewals(self) -> None:
        self._term(-345, 5)
        self._term(6, 20)
        self._term(21, 400)
        self.assertEqual(
            self.member.covered_through,
            self.today + datetime.timedelta(days=400),
        )

    def test_a_gap_before_the_renewal_still_expires_soon(self) -> None:
        """A day without cover is a lapse, however short."""
        self._term(-345, 20)
        self._term(22, 386)
        self.assertEqual(self.member.status, "expiring")
        self.assertEqual(
            self.member.covered_through,
            self.today + datetime.timedelta(days=20),
        )

    def test_no_cover_today_means_no_covered_through(self) -> None:
        self._term(-400, -1)
        self.assertIsNone(self.member.covered_through)

    def test_only_future_terms_is_not_started_yet_rather_than_lapsed(self) -> None:
        self._term(10, 375)
        self.assertFalse(self.member.is_active)
        self.assertEqual(self.member.status, "upcoming")
        self.assertEqual(self.member.status_label, "Not started yet")

    def test_a_lapsed_member_with_a_booked_renewal_is_not_started_yet(self) -> None:
        self._term(-400, -10)
        self._term(10, 375)
        self.assertEqual(self.member.status, "upcoming")

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


class SameDayTermTests(TestCase):
    """Terms that start on the same day, or overlap, have one winner.

    current_term walks terms in Meta.ordering (-started_on, -id), and the
    status pill, free-admission allowance and roster tier all read through
    it. Without the -id tiebreaker the winner was whatever order the
    database returned.
    """

    def setUp(self) -> None:
        self.member = Member.objects.create(
            first_name="Ada", last_name="Lovelace", email="ada@example.com"
        )
        self.today = timezone.localdate()

    def _term(self, slug: str, start_offset: int, end_offset: int) -> MembershipTerm:
        term: MembershipTerm = MembershipTerm.objects.create(
            member=self.member,
            tier=MembershipTier.objects.get(slug=slug),
            started_on=self.today + datetime.timedelta(days=start_offset),
            expires_on=self.today + datetime.timedelta(days=end_offset),
            price_paid=Decimal("60.00"),
        )
        return term

    def test_the_later_entry_wins_a_same_day_start(self) -> None:
        self._term("individual", -10, 355)
        later = self._term("family-plus", -10, 355)
        self.assertEqual(self.member.current_term, later)
        self.assertEqual(self.member.free_admission_allowance, 4)

    def test_the_later_entry_wins_whichever_tier_it_is(self) -> None:
        """Entry order, not tier or pk accident, decides."""
        self._term("family-plus", -10, 355)
        later = self._term("individual", -10, 355)
        self.assertEqual(self.member.current_term, later)
        self.assertEqual(self.member.free_admission_allowance, 0)

    def test_the_prefetched_roster_agrees(self) -> None:
        self._term("individual", -10, 355)
        later = self._term("family-plus", -10, 355)
        member = Member.objects.prefetch_related("terms__tier").get(pk=self.member.pk)
        with self.assertNumQueries(0):
            self.assertEqual(member.current_term, later)
            self.assertEqual(member.free_admission_allowance, 4)

    def test_a_renewal_wins_over_the_term_it_overlaps(self) -> None:
        self._term("individual", -300, 65)
        renewal = self._term("cinema-supporter", -5, 360)
        self.assertEqual(self.member.current_term, renewal)
        self.assertEqual(self.member.free_admission_allowance, 1)
