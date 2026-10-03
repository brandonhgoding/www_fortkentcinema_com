import datetime
import json
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from audience.models import Member, MembershipTerm, MembershipTier

User = get_user_model()


def a_tier(slug="individual"):
    return MembershipTier.objects.get(slug=slug)


def make_member():
    return Member.objects.create(
        first_name="Ada", last_name="Lovelace", email="ada@example.com"
    )


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
            member=self.member, tier=a_tier("individual"),
            started_on=datetime.date(2025, 1, 1),
            expires_on=datetime.date(2026, 1, 1), price_paid=Decimal("60.00"),
        )
        MembershipTerm.objects.create(
            member=self.member, tier=a_tier("cinema-supporter"),
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
            {"tier": a_tier().pk, "started_on": "2026-09-11",
             "expires_on": "", "price_paid": "", "purchased_at": "", "notes": ""},
        )
        self.assertEqual(resp.status_code, 200)
        term = MembershipTerm.objects.get()
        self.assertEqual(term.member, self.member)
        self.assertEqual(term.expires_on, datetime.date(2027, 9, 10))
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
            member=self.member, tier=a_tier("individual"),
            started_on=today - datetime.timedelta(days=800),
            expires_on=today - datetime.timedelta(days=400),
            price_paid=Decimal("60.00"),
        )
        self.assertFalse(self.member.is_active)

        self.client.post(
            reverse("dashboard:term_create", args=[self.member.pk]),
            {"tier": a_tier().pk, "started_on": today.isoformat(),
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
            member=self.member, tier=a_tier("individual"),
            started_on=datetime.date(2026, 1, 1),
            expires_on=datetime.date(2027, 1, 1), price_paid=Decimal("60.00"),
        )

    def test_edit_fixes_a_typo(self) -> None:
        self.client.post(
            reverse("dashboard:term_edit", args=[self.term.pk]),
            {"tier": a_tier().pk, "started_on": "2026-01-02",
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
            {"tier": a_tier().pk, "started_on": "2026-01-01",
             "expires_on": "2027-01-01", "price_paid": "60.00",
             "purchased_at": "", "notes": "", "member": other.pk},
        )
        self.term.refresh_from_db()
        self.assertEqual(self.term.member, self.member)

    def test_delete_removes_only_that_term(self) -> None:
        MembershipTerm.objects.create(
            member=self.member, tier=a_tier("individual"),
            started_on=datetime.date(2025, 1, 1),
            expires_on=datetime.date(2026, 1, 1), price_paid=Decimal("60.00"),
        )
        self.client.post(reverse("dashboard:term_delete", args=[self.term.pk]))
        self.assertEqual(self.member.terms.count(), 1)
        self.assertEqual(Member.objects.count(), 1)


class TermFormTierChoicesTests(TestCase):
    """The dropdown comes from the database, and retiring is not destructive."""

    def test_choices_come_from_the_catalogue(self) -> None:
        from dashboard.forms import MembershipTermForm

        slugs = {t.slug for t in MembershipTermForm().fields["tier"].queryset}
        self.assertEqual(
            slugs,
            {"silver-screen", "individual", "cinema-supporter", "family",
             "family-plus"},
        )

    def test_retired_tier_drops_out_for_a_new_term(self) -> None:
        from dashboard.forms import MembershipTermForm

        tier = MembershipTier.objects.get(slug="family-plus")
        tier.show_on_membership_page = False
        tier.save(update_fields=["show_on_membership_page"])

        slugs = {t.slug for t in MembershipTermForm().fields["tier"].queryset}
        self.assertNotIn("family-plus", slugs)

    def test_retired_tier_stays_selectable_on_a_term_that_uses_it(self) -> None:
        """Editing an old record must not quietly re-tier it."""
        import datetime
        from decimal import Decimal

        from dashboard.forms import MembershipTermForm

        tier = MembershipTier.objects.get(slug="family-plus")
        member = make_member()
        term = MembershipTerm.objects.create(
            member=member, tier=tier,
            started_on=datetime.date(2026, 1, 1),
            expires_on=datetime.date(2026, 12, 31),
            price_paid=Decimal("250.00"),
        )
        tier.show_on_membership_page = False
        tier.save(update_fields=["show_on_membership_page"])

        form = MembershipTermForm(instance=term)
        self.assertIn(tier, form.fields["tier"].queryset)

    def test_expiry_defaults_from_the_selected_tier(self) -> None:
        import datetime

        from dashboard.forms import MembershipTermForm

        form = MembershipTermForm(data={
            "tier": a_tier("individual").pk,
            "started_on": "2026-03-01",
        })
        self.assertTrue(form.is_valid(), form.errors)
        # 12 months, inclusive: good through the day before the anniversary.
        self.assertEqual(
            form.cleaned_data["expires_on"],
            datetime.date(2027, 2, 28),
        )

        # Every seeded tier is 12 months, so the case above alone would
        # pass just as well against a clean() that hardcoded 12 months and
        # never read tier.duration_months. Give a tier a different
        # duration so only reading the field can produce the right answer.
        short_tier = a_tier("individual")
        short_tier.duration_months = 6
        short_tier.save(update_fields=["duration_months"])

        form = MembershipTermForm(data={
            "tier": short_tier.pk,
            "started_on": "2026-03-01",
        })
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(
            form.cleaned_data["expires_on"],
            datetime.date(2026, 8, 31),
        )

    def test_price_defaults_from_the_selected_tier(self) -> None:
        from dashboard.forms import MembershipTermForm

        form = MembershipTermForm(data={
            "tier": a_tier("cinema-supporter").pk,
            "started_on": "2026-03-01",
        })
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data["price_paid"], 120)


class RenewPrefillTests(TestCase):
    """The Renew button opens the same form as Add Term, pre-answered."""

    def setUp(self) -> None:
        User.objects.create_user(username="s", password="pw12345", is_staff=True)
        self.client.login(username="s", password="pw12345")
        self.member = make_member()

    def renew_form(self):
        from dashboard.forms import MembershipTermForm  # noqa: F401

        return self.client.get(
            reverse("dashboard:term_create", args=[self.member.pk]), {"renew": "1"}
        ).content.decode()

    def test_prefills_the_tier_and_a_continuing_start_date(self) -> None:
        # Relative to today: renewal_start never goes earlier than today,
        # so a fixed expiry date stops "continuing" once it is in the past.
        today = timezone.localdate()
        MembershipTerm.objects.create(
            member=self.member, tier=a_tier("cinema-supporter"),
            started_on=today - datetime.timedelta(days=300),
            expires_on=today + datetime.timedelta(days=20),
            price_paid=Decimal("120.00"),
        )
        html = self.renew_form()
        continuing = today + datetime.timedelta(days=21)
        self.assertIn(f'value="{continuing.isoformat()}"', html)
        self.assertIn(
            f'value="{a_tier("cinema-supporter").pk}" selected', html
        )

    def test_expiry_and_price_are_left_blank_to_refill_from_the_tier(self) -> None:
        """A renewal must pick up a price rise since the last term."""
        MembershipTerm.objects.create(
            member=self.member, tier=a_tier("individual"),
            started_on=datetime.date(2026, 1, 1),
            expires_on=datetime.date(2026, 12, 31),
            price_paid=Decimal("45.00"),
        )
        html = self.renew_form()
        self.assertNotIn("45.00", html)
        self.assertNotIn('value="2026-12-31"', html)

    def test_add_term_without_the_flag_still_opens_blank(self) -> None:
        MembershipTerm.objects.create(
            member=self.member, tier=a_tier("individual"),
            started_on=datetime.date(2026, 1, 1),
            expires_on=datetime.date(2026, 12, 31),
            price_paid=Decimal("60.00"),
        )
        html = self.client.get(
            reverse("dashboard:term_create", args=[self.member.pk])
        ).content.decode()
        self.assertNotIn('value="2027-01-01"', html)

    def test_renewing_a_lapsed_member_starts_today(self) -> None:
        MembershipTerm.objects.create(
            member=self.member, tier=a_tier("individual"),
            started_on=datetime.date(2020, 1, 1),
            expires_on=datetime.date(2020, 12, 31),
            price_paid=Decimal("60.00"),
        )
        html = self.renew_form()
        self.assertIn(f'value="{timezone.localdate().isoformat()}"', html)

    def test_continues_from_the_term_that_runs_latest(self) -> None:
        """A short comp started inside a longer term must not become the
        renewal's starting point or its tier."""
        today = timezone.localdate()
        MembershipTerm.objects.create(
            member=self.member, tier=a_tier("family-plus"),
            started_on=today - datetime.timedelta(days=200),
            expires_on=today + datetime.timedelta(days=165),
            price_paid=Decimal("250.00"),
        )
        MembershipTerm.objects.create(
            member=self.member, tier=a_tier("individual"),
            started_on=today - datetime.timedelta(days=100),
            expires_on=today - datetime.timedelta(days=70),
            price_paid=Decimal("0.00"),
        )
        html = self.renew_form()
        continuing = today + datetime.timedelta(days=166)
        self.assertIn(f'value="{continuing.isoformat()}"', html)
        self.assertIn(f'value="{a_tier("family-plus").pk}" selected', html)

    def test_a_member_with_no_terms_gets_a_blank_form(self) -> None:
        resp = self.client.get(
            reverse("dashboard:term_create", args=[self.member.pk]), {"renew": "1"}
        )
        self.assertEqual(resp.status_code, 200)

    def test_a_retired_tier_is_not_prefilled(self) -> None:
        """It is not in the dropdown for a new term, so seeding it would
        render a select with nothing chosen and lose the intent silently."""
        tier = a_tier("family-plus")
        today = timezone.localdate()
        MembershipTerm.objects.create(
            member=self.member, tier=tier,
            started_on=today - datetime.timedelta(days=300),
            expires_on=today + datetime.timedelta(days=20),
            price_paid=Decimal("250.00"),
        )
        tier.show_on_membership_page = False
        tier.save(update_fields=["show_on_membership_page"])

        html = self.renew_form()
        continuing = today + datetime.timedelta(days=21)
        self.assertIn(f'value="{continuing.isoformat()}"', html)
        self.assertNotIn(f'value="{tier.pk}" selected', html)

    def test_the_renew_button_is_hidden_for_a_member_with_no_terms(self) -> None:
        html = self.client.get(
            reverse("dashboard:member_detail", args=[self.member.pk])
        ).content.decode()
        self.assertNotIn("renew=1", html)


class OverlapFlagTests(TestCase):
    """Double-entered renewals look exactly like early ones to the model,
    so the roster flags the pair instead of refusing the save."""

    def setUp(self) -> None:
        User.objects.create_user(username="s", password="pw12345", is_staff=True)
        self.client.login(username="s", password="pw12345")
        self.member = make_member()

    def add_term(self, start, end):
        return MembershipTerm.objects.create(
            member=self.member, tier=a_tier("individual"),
            started_on=start, expires_on=end, price_paid=Decimal("60.00"),
        )

    def detail_html(self):
        return self.client.get(
            reverse("dashboard:member_detail", args=[self.member.pk])
        ).content.decode()

    def test_consecutive_terms_are_not_flagged(self) -> None:
        self.add_term(datetime.date(2025, 1, 1), datetime.date(2025, 12, 31))
        self.add_term(datetime.date(2026, 1, 1), datetime.date(2026, 12, 31))
        self.assertNotIn("Overlaps", self.detail_html())

    def test_a_duplicated_renewal_is_flagged(self) -> None:
        self.add_term(datetime.date(2026, 1, 1), datetime.date(2026, 12, 31))
        self.add_term(datetime.date(2026, 1, 1), datetime.date(2026, 12, 31))
        self.assertEqual(self.detail_html().count("Overlaps"), 2)

    def test_the_flag_appears_on_the_swapped_back_list_too(self) -> None:
        """The OOB swap after a save must agree with a fresh page load."""
        self.add_term(datetime.date(2026, 1, 1), datetime.date(2026, 12, 31))
        html = self.client.post(
            reverse("dashboard:term_create", args=[self.member.pk]),
            {
                "tier": a_tier("individual").pk,
                "started_on": "2026-06-01",
                "expires_on": "",
                "price_paid": "",
                "purchased_at": "",
                "notes": "",
            },
        ).content.decode()
        self.assertEqual(html.count("Overlaps"), 2)

    def test_an_anniversary_renewal_with_default_dates_is_not_flagged(
        self,
    ) -> None:
        """Default expiries must leave room for a renewal on the anniversary."""
        for start in ("2025-03-01", "2026-03-01"):
            self.client.post(
                reverse("dashboard:term_create", args=[self.member.pk]),
                {
                    "tier": a_tier("individual").pk,
                    "started_on": start,
                    "expires_on": "",
                    "price_paid": "",
                    "purchased_at": "",
                    "notes": "",
                },
            )
        self.assertEqual(self.member.terms.count(), 2)
        self.assertNotIn("Overlaps", self.detail_html())

    def test_the_flag_clears_when_the_duplicate_is_deleted(self) -> None:
        self.add_term(datetime.date(2026, 1, 1), datetime.date(2026, 12, 31))
        dupe = self.add_term(
            datetime.date(2026, 1, 1), datetime.date(2026, 12, 31)
        )
        html = self.client.post(
            reverse("dashboard:term_delete", args=[dupe.pk])
        ).content.decode()
        self.assertNotIn("Overlaps", html)
