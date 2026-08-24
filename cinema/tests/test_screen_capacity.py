from cinema.models import Screen
from cinema.screen_capacity import PLACEHOLDER_CAPACITY, backfill_placeholder_capacity
from django.test import TestCase


class BackfillPlaceholderCapacityTests(TestCase):
    def test_replaces_placeholder_values(self):
        screen = Screen.objects.create(name="Placeholder", capacity=1)
        backfill_placeholder_capacity(Screen.objects)
        screen.refresh_from_db()
        self.assertEqual(screen.capacity, PLACEHOLDER_CAPACITY)

    def test_replaces_a_zero_capacity(self):
        screen = Screen.objects.create(name="Zero", capacity=0)
        backfill_placeholder_capacity(Screen.objects)
        screen.refresh_from_db()
        self.assertEqual(screen.capacity, PLACEHOLDER_CAPACITY)

    def test_leaves_a_real_seat_count_alone(self):
        # The guard that makes this safe to run on production.
        screen = Screen.objects.create(name="Real", capacity=248)
        backfill_placeholder_capacity(Screen.objects)
        screen.refresh_from_db()
        self.assertEqual(screen.capacity, 248)

    def test_returns_the_number_of_rows_changed(self):
        Screen.objects.create(name="A", capacity=1)
        Screen.objects.create(name="B", capacity=1)
        Screen.objects.create(name="C", capacity=248)
        self.assertEqual(backfill_placeholder_capacity(Screen.objects), 2)

    def test_is_idempotent(self):
        Screen.objects.create(name="A", capacity=1)
        backfill_placeholder_capacity(Screen.objects)
        self.assertEqual(backfill_placeholder_capacity(Screen.objects), 0)
