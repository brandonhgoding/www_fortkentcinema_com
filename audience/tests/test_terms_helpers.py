"""Term-set helpers: overlap detection and where a renewal starts."""

import datetime
from decimal import Decimal

from audience.models import Member, MembershipTerm, MembershipTier
from audience.terms import latest_term, overlapping_term_ids, renewal_start
from django.test import TestCase


def make_term(member, tier, start, end):
    return MembershipTerm.objects.create(
        member=member,
        tier=tier,
        started_on=start,
        expires_on=end,
        price_paid=Decimal("60.00"),
    )


class OverlappingTermIdsTests(TestCase):
    def setUp(self) -> None:
        self.member = Member.objects.create(
            first_name="Ada", last_name="Lovelace", email="ada@example.com"
        )
        self.tier = MembershipTier.objects.get(slug="individual")

    def test_consecutive_terms_do_not_overlap(self) -> None:
        """The normal shape: a renewal starts the day after the last expiry."""
        a = make_term(
            self.member, self.tier,
            datetime.date(2025, 1, 1), datetime.date(2025, 12, 31),
        )
        b = make_term(
            self.member, self.tier,
            datetime.date(2026, 1, 1), datetime.date(2026, 12, 31),
        )
        self.assertEqual(overlapping_term_ids([a, b]), set())

    def test_shared_boundary_day_counts_as_an_overlap(self) -> None:
        """expires_on is inclusive, so a term ending the day the next one
        starts covers that day twice."""
        a = make_term(
            self.member, self.tier,
            datetime.date(2025, 1, 1), datetime.date(2026, 1, 1),
        )
        b = make_term(
            self.member, self.tier,
            datetime.date(2026, 1, 1), datetime.date(2026, 12, 31),
        )
        self.assertEqual(overlapping_term_ids([a, b]), {a.pk, b.pk})

    def test_both_sides_of_an_overlapping_pair_are_returned(self) -> None:
        a = make_term(
            self.member, self.tier,
            datetime.date(2026, 1, 1), datetime.date(2026, 12, 31),
        )
        b = make_term(
            self.member, self.tier,
            datetime.date(2026, 6, 1), datetime.date(2027, 5, 31),
        )
        self.assertEqual(overlapping_term_ids([a, b]), {a.pk, b.pk})

    def test_an_untouched_term_stays_unflagged(self) -> None:
        """A clean older term is not dragged in by a later duplicate."""
        clean = make_term(
            self.member, self.tier,
            datetime.date(2020, 1, 1), datetime.date(2020, 12, 31),
        )
        a = make_term(
            self.member, self.tier,
            datetime.date(2026, 1, 1), datetime.date(2026, 12, 31),
        )
        b = make_term(
            self.member, self.tier,
            datetime.date(2026, 1, 1), datetime.date(2026, 12, 31),
        )
        self.assertEqual(overlapping_term_ids([clean, a, b]), {a.pk, b.pk})

    def test_a_term_does_not_overlap_itself(self) -> None:
        a = make_term(
            self.member, self.tier,
            datetime.date(2026, 1, 1), datetime.date(2026, 12, 31),
        )
        self.assertEqual(overlapping_term_ids([a]), set())

    def test_empty_input(self) -> None:
        self.assertEqual(overlapping_term_ids([]), set())


class RenewalStartTests(TestCase):
    def setUp(self) -> None:
        self.member = Member.objects.create(
            first_name="Ada", last_name="Lovelace", email="ada@example.com"
        )
        self.tier = MembershipTier.objects.get(slug="individual")

    def test_early_renewal_continues_from_the_current_expiry(self) -> None:
        """Renewing in November of a term that runs to December must not
        throw away the weeks already paid for."""
        term = make_term(
            self.member, self.tier,
            datetime.date(2026, 1, 1), datetime.date(2026, 12, 31),
        )
        self.assertEqual(
            renewal_start(term, datetime.date(2026, 11, 15)),
            datetime.date(2027, 1, 1),
        )

    def test_renewal_after_a_lapse_starts_today(self) -> None:
        """Back-dating would burn the new term against months the member
        was not a member."""
        term = make_term(
            self.member, self.tier,
            datetime.date(2023, 1, 1), datetime.date(2023, 12, 31),
        )
        self.assertEqual(
            renewal_start(term, datetime.date(2026, 9, 18)),
            datetime.date(2026, 9, 18),
        )

    def test_renewal_on_the_expiry_day_starts_tomorrow(self) -> None:
        """expires_on is inclusive: the member is still covered today."""
        term = make_term(
            self.member, self.tier,
            datetime.date(2026, 1, 1), datetime.date(2026, 9, 18),
        )
        self.assertEqual(
            renewal_start(term, datetime.date(2026, 9, 18)),
            datetime.date(2026, 9, 19),
        )


class LatestTermTests(TestCase):
    """The term a renewal continues from is the one that runs latest."""

    def setUp(self) -> None:
        self.member = Member.objects.create(
            first_name="Ada", last_name="Lovelace", email="ada@example.com"
        )
        self.tier = MembershipTier.objects.get(slug="individual")

    def test_no_terms(self) -> None:
        self.assertIsNone(latest_term([]))

    def test_a_short_comp_inside_a_long_term_does_not_win(self) -> None:
        """A comp that started later but ends sooner is not what is renewed."""
        long = make_term(
            self.member, self.tier,
            datetime.date(2026, 3, 17), datetime.date(2027, 3, 17),
        )
        make_term(
            self.member, self.tier,
            datetime.date(2026, 6, 25), datetime.date(2026, 7, 25),
        )
        self.assertEqual(latest_term(self.member.terms.all()), long)

    def test_equal_expiry_prefers_the_later_entry(self) -> None:
        make_term(
            self.member, self.tier,
            datetime.date(2026, 1, 1), datetime.date(2026, 12, 31),
        )
        second = make_term(
            self.member, self.tier,
            datetime.date(2026, 1, 1), datetime.date(2026, 12, 31),
        )
        self.assertEqual(latest_term(self.member.terms.all()), second)
