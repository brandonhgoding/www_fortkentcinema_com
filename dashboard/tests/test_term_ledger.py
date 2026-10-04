"""The cross-member term ledger: who is about to lapse, and what sold."""

import datetime
from decimal import Decimal

from audience.models import Member, MembershipTerm, MembershipTier
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

User = get_user_model()


class LedgerTestCase(TestCase):
    def setUp(self) -> None:
        User.objects.create_user(username="s", password="pw12345", is_staff=True)
        self.client.login(username="s", password="pw12345")
        self.today = timezone.localdate()

    def term(self, last_name, slug, start, end, price="60.00", **kwargs):
        member = Member.objects.create(
            first_name="A",
            last_name=last_name,
            email=f"{last_name.lower()}@example.com",
        )
        return MembershipTerm.objects.create(
            member=member,
            tier=MembershipTier.objects.get(slug=slug),
            started_on=start,
            expires_on=end,
            price_paid=Decimal(price),
            **kwargs,
        )

    def get(self, **params):
        return self.client.get(reverse("dashboard:terms"), params).content.decode()


class StaffOnlyTests(TestCase):
    def test_ledger_and_export_require_staff(self) -> None:
        for url in (reverse("dashboard:terms"), reverse("dashboard:terms_export")):
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code, 302)


class WindowFilterTests(LedgerTestCase):
    """Sentinel surnames are nonsense words on purpose: "Expired" and
    "Current" also appear in the filter dropdown and the expiry pill, so an
    assertNotIn against the whole document would fail on page chrome rather
    than on a row that should have been filtered out."""

    def setUp(self) -> None:
        super().setUp()
        day = datetime.timedelta(days=1)
        self.current = self.term(
            "Nowden", "individual",
            self.today - 200 * day, self.today + 200 * day,
        )
        self.expiring = self.term(
            "Soonby", "individual",
            self.today - 350 * day, self.today + 10 * day,
        )
        self.expired = self.term(
            "Pastly", "individual",
            self.today - 400 * day, self.today - 30 * day,
        )
        self.future = self.term(
            "Laterby", "individual",
            self.today + 30 * day, self.today + 395 * day,
        )

    def test_all_terms_by_default(self) -> None:
        html = self.get()
        for name in ("Nowden", "Soonby", "Pastly", "Laterby"):
            self.assertIn(name, html)

    def test_current_excludes_expired_and_future(self) -> None:
        html = self.get(window="current")
        self.assertIn("Nowden", html)
        self.assertIn("Soonby", html)
        self.assertNotIn("Pastly", html)
        self.assertNotIn("Laterby", html)

    def test_expiring_soon_is_a_subset_of_current(self) -> None:
        """An already-expired term is expired, not expiring."""
        html = self.get(window="expiring")
        self.assertIn("Soonby", html)
        self.assertNotIn("Pastly", html)
        self.assertNotIn("Nowden", html)

    def test_expiring_skips_a_term_already_renewed(self) -> None:
        """A renewal that continues the term means nobody is about to
        lapse, so there is no one to chase."""
        day = datetime.timedelta(days=1)
        MembershipTerm.objects.create(
            member=self.expiring.member,
            tier=self.expiring.tier,
            started_on=self.expiring.expires_on + day,
            expires_on=self.expiring.expires_on + 365 * day,
            price_paid=Decimal("60.00"),
        )
        gappy = self.term(
            "Gapwell",
            "individual",
            self.today - 350 * day,
            self.today + 10 * day,
        )
        MembershipTerm.objects.create(
            member=gappy.member,
            tier=gappy.tier,
            started_on=gappy.expires_on + 2 * day,
            expires_on=gappy.expires_on + 366 * day,
            price_paid=Decimal("60.00"),
        )
        html = self.get(window="expiring")
        self.assertNotIn("Soonby", html)
        self.assertIn("Gapwell", html)

    def test_expired(self) -> None:
        html = self.get(window="expired")
        self.assertIn("Pastly", html)
        self.assertNotIn("Nowden", html)

    def test_future(self) -> None:
        html = self.get(window="future")
        self.assertIn("Laterby", html)
        self.assertNotIn("Nowden", html)

    def test_unknown_window_is_ignored_rather_than_erroring(self) -> None:
        html = self.get(window="nonsense")
        self.assertIn("Nowden", html)
        self.assertIn("Pastly", html)

    def test_expiring_lists_soonest_first(self) -> None:
        """The question this window answers is "who do I chase first"."""
        html = self.get(window="current")
        self.assertLess(html.index("Soonby"), html.index("Nowden"))


class OtherFilterTests(LedgerTestCase):
    def test_tier_filter(self) -> None:
        self.term(
            "Indy", "individual",
            datetime.date(2026, 1, 1), datetime.date(2026, 12, 31),
        )
        self.term(
            "Fam", "family",
            datetime.date(2026, 1, 1), datetime.date(2026, 12, 31),
        )
        html = self.get(tier="family")
        self.assertIn("Fam", html)
        self.assertNotIn("Indy", html)

    def test_search_matches_name_and_email(self) -> None:
        self.term(
            "Lovelace", "individual",
            datetime.date(2026, 1, 1), datetime.date(2026, 12, 31),
        )
        self.term(
            "Hopper", "individual",
            datetime.date(2026, 1, 1), datetime.date(2026, 12, 31),
        )
        self.assertIn("Hopper", self.get(q="hopper"))
        self.assertNotIn("Hopper", self.get(q="lovelace@"))

    def test_started_on_date_range(self) -> None:
        self.term(
            "Older", "individual",
            datetime.date(2025, 3, 1), datetime.date(2026, 2, 28),
        )
        self.term(
            "Newer", "individual",
            datetime.date(2026, 3, 1), datetime.date(2027, 2, 28),
        )
        html = self.get(**{"from": "2026-01-01", "to": "2026-12-31"})
        self.assertIn("Newer", html)
        self.assertNotIn("Older", html)

    def test_a_typo_in_a_date_is_dropped_rather_than_500ing(self) -> None:
        """These are hand-editable URL parameters."""
        self.term(
            "Anyone", "individual",
            datetime.date(2026, 1, 1), datetime.date(2026, 12, 31),
        )
        resp = self.client.get(
            reverse("dashboard:terms"), {"from": "not-a-date", "to": "13/13/2026"}
        )
        self.assertEqual(resp.status_code, 200)
        self.assertIn("Anyone", resp.content.decode())


class RevenueTests(LedgerTestCase):
    def test_total_counts_every_term_not_every_member(self) -> None:
        """A member who has renewed three times contributed three times."""
        member = Member.objects.create(
            first_name="Ada", last_name="Lovelace", email="ada@example.com"
        )
        tier = MembershipTier.objects.get(slug="individual")
        for year in (2024, 2025, 2026):
            MembershipTerm.objects.create(
                member=member, tier=tier,
                started_on=datetime.date(year, 1, 1),
                expires_on=datetime.date(year, 12, 31),
                price_paid=Decimal("60.00"),
            )
        html = self.get()
        self.assertIn("3 terms", html)
        self.assertIn("$180", html)

    def test_total_follows_the_filters(self) -> None:
        self.term(
            "Cheap", "individual",
            datetime.date(2025, 1, 1), datetime.date(2025, 12, 31), price="60.00",
        )
        self.term(
            "Dear", "individual",
            datetime.date(2026, 1, 1), datetime.date(2026, 12, 31), price="250.00",
        )
        html = self.get(**{"from": "2026-01-01"})
        self.assertIn("1 term", html)
        self.assertIn("$250", html)

    def test_empty_result_reports_zero_not_none(self) -> None:
        html = self.get(q="nobody-by-that-name")
        self.assertIn("0 terms", html)
        self.assertIn("$0", html)


class ExportTests(LedgerTestCase):
    def test_one_row_per_term_with_the_same_filters(self) -> None:
        member = Member.objects.create(
            first_name="Ada", last_name="Lovelace", email="ada@example.com"
        )
        tier = MembershipTier.objects.get(slug="individual")
        for year in (2025, 2026):
            MembershipTerm.objects.create(
                member=member, tier=tier,
                started_on=datetime.date(year, 1, 1),
                expires_on=datetime.date(year, 12, 31),
                price_paid=Decimal("60.00"),
            )

        body = self.client.get(
            reverse("dashboard:terms_export")
        ).content.decode()
        rows = [r for r in body.splitlines() if r.strip()]
        self.assertEqual(len(rows), 3)  # header + two terms
        self.assertIn("first_name,last_name,email,tier", rows[0])

        filtered = self.client.get(
            reverse("dashboard:terms_export"), {"from": "2026-01-01"}
        ).content.decode()
        self.assertEqual(
            len([r for r in filtered.splitlines() if r.strip()]), 2
        )

    def test_is_a_csv_attachment(self) -> None:
        resp = self.client.get(reverse("dashboard:terms_export"))
        self.assertEqual(resp["Content-Type"], "text/csv")
        self.assertIn("membership-terms.csv", resp["Content-Disposition"])


class EndOfTimeTests(LedgerTestCase):
    def test_a_term_running_to_date_max_renders_in_every_window(self) -> None:
        self.term("Forever", "individual", self.today, datetime.date.max)
        for window in ("", "current", "expiring", "expired", "future"):
            with self.subTest(window=window):
                resp = self.client.get(reverse("dashboard:terms"), {"window": window})
                self.assertEqual(resp.status_code, 200)

    def test_the_roster_and_member_page_render_it(self) -> None:
        term = self.term("Forever", "individual", self.today, datetime.date.max)
        for url in (
            reverse("dashboard:members"),
            reverse("dashboard:member_detail", args=[term.member_id]),
            reverse("dashboard:members_export"),
        ):
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code, 200)
