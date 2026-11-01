import datetime

from accounts.tests.factories import make_user
from cinema.admin import EngagementFilmInline, ShowtimeInline
from cinema.models import Engagement, Screen
from django.test import TestCase
from django.urls import reverse


class EngagementAdminTests(TestCase):
    def test_change_page_renders_with_films_and_showtimes_inlines(self) -> None:
        self.client.force_login(
            make_user(
                email="root@example.com",
                password="pw",
                is_staff=True,
                is_superuser=True,
            )
        )
        eng = Engagement.objects.create(
            screen=Screen.objects.create(name="Screen 1", capacity=100),
            start_date=datetime.date(2026, 7, 1),
            end_date=datetime.date(2026, 7, 7),
        )
        resp = self.client.get(
            reverse("admin:cinema_engagement_change", args=[eng.pk])
        )
        self.assertEqual(resp.status_code, 200)
        inlines = {
            type(formset.opts) for formset in resp.context["inline_admin_formsets"]
        }
        self.assertEqual(inlines, {EngagementFilmInline, ShowtimeInline})
