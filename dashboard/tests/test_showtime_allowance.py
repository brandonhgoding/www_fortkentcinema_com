import datetime
import json
from zoneinfo import ZoneInfo

from cinema.models import Film, Screen, Showtime
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from tickets.availability import remaining
from tickets.tests.factories import make_order

from dashboard.tests.test_engagement_detail import make_eng

User = get_user_model()
TZ = ZoneInfo("America/New_York")
ALLOWANCE_ERROR = "Online allowance must be a whole number."


class ShowtimeAllowanceTests(TestCase):
    def setUp(self) -> None:
        User.objects.create_user(username="s", password="pw12345", is_staff=True)
        self.client.login(username="s", password="pw12345")
        self.screen = Screen.objects.create(name="Screen 1", capacity=100)
        film = Film.objects.create(title="Dune", runtime_minutes=155)
        self.eng = make_eng(self.screen, films=[film])
        self.st = Showtime.objects.create(
            engagement=self.eng,
            starts_at=datetime.datetime(2026, 7, 4, 19, 0, tzinfo=TZ),
        )

    def edit(self, **over):
        data = {
            "date": "2026-07-04",
            "time": "19:00",
            "captions": "",
            "online_allowance": "",
        }
        data.update(over)
        return self.client.post(
            reverse("dashboard:showtime_edit", args=[self.st.pk]), data
        )

    def toast(self, resp):
        return json.loads(resp["HX-Trigger"])["dashboard-toast"]

    def test_edit_saves_allowance_and_blank_means_default(self) -> None:
        self.edit(online_allowance="7")
        self.st.refresh_from_db()
        self.assertEqual(self.st.online_allowance, 7)
        self.edit(online_allowance="")
        self.st.refresh_from_db()
        self.assertIsNone(self.st.online_allowance)

    def test_zero_allowance_is_saved(self) -> None:
        self.edit(online_allowance="0")
        self.st.refresh_from_db()
        self.assertEqual(self.st.online_allowance, 0)

    def test_edit_form_shows_allowance_with_default_placeholder(self) -> None:
        self.st.online_allowance = 12
        self.st.save()
        html = self.client.get(
            reverse("dashboard:showtime_edit", args=[self.st.pk])
        ).content.decode()
        self.assertIn('name="online_allowance"', html)
        self.assertIn('value="12"', html)
        self.assertIn('placeholder="50"', html)

    def test_edit_rejects_negative_or_non_number(self) -> None:
        for bad in ("-1", "lots", "2.5"):
            with self.subTest(bad=bad):
                resp = self.edit(online_allowance=bad)
                self.assertIn(ALLOWANCE_ERROR, resp.content.decode())
                self.st.refresh_from_db()
                self.assertIsNone(self.st.online_allowance)

    def test_allowance_below_sold_is_allowed(self) -> None:
        make_order(self.st, status="PAID", lines={"adult": 5})
        resp = self.edit(online_allowance="2")
        self.assertNotIn("formAlert", resp.content.decode())
        self.st.refresh_from_db()
        self.assertEqual(self.st.online_allowance, 2)
        self.assertEqual(remaining(self.st, timezone.now()), 0)

    def test_list_shows_online_count_with_link(self) -> None:
        make_order(self.st, status="PAID", lines={"adult": 3, "child": 2})
        html = self.client.get(
            reverse("dashboard:engagement_detail", args=[self.eng.pk])
        ).content.decode()
        orders_url = reverse("dashboard:showtime_orders", args=[self.st.pk])
        self.assertIn("<th>Online</th>", html)
        self.assertEqual(
            html.count(f'href="{orders_url}">5</a> / 50'), 2
        )  # table and card

    def test_saved_list_shows_online_count(self) -> None:
        make_order(self.st, status="PAID", lines={"adult": 5})
        html = self.edit(online_allowance="8").content.decode()
        self.assertIn(">5</a> / 8", html)

    def test_moving_a_showtime_with_orders_warns(self) -> None:
        make_order(self.st, status="PAID", lines={"adult": 2})
        make_order(self.st, status="PAID", email="bo@example.com")
        make_order(self.st, status="EXPIRED")
        resp = self.edit(time="20:00")
        self.assertEqual(
            self.toast(resp),
            {
                "kind": "warning",
                "message": "Showtime updated. 2 online orders were emailed"
                " the old time. Let them know.",
            },
        )

    def test_moving_a_showtime_with_one_order_warns_in_the_singular(self) -> None:
        make_order(self.st, status="PAID", lines={"adult": 3})
        resp = self.edit(time="20:00")
        self.assertEqual(
            self.toast(resp)["message"],
            "Showtime updated. 1 online order was emailed the old time. Let them know.",
        )

    def test_editing_without_moving_does_not_warn(self) -> None:
        make_order(self.st, status="PAID")
        resp = self.edit(online_allowance="10")
        self.assertEqual(
            self.toast(resp), {"kind": "success", "message": "Showtime updated"}
        )

    def test_moving_a_showtime_without_sold_orders_does_not_warn(self) -> None:
        make_order(self.st, status="PENDING")
        resp = self.edit(time="20:00")
        self.assertEqual(self.toast(resp)["kind"], "success")

    def test_create_form_accepts_allowance(self) -> None:
        url = reverse("dashboard:showtime_create", args=[self.eng.pk])
        html = self.client.get(url).content.decode()
        self.assertIn('name="online_allowance"', html)
        self.assertIn('placeholder="50"', html)
        self.client.post(
            url,
            {
                "date": "2026-07-05",
                "time": "19:00",
                "captions": "",
                "online_allowance": "30",
            },
        )
        self.assertEqual(
            Showtime.objects.get(starts_at__date="2026-07-05").online_allowance, 30
        )

    def test_create_rejects_bad_allowance(self) -> None:
        url = reverse("dashboard:showtime_create", args=[self.eng.pk])
        resp = self.client.post(
            url,
            {
                "date": "2026-07-05",
                "time": "19:00",
                "captions": "",
                "online_allowance": "-3",
            },
        )
        self.assertIn(ALLOWANCE_ERROR, resp.content.decode())
        self.assertEqual(Showtime.objects.count(), 1)


class ShowtimeOrdersStubTests(TestCase):
    def test_orders_page_resolves_for_staff(self) -> None:
        User.objects.create_user(username="s", password="pw12345", is_staff=True)
        self.client.login(username="s", password="pw12345")
        screen = Screen.objects.create(name="Screen 1", capacity=100)
        film = Film.objects.create(title="Dune", runtime_minutes=155)
        st = Showtime.objects.create(
            engagement=make_eng(screen, films=[film]),
            starts_at=datetime.datetime(2026, 7, 4, 19, 0, tzinfo=TZ),
        )
        resp = self.client.get(reverse("dashboard:showtime_orders", args=[st.pk]))
        self.assertContains(resp, "Dune")
