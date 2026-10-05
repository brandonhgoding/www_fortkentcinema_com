import dataclasses
import datetime
from unittest import mock

from boxoffice.gateway import GatewayError
from boxoffice.models import SquareItem
from boxoffice.sync import delete, live_item, push, schedule, should_have_item, sync
from boxoffice.tests.fakes import FakeGateway
from cinema.models import Engagement, EngagementFilm, Film, Screen
from django.test import TestCase, override_settings

LOGGER = "boxoffice.sync"


def make_eng(**over):
    screen = Screen.objects.get_or_create(name="Screen 1", capacity=50)[0]
    defaults = dict(
        screen=screen,
        start_date=datetime.date(2026, 10, 9),
        end_date=datetime.date(2026, 10, 15),
        status="CONFIRMED",
    )
    defaults.update(over)
    eng = Engagement.objects.create(**defaults)
    film = Film.objects.get_or_create(title="Dune")[0]
    EngagementFilm.objects.create(engagement=eng, film=film, position=1)
    return eng


class PushTests(TestCase):
    def setUp(self) -> None:
        self.gw = FakeGateway()
        self.eng = make_eng()

    def test_first_push_creates_item_and_five_variations(self) -> None:
        item = push(self.eng, self.gw)
        self.assertEqual(item.square_id, "item-1")
        self.assertEqual(item.name, "Dune")
        self.assertEqual(item.version, 1)
        self.assertEqual(item.last_error, "")
        self.assertEqual(item.variations.count(), 5)
        self.assertEqual(item.variations.get(tier="member").price_cents, 400)
        self.assertEqual(
            set(item.variations.values_list("square_id", flat=True)),
            {f"var-{n}" for n in range(1, 6)},
        )
        self.assertIsNotNone(item.synced_at)

    def test_unchanged_second_push_makes_no_call(self) -> None:
        first = push(self.eng, self.gw)
        self.gw.calls.clear()
        second = push(self.eng, self.gw)
        self.assertEqual(self.gw.calls, [])
        self.assertEqual(second.pk, first.pk)

    def test_rename_repushes_with_stored_version(self) -> None:
        item = push(self.eng, self.gw)
        self.eng.event_title = "Dune: Part One"
        self.eng.save()
        pushed = push(self.eng, self.gw)
        self.assertEqual(self.gw.items[item.square_id].name, "Dune: Part One")
        self.assertEqual(self.gw.calls[-1][0], "upsert_item")
        self.assertEqual(self.gw.calls[-1][1]["version"], item.version)
        self.assertEqual(self.gw.calls[-1][1]["item_id"], "item-1")
        self.assertEqual((pushed.name, pushed.version), ("Dune: Part One", 2))
        # Variation IDs are reused, not re-minted.
        self.assertEqual(
            set(pushed.variations.values_list("square_id", flat=True)),
            {f"var-{n}" for n in range(1, 6)},
        )

    def test_version_mismatch_refetches_and_wins(self) -> None:
        item = push(self.eng, self.gw)
        self.gw.items[item.square_id] = dataclasses.replace(
            self.gw.items[item.square_id], version=99, name="Varity")
        # The brief set event_title to "Dune", which equals the stored name and
        # so would never reach Square; a real rename forces the push.
        self.eng.event_title = "Dune: Part One"
        self.eng.save()
        with self.assertLogs(LOGGER, "WARNING") as logs:
            push(self.eng, self.gw)
        self.assertIn("overwr", logs.output[0])
        self.assertEqual(self.gw.items[item.square_id].name, "Dune: Part One")
        self.assertEqual([c[0] for c in self.gw.calls[-3:]],
                         ["upsert_item", "retrieve_item", "upsert_item"])
        item.refresh_from_db()
        self.assertEqual(item.version, 100)
        self.assertEqual(item.last_error, "")

    def test_gateway_failure_records_error_and_keeps_engagement(self) -> None:
        item = push(self.eng, self.gw)
        self.gw.fail_with = GatewayError("boom")
        self.eng.event_title = "X"
        self.eng.save()
        with self.assertLogs(LOGGER, "WARNING"):
            push(self.eng, self.gw)
        item.refresh_from_db()
        self.assertEqual(item.last_error, "boom")
        self.assertEqual(item.square_id, "item-1")
        self.assertTrue(Engagement.objects.filter(pk=self.eng.pk).exists())

    def test_empty_title_records_error_without_calling_square(self) -> None:
        self.eng.engagement_films.all().delete()
        with self.assertLogs(LOGGER, "WARNING"):
            item = push(self.eng, self.gw)
        self.assertIn("no title", item.last_error)
        self.assertIsNone(item.square_id)
        self.assertEqual(self.gw.calls, [])

    def test_first_push_failure_leaves_row_with_error_and_no_id(self) -> None:
        self.gw.fail_with = GatewayError("boom")
        with self.assertLogs(LOGGER, "WARNING"):
            item = push(self.eng, self.gw)
        self.assertEqual((item.square_id, item.last_error), (None, "boom"))
        self.gw.fail_with = None
        item = push(self.eng, self.gw)
        self.assertEqual((item.square_id, item.last_error), ("item-1", ""))
        self.assertEqual(SquareItem.objects.count(), 1)

    @override_settings(SQUARE_ACCESS_TOKEN="")
    def test_none_gateway_does_nothing(self) -> None:
        with self.assertLogs(LOGGER, "INFO"):
            self.assertIsNone(push(self.eng, None))
        self.assertEqual(SquareItem.objects.count(), 0)

    def test_reconfirmed_run_after_deletion_gets_new_item(self) -> None:
        old = push(self.eng, self.gw)
        old_skus = sorted(old.variations.values_list("sku", flat=True))
        delete(self.eng, self.gw)
        new = push(self.eng, self.gw)
        self.assertNotEqual(old.pk, new.pk)
        self.assertEqual(new.square_id, "item-2")
        self.assertEqual(sorted(new.variations.values_list("sku", flat=True)),
                         old_skus)
        old.refresh_from_db()
        self.assertIsNotNone(old.deleted_at)
        # Kept, unchanged, so old sales still resolve.
        self.assertEqual(sorted(old.variations.values_list("sku", flat=True)),
                         old_skus)
        self.assertEqual(live_item(self.eng).pk, new.pk)


class DeleteTests(TestCase):
    def setUp(self) -> None:
        self.gw = FakeGateway()
        self.eng = make_eng()

    def test_delete_marks_row_and_removes_remote(self) -> None:
        item = push(self.eng, self.gw)
        delete(self.eng, self.gw)
        self.assertEqual(self.gw.calls[-1], ("delete_item", {"item_id": "item-1"}))
        self.assertNotIn("item-1", self.gw.items)
        item.refresh_from_db()
        self.assertIsNotNone(item.deleted_at)
        self.assertIsNone(live_item(self.eng))

    def test_delete_without_item_is_noop(self) -> None:
        delete(self.eng, self.gw)
        self.assertEqual(self.gw.calls, [])

    def test_delete_failure_raises(self) -> None:
        item = push(self.eng, self.gw)
        self.gw.fail_with = GatewayError("nope")
        with self.assertRaises(GatewayError):
            delete(self.eng, self.gw)
        item.refresh_from_db()
        self.assertIsNone(item.deleted_at)

    def test_delete_of_never_pushed_row_is_local(self) -> None:
        self.gw.fail_with = GatewayError("boom")
        with self.assertLogs(LOGGER, "WARNING"):
            item = push(self.eng, self.gw)
        self.gw.calls.clear()
        delete(self.eng, self.gw)
        self.assertEqual(self.gw.calls, [])
        item.refresh_from_db()
        self.assertIsNotNone(item.deleted_at)


class SyncAndScheduleTests(TestCase):
    def setUp(self) -> None:
        self.gw = FakeGateway()
        self.eng = make_eng(end_date=datetime.date(2099, 1, 1))

    def test_should_have_item(self) -> None:
        today = datetime.date(2026, 10, 9)
        self.assertTrue(should_have_item(make_eng(end_date=today), today))
        self.assertFalse(should_have_item(
            make_eng(end_date=datetime.date(2026, 10, 8)), today))
        self.assertFalse(should_have_item(make_eng(status="CANCELLED"), today))
        self.assertFalse(should_have_item(make_eng(status="DRAFT"), today))

    def test_sync_pushes_confirmed_and_deletes_cancelled(self) -> None:
        sync(self.eng, self.gw)
        self.assertEqual(live_item(self.eng).square_id, "item-1")
        self.assertIn("item-1", self.gw.items)
        self.eng.status = "CANCELLED"
        self.eng.save()
        sync(self.eng, self.gw)
        self.assertIsNone(live_item(self.eng))
        self.assertNotIn("item-1", self.gw.items)

    def test_sync_swallows_gateway_error(self) -> None:
        push(self.eng, self.gw)
        self.eng.status = "CANCELLED"
        self.eng.save()
        self.gw.fail_with = GatewayError("down")
        with self.assertLogs(LOGGER, "WARNING"):
            sync(self.eng, self.gw)  # does not raise
        self.assertIsNotNone(live_item(self.eng))

    def test_schedule_runs_after_commit(self) -> None:
        with mock.patch("boxoffice.sync.get_gateway", return_value=self.gw):
            with self.captureOnCommitCallbacks(execute=True) as callbacks:
                schedule(self.eng)
                self.assertEqual(SquareItem.objects.count(), 0)
        self.assertEqual(len(callbacks), 1)
        self.assertEqual(live_item(self.eng).square_id, "item-1")
