"""The seed migration's output.

Django runs every migration to build the test database, so the seeded rows
are simply present — no migration-executor harness needed.
"""

from django.test import TestCase

from audience.models import MembershipBenefit, MembershipTier

EXPECTED = {
    "silver-screen": (35, "Seniors 65+", False, False,
                      "https://square.link/u/UnQLNeHp"),
    "individual": (60, "", False, False,
                   "https://square.link/u/zricPsRR"),
    "cinema-supporter": (120, "", True, False,
                         "https://square.link/u/2HnpAb9N"),
    "family": (150, "", False, True,
               "https://square.link/u/FkcUasKu"),
    "family-plus": (250, "", False, True,
                    "https://square.link/u/1YSgMFSQ"),
}


class SeededCatalogueTests(TestCase):
    def test_five_tiers(self) -> None:
        self.assertEqual(MembershipTier.objects.count(), 5)

    def test_ten_benefits(self) -> None:
        self.assertEqual(MembershipBenefit.objects.count(), 10)

    def test_tier_fields(self) -> None:
        for slug, (price, eyebrow, featured, family, checkout_url) in EXPECTED.items():
            tier = MembershipTier.objects.get(slug=slug)
            self.assertEqual(tier.price, price, slug)
            self.assertEqual(tier.eyebrow, eyebrow, slug)
            self.assertEqual(tier.featured, featured, slug)
            self.assertEqual(tier.is_family_tier, family, slug)
            self.assertEqual(tier.duration_months, 12, slug)
            self.assertTrue(tier.show_on_membership_page, slug)
            self.assertEqual(tier.checkout_url, checkout_url, slug)

    def test_tiers_sort_by_price(self) -> None:
        self.assertEqual(
            [t.slug for t in MembershipTier.objects.all()],
            ["silver-screen", "individual", "cinema-supporter", "family",
             "family-plus"],
        )

    def test_silver_screen_perks(self) -> None:
        """The tier whose perks differ from every other one."""
        tier = MembershipTier.objects.get(slug="silver-screen")
        self.assertEqual(
            [b.name for b in tier.benefits.all()],
            [
                "$2 off matinee tickets",
                "$1 off evening tickets",
                "$1 off small popcorn",
                "$1 off medium & large popcorn",
                "Free small popcorn during your birthday month",
                "10% off rentals",
            ],
        )

    def test_family_plus_perks(self) -> None:
        tier = MembershipTier.objects.get(slug="family-plus")
        self.assertEqual(
            [b.name for b in tier.benefits.all()],
            [
                "$2 off matinee tickets",
                "$4 off evening tickets",
                "$1 off small popcorn",
                "$2 off medium & large popcorn",
                "Free small popcorn during your birthday month",
                "20% off rentals & parties",
            ],
        )

    def test_every_tier_has_six_perks(self) -> None:
        for tier in MembershipTier.objects.all():
            self.assertEqual(tier.benefits.count(), 6, tier.slug)

    def test_benefits_are_shared_not_duplicated(self) -> None:
        """Ten rows for thirty tier-perk pairings is the point of the M2M."""
        matinee = MembershipBenefit.objects.get(name="$2 off matinee tickets")
        self.assertEqual(matinee.membershiptier_set.count(), 5)
