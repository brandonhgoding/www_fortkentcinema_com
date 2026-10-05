import dataclasses
import datetime
from unittest import mock

from boxoffice.gateway import GatewayError, RemoteItem
from boxoffice.models import SquareItem
from boxoffice.sync import (
    delete,
    live_item,
    push,
    reconcile,
    schedule,
    should_have_item,
    sync,
)
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
        remote_ids = {
            sku: f"rv-{sku.rsplit('-', 1)[1]}"
            for sku in self.gw.items[item.square_id].variation_ids_by_sku
        }
        self.gw.items[item.square_id] = dataclasses.replace(
            self.gw.items[item.square_id], version=99, name="Varity",
            variation_ids_by_sku=remote_ids)
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
        expected = {t: f"rv-{t}"
                    for t in ("adult", "senior", "child", "matinee", "member")}
        self.assertEqual(self.gw.calls[-1][1]["variation_ids_by_tier"], expected)
        item.refresh_from_db()
        self.assertEqual(item.version, 100)
        self.assertEqual(item.last_error, "")
        self.assertEqual(dict(item.variations.values_list("tier", "square_id")),
                         expected)

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

    def test_sync_logs_unexpected_error_without_raising(self) -> None:
        self.gw.fail_with = RuntimeError("SDK exploded")
        with self.assertLogs(LOGGER, "ERROR") as logs:
            sync(self.eng, self.gw)  # does not raise
        self.assertIn("SDK exploded", "\n".join(logs.output))

    def test_schedule_runs_after_commit(self) -> None:
        with mock.patch("boxoffice.sync.get_gateway", return_value=self.gw):
            with self.captureOnCommitCallbacks(execute=True) as callbacks:
                schedule(self.eng)
                self.assertEqual(SquareItem.objects.count(), 0)
                self.assertEqual(self.gw.calls, [])
        self.assertEqual(len(callbacks), 1)
        self.assertEqual(live_item(self.eng).square_id, "item-1")

    def test_schedule_uses_fresh_row_and_skips_deleted(self) -> None:
        with mock.patch("boxoffice.sync.get_gateway", return_value=self.gw):
            with self.captureOnCommitCallbacks(execute=True):
                schedule(self.eng)
                # A rename saved elsewhere before commit; the stale instance
                # passed to schedule still holds the old (empty) event_title.
                Engagement.objects.filter(pk=self.eng.pk).update(
                    event_title="Fresh Title")
            self.assertEqual(self.gw.items["item-1"].name, "Fresh Title")

            gone = make_eng(end_date=datetime.date(2099, 1, 1))
            self.gw.calls.clear()
            with self.captureOnCommitCallbacks(execute=True):
                schedule(gone)
                gone.delete()
        self.assertEqual(self.gw.calls, [])


class ReconcileTests(TestCase):
    def setUp(self) -> None:
        self.gw = FakeGateway()
        self.today = datetime.date(2026, 10, 9)

    def test_pushes_confirmed_future_and_deletes_ended(self) -> None:
        live = make_eng(end_date=datetime.date(2026, 10, 20))
        ended = make_eng(end_date=datetime.date(2026, 10, 1))
        push(ended, self.gw)
        cancelled = make_eng()
        push(cancelled, self.gw)
        Engagement.objects.filter(pk=cancelled.pk).update(status="CANCELLED")
        report = reconcile(self.today, self.gw)
        self.assertEqual(report.pushed, [live.pk])
        self.assertEqual(sorted(report.deleted), sorted([ended.pk, cancelled.pk]))
        self.assertIsNone(live_item(ended))
        self.assertIsNone(live_item(cancelled))
        self.assertEqual(report.errors, [])

    def test_repushes_item_edited_in_admin(self) -> None:
        eng = make_eng()
        push(eng, self.gw)
        Engagement.objects.filter(pk=eng.pk).update(event_title="Renamed")
        report = reconcile(self.today, self.gw)
        self.assertEqual(report.pushed, [eng.pk])
        self.assertEqual(self.gw.items[live_item(eng).square_id].name, "Renamed")

    def test_unchanged_engagement_is_not_reported_pushed(self) -> None:
        eng = make_eng()
        push(eng, self.gw)
        self.assertEqual(reconcile(self.today, self.gw).pushed, [])

    def test_unknown_items_reported_not_deleted(self) -> None:
        self.gw.items["hand"] = RemoteItem("hand", 1, "Varity", {})
        report = reconcile(self.today, self.gw)
        self.assertEqual(report.unknown_items, ["Varity (hand)"])
        self.assertIn("hand", self.gw.items)

    def test_django_made_item_without_link_row_is_an_error(self) -> None:
        self.gw.items["orphan"] = RemoteItem(
            "orphan", 1, "Old", {"fkc-eng-9-adult": "v"})
        report = reconcile(self.today, self.gw)
        self.assertEqual(report.unknown_items, [])
        self.assertEqual(
            report.errors, ["Django-made item without a link row: orphan"])
        self.assertIn("orphan", self.gw.items)

    def test_dry_run_changes_nothing(self) -> None:
        eng = make_eng()
        report = reconcile(self.today, self.gw, dry_run=True)
        self.assertEqual(report.pushed, [eng.pk])
        self.assertEqual(
            self.gw.calls, [c for c in self.gw.calls if c[0] == "list_ticket_items"])
        self.assertEqual(SquareItem.objects.count(), 0)

    def test_dry_run_reports_deletes_without_deleting(self) -> None:
        ended = make_eng(end_date=datetime.date(2026, 10, 1))
        push(ended, self.gw)
        self.gw.calls.clear()
        report = reconcile(self.today, self.gw, dry_run=True)
        self.assertEqual(report.deleted, [ended.pk])
        self.assertIsNotNone(live_item(ended))
        self.assertNotIn("delete_item", [c[0] for c in self.gw.calls])

    def test_listing_failure_is_reported_and_reconcile_continues(self) -> None:
        eng = make_eng()

        def failing_list():
            raise GatewayError("boom")

        self.gw.list_ticket_items = failing_list
        report = reconcile(self.today, self.gw)
        self.assertEqual(report.pushed, [eng.pk])
        self.assertEqual(len(report.errors), 1)
        self.assertIn("boom", report.errors[0])

    def test_delete_failure_is_reported_and_loop_continues(self) -> None:
        a = make_eng(end_date=datetime.date(2026, 10, 1))
        b = make_eng(end_date=datetime.date(2026, 10, 2))
        push(a, self.gw)
        push(b, self.gw)
        real_delete = self.gw.delete_item
        a_id = live_item(a).square_id

        def refuse_a(item_id: str) -> None:
            if item_id == a_id:
                self.gw.fail_with = GatewayError("refused")
            try:
                real_delete(item_id)
            finally:
                self.gw.fail_with = None

        self.gw.delete_item = refuse_a
        report = reconcile(self.today, self.gw)
        self.assertEqual(report.deleted, [b.pk])
        self.assertEqual(len(report.errors), 1)
        self.assertIn("refused", report.errors[0])
        self.assertIsNotNone(live_item(a))

    def test_hand_made_item_without_skus_is_unknown_not_a_crash(self) -> None:
        self.gw.items["hand"] = RemoteItem(
            "hand", 1, "Hand Made", variation_ids_by_sku={})
        report = reconcile(self.today, self.gw)
        self.assertEqual(report.unknown_items, ["Hand Made (hand)"])
        self.assertEqual(report.errors, [])

    def test_row_whose_engagement_was_deleted_is_removed(self) -> None:
        eng = make_eng()
        item = push(eng, self.gw)
        Engagement.objects.filter(pk=eng.pk).delete()
        report = reconcile(self.today, self.gw)
        self.assertNotIn(item.square_id, self.gw.items)
        item.refresh_from_db()
        self.assertIsNone(item.engagement_id)
        self.assertIsNotNone(item.deleted_at)
        self.assertEqual(report.errors, [])
        self.assertEqual(report.deleted, [])

    def test_one_bad_row_does_not_stop_the_others(self) -> None:
        a = make_eng(end_date=datetime.date(2026, 10, 1))
        b = make_eng(end_date=datetime.date(2026, 10, 2))
        push(a, self.gw)
        push(b, self.gw)
        real_delete = self.gw.delete_item
        a_id = live_item(a).square_id

        def explode_on_a(item_id: str) -> None:
            if item_id == a_id:
                raise KeyError("odd response")
            real_delete(item_id)

        self.gw.delete_item = explode_on_a
        report = reconcile(self.today, self.gw)
        self.assertEqual(report.deleted, [b.pk])
        self.assertEqual(len(report.errors), 1)
        self.assertIn("KeyError", report.errors[0])

    def test_one_bad_push_does_not_stop_the_others(self) -> None:
        a = make_eng()
        b = make_eng()
        real_upsert = self.gw.upsert_item

        def explode_on_a(spec, **kwargs):
            if spec.engagement_id == a.pk:
                raise IndexError("odd response")
            return real_upsert(spec, **kwargs)

        self.gw.upsert_item = explode_on_a
        report = reconcile(self.today, self.gw)
        self.assertEqual(report.pushed, [b.pk])
        self.assertEqual(len(report.errors), 1)
        self.assertIn("IndexError", report.errors[0])

    def test_item_deleted_by_hand_in_square_is_recreated(self) -> None:
        eng = make_eng()
        old = push(eng, self.gw)
        del self.gw.items[old.square_id]
        report = reconcile(self.today, self.gw)
        old.refresh_from_db()
        self.assertIsNotNone(old.deleted_at)
        new = live_item(eng)
        self.assertNotEqual(new.pk, old.pk)
        self.assertNotEqual(new.square_id, old.square_id)
        self.assertIn(new.square_id, self.gw.items)
        self.assertEqual(report.pushed, [eng.pk])
        self.assertEqual(report.errors, [
            f"Item {old.square_id} for engagement {eng.pk} was deleted in "
            "Square; it will be recreated"])

    def test_item_moved_out_of_category_is_repushed(self) -> None:
        eng = make_eng()
        item = push(eng, self.gw)
        real_list = self.gw.list_ticket_items

        def without_item():
            return [r for r in real_list() if r.item_id != item.square_id]

        self.gw.list_ticket_items = without_item
        self.gw.calls.clear()
        report = reconcile(self.today, self.gw)
        self.assertEqual(report.pushed, [eng.pk])
        self.assertEqual(report.errors, [])
        self.assertIn("upsert_item", [c[0] for c in self.gw.calls])
        self.assertEqual(live_item(eng).pk, item.pk)
        self.assertEqual(SquareItem.objects.count(), 1)

    def test_dry_run_reports_missing_item_without_touching_it(self) -> None:
        eng = make_eng()
        old = push(eng, self.gw)
        del self.gw.items[old.square_id]
        self.gw.calls.clear()
        report = reconcile(self.today, self.gw, dry_run=True)
        self.assertEqual([c[0] for c in self.gw.calls], ["list_ticket_items"])
        self.assertEqual(len(report.errors), 1)
        self.assertIn("would be restored", report.errors[0])
        self.assertEqual(live_item(eng).pk, old.pk)
