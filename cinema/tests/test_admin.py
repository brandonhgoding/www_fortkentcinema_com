from cinema.admin import EngagementAdmin, EngagementFilmInline, ShowtimeInline
from cinema.models import Engagement, Film, Screen, Showtime
from django.contrib import admin
from django.test import TestCase


class CinemaAdminTestCase(TestCase):
    def test_models_registered(self) -> None:
        for model in (Film, Screen, Showtime, Engagement):
            self.assertIn(model, admin.site._registry)

    def test_engagement_admin_has_inlines(self) -> None:
        engagement_admin = admin.site._registry[Engagement]
        self.assertIsInstance(engagement_admin, EngagementAdmin)
        self.assertIn(EngagementFilmInline, engagement_admin.inlines)
        self.assertIn(ShowtimeInline, engagement_admin.inlines)
