import datetime
import json
from unittest import mock

from boxoffice.gateway import GatewayError
from boxoffice.models import SquareItem, SquareVariation
from boxoffice.sync import live_item
from boxoffice.tests.fakes import FakeGateway
from cinema.models import Engagement, Film, Screen, Showtime
from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from .test_engagement_detail import make_eng

User = get_user_model()


def retry_url(pk: int) -> str:
    return reverse("dashboard:engagement_square_retry", args=[pk])


def delete_url(eng: Engagement) -> str:
    return reverse("dashboard:engagement_delete", args=[eng.pk]) + "?tab=CURRENT"


class StaffTestCase(TestCase):
    def setUp(self) -> None:
        User.objects.create_user(username="s", password="pw12345", is_staff=True)
        self.client.login(username="s", password="pw12345")
        self.screen = Screen.objects.create(name="S1", capacity=50)
        self.film = Film.objects.create(title="Dune", runtime_minutes=155)
        self.today = timezone.localdate()


@override_settings(SQUARE_ACCESS_TOKEN="tok", SQUARE_LOCATION_ID="L",
                   SQUARE_TICKET_CATEGORY_ID="C")
class EngagementSquareHookTests(StaffTestCase):
    def _payload(self, **over):
        data = {
            "kind": "REGULAR", "display_title": "", "screen": self.screen.pk,
            "start_date": self.today.isoformat(),
            "end_date": self.today.isoformat(),
            "presentation_format": "2d", "language": "english", "translation": "none", "status": "DRAFT",
            "show_in_main_listings": "on", "notes": "", "films": [self.film.pk],
        }
        data.update(over)
        return data

    def test_create_schedules_sync(self) -> None:
        with mock.patch("dashboard.views.schedule") as schedule:
            resp = self.client.post(reverse("dashboard:engagement_create"),
                                    self._payload(status="CONFIRMED"))
        self.assertEqual(resp.status_code, 200)
        schedule.assert_called_once()
        self.assertEqual(schedule.call_args.args[0], Engagement.objects.get())

    def test_edit_and_status_schedule_sync(self) -> None:
        eng = make_eng(self.screen, films=[self.film], status="DRAFT")
        with mock.patch("dashboard.views.schedule") as schedule:
            self.client.post(reverse("dashboard:engagement_edit", args=[eng.pk]),
                             self._payload(status="CONFIRMED"))
            status_url = reverse("dashboard:engagement_status", args=[eng.pk])
            self.client.post(status_url + "?tab=CURRENT", {"status": "CANCELLED"})
        self.assertEqual(schedule.call_count, 2)
        pks = [c.args[0].pk for c in schedule.call_args_list]
        self.assertEqual(pks, [eng.pk, eng.pk])
        eng.refresh_from_db()
        self.assertEqual(eng.status, "CANCELLED")

    def test_showtime_create_does_not_schedule(self) -> None:
        eng = make_eng(self.screen, films=[self.film])
        with mock.patch("dashboard.views.schedule") as schedule:
            resp = self.client.post(
                reverse("dashboard:showtime_create", args=[eng.pk]),
                {"date": "2026-07-04", "time": "19:30", "captions": ""},
            )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(Showtime.objects.count(), 1)
        schedule.assert_not_called()

    def test_delete_refused_when_square_refuses(self) -> None:
        eng = make_eng(self.screen, films=[self.film])
        refuse = GatewayError("nope")
        with mock.patch("dashboard.views.delete", side_effect=refuse):
            resp = self.client.post(delete_url(eng))
        self.assertTrue(Engagement.objects.filter(pk=eng.pk).exists())
        # The toast travels in the HX-Trigger header, not the body.
        self.assertIn("The engagement was kept", resp["HX-Trigger"])
        self.assertIn("nope", resp["HX-Trigger"])

    def test_delete_without_item_proceeds(self) -> None:
        eng = make_eng(self.screen, films=[self.film])
        resp = self.client.post(delete_url(eng))
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(Engagement.objects.filter(pk=eng.pk).exists())
        self.assertIn("Engagement deleted", resp["HX-Trigger"])


@override_settings(SQUARE_ACCESS_TOKEN="tok", SQUARE_LOCATION_ID="L",
                   SQUARE_TICKET_CATEGORY_ID="C")
class SquarePillTests(StaffTestCase):
    def _detail(self, eng) -> str:
        url = reverse("dashboard:engagement_detail", args=[eng.pk])
        return self.client.get(url).content.decode()

    def test_not_in_square(self) -> None:
        eng = make_eng(self.screen, films=[self.film])
        html = self._detail(eng)
        self.assertIn("Not in Square", html)
        self.assertNotIn("Square sync failed", html)

    def test_in_square(self) -> None:
        eng = make_eng(self.screen, films=[self.film])
        item = SquareItem.objects.create(engagement=eng, square_id="ITEM1",
                                         name="Dune", synced_at=timezone.now())
        for i, tier in enumerate(["ADULT", "CHILD", "SENIOR", "MEMBER", "MATINEE"]):
            SquareVariation.objects.create(
                item=item, square_id=f"V{i}", sku=f"SKU{i}", tier=tier,
                name=tier.title(), price_cents=500, ordinal=i,
            )
        html = self._detail(eng)
        self.assertIn("In Square · 5 variations · synced", html)
        self.assertNotIn("Not in Square", html)
        self.assertNotIn("Retry", html)

    def test_failed_with_retry(self) -> None:
        eng = make_eng(self.screen, films=[self.film])
        SquareItem.objects.create(engagement=eng, name="Dune",
                                  last_error="Square said no")
        html = self._detail(eng)
        self.assertIn("Square sync failed", html)
        self.assertIn("Square said no", html)
        self.assertIn("Retry", html)
        self.assertIn(retry_url(eng.pk), html)

    def test_live_row_without_square_id_or_error_shows_failed(self) -> None:
        eng = make_eng(self.screen, films=[self.film])
        SquareItem.objects.create(engagement=eng, name="Dune")
        html = self._detail(eng)
        self.assertIn("Square sync failed", html)
        self.assertIn("Retry", html)
        self.assertNotIn("In Square ·", html)

    def test_deleted_item_counts_as_not_in_square(self) -> None:
        eng = make_eng(self.screen, films=[self.film])
        SquareItem.objects.create(engagement=eng, square_id="OLD", name="Dune",
                                  deleted_at=timezone.now())
        self.assertIn("Not in Square", self._detail(eng))

    @override_settings(SQUARE_ACCESS_TOKEN="")
    def test_hidden_when_disabled(self) -> None:
        eng = make_eng(self.screen, films=[self.film])
        SquareItem.objects.create(engagement=eng, name="Dune",
                                  last_error="Square said no")
        html = self._detail(eng)
        for text in ("Not in Square", "In Square ·", "Square sync failed", "Retry"):
            self.assertNotIn(text, html)


class RetryViewTests(StaffTestCase):
    def test_requires_staff(self) -> None:
        eng = make_eng(self.screen, films=[self.film])
        self.client.logout()
        with mock.patch("dashboard.views.sync") as sync:
            resp = self.client.post(retry_url(eng.pk))
        self.assertEqual(resp.status_code, 302)
        sync.assert_not_called()

    def test_calls_sync_and_redirects(self) -> None:
        eng = make_eng(self.screen, films=[self.film])
        with mock.patch("dashboard.views.sync") as sync:
            resp = self.client.post(retry_url(eng.pk))
        sync.assert_called_once_with(eng)
        detail = reverse("dashboard:engagement_detail", args=[eng.pk])
        self.assertRedirects(resp, detail, fetch_redirect_response=False)

    def test_unknown_engagement_404(self) -> None:
        with mock.patch("dashboard.views.sync") as sync:
            resp = self.client.post(retry_url(999999))
        self.assertEqual(resp.status_code, 404)
        sync.assert_not_called()


class RetryViewSquareTests(StaffTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.gw = FakeGateway()
        patcher = mock.patch("boxoffice.sync.get_gateway", return_value=self.gw)
        patcher.start()
        self.addCleanup(patcher.stop)

    def _eng_with_error_row(self, status: str) -> tuple[Engagement, SquareItem]:
        eng = make_eng(self.screen, films=[self.film], status=status,
                       end_date=self.today + datetime.timedelta(days=7))
        row = SquareItem.objects.create(engagement=eng, name="Dune",
                                        last_error="Square said no")
        return eng, row

    def test_retry_on_cancelled_run_retires_row_without_creating_item(self) -> None:
        eng, row = self._eng_with_error_row("CANCELLED")
        resp = self.client.post(retry_url(eng.pk))
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(self.gw.items, {})
        self.assertNotIn("upsert_item", [c[0] for c in self.gw.calls])
        row.refresh_from_db()
        self.assertIsNotNone(row.deleted_at)
        self.assertIsNone(live_item(eng))

    def test_retry_on_confirmed_run_creates_item(self) -> None:
        eng, row = self._eng_with_error_row("CONFIRMED")
        self.client.post(retry_url(eng.pk))
        item = live_item(eng)
        self.assertEqual(item.pk, row.pk)
        self.assertEqual((item.square_id, item.last_error), ("item-1", ""))
        self.assertIn("item-1", self.gw.items)


@override_settings(SQUARE_ACCESS_TOKEN="tok", SQUARE_LOCATION_ID="L",
                   SQUARE_TICKET_CATEGORY_ID="C")
class SaveToastTests(StaffTestCase):
    """In production the view's atomic block commits on exit and runs the
    on-commit sync before the toast is built. A TestCase never commits (and
    captureOnCommitCallbacks only runs callbacks after the response), so
    on_commit runs its callback at once here, which gives the same order.
    """

    def setUp(self) -> None:
        super().setUp()
        self.gw = FakeGateway()
        for patcher in (
            mock.patch("boxoffice.sync.get_gateway", return_value=self.gw),
            mock.patch("boxoffice.sync.transaction.on_commit",
                       side_effect=lambda fn, *a, **kw: fn()),
        ):
            patcher.start()
            self.addCleanup(patcher.stop)

    def _payload(self, **over):
        data = {
            "kind": "REGULAR", "display_title": "", "screen": self.screen.pk,
            "start_date": self.today.isoformat(),
            "end_date": self.today.isoformat(),
            "presentation_format": "2d", "language": "english", "translation": "none", "status": "CONFIRMED",
            "show_in_main_listings": "on", "notes": "", "films": [self.film.pk],
        }
        data.update(over)
        return data

    def _toast(self, resp) -> dict:
        return json.loads(resp["HX-Trigger"])["dashboard-toast"]

    def test_create_with_square_failure_says_so(self) -> None:
        self.gw.fail_with = GatewayError("boom")
        with self.assertLogs("boxoffice.sync", "WARNING"):
            resp = self.client.post(reverse("dashboard:engagement_create"),
                                    self._payload())
        self.assertEqual(self._toast(resp), {
            "kind": "error", "message": "Saved. Square sync failed — see the run"})
        self.assertTrue(json.loads(resp["HX-Trigger"])["close-drawer"])

    def test_create_with_square_success_is_normal(self) -> None:
        resp = self.client.post(reverse("dashboard:engagement_create"),
                                self._payload())
        self.assertEqual(self._toast(resp),
                         {"kind": "success", "message": "Engagement created"})
        self.assertIn("item-1", self.gw.items)

    def test_edit_and_status_with_square_failure_say_so(self) -> None:
        eng = make_eng(self.screen, films=[self.film], status="DRAFT",
                       end_date=self.today)
        self.gw.fail_with = GatewayError("boom")
        failed = {"kind": "error",
                  "message": "Saved. Square sync failed — see the run"}
        with self.assertLogs("boxoffice.sync", "WARNING"):
            resp = self.client.post(
                reverse("dashboard:engagement_edit", args=[eng.pk]),
                self._payload())
        self.assertEqual(self._toast(resp), failed)
        status_url = reverse("dashboard:engagement_status", args=[eng.pk])
        with self.assertLogs("boxoffice.sync", "WARNING"):
            resp = self.client.post(status_url + "?tab=CURRENT",
                                    {"status": "CONFIRMED"})
        self.assertEqual(self._toast(resp), failed)

    def test_edit_and_status_with_square_success_are_normal(self) -> None:
        eng = make_eng(self.screen, films=[self.film], status="DRAFT",
                       end_date=self.today)
        resp = self.client.post(
            reverse("dashboard:engagement_edit", args=[eng.pk]), self._payload())
        self.assertEqual(self._toast(resp),
                         {"kind": "success", "message": "Engagement updated"})
        status_url = reverse("dashboard:engagement_status", args=[eng.pk])
        resp = self.client.post(status_url + "?tab=CURRENT",
                                {"status": "CONFIRMED"})
        self.assertEqual(self._toast(resp),
                         {"kind": "success", "message": "Status updated"})

    @override_settings(SQUARE_ACCESS_TOKEN="")
    def test_disabled_square_never_shows_the_failure_toast(self) -> None:
        eng = make_eng(self.screen, films=[self.film], status="CONFIRMED",
                       end_date=self.today)
        SquareItem.objects.create(engagement=eng, name="Dune",
                                  last_error="stale")
        status_url = reverse("dashboard:engagement_status", args=[eng.pk])
        with mock.patch("boxoffice.sync.get_gateway", return_value=None):
            resp = self.client.post(status_url + "?tab=CURRENT",
                                    {"status": "CONFIRMED"})
        self.assertEqual(live_item(eng).last_error, "stale")
        self.assertEqual(self._toast(resp),
                         {"kind": "success", "message": "Status updated"})
