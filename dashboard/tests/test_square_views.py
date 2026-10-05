from unittest import mock

from boxoffice.gateway import GatewayError
from boxoffice.models import SquareItem, SquareVariation
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


@override_settings(SQUARE_ACCESS_TOKEN="tok")
class EngagementSquareHookTests(StaffTestCase):
    def _payload(self, **over):
        data = {
            "kind": "REGULAR", "event_title": "", "screen": self.screen.pk,
            "start_date": self.today.isoformat(),
            "end_date": self.today.isoformat(),
            "presentation_format": "2d", "status": "DRAFT",
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


@override_settings(SQUARE_ACCESS_TOKEN="tok")
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
        with mock.patch("dashboard.views.push") as push:
            resp = self.client.post(retry_url(eng.pk))
        self.assertEqual(resp.status_code, 302)
        push.assert_not_called()

    def test_calls_push_and_redirects(self) -> None:
        eng = make_eng(self.screen, films=[self.film])
        with mock.patch("dashboard.views.push") as push:
            resp = self.client.post(retry_url(eng.pk))
        push.assert_called_once_with(eng)
        detail = reverse("dashboard:engagement_detail", args=[eng.pk])
        self.assertRedirects(resp, detail, fetch_redirect_response=False)

    def test_unknown_engagement_404(self) -> None:
        with mock.patch("dashboard.views.push") as push:
            resp = self.client.post(retry_url(999999))
        self.assertEqual(resp.status_code, 404)
        push.assert_not_called()
