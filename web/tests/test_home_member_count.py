"""The home-page active-member count.

"Active" is Member.objects.active(): a member with a term whose
started_on..expires_on (both inclusive) covers today. The count is of
people, not terms, so a renewal that overlaps the term it replaces must not
count anyone twice.
"""

import datetime
from decimal import Decimal
from unittest import mock

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from audience.models import Member, MembershipTerm, MembershipTier


@mock.patch("web.views.get_coming_soon", return_value=[])
@mock.patch("web.views.get_now_showing", return_value=[])
class HomeMemberCountTests(TestCase):
    def setUp(self) -> None:
        self.today = timezone.localdate()
        self.tier = MembershipTier.objects.get(slug="individual")

    def _member(self, email: str, *terms: tuple[int, int]) -> Member:
        """A member with one term per (start, expiry) offset from today."""
        member: Member = Member.objects.create(
            first_name="A", last_name="B", email=email
        )
        for start, end in terms:
            MembershipTerm.objects.create(
                member=member,
                tier=self.tier,
                started_on=self.today + datetime.timedelta(days=start),
                expires_on=self.today + datetime.timedelta(days=end),
                price_paid=Decimal("60.00"),
            )
        return member

    def _count(self) -> int:
        count: int = self.client.get(reverse("home")).context["member_count"]
        return count

    def test_counts_a_member_whose_term_covers_today(
        self, _ns: mock.Mock, _cs: mock.Mock
    ) -> None:
        self._member("current@example.com", (-10, 10))
        self.assertEqual(self._count(), 1)

    def test_term_boundaries_are_inclusive(
        self, _ns: mock.Mock, _cs: mock.Mock
    ) -> None:
        self._member("starts@example.com", (0, 30))
        self._member("ends@example.com", (-30, 0))
        self.assertEqual(self._count(), 2)

    def test_skips_an_expired_term(self, _ns: mock.Mock, _cs: mock.Mock) -> None:
        self._member("lapsed@example.com", (-400, -1))
        self.assertEqual(self._count(), 0)

    def test_skips_a_term_that_has_not_started(
        self, _ns: mock.Mock, _cs: mock.Mock
    ) -> None:
        self._member("future@example.com", (1, 365))
        self.assertEqual(self._count(), 0)

    def test_skips_a_member_with_no_terms(self, _ns: mock.Mock, _cs: mock.Mock) -> None:
        self._member("never@example.com")
        self.assertEqual(self._count(), 0)

    def test_two_active_terms_count_once(self, _ns: mock.Mock, _cs: mock.Mock) -> None:
        self._member("renewed@example.com", (-10, 10), (-5, 360))
        self.assertEqual(self._count(), 1)

    def test_an_old_lapsed_term_does_not_hide_a_current_one(
        self, _ns: mock.Mock, _cs: mock.Mock
    ) -> None:
        self._member("returning@example.com", (-800, -400), (-10, 10))
        self.assertEqual(self._count(), 1)

    def test_mixed_roster(self, _ns: mock.Mock, _cs: mock.Mock) -> None:
        self._member("a@example.com", (-10, 10))
        self._member("b@example.com", (-10, 10), (-1, 400))
        self._member("c@example.com", (-400, -1))
        self._member("d@example.com", (5, 400))
        self._member("e@example.com")
        self.assertEqual(self._count(), 2)

    def test_the_count_is_one_query(self, _ns: mock.Mock, _cs: mock.Mock) -> None:
        self._member("a@example.com", (-10, 10), (-5, 360))
        self._member("b@example.com", (-10, 10))
        with self.assertNumQueries(1):
            self.assertEqual(Member.objects.active().count(), 2)


@mock.patch("web.views.get_coming_soon", return_value=[])
@mock.patch("web.views.get_now_showing", return_value=[])
class HomeMemberCountRenderTests(TestCase):
    def setUp(self) -> None:
        today = timezone.localdate()
        tier = MembershipTier.objects.get(slug="individual")
        self.members = []
        for i in range(3):
            member = Member.objects.create(
                first_name="M", last_name=str(i), email=f"m{i}@example.com"
            )
            MembershipTerm.objects.create(
                member=member,
                tier=tier,
                started_on=today - datetime.timedelta(days=10),
                expires_on=today + datetime.timedelta(days=10),
                price_paid=Decimal("60.00"),
            )
            self.members.append(member)

    def _html(self) -> str:
        return self.client.get(reverse("home")).content.decode()

    def test_renders_the_count_in_the_hero(
        self, _ns: mock.Mock, _cs: mock.Mock
    ) -> None:
        html = self._html()
        self.assertIn('class="hero-members"', html)
        self.assertIn('<span class="hero-members-count">3</span>', html)
        self.assertIn("members help to keep the lights on", html)

    def test_sits_under_the_hero_buttons(self, _ns: mock.Mock, _cs: mock.Mock) -> None:
        html = self._html()
        self.assertLess(html.index("Join Membership"), html.index("hero-members"))
        self.assertLess(html.index("hero-members"), html.index("</section>"))

    def test_one_member_reads_singular(self, _ns: mock.Mock, _cs: mock.Mock) -> None:
        Member.objects.exclude(pk=self.members[0].pk).delete()
        html = self._html()
        self.assertIn('<span class="hero-members-count">1</span>', html)
        self.assertIn("member helps to keep the lights on", html)

    def test_renders_nothing_with_no_active_members(
        self, _ns: mock.Mock, _cs: mock.Mock
    ) -> None:
        MembershipTerm.objects.all().delete()
        html = self._html()
        self.assertNotIn("hero-members-count", html)
        self.assertNotIn("keep the lights on", html)

    def test_star_is_hidden_from_screen_readers(
        self, _ns: mock.Mock, _cs: mock.Mock
    ) -> None:
        self.assertIn(
            '<span class="hero-members-star" aria-hidden="true">', self._html()
        )
