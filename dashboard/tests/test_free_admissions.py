import datetime
from decimal import Decimal
from unittest import mock

from audience.models import FreeAdmission, Member, MembershipTerm, MembershipTier
from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from dashboard.tests.helpers import make_staff


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


def give_expired_term(member, slug="family-plus"):
    today = timezone.localdate()
    return MembershipTerm.objects.create(
        member=member,
        tier=MembershipTier.objects.get(slug=slug),
        started_on=today - datetime.timedelta(days=400),
        expires_on=today - datetime.timedelta(days=30),
        price_paid=Decimal("120.00"),
    )


class StaffClient(TestCase):
    def setUp(self) -> None:
        self.staff = make_staff(
            username="s", password="pw12345"
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
        """A member whose family-plus term *expired* — the tier grants 4,
        but a lapsed membership carries no benefit."""
        member = make_member()
        give_expired_term(member, "family-plus")
        html = self.roster()
        self.assertNotIn("Redeem", html)
        self.assertNotIn("0 / 4", html)

    def test_a_member_with_no_term_at_all_shows_no_button(self) -> None:
        make_member()
        self.assertNotIn("Redeem", self.roster())

    def test_over_allowance_is_visible(self) -> None:
        member = make_member()
        give_term(member, "cinema-supporter")
        FreeAdmission.objects.create(member=member)
        FreeAdmission.objects.create(member=member)
        self.assertIn("2 / 1", self.roster())


class AllowanceBoundaryTests(StaffClient):
    """`>` styles "over"; `>=` fires the confirm. At exactly the allowance,
    the member is *at* the limit, not over it — but the next redemption
    must still warn. Nothing previously checked the class or the attribute
    themselves, only the "N / M" text, so flipping either operator would
    have passed the roster tests silently.

    The confirm-warning check looks for text unique to the redeem button's
    payload ("Monthly allowance already used") rather than the bare
    `data-dashboard-confirm` attribute, since the Delete button on every
    row always carries that attribute regardless of allowance.
    """

    CONFIRM_TITLE = "Monthly allowance already used"

    def roster(self) -> str:
        return self.client.get(reverse("dashboard:members")).content.decode()

    def test_at_exactly_the_allowance_is_not_styled_over(self) -> None:
        member = make_member()
        give_term(member, "cinema-supporter")  # allowance 1
        FreeAdmission.objects.create(member=member)
        html = self.roster()
        self.assertIn("1 / 1", html)
        self.assertNotIn("freeCount--over", html)

    def test_at_exactly_the_allowance_the_button_warns(self) -> None:
        member = make_member()
        give_term(member, "cinema-supporter")  # allowance 1
        FreeAdmission.objects.create(member=member)
        self.assertIn(self.CONFIRM_TITLE, self.roster())

    def test_strictly_over_is_styled_over(self) -> None:
        member = make_member()
        give_term(member, "cinema-supporter")  # allowance 1
        FreeAdmission.objects.create(member=member)
        FreeAdmission.objects.create(member=member)
        self.assertIn("freeCount--over", self.roster())

    def test_below_the_allowance_the_button_does_not_warn(self) -> None:
        give_term(make_member(), "cinema-supporter")  # allowance 1, 0 used
        self.assertNotIn(self.CONFIRM_TITLE, self.roster())


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


class RosterCountJoinTests(StaffClient):
    """The roster's count joins only this month's redemptions.

    Filtering the Count after the join would pull every redemption ever
    recorded into the grouped query — a table that only grows.
    """

    def test_the_month_is_in_the_join_condition(self) -> None:
        from django.db import connection
        from django.test.utils import CaptureQueriesContext

        give_term(make_member(), "family-plus")
        with CaptureQueriesContext(connection) as ctx:
            self.client.get(reverse("dashboard:members"))
        roster_sql = next(
            q["sql"] for q in ctx.captured_queries if "COUNT(DISTINCT" in q["sql"]
        )
        join = roster_sql.split("JOIN", 1)[1].split("GROUP BY", 1)[0]
        on_clause = join.split("WHERE", 1)[0]
        self.assertIn("redeemed_on", on_clause)


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

    def test_the_swapped_back_list_shows_the_incremented_count(self) -> None:
        """`_member_list_response` re-runs member_roster, so the count the
        person at the counter sees should move without a page reload."""
        before = self.client.get(reverse("dashboard:members")).content.decode()
        self.assertIn("0 / 1", before)

        after = self.client.post(self.url).content.decode()
        self.assertIn("1 / 1", after)

    def test_redeeming_from_a_filtered_roster_keeps_the_filter(self) -> None:
        """The Redeem button's `hx-include=".memberFilters"` carries the
        filter form's fields along with the POST, so the swapped-back
        list stays filtered to whoever the box office was looking at
        instead of reverting to the full roster. The test posts `q`
        directly rather than driving htmx, since that is what the
        browser sends once hx-include picks the field up."""
        other = make_member("Someone", "Else", "else@example.com")
        give_term(other, "family-plus")

        html = self.client.post(
            self.url, {"q": self.member.last_name}
        ).content.decode()
        self.assertIn(self.member.last_name, html)
        self.assertNotIn(other.last_name, html)

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


class DetailPanelTests(StaffClient):
    def setUp(self) -> None:
        super().setUp()
        self.member = make_member()
        give_term(self.member, "family-plus")
        self.url = reverse("dashboard:member_detail", args=[self.member.pk])

    def page(self) -> str:
        return self.client.get(self.url).content.decode()

    def test_groups_by_month_with_a_used_over_allowance_header(self) -> None:
        # Created with an August row sandwiched between two September
        # ones, so creation order (Sep, Aug, Sep) differs from date order.
        # `FreeAdmission.Meta.ordering` is `-redeemed_on` today, which
        # always keeps same-month rows contiguous regardless of creation
        # order, so this alone would not catch a sequential-scan bug — the
        # ordering override below is what actually exercises it (see
        # comment there).
        FreeAdmission.objects.create(
            member=self.member, redeemed_on=datetime.date(2026, 9, 14)
        )
        FreeAdmission.objects.create(
            member=self.member, redeemed_on=datetime.date(2026, 8, 30)
        )
        FreeAdmission.objects.create(
            member=self.member, redeemed_on=datetime.date(2026, 9, 6)
        )

        # `_free_admission_months` must not depend on same-month rows
        # being contiguous — only on `Meta.ordering` giving newest-first.
        # Force ordering by creation order (Sep, Aug, Sep — not
        # month-contiguous) to simulate a future reordering (e.g. to
        # "most recently entered first") and prove the grouping survives
        # it. Without this override, `-redeemed_on` sorts strictly by
        # date and is always month-contiguous, so the bug this test
        # guards against would slip past it.
        with mock.patch.object(FreeAdmission._meta, "ordering", ["created_at"]):
            response = self.client.get(self.url)
        html = response.content.decode()
        self.assertIn("September 2026", html)
        self.assertIn("2 of 4 used", html)

        # `assertIn` above can't tell two correct groups from three broken
        # ones — it would still find "September 2026" and "2 of 4 used"
        # somewhere on the page either way. Assert on the grouping object
        # itself: two months, with both September redemptions under one
        # and the August redemption under the other.
        months = response.context["free_admission_months"]
        self.assertEqual(len(months), 2)
        by_key = {month["key"]: month for month in months}
        self.assertEqual(len(by_key[(2026, 9)]["admissions"]), 2)
        self.assertEqual(len(by_key[(2026, 8)]["admissions"]), 1)

    def test_separates_months(self) -> None:
        FreeAdmission.objects.create(
            member=self.member, redeemed_on=datetime.date(2026, 9, 2)
        )
        FreeAdmission.objects.create(
            member=self.member, redeemed_on=datetime.date(2026, 8, 30)
        )
        html = self.page()
        self.assertIn("September 2026", html)
        self.assertIn("August 2026", html)

    def test_newest_month_first(self) -> None:
        FreeAdmission.objects.create(
            member=self.member, redeemed_on=datetime.date(2026, 8, 30)
        )
        FreeAdmission.objects.create(
            member=self.member, redeemed_on=datetime.date(2026, 9, 2)
        )
        html = self.page()
        self.assertLess(html.index("September 2026"), html.index("August 2026"))

    def test_shows_who_recorded_it(self) -> None:
        # A username unlikely to occur by accident elsewhere on the page —
        # unlike `self.staff` (username "s"), which is a single letter that
        # appears in ordinary markup and words regardless of whether
        # `recorded_by` is ever rendered.
        recorder = User.objects.create_user(username="ouellette_m", password="pw12345")
        FreeAdmission.objects.create(member=self.member, recorded_by=recorder)
        self.assertContains(self.client.get(self.url), "ouellette_m", count=1)

    def test_empty_state(self) -> None:
        self.assertIn("No free admissions yet", self.page())


class DetailPanelZeroAllowanceTests(StaffClient):
    """A lapsed or zero-allowance member's month header must not claim an
    allowance they don't have — the roster shows "—" rather than "0 / 0"
    for the same reason."""

    def test_lapsed_member_with_history_has_no_of_m(self) -> None:
        member = make_member()
        give_expired_term(member, "family-plus")
        FreeAdmission.objects.create(
            member=member, redeemed_on=datetime.date(2026, 8, 12)
        )
        FreeAdmission.objects.create(
            member=member, redeemed_on=datetime.date(2026, 8, 20)
        )
        html = self.client.get(
            reverse("dashboard:member_detail", args=[member.pk])
        ).content.decode()
        self.assertIn("August 2026", html)
        self.assertIn("2 used", html)
        self.assertNotIn("of 0 used", html)


class DeleteRedemptionTests(StaffClient):
    def setUp(self) -> None:
        super().setUp()
        self.member = make_member()
        give_term(self.member, "family-plus")
        self.admission = FreeAdmission.objects.create(member=self.member)
        self.url = reverse(
            "dashboard:free_admission_delete", args=[self.admission.pk]
        )

    def test_deletes_it(self) -> None:
        self.client.post(self.url)
        self.assertEqual(FreeAdmission.objects.count(), 0)

    def test_leaves_other_redemptions_alone(self) -> None:
        other = FreeAdmission.objects.create(
            member=self.member, redeemed_on=datetime.date(2026, 8, 1)
        )
        self.client.post(self.url)
        self.assertTrue(FreeAdmission.objects.filter(pk=other.pk).exists())

    def test_swaps_the_panel_back(self) -> None:
        html = self.client.post(self.url).content.decode()
        self.assertIn('id="free-admission-list"', html)
        self.assertIn("hx-swap-oob", html)

    def test_swapped_back_panel_shows_the_decremented_count(self) -> None:
        """The panel that comes back is recomputed after the delete, not
        the one from before it — so its count reflects the row that's
        gone."""
        FreeAdmission.objects.create(
            member=self.member, redeemed_on=self.admission.redeemed_on
        )
        before = self.page()
        self.assertIn("2 of 4 used", before)

        html = self.client.post(self.url).content.decode()
        self.assertIn("1 of 4 used", html)
        self.assertNotIn("2 of 4 used", html)

    def page(self) -> str:
        return self.client.get(
            reverse("dashboard:member_detail", args=[self.member.pk])
        ).content.decode()

    def test_toasts(self) -> None:
        self.assertIn("dashboard-toast", self.client.post(self.url)["HX-Trigger"])

    def test_requires_staff(self) -> None:
        self.client.logout()
        self.assertEqual(self.client.post(self.url).status_code, 302)


class MemberPageQueryCountTests(StaffClient):
    """The member page answers every row from a fixed number of queries.

    It used to read the terms twice (a prefetch, then a fresh select for
    the term list) and fetch each redemption's recorded_by separately.
    Five now: session, user, the member, their redemptions with who
    recorded them, and their terms with each tier.
    """

    def setUp(self) -> None:
        super().setUp()
        self.member = make_member()
        self.url = reverse("dashboard:member_detail", args=[self.member.pk])

    def add_rows(self, n: int) -> None:
        today = timezone.localdate()
        for i in range(n):
            recorder = User.objects.create_user(
                username=f"recorder-{FreeAdmission.objects.count()}"
            )
            FreeAdmission.objects.create(member=self.member, recorded_by=recorder)
            MembershipTerm.objects.create(
                member=self.member,
                tier=MembershipTier.objects.get(slug="cinema-supporter"),
                started_on=today - datetime.timedelta(days=400 * (i + 1)),
                expires_on=today - datetime.timedelta(days=400 * i + 40),
                price_paid=Decimal("120.00"),
            )

    def test_query_count_is_fixed(self) -> None:
        self.add_rows(1)
        # 6 includes the sidebar's new-voicemail badge count.
        with self.assertNumQueries(6):
            self.client.get(self.url)
        self.add_rows(4)
        with self.assertNumQueries(6):
            self.client.get(self.url)
