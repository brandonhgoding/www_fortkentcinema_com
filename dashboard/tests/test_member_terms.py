import datetime
import json
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from audience.models import Member, MembershipTerm

User = get_user_model()


class MemberDetailTests(TestCase):
    def setUp(self) -> None:
        User.objects.create_user(username="s", password="pw12345", is_staff=True)
        self.client.login(username="s", password="pw12345")
        self.member = Member.objects.create(
            first_name="Ada",
            last_name="Lovelace",
            email="ada@example.com",
            phone="207-555-0100",
        )

    def test_shows_contact_details(self) -> None:
        html = self.client.get(
            reverse("dashboard:member_detail", args=[self.member.pk])
        ).content.decode()
        self.assertIn("Ada Lovelace", html)
        self.assertIn("ada@example.com", html)
        self.assertIn("207-555-0100", html)

    def test_lists_terms_newest_first_with_tier_labels(self) -> None:
        MembershipTerm.objects.create(
            member=self.member, tier="individual",
            started_on=datetime.date(2025, 1, 1),
            expires_on=datetime.date(2026, 1, 1), price_paid=Decimal("60.00"),
        )
        MembershipTerm.objects.create(
            member=self.member, tier="cinema-supporter",
            started_on=datetime.date(2026, 1, 1),
            expires_on=datetime.date(2027, 1, 1), price_paid=Decimal("120.00"),
        )
        html = self.client.get(
            reverse("dashboard:member_detail", args=[self.member.pk])
        ).content.decode()
        self.assertLess(html.index("Cinema Supporter"), html.index("Individual"))

    def test_empty_terms_state(self) -> None:
        html = self.client.get(
            reverse("dashboard:member_detail", args=[self.member.pk])
        ).content.decode()
        self.assertIn("No membership terms yet", html)

    def test_missing_member_is_404(self) -> None:
        self.assertEqual(
            self.client.get(
                reverse("dashboard:member_detail", args=[99999])
            ).status_code,
            404,
        )

    def test_requires_staff(self) -> None:
        self.client.logout()
        self.assertEqual(
            self.client.get(
                reverse("dashboard:member_detail", args=[self.member.pk])
            ).status_code,
            302,
        )


class TermCreateTests(TestCase):
    def setUp(self) -> None:
        User.objects.create_user(username="s", password="pw12345", is_staff=True)
        self.client.login(username="s", password="pw12345")
        self.member = Member.objects.create(
            first_name="Ada", last_name="Lovelace", email="ada@example.com"
        )

    def test_get_form(self) -> None:
        html = self.client.get(
            reverse("dashboard:term_create", args=[self.member.pk])
        ).content.decode()
        self.assertIn('id="term-form"', html)
        self.assertIn("Add Term", html)

    def test_renewal_needs_only_a_tier_and_a_start_date(self) -> None:
        resp = self.client.post(
            reverse("dashboard:term_create", args=[self.member.pk]),
            {"tier": "individual", "started_on": "2026-09-11",
             "expires_on": "", "price_paid": "", "purchased_at": "", "notes": ""},
        )
        self.assertEqual(resp.status_code, 200)
        term = MembershipTerm.objects.get()
        self.assertEqual(term.member, self.member)
        self.assertEqual(term.expires_on, datetime.date(2027, 9, 11))
        self.assertEqual(term.price_paid, Decimal("60.00"))

        triggers = json.loads(resp["HX-Trigger"])
        self.assertEqual(triggers["dashboard-toast"]["kind"], "success")

    def test_invalid_tier_redisplays_the_form(self) -> None:
        resp = self.client.post(
            reverse("dashboard:term_create", args=[self.member.pk]),
            {"tier": "invented", "started_on": "2026-09-11"},
        )
        self.assertIn('id="term-form"', resp.content.decode())
        self.assertEqual(MembershipTerm.objects.count(), 0)

    def test_a_second_term_makes_a_lapsed_member_active(self) -> None:
        today = timezone.localdate()
        MembershipTerm.objects.create(
            member=self.member, tier="individual",
            started_on=today - datetime.timedelta(days=800),
            expires_on=today - datetime.timedelta(days=400),
            price_paid=Decimal("60.00"),
        )
        self.assertFalse(self.member.is_active)

        self.client.post(
            reverse("dashboard:term_create", args=[self.member.pk]),
            {"tier": "individual", "started_on": today.isoformat(),
             "expires_on": "", "price_paid": "", "purchased_at": "", "notes": ""},
        )
        self.member.refresh_from_db()
        self.assertTrue(self.member.is_active)
        self.assertEqual(self.member.terms.count(), 2)

    def test_requires_staff(self) -> None:
        self.client.logout()
        self.assertEqual(
            self.client.get(
                reverse("dashboard:term_create", args=[self.member.pk])
            ).status_code,
            302,
        )


class TermEditDeleteTests(TestCase):
    def setUp(self) -> None:
        User.objects.create_user(username="s", password="pw12345", is_staff=True)
        self.client.login(username="s", password="pw12345")
        self.member = Member.objects.create(
            first_name="Ada", last_name="Lovelace", email="ada@example.com"
        )
        self.term = MembershipTerm.objects.create(
            member=self.member, tier="individual",
            started_on=datetime.date(2026, 1, 1),
            expires_on=datetime.date(2027, 1, 1), price_paid=Decimal("60.00"),
        )

    def test_edit_fixes_a_typo(self) -> None:
        self.client.post(
            reverse("dashboard:term_edit", args=[self.term.pk]),
            {"tier": "individual", "started_on": "2026-01-02",
             "expires_on": "2027-01-02", "price_paid": "60.00",
             "purchased_at": "", "notes": ""},
        )
        self.term.refresh_from_db()
        self.assertEqual(self.term.started_on, datetime.date(2026, 1, 2))

    def test_edit_cannot_move_a_term_to_another_member(self) -> None:
        other = Member.objects.create(
            first_name="Grace", last_name="Hopper", email="grace@example.com"
        )
        self.client.post(
            reverse("dashboard:term_edit", args=[self.term.pk]),
            {"tier": "individual", "started_on": "2026-01-01",
             "expires_on": "2027-01-01", "price_paid": "60.00",
             "purchased_at": "", "notes": "", "member": other.pk},
        )
        self.term.refresh_from_db()
        self.assertEqual(self.term.member, self.member)

    def test_delete_removes_only_that_term(self) -> None:
        MembershipTerm.objects.create(
            member=self.member, tier="individual",
            started_on=datetime.date(2025, 1, 1),
            expires_on=datetime.date(2026, 1, 1), price_paid=Decimal("60.00"),
        )
        self.client.post(reverse("dashboard:term_delete", args=[self.term.pk]))
        self.assertEqual(self.member.terms.count(), 1)
        self.assertEqual(Member.objects.count(), 1)
