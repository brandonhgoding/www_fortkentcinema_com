import datetime

from boxoffice.spec import ItemSpec, desired_item, priced_tiers
from cinema.models import Engagement, EngagementFilm, Film, Screen
from django.test import TestCase


class PricedTiersTests(TestCase):
    def test_five_tiers_in_constant_order(self) -> None:
        self.assertEqual(priced_tiers(), [
            ("adult", 8), ("senior", 7), ("child", 6), ("matinee", 6), ("member", 4),
        ])


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

    def test_five_variations_with_prices_skus_ordinals(self) -> None:
        spec = desired_item(self.eng)
        self.assertIsInstance(spec, ItemSpec)
        self.assertEqual(
            [(v.tier, v.name, v.price_cents, v.ordinal) for v in spec.variations],
            [("adult", "Adult", 800, 0), ("senior", "Senior", 700, 1),
             ("child", "Child", 600, 2), ("matinee", "Matinee", 600, 3),
             ("member", "Member", 400, 4)],
        )
        self.assertEqual(spec.variations[3].sku, f"fkc-eng-{self.eng.pk}-matinee")

    def test_free_for_members_changes_nothing(self) -> None:
        self.eng.is_free_for_members = True
        self.assertEqual(desired_item(self.eng).variations[4].price_cents, 400)

    def test_empty_title_raises(self) -> None:
        self.eng.engagement_films.all().delete()
        with self.assertRaisesMessage(ValueError, "no title"):
            desired_item(self.eng)
