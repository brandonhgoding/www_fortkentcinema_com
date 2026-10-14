import datetime

from boxoffice.spec import ItemSpec, desired_item, priced_tiers
from cinema.models import Engagement, EngagementFilm, Film, Screen
from django.test import TestCase


class PricedTiersTests(TestCase):
    def test_three_tiers_in_order(self) -> None:
        self.assertEqual(priced_tiers(), [("adult", 8), ("senior", 7), ("child", 6)])

    def test_matinee_and_member_are_not_variations(self) -> None:
        # They are register discounts; TICKET_PRICES keeps them for the site
        # and the phone line.
        tiers = [t for t, _ in priced_tiers()]
        self.assertNotIn("matinee", tiers)
        self.assertNotIn("member", tiers)


class DesiredItemTests(TestCase):
    def setUp(self) -> None:
        screen = Screen.objects.create(name="S1", capacity=50)
        self.eng = Engagement.objects.create(
            screen=screen, start_date=datetime.date(2026, 10, 9),
            end_date=datetime.date(2026, 10, 15), status="CONFIRMED")
        film = Film.objects.create(title="Dune")
        EngagementFilm.objects.create(engagement=self.eng, film=film, position=1)

    def test_item_name_is_display_title(self) -> None:
        self.assertEqual(desired_item(self.eng).name, "Dune")

    def test_three_variations_with_prices_skus_ordinals(self) -> None:
        spec = desired_item(self.eng)
        self.assertIsInstance(spec, ItemSpec)
        self.assertEqual(
            [(v.tier, v.name, v.price_cents, v.ordinal) for v in spec.variations],
            [("adult", "Adult", 800, 0), ("senior", "Senior", 700, 1),
             ("child", "Child", 600, 2)],
        )
        self.assertEqual(spec.variations[2].sku, f"fkc-eng-{self.eng.pk}-child")

    def test_free_for_members_changes_nothing(self) -> None:
        before = desired_item(self.eng).variations
        self.eng.is_free_for_members = True
        self.assertEqual(desired_item(self.eng).variations, before)

    def test_empty_title_raises(self) -> None:
        self.eng.engagement_films.all().delete()
        with self.assertRaisesMessage(ValueError, "no title"):
            desired_item(self.eng)

    def test_title_over_200_characters_raises(self) -> None:
        # Joined film titles have no length limit; SquareItem.name holds 200.
        second = Film.objects.create(title="X" * 199)
        EngagementFilm.objects.create(engagement=self.eng, film=second, position=2)
        with self.assertRaisesMessage(
                ValueError,
                f"Engagement {self.eng.pk} title is longer than 200 characters"):
            desired_item(self.eng)

    def test_title_of_exactly_200_characters_is_allowed(self) -> None:
        self.eng.display_title = "Y" * 200
        self.assertEqual(len(desired_item(self.eng).name), 200)
