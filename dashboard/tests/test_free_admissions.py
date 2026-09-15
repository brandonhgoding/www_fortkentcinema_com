import datetime
from decimal import Decimal

from audience.models import FreeAdmission, Member, MembershipTerm, MembershipTier
from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone


def make_member(first="Marguerite", last="Ouellette", email="m.o@example.com"):
    return Member.objects.create(first_name=first, last_name=last, email=email)


def give_term(member, slug="cinema-supporter"):
    today = timezone.localdate()
    return MembershipTerm.objects.create(
        member=member,
        tier=MembershipTier.objects.get(slug=slug),
        started_on=today - datetime.timedelta(days=30),
        expires_on=today + datetime.timedelta(days=300),
        price_paid=Decimal("120.00"),
    )


class StaffClient(TestCase):
    def setUp(self) -> None:
        self.staff = User.objects.create_user(
            username="s", password="pw12345", is_staff=True
        )
        self.client.login(username="s", password="pw12345")


class RosterColumnTests(StaffClient):
    def roster(self) -> str:
        return self.client.get(reverse("dashboard:members")).content.decode()

    def test_shows_used_over_allowance(self) -> None:
        give_term(make_member(), "cinema-supporter")
        self.assertIn("0 / 1", self.roster())

    def test_counts_this_months_redemptions(self) -> None:
        member = make_member()
        give_term(member, "family-plus")
        FreeAdmission.objects.create(member=member)
        FreeAdmission.objects.create(member=member)
        self.assertIn("2 / 4", self.roster())

    def test_last_months_redemptions_do_not_count(self) -> None:
        member = make_member()
        give_term(member, "family-plus")
        first_of_month = timezone.localdate().replace(day=1)
        FreeAdmission.objects.create(
            member=member, redeemed_on=first_of_month - datetime.timedelta(days=1)
        )
        self.assertIn("0 / 4", self.roster())

    def test_a_tier_granting_none_shows_a_dash_and_no_button(self) -> None:
        give_term(make_member(), "individual")
        html = self.roster()
        self.assertNotIn("0 / 0", html)
        self.assertNotIn("Redeem", html)

    def test_a_lapsed_member_shows_no_button(self) -> None:
        make_member()
        self.assertNotIn("Redeem", self.roster())

    def test_over_allowance_is_visible(self) -> None:
        member = make_member()
        give_term(member, "cinema-supporter")
        FreeAdmission.objects.create(member=member)
        FreeAdmission.objects.create(member=member)
        self.assertIn("2 / 1", self.roster())


class BothCountingPathsAgreeTests(StaffClient):
    """The roster counts in SQL; the detail page counts in Python.

    Two implementations of "this calendar month" is two chances to get the
    boundary wrong in different directions, so this pins them against one
    another on the same fixture rather than trusting that each one's own
    boundary test was enough.
    """

    def test_they_report_the_same_number(self) -> None:
        member = make_member()
        give_term(member, "family-plus")
        first_of_month = timezone.localdate().replace(day=1)
        FreeAdmission.objects.create(member=member, redeemed_on=first_of_month)
        FreeAdmission.objects.create(member=member, redeemed_on=timezone.localdate())
        FreeAdmission.objects.create(
            member=member, redeemed_on=first_of_month - datetime.timedelta(days=1)
        )

        from dashboard.member_views import member_roster

        request = self.client.get(reverse("dashboard:members")).wsgi_request
        annotated = {m.pk: m.free_used_this_month for m in member_roster(request)[0]}

        today = timezone.localdate()
        self.assertEqual(
            annotated[member.pk],
            member.free_admissions_in(today.year, today.month),
        )
        self.assertEqual(annotated[member.pk], 2)


class RedeemTests(StaffClient):
    def setUp(self) -> None:
        super().setUp()
        self.member = make_member()
        give_term(self.member, "cinema-supporter")
        self.url = reverse(
            "dashboard:free_admission_redeem", args=[self.member.pk]
        )

    def test_records_a_redemption(self) -> None:
        self.client.post(self.url)
        self.assertEqual(self.member.free_admissions.count(), 1)

    def test_dated_today(self) -> None:
        self.client.post(self.url)
        self.assertEqual(
            self.member.free_admissions.first().redeemed_on, timezone.localdate()
        )

    def test_records_who_did_it(self) -> None:
        self.client.post(self.url)
        self.assertEqual(
            self.member.free_admissions.first().recorded_by, self.staff
        )

    def test_swaps_the_list_back(self) -> None:
        html = self.client.post(self.url).content.decode()
        self.assertIn('id="member-list"', html)
        self.assertIn("hx-swap-oob", html)

    def test_toasts(self) -> None:
        resp = self.client.post(self.url)
        self.assertIn("dashboard-toast", resp["HX-Trigger"])

    def test_allows_going_over_the_allowance(self) -> None:
        """Staff judgement wins; the UI warns, the server does not refuse."""
        self.client.post(self.url)
        self.client.post(self.url)
        self.assertEqual(self.member.free_admissions.count(), 2)

    def test_get_is_not_allowed(self) -> None:
        self.assertEqual(self.client.get(self.url).status_code, 405)

    def test_requires_staff(self) -> None:
        self.client.logout()
        self.assertEqual(self.client.post(self.url).status_code, 302)


class HouseTotalTests(StaffClient):
    def test_counts_every_member_this_month(self) -> None:
        for i in range(3):
            member = make_member(f"F{i}", f"L{i}", f"m{i}@example.com")
            give_term(member, "family-plus")
            FreeAdmission.objects.create(member=member)
        html = self.client.get(reverse("dashboard:members")).content.decode()
        self.assertIn("3 free admissions given", html)

    def test_ignores_the_roster_filters(self) -> None:
        """A house figure, not a total of the rows on screen."""
        for i in range(3):
            member = make_member(f"F{i}", f"L{i}", f"m{i}@example.com")
            give_term(member, "family-plus")
            FreeAdmission.objects.create(member=member)
        html = self.client.get(
            reverse("dashboard:members"), {"q": "L1"}
        ).content.decode()
        self.assertIn("3 free admissions given", html)

    def test_singular(self) -> None:
        member = make_member()
        give_term(member, "family-plus")
        FreeAdmission.objects.create(member=member)
        html = self.client.get(reverse("dashboard:members")).content.decode()
        self.assertIn("1 free admission given", html)

    def test_last_month_does_not_count(self) -> None:
        member = make_member()
        give_term(member, "family-plus")
        first_of_month = timezone.localdate().replace(day=1)
        FreeAdmission.objects.create(
            member=member, redeemed_on=first_of_month - datetime.timedelta(days=1)
        )
        html = self.client.get(reverse("dashboard:members")).content.decode()
        self.assertIn("0 free admissions given", html)
