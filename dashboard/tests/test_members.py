import datetime
import json
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from audience.models import FreeAdmission, Member, MembershipTerm, MembershipTier
from dashboard.tests.helpers import make_staff

User = get_user_model()


def a_tier(slug="individual"):
    return MembershipTier.objects.get(slug=slug)


def make_member(first="Ada", last="Lovelace", email="ada@example.com", **kwargs):
    return Member.objects.create(
        first_name=first, last_name=last, email=email, **kwargs
    )


def give_term(member, days_left=100, tier=None):
    today = timezone.localdate()
    return MembershipTerm.objects.create(
        member=member,
        tier=tier or a_tier(),
        started_on=today - datetime.timedelta(days=30),
        expires_on=today + datetime.timedelta(days=days_left),
        price_paid=Decimal("60.00"),
    )


class MemberListTests(TestCase):
    def setUp(self) -> None:
        make_staff(username="s", password="pw12345")
        self.client.login(username="s", password="pw12345")

    def test_empty_state(self) -> None:
        html = self.client.get(reverse("dashboard:members")).content.decode()
        self.assertIn("empty-state", html)
        self.assertIn("No Members Yet", html)

    def test_rows_show_name_email_tier_and_expiry(self) -> None:
        member = make_member()
        give_term(member)
        html = self.client.get(reverse("dashboard:members")).content.decode()
        self.assertIn("Lovelace", html)
        self.assertIn("ada@example.com", html)
        self.assertIn("Individual", html)  # tier label, not the slug

    def test_status_pills(self) -> None:
        give_term(make_member(email="a@example.com"), days_left=200)
        give_term(make_member("Soon", "Expiring", "b@example.com"), days_left=5)
        make_member("No", "Terms", "c@example.com")
        html = self.client.get(reverse("dashboard:members")).content.decode()
        self.assertIn("Active", html)
        self.assertIn("Expiring soon", html)
        self.assertIn("Lapsed", html)

    def test_query_filter_matches_name_and_email(self) -> None:
        give_term(make_member("Ada", "Lovelace", "ada@example.com"))
        give_term(make_member("Grace", "Hopper", "grace@example.com"))

        by_name = self.client.get(
            reverse("dashboard:members"), {"q": "hopper"}
        ).content.decode()
        self.assertIn("Hopper", by_name)
        self.assertNotIn("Lovelace", by_name)

        by_email = self.client.get(
            reverse("dashboard:members"), {"q": "ada@"}
        ).content.decode()
        self.assertIn("Lovelace", by_email)
        self.assertNotIn("Hopper", by_email)

    def test_status_filter(self) -> None:
        # Surnames that appear nowhere in the page chrome: an assertNotIn
        # against the whole document is only meaningful if the sentinel
        # can't also arrive from a nav link or a column heading. (It was
        # "Rent" until the sidebar grew a "Rental Inquiries" link.)
        give_term(make_member("Cur", "Qwyllt", "current@example.com"))
        make_member("No", "Zzyzx", "never@example.com")

        active = self.client.get(
            reverse("dashboard:members"), {"status": "active"}
        ).content.decode()
        self.assertIn("Qwyllt", active)
        self.assertNotIn("Zzyzx", active)

        lapsed = self.client.get(
            reverse("dashboard:members"), {"status": "lapsed"}
        ).content.decode()
        self.assertIn("Zzyzx", lapsed)
        self.assertNotIn("Qwyllt", lapsed)

    def test_active_filter_includes_expiring_members(self) -> None:
        """Expiring soon is still active: the header count and the Active
        filter's rows must agree."""
        give_term(make_member("Long", "Wayoff", "long@example.com"), days_left=200)
        give_term(make_member("Soon", "Nearly", "soon@example.com"), days_left=5)
        make_member("No", "Zzyzx", "never@example.com")

        html = self.client.get(
            reverse("dashboard:members"), {"status": "active"}
        ).content.decode()
        self.assertIn("2 active members.", html)
        self.assertIn("Wayoff", html)
        self.assertIn("Nearly", html)
        self.assertNotIn("Zzyzx", html)

        body = self.client.get(
            reverse("dashboard:members_export"), {"status": "active"}
        ).content.decode()
        self.assertIn("long@example.com", body)
        self.assertIn("soon@example.com", body)
        self.assertNotIn("never@example.com", body)

    def test_an_early_renewal_is_not_listed_as_expiring(self) -> None:
        today = timezone.localdate()
        member = make_member("Re", "Newwell", "renew@example.com")
        give_term(member, days_left=10)
        renewal = MembershipTerm.objects.create(
            member=member,
            tier=a_tier(),
            started_on=today + datetime.timedelta(days=11),
            expires_on=today + datetime.timedelta(days=375),
            price_paid=Decimal("60.00"),
        )

        expiring = self.client.get(
            reverse("dashboard:members"), {"status": "expiring"}
        ).content.decode()
        self.assertNotIn("Newwell", expiring)

        roster = self.client.get(reverse("dashboard:members")).content.decode()
        self.assertNotIn("Expiring soon</span>", roster)
        # The Expires column shows where cover ends, not the old term's end.
        self.assertIn(f"{renewal.expires_on:%b} {renewal.expires_on.day}, ", roster)

    def test_future_only_members_have_their_own_status(self) -> None:
        today = timezone.localdate()
        member = make_member("Up", "Comingly", "upcoming@example.com")
        MembershipTerm.objects.create(
            member=member,
            tier=a_tier(),
            started_on=today + datetime.timedelta(days=10),
            expires_on=today + datetime.timedelta(days=375),
            price_paid=Decimal("60.00"),
        )
        make_member("No", "Zzyzx", "never@example.com")

        upcoming = self.client.get(
            reverse("dashboard:members"), {"status": "upcoming"}
        ).content.decode()
        self.assertIn("Comingly", upcoming)
        self.assertNotIn("Zzyzx", upcoming)
        self.assertIn('<option value="upcoming"', upcoming)
        self.assertIn("Not started yet</span>", upcoming)

        lapsed = self.client.get(
            reverse("dashboard:members"), {"status": "lapsed"}
        ).content.decode()
        self.assertNotIn("Comingly", lapsed)

    def test_unknown_status_filter_is_ignored(self) -> None:
        give_term(make_member())
        html = self.client.get(
            reverse("dashboard:members"), {"status": "nonsense"}
        ).content.decode()
        self.assertIn("Lovelace", html)

    def test_requires_staff(self) -> None:
        self.client.logout()
        self.assertEqual(
            self.client.get(reverse("dashboard:members")).status_code, 302
        )
        User.objects.create_user(username="p", password="pw12345", is_staff=False)
        self.client.login(username="p", password="pw12345")
        self.assertEqual(
            self.client.get(reverse("dashboard:members")).status_code, 403
        )

    def test_members_css_linked(self) -> None:
        html = self.client.get(reverse("dashboard:members")).content.decode()
        self.assertIn("dashboard/css/members.css", html)

    def test_sidebar_links_to_members(self) -> None:
        html = self.client.get(reverse("dashboard:home")).content.decode()
        self.assertIn(reverse("dashboard:members"), html)


class MemberCreateEditTests(TestCase):
    def setUp(self) -> None:
        make_staff(username="s", password="pw12345")
        self.client.login(username="s", password="pw12345")

    def test_get_create_form(self) -> None:
        html = self.client.get(reverse("dashboard:member_create")).content.decode()
        self.assertIn('id="member-form"', html)
        self.assertIn("Create Member", html)

    def test_post_create_valid(self) -> None:
        resp = self.client.post(
            reverse("dashboard:member_create"),
            {
                "first_name": "Ada",
                "last_name": "Lovelace",
                "email": "Ada@Example.com",
                "phone": "",
                "notes": "",
            },
        )
        self.assertEqual(resp.status_code, 200)
        member = Member.objects.get()
        self.assertEqual(member.email, "ada@example.com")

        triggers = json.loads(resp["HX-Trigger"])
        self.assertTrue(triggers["close-drawer"])
        self.assertEqual(triggers["dashboard-toast"]["kind"], "success")
        self.assertIn('hx-swap-oob="true"', resp.content.decode())

    def test_post_create_invalid_redisplays_the_form(self) -> None:
        resp = self.client.post(
            reverse("dashboard:member_create"),
            {"first_name": "Ada", "last_name": "Lovelace", "email": "not-an-email"},
        )
        self.assertEqual(resp.status_code, 200)
        self.assertIn('id="member-form"', resp.content.decode())
        self.assertEqual(Member.objects.count(), 0)

    def test_post_edit_updates(self) -> None:
        member = make_member()
        self.client.post(
            reverse("dashboard:member_edit", args=[member.pk]),
            {
                "first_name": "Ada",
                "last_name": "King",
                "email": "ada@example.com",
                "phone": "207-555-0100",
                "notes": "",
            },
        )
        member.refresh_from_db()
        self.assertEqual(member.last_name, "King")
        self.assertEqual(member.phone, "207-555-0100")

    def test_requires_staff(self) -> None:
        self.client.logout()
        self.assertEqual(
            self.client.get(reverse("dashboard:member_create")).status_code, 302
        )


class MemberDeleteTests(TestCase):
    def setUp(self) -> None:
        make_staff(username="s", password="pw12345")
        self.client.login(username="s", password="pw12345")

    def test_delete_removes_the_member_and_their_terms(self) -> None:
        member = make_member()
        give_term(member)
        resp = self.client.post(reverse("dashboard:member_delete", args=[member.pk]))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(Member.objects.count(), 0)
        self.assertEqual(MembershipTerm.objects.count(), 0)

    def test_delete_toasts(self) -> None:
        member = make_member()
        resp = self.client.post(reverse("dashboard:member_delete", args=[member.pk]))
        triggers = json.loads(resp["HX-Trigger"])
        self.assertEqual(triggers["dashboard-toast"]["kind"], "success")

    def test_confirm_copy_names_the_term_count(self) -> None:
        member = make_member()
        give_term(member)
        html = self.client.get(reverse("dashboard:members")).content.decode()
        self.assertIn("1 membership term", html)


class MemberExportTests(TestCase):
    def setUp(self) -> None:
        make_staff(username="s", password="pw12345")
        self.client.login(username="s", password="pw12345")

    def test_export_is_a_csv_attachment(self) -> None:
        resp = self.client.get(reverse("dashboard:members_export"))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp["Content-Type"], "text/csv")
        self.assertIn("attachment", resp["Content-Disposition"])
        self.assertIn("members.csv", resp["Content-Disposition"])

    def test_header_row(self) -> None:
        body = self.client.get(reverse("dashboard:members_export")).content.decode()
        self.assertTrue(
            body.startswith(
                "first_name,last_name,email,phone,tier,started_on,"
                "expires_on,price_paid,status"
            )
        )

    def test_one_row_per_member_from_the_latest_term(self) -> None:
        member = make_member()
        MembershipTerm.objects.create(
            member=member, tier=a_tier("individual"),
            started_on=datetime.date(2025, 1, 1),
            expires_on=datetime.date(2026, 1, 1), price_paid=Decimal("60.00"),
        )
        give_term(member, tier=a_tier("cinema-supporter"))  # newer

        rows = [
            r for r in self.client.get(
                reverse("dashboard:members_export")
            ).content.decode().splitlines() if r
        ]
        self.assertEqual(len(rows), 2)  # header + one member
        self.assertIn("cinema-supporter", rows[1])
        self.assertNotIn("individual", rows[1])

    def test_an_early_renewal_exports_as_active_with_its_dates(self) -> None:
        """The row's dates and status must describe the same membership."""
        today = timezone.localdate()
        member = make_member()
        give_term(member, days_left=10)
        renewal = MembershipTerm.objects.create(
            member=member,
            tier=a_tier(),
            started_on=today + datetime.timedelta(days=11),
            expires_on=today + datetime.timedelta(days=375),
            price_paid=Decimal("60.00"),
        )
        rows = (
            self.client.get(reverse("dashboard:members_export"))
            .content.decode()
            .splitlines()
        )
        self.assertTrue(rows[1].endswith(",active"), rows[1])
        self.assertIn(renewal.expires_on.isoformat(), rows[1])

    def test_a_comp_inside_a_longer_term_does_not_become_the_row(self) -> None:
        """The row is the term that runs latest, as Renew uses, so an
        expired comp is never exported beside an active status."""
        today = timezone.localdate()
        member = make_member()
        MembershipTerm.objects.create(
            member=member,
            tier=a_tier("family-plus"),
            started_on=today - datetime.timedelta(days=200),
            expires_on=today + datetime.timedelta(days=165),
            price_paid=Decimal("250.00"),
        )
        MembershipTerm.objects.create(
            member=member,
            tier=a_tier("individual"),
            started_on=today - datetime.timedelta(days=100),
            expires_on=today - datetime.timedelta(days=70),
            price_paid=Decimal("0.00"),
        )
        rows = (
            self.client.get(reverse("dashboard:members_export"))
            .content.decode()
            .splitlines()
        )
        self.assertIn("family-plus", rows[1])
        self.assertTrue(rows[1].endswith(",active"), rows[1])

    def test_a_member_with_no_terms_still_exports(self) -> None:
        make_member("No", "Terms", "never@example.com")
        rows = [
            r for r in self.client.get(
                reverse("dashboard:members_export")
            ).content.decode().splitlines() if r
        ]
        self.assertEqual(len(rows), 2)
        self.assertIn("lapsed", rows[1])

    def test_export_honours_the_status_filter(self) -> None:
        give_term(make_member("Cur", "Rent", "current@example.com"))
        make_member("No", "Terms", "never@example.com")
        body = self.client.get(
            reverse("dashboard:members_export"), {"status": "lapsed"}
        ).content.decode()
        self.assertIn("never@example.com", body)
        self.assertNotIn("current@example.com", body)

    def test_requires_staff(self) -> None:
        self.client.logout()
        self.assertEqual(
            self.client.get(reverse("dashboard:members_export")).status_code, 302
        )


class RosterOrderTests(TestCase):
    """The roster sorts by last name, then first name, wherever it is read.

    The free-admission annotation adds a GROUP BY, and Django drops
    `Meta.ordering` from grouped queries — so the order has to be explicit.
    """

    def setUp(self) -> None:
        make_staff(username="s", password="pw12345")
        self.client.login(username="s", password="pw12345")
        # Created out of order, so insertion (pk) order is not the answer.
        make_member("Ann", "Young", "ann@example.com")
        make_member("Zed", "Adams", "zed@example.com")
        make_member("Bob", "Adams", "bob@example.com")
        self.expected = ["Bob Adams", "Zed Adams", "Ann Young"]

    def test_members_page(self) -> None:
        resp = self.client.get(reverse("dashboard:members"))
        self.assertEqual([m.full_name for m in resp.context["members"]], self.expected)

    def test_htmx_refresh_after_a_change(self) -> None:
        resp = self.client.post(
            reverse("dashboard:member_create"),
            {"first_name": "Cy", "last_name": "Mann", "email": "cy@example.com"},
        )
        self.assertEqual(
            [m.full_name for m in resp.context["members"]],
            ["Bob Adams", "Zed Adams", "Cy Mann", "Ann Young"],
        )

    def test_csv_export(self) -> None:
        rows = (
            self.client.get(reverse("dashboard:members_export"))
            .content.decode()
            .splitlines()[1:]
        )
        self.assertEqual([" ".join(row.split(",")[:2]) for row in rows], self.expected)


class MemberRosterQueryCountTests(TestCase):
    """Pin the roster's query count so the tier N+1 can't come back quietly.

    Before this branch, tier was a plain string column and cost nothing
    extra to read. The FK it became is fetched through
    prefetch_related("terms__tier"), which should still answer the whole
    roster from a fixed, small number of queries — not one that grows with
    the number of members. Measured directly against this test with 8
    members each with a term: 7 queries — session lookup, auth user lookup,
    the member query (now carrying the free_used_this_month annotation,
    which joins the single free_admissions relation and rides along on this
    same query rather than adding one), the prefetched terms query, the
    prefetched tiers query, active_count's query for the header pill, and
    the house total's aggregate over FreeAdmission for the month. None of
    the seven scale with the member count. Confirmed by temporarily
    reverting the prefetch to plain "terms": query count jumped (one extra
    tier query per member) and this test failed as expected.
    """

    def setUp(self) -> None:
        make_staff(username="s", password="pw12345")
        self.client.login(username="s", password="pw12345")

    def test_roster_query_count_does_not_scale_with_member_count(self) -> None:
        for i in range(8):
            member = make_member(
                first=f"First{i}", last=f"Last{i}", email=f"m{i}@example.com"
            )
            give_term(member)
            if i % 2 == 0:
                FreeAdmission.objects.create(member=member)

        # 8 includes the sidebar's new-voicemail badge count.
        with self.assertNumQueries(8):
            self.client.get(reverse("dashboard:members"))
