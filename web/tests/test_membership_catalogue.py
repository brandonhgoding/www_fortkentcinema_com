"""What /membership/ renders, pinned.

Written against the constant-driven page and left untouched when the
catalogue moves into the database. If this still passes afterwards, the
refactor was invisible to visitors, which is the entire goal.

It hardcodes its expectations on purpose. Importing web.constants here
would mean asserting the page matches the thing that generated it.
"""

from html import unescape

from django.test import TestCase
from django.urls import reverse

# (slug, name, eyebrow, price, featured, is_family, perks)
EXPECTED_TIERS = [
    (
        "silver-screen", "Silver Screen", "Seniors 65+", 35, False, False,
        [
            "$2 off matinee tickets",
            "$1 off evening tickets",
            "$1 off small popcorn",
            "$1 off medium & large popcorn",
            "Free small popcorn during your birthday month",
            "10% off rentals",
        ],
    ),
    (
        "individual", "Individual", "", 60, False, False,
        [
            "$2 off matinee tickets",
            "$4 off evening tickets",
            "$1 off small popcorn",
            "$2 off medium & large popcorn",
            "Free small popcorn during your birthday month",
            "10% off rentals",
        ],
    ),
    (
        "cinema-supporter", "Cinema Supporter", "", 120, True, False,
        [
            "$2 off matinee tickets",
            "$4 off evening tickets",
            "$1 off small popcorn",
            "$2 off medium & large popcorn",
            "Free small popcorn during your birthday month",
            "15% off rentals & parties",
        ],
    ),
    (
        "family", "Family", "", 150, False, True,
        [
            "$2 off matinee tickets",
            "$4 off evening tickets",
            "$1 off small popcorn",
            "$2 off medium & large popcorn",
            "Free small popcorn during your birthday month",
            "15% off rentals & parties",
        ],
    ),
    (
        "family-plus", "Family Plus", "", 250, False, True,
        [
            "$2 off matinee tickets",
            "$4 off evening tickets",
            "$1 off small popcorn",
            "$2 off medium & large popcorn",
            "Free small popcorn during your birthday month",
            "20% off rentals & parties",
        ],
    ),
]


class MembershipPageIsUnchangedTests(TestCase):
    def setUp(self) -> None:
        # Unescaped, so the expectations below stay the literal catalogue
        # wording. Django renders "&" as "&amp;", and asserting against the
        # entity would mean the test no longer reads like the copy it pins.
        self.html = unescape(
            self.client.get(reverse("membership")).content.decode()
        )

    def test_every_tier_name_is_present(self) -> None:
        for _slug, name, *_rest in EXPECTED_TIERS:
            self.assertIn(name, self.html)

    def test_prices_render_as_whole_dollars(self) -> None:
        for _slug, name, _eyebrow, price, *_rest in EXPECTED_TIERS:
            self.assertIn(f"${price}", self.html, f"{name} price")
            self.assertNotIn(f"${price}.00", self.html, f"{name} price is decimal")

    def test_every_perk_is_present(self) -> None:
        for *_head, perks in EXPECTED_TIERS:
            for perk in perks:
                self.assertIn(perk, self.html)

    def test_perks_appear_in_catalogue_order_within_each_card(self) -> None:
        """Ordering is the thing a plain ManyToManyField would scramble."""
        for slug, name, _eyebrow, _price, _f, _fam, perks in EXPECTED_TIERS:
            card = self.card_for(slug)
            positions = [card.index(p) for p in perks]
            self.assertEqual(
                positions, sorted(positions), f"{name} perks are out of order"
            )

    def test_tiers_appear_in_price_order(self) -> None:
        positions = [self.html.index(f'data-tier="{t[0]}"')
                     for t in EXPECTED_TIERS]
        self.assertEqual(positions, sorted(positions))

    def test_ribbons_follow_the_featured_and_family_flags(self) -> None:
        for slug, name, _eyebrow, _price, featured, family, _perks in EXPECTED_TIERS:
            card = self.card_for(slug)
            with self.subTest(tier=name):
                self.assertEqual("Best Value" in card, featured)
                self.assertEqual("For Families" in card, family)

    def test_eyebrow_and_its_fallback(self) -> None:
        self.assertIn("Seniors 65+", self.html)
        self.assertIn("Patron Card", self.html)  # every tier without an eyebrow

    def card_for(self, slug: str) -> str:
        """The slice of HTML belonging to one tier card.

        Cards are <article> elements carrying their slug as data-tier.
        """
        start = self.html.index(f'data-tier="{slug}"')
        end = self.html.index("</article>", start)
        return self.html[start:end]


class RetiredTierTests(TestCase):
    """show_on_membership_page is a website switch, nothing more."""

    def retire(self, slug="family-plus"):
        from audience.models import MembershipTier

        tier = MembershipTier.objects.get(slug=slug)
        tier.show_on_membership_page = False
        tier.save(update_fields=["show_on_membership_page"])
        return tier

    def test_retired_tier_is_absent_from_the_page(self) -> None:
        self.retire()
        html = self.client.get(reverse("membership")).content.decode()
        self.assertNotIn('data-tier="family-plus"', html)

    def test_the_other_tiers_still_render(self) -> None:
        self.retire()
        html = self.client.get(reverse("membership")).content.decode()
        for slug in ("silver-screen", "individual", "cinema-supporter", "family"):
            self.assertIn(f'data-tier="{slug}"', html)
