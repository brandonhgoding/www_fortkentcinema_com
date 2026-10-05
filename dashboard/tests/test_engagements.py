import datetime

from cinema.models import Engagement, EngagementFilm, Film, Screen, Showtime
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

User = get_user_model()


def make_engagement(screen, *, start, end, status="CONFIRMED", kind="REGULAR",
                    films=(), show=True, event_title=""):
    eng = Engagement.objects.create(
        screen=screen, start_date=start, end_date=end, status=status, kind=kind,
        show_in_main_listings=show, event_title=event_title,
    )
    for i, f in enumerate(films, start=1):
        EngagementFilm.objects.create(engagement=eng, film=f, position=i)
    return eng


class EngagementListTests(TestCase):
    def setUp(self) -> None:
        User.objects.create_user(username="s", password="pw12345", is_staff=True)
        self.client.login(username="s", password="pw12345")
        self.screen = Screen.objects.create(name="Screen 1", capacity=100)
        self.film = Film.objects.create(title="Jaws", poster_url="https://img/j.jpg")
        self.today = timezone.localdate()

    def test_current_tab_default(self) -> None:
        make_engagement(self.screen, start=self.today - datetime.timedelta(days=1),
                        end=self.today + datetime.timedelta(days=1), films=[self.film])
        html = self.client.get(reverse("dashboard:engagements")).content.decode()
        self.assertIn("Jaws", html)
        self.assertIn("Screen 1", html)

    def test_upcoming_excludes_current(self) -> None:
        make_engagement(self.screen, start=self.today - datetime.timedelta(days=1),
                        end=self.today + datetime.timedelta(days=1), films=[self.film])
        html = self.client.get(reverse("dashboard:engagements"), {"tab": "UPCOMING"}).content.decode()
        self.assertNotIn("Jaws", html)
        self.assertIn("empty-state", html)

    def test_draft_tab(self) -> None:
        make_engagement(self.screen, start=self.today, end=self.today, status="DRAFT",
                        films=[self.film])
        html = self.client.get(reverse("dashboard:engagements"), {"tab": "DRAFT"}).content.decode()
        self.assertIn("Jaws", html)

    def test_kind_and_hidden_badges(self) -> None:
        make_engagement(self.screen, start=self.today, end=self.today, kind="CLASSIC",
                        films=[self.film], show=False, event_title="Noir Night")
        html = self.client.get(reverse("dashboard:engagements")).content.decode()
        self.assertIn("Classic", html)   # kind badge
        self.assertIn("Hidden", html)    # hidden badge

    def test_detail_stub_resolves(self) -> None:
        self.assertEqual(reverse("dashboard:engagement_detail", args=[1]), "/dashboard/engagements/1")

    def test_combo_css_and_reactive_tabs_present(self) -> None:
        html = self.client.get(reverse("dashboard:engagements")).content.decode()
        # FilmSearchCombo dropdown CSS must be linked (else the picker is unstyled/off-screen)
        self.assertIn("dashboard/css/film_search_combo.css", html)
        # Filter tabs are client-reactive so the active pill follows HTMX tab selection
        self.assertIn("x-data=\"{ tab:", html)
        self.assertIn(":class=\"{ active: tab ===", html)

    def test_requires_staff(self) -> None:
        self.client.logout()
        self.assertEqual(self.client.get(reverse("dashboard:engagements")).status_code, 302)

    def test_htmx_tab_returns_partial(self) -> None:
        resp = self.client.get(reverse("dashboard:engagements"), {"tab": "DRAFT"},
                               HTTP_HX_REQUEST="true")
        body = resp.content.decode()
        self.assertIn('id="engagement-list"', body)
        self.assertNotIn("<!doctype", body.lower())   # not the full page
        self.assertNotIn('class="sidebar"', body)       # no chrome

    def test_non_htmx_returns_full_page(self) -> None:
        body = self.client.get(reverse("dashboard:engagements")).content.decode()
        self.assertIn("<!doctype", body.lower())


class EngagementStatusTests(TestCase):
    def setUp(self) -> None:
        User.objects.create_user(username="s", password="pw12345", is_staff=True)
        self.client.login(username="s", password="pw12345")
        self.screen = Screen.objects.create(name="S1", capacity=50)
        self.today = timezone.localdate()

    def test_cancelling_frees_the_upcoming_showtimes(self) -> None:
        e = make_engagement(self.screen, start=self.today, end=self.today)
        st = Showtime.objects.create(
            engagement=e, starts_at=timezone.now() + datetime.timedelta(hours=2))
        self.client.post(reverse("dashboard:engagement_status", args=[e.pk]),
                         {"status": "CANCELLED"})
        st.refresh_from_db()
        self.assertTrue(st.is_cancelled)

    def test_status_change_updates_and_refreshes(self) -> None:
        e = make_engagement(self.screen, start=self.today, end=self.today, status="DRAFT")
        resp = self.client.post(reverse("dashboard:engagement_status", args=[e.pk]) + "?tab=DRAFT",
                                {"status": "CONFIRMED"})
        self.assertEqual(resp.status_code, 200)
        e.refresh_from_db()
        self.assertEqual(e.status, "CONFIRMED")
        self.assertIn('id="engagement-list"', resp.content.decode())
        self.assertIn("dashboard-toast", resp["HX-Trigger"])

    def test_status_rejects_ended_value(self) -> None:
        e = make_engagement(self.screen, start=self.today, end=self.today, status="DRAFT")
        resp = self.client.post(reverse("dashboard:engagement_status", args=[e.pk]),
                                {"status": "ENDED"})
        e.refresh_from_db()
        self.assertEqual(e.status, "DRAFT")  # ENDED not manually settable
        self.assertEqual(resp.status_code, 400)

    def test_ended_engagement_locked(self) -> None:
        past = self.today - datetime.timedelta(days=5)
        make_engagement(self.screen, start=past, end=past, status="CONFIRMED")
        html = self.client.get(reverse("dashboard:engagements"), {"tab": "ENDED"}).content.decode()
        # locked: the status button is disabled for an ended engagement
        self.assertIn("disabled", html)


class EngagementDeleteTests(TestCase):
    def setUp(self) -> None:
        User.objects.create_user(username="s", password="pw12345", is_staff=True)
        self.client.login(username="s", password="pw12345")
        self.screen = Screen.objects.create(name="S1", capacity=50)
        self.today = timezone.localdate()

    def test_delete_cascades(self) -> None:
        f = Film.objects.create(title="X")
        e = make_engagement(self.screen, start=self.today, end=self.today, films=[f])
        resp = self.client.post(reverse("dashboard:engagement_delete", args=[e.pk]) + "?tab=CURRENT")
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(Engagement.objects.filter(pk=e.pk).exists())
        self.assertEqual(EngagementFilm.objects.count(), 0)  # cascaded
        self.assertIn("dashboard-toast", resp["HX-Trigger"])


class EngagementCreateTests(TestCase):
    def setUp(self) -> None:
        User.objects.create_user(username="s", password="pw12345", is_staff=True)
        self.client.login(username="s", password="pw12345")
        self.screen = Screen.objects.create(name="S1", capacity=50)
        self.f1 = Film.objects.create(title="A")
        self.f2 = Film.objects.create(title="B")
        self.today = timezone.localdate()

    def _payload(self, **over):
        data = {
            "kind": "REGULAR", "event_title": "", "screen": self.screen.pk,
            "start_date": self.today.isoformat(), "end_date": self.today.isoformat(),
            "presentation_format": "2d", "status": "DRAFT", "show_in_main_listings": "on",
            "notes": "", "films": [self.f1.pk],
        }
        data.update(over)
        return data

    def test_get_form(self) -> None:
        html = self.client.get(reverse("dashboard:engagement_create")).content.decode()
        self.assertIn('id="engagement-form"', html)
        self.assertIn("Create Engagement", html)

    def test_create_single_film(self) -> None:
        resp = self.client.post(reverse("dashboard:engagement_create") + "?tab=DRAFT", self._payload())
        self.assertEqual(resp.status_code, 200)
        e = Engagement.objects.get()
        self.assertEqual(list(e.engagement_films.values_list("film_id", "position")), [(self.f1.pk, 1)])
        self.assertIn("close-drawer", resp["HX-Trigger"])

    def test_create_double_feature_orders_films(self) -> None:
        resp = self.client.post(reverse("dashboard:engagement_create"),
                                self._payload(kind="DOUBLE_FEATURE", films=[self.f2.pk, self.f1.pk]))
        self.assertEqual(resp.status_code, 200)
        e = Engagement.objects.get()
        self.assertEqual(list(e.engagement_films.values_list("film_id", "position")),
                         [(self.f2.pk, 1), (self.f1.pk, 2)])

    def test_double_feature_requires_two(self) -> None:
        resp = self.client.post(reverse("dashboard:engagement_create"),
                                self._payload(kind="DOUBLE_FEATURE", films=[self.f1.pk]))
        self.assertEqual(Engagement.objects.count(), 0)
        self.assertIn("at least two", resp.content.decode().lower())

    def test_missing_film(self) -> None:
        resp = self.client.post(reverse("dashboard:engagement_create"), self._payload(films=[]))
        self.assertEqual(Engagement.objects.count(), 0)
        self.assertIn('id="engagement-form"', resp.content.decode())

    def test_end_before_start(self) -> None:
        self.client.post(reverse("dashboard:engagement_create"),
                         self._payload(end_date=(self.today - datetime.timedelta(days=1)).isoformat()))
        self.assertEqual(Engagement.objects.count(), 0)

    def test_in_ticket_report_unticked_saves_false(self) -> None:
        payload = self._payload()
        payload.pop("in_ticket_report", None)  # an unticked checkbox is absent from POST
        self.client.post(reverse("dashboard:engagement_create"), payload)
        self.assertFalse(Engagement.objects.get().in_ticket_report)

    def test_in_ticket_report_ticked_saves_true(self) -> None:
        self.client.post(reverse("dashboard:engagement_create"),
                         self._payload(in_ticket_report="on"))
        self.assertTrue(Engagement.objects.get().in_ticket_report)


class EngagementEditTests(TestCase):
    def setUp(self) -> None:
        User.objects.create_user(username="s", password="pw12345", is_staff=True)
        self.client.login(username="s", password="pw12345")
        self.screen = Screen.objects.create(name="S1", capacity=50)
        self.f1 = Film.objects.create(title="A")
        self.f2 = Film.objects.create(title="B")
        self.today = timezone.localdate()

    def test_get_prefilled(self) -> None:
        e = make_engagement(self.screen, start=self.today, end=self.today, films=[self.f1])
        html = self.client.get(reverse("dashboard:engagement_edit", args=[e.pk])).content.decode()
        self.assertIn("Save Changes", html)
        self.assertIn('"title": "A"', html)  # initial_films_json seeds the Alpine state

    def test_edit_replaces_film_set(self) -> None:
        e = make_engagement(self.screen, start=self.today, end=self.today,
                            kind="DOUBLE_FEATURE", films=[self.f1, self.f2])
        data = {
            "kind": "DOUBLE_FEATURE", "event_title": "", "screen": self.screen.pk,
            "start_date": self.today.isoformat(), "end_date": self.today.isoformat(),
            "presentation_format": "2d", "status": "DRAFT", "show_in_main_listings": "on",
            "notes": "", "films": [self.f2.pk, self.f1.pk],  # reversed order
        }
        resp = self.client.post(reverse("dashboard:engagement_edit", args=[e.pk]), data)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(list(e.engagement_films.values_list("film_id", "position")),
                         [(self.f2.pk, 1), (self.f1.pk, 2)])
