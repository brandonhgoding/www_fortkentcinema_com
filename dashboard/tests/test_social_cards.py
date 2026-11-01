"""The engagement social cards were removed on 2026-11-01: nothing renders or
serves them any more."""

import datetime

from django.conf import settings
from django.test import TestCase
from django.urls import NoReverseMatch, reverse

from cinema.models import Engagement, Screen
from dashboard.tests.helpers import make_staff


class SocialCardsRemovedTests(TestCase):
    def setUp(self) -> None:
        make_staff(email="s@example.com", password="pw12345")
        self.client.login(username="s@example.com", password="pw12345")
        self.eng = Engagement.objects.create(
            screen=Screen.objects.create(name="Screen 1", capacity=100),
            start_date=datetime.date(2026, 7, 1),
            end_date=datetime.date(2026, 7, 7),
        )

    def test_engagement_page_has_no_social_cards_panel(self) -> None:
        html = self.client.get(
            reverse("dashboard:engagement_detail", args=[self.eng.pk])
        ).content.decode()
        self.assertNotIn("socialCards", html)
        self.assertNotIn("social_cards.css", html)

    def test_the_card_route_is_gone(self) -> None:
        with self.assertRaises(NoReverseMatch):
            reverse("dashboard:engagement_social_card", args=[self.eng.pk, "facebook"])
        url = f"/dashboard/engagements/{self.eng.pk}/social/facebook.png"
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 404)

    def test_no_artwork_cache(self) -> None:
        self.assertNotIn("social_cards", settings.CACHES)
