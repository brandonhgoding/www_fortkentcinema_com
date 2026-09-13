from django.test import TestCase

from audience.models import MembershipBenefit, MembershipTier


def make_benefit(name="$2 off matinee tickets", sort_order=10, **kw):
    return MembershipBenefit.objects.create(
        name=name, sort_order=sort_order, **kw
    )


def make_tier(slug="individual", name="Individual", price=60, **kw):
    return MembershipTier.objects.create(
        slug=slug, name=name, price=price, **kw
    )


class MembershipBenefitTests(TestCase):
    def test_str_is_the_name(self) -> None:
        self.assertEqual(str(make_benefit()), "$2 off matinee tickets")

    def test_description_is_optional(self) -> None:
        """Nothing on the public page renders it."""
        self.assertEqual(make_benefit().description, "")

    def test_ordering_is_by_sort_order_then_name(self) -> None:
        make_benefit(name="20% off rentals & parties", sort_order=60)
        make_benefit(name="$4 off evening tickets", sort_order=20)
        make_benefit(name="$2 off matinee tickets", sort_order=10)
        make_benefit(name="10% off rentals", sort_order=60)
        self.assertEqual(
            [b.name for b in MembershipBenefit.objects.all()],
            [
                "$2 off matinee tickets",
                "$4 off evening tickets",
                "10% off rentals",
                "20% off rentals & parties",
            ],
        )


class MembershipTierTests(TestCase):
    def test_str_is_the_name(self) -> None:
        self.assertEqual(str(make_tier()), "Individual")

    def test_slug_is_unique(self) -> None:
        from django.db import IntegrityError, transaction

        make_tier()
        with self.assertRaises(IntegrityError), transaction.atomic():
            make_tier(name="Duplicate")

    def test_defaults(self) -> None:
        tier = make_tier()
        self.assertEqual(tier.duration_months, 12)
        self.assertFalse(tier.featured)
        self.assertFalse(tier.is_family_tier)
        self.assertEqual(tier.eyebrow, "")
        self.assertEqual(tier.checkout_url, "")

    def test_shown_on_the_membership_page_by_default(self) -> None:
        """Retiring is the deliberate act; being listed is the norm."""
        self.assertTrue(make_tier().show_on_membership_page)

    def test_price_is_a_whole_number(self) -> None:
        """$35, never $35.00 — the card renders it raw."""
        self.assertEqual(make_tier(price=35).price, 35)
        self.assertNotIn(".", str(make_tier(slug="x", price=35).price))

    def test_ordering_is_by_sort_order_then_price(self) -> None:
        make_tier(slug="family-plus", name="Family Plus", price=250, sort_order=50)
        make_tier(slug="silver-screen", name="Silver Screen", price=35, sort_order=10)
        make_tier(slug="individual", name="Individual", price=60, sort_order=20)
        self.assertEqual(
            [t.slug for t in MembershipTier.objects.all()],
            ["silver-screen", "individual", "family-plus"],
        )

    def test_ties_on_sort_order_resolve_by_price(self) -> None:
        """Only a true price tiebreak explains this order."""
        make_tier(
            slug="individual-plus", name="Individual Plus", price=90, sort_order=20
        )
        make_tier(slug="individual", name="Individual", price=60, sort_order=20)
        self.assertEqual(
            [t.slug for t in MembershipTier.objects.filter(sort_order=20)],
            ["individual", "individual-plus"],
        )

    def test_benefits_come_back_in_benefit_order(self) -> None:
        """The M2M is plain; the order lives on the benefit."""
        tier = make_tier()
        rentals = make_benefit(name="10% off rentals", sort_order=60)
        matinee = make_benefit(name="$2 off matinee tickets", sort_order=10)
        tier.benefits.add(rentals, matinee)
        self.assertEqual(
            [b.name for b in tier.benefits.all()],
            ["$2 off matinee tickets", "10% off rentals"],
        )
