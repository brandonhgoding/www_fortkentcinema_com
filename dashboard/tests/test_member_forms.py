import datetime
from decimal import Decimal

from django.test import TestCase

from audience.models import Member, MembershipTier
from dashboard.forms import MemberForm, MembershipTermForm


def a_tier(slug="individual"):
    return MembershipTier.objects.get(slug=slug)


class MemberFormTests(TestCase):
    def test_valid_with_name_and_email_only(self) -> None:
        form = MemberForm(
            {"first_name": "Ada", "last_name": "Lovelace", "email": "ada@example.com"}
        )
        self.assertTrue(form.is_valid(), form.errors)

    def test_email_is_required(self) -> None:
        form = MemberForm({"first_name": "Ada", "last_name": "Lovelace"})
        self.assertFalse(form.is_valid())
        self.assertIn("email", form.errors)

    def test_duplicate_email_is_rejected_with_a_readable_message(self) -> None:
        Member.objects.create(
            first_name="Ada", last_name="Lovelace", email="ada@example.com"
        )
        form = MemberForm(
            {"first_name": "Other", "last_name": "Person", "email": "ADA@example.com"}
        )
        self.assertFalse(form.is_valid())
        self.assertIn("email", form.errors)


class MembershipTermFormTests(TestCase):
    def setUp(self) -> None:
        self.member = Member.objects.create(
            first_name="Ada", last_name="Lovelace", email="ada@example.com"
        )

    def test_unknown_tier_is_rejected(self) -> None:
        form = MembershipTermForm(
            {"tier": "platinum-invented", "started_on": "2026-09-11"}
        )
        self.assertFalse(form.is_valid())
        self.assertIn("tier", form.errors)

    def test_expiry_defaults_to_the_tier_duration(self) -> None:
        form = MembershipTermForm(
            {"tier": a_tier().pk, "started_on": "2026-09-11"}
        )
        self.assertTrue(form.is_valid(), form.errors)
        term = form.save(commit=False)
        term.member = self.member
        term.save()
        self.assertEqual(term.expires_on, datetime.date(2027, 9, 10))

    def test_a_new_term_has_no_tier_chosen_for_it(self) -> None:
        """Staff pick the tier; the first one in the list is not a default."""
        form = MembershipTermForm({"started_on": "2026-09-11"})
        self.assertFalse(form.is_valid())
        self.assertIn("tier", form.errors)
        self.assertIn('<option value="" selected>', str(MembershipTermForm()["tier"]))

    def test_price_defaults_to_the_tier_price(self) -> None:
        form = MembershipTermForm(
            {"tier": a_tier().pk, "started_on": "2026-09-11"}
        )
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data["price_paid"], Decimal("60"))

    def test_an_explicit_price_survives(self) -> None:
        form = MembershipTermForm(
            {"tier": a_tier().pk, "started_on": "2026-09-11", "price_paid": "0"}
        )
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data["price_paid"], Decimal("0"))

    def test_an_explicit_expiry_survives(self) -> None:
        form = MembershipTermForm(
            {
                "tier": a_tier().pk,
                "started_on": "2026-09-11",
                "expires_on": "2027-03-11",
            }
        )
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data["expires_on"], datetime.date(2027, 3, 11))

    def test_start_date_is_required(self) -> None:
        form = MembershipTermForm({"tier": a_tier().pk})
        self.assertFalse(form.is_valid())
        self.assertIn("started_on", form.errors)

    def test_every_catalogue_tier_is_offered(self) -> None:
        offered = {
            t.slug for t in MembershipTermForm().fields["tier"].queryset
        }
        self.assertEqual(
            offered,
            {t.slug for t in MembershipTier.objects.filter(
                show_on_membership_page=True
            )},
        )
