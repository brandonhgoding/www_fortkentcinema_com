import datetime
from io import BytesIO
from unittest import mock

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from PIL import Image

from cinema.models import Engagement, EngagementFilm, Film, Screen

User = get_user_model()


def an_image() -> Image.Image:
    return Image.new("RGB", (400, 600), (200, 40, 40))


class SocialCardViewTests(TestCase):
    def setUp(self) -> None:
        User.objects.create_user(username="s", password="pw12345", is_staff=True)
        self.client.login(username="s", password="pw12345")
        self.screen = Screen.objects.create(name="Screen 1", capacity=100)
        self.film = Film.objects.create(
            title="Dune", poster_url="https://image.tmdb.org/t/p/w500/d.jpg"
        )
        self.eng = Engagement.objects.create(
            screen=self.screen,
            start_date=datetime.date(2026, 7, 1),
            end_date=datetime.date(2026, 7, 7),
        )
        EngagementFilm.objects.create(
            engagement=self.eng, film=self.film, position=1
        )
        patcher = mock.patch(
            "cinema.social_cards.fetch_artwork", return_value=an_image()
        )
        self.addCleanup(patcher.stop)
        patcher.start()

    def url(self, platform: str = "instagram", **params: str) -> str:
        base = reverse(
            "dashboard:engagement_social_card", args=[self.eng.pk, platform]
        )
        if not params:
            return base
        query = "&".join(f"{k}={v}" for k, v in params.items())
        return f"{base}?{query}"

    def test_returns_a_png(self) -> None:
        response = self.client.get(self.url())
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "image/png")
        self.assertEqual(Image.open(BytesIO(response.content)).size, (1080, 1080))

    def test_facebook_dimensions(self) -> None:
        response = self.client.get(self.url("facebook"))
        self.assertEqual(Image.open(BytesIO(response.content)).size, (1200, 630))

    def test_served_inline_by_default(self) -> None:
        response = self.client.get(self.url())
        self.assertIn("inline", response["Content-Disposition"])

    def test_download_param_forces_an_attachment(self) -> None:
        response = self.client.get(self.url("instagram", download="1"))
        self.assertIn("attachment", response["Content-Disposition"])
        self.assertIn(
            'filename="fkc-dune-now-playing-instagram.png"',
            response["Content-Disposition"],
        )

    def test_badge_param_is_honoured(self) -> None:
        response = self.client.get(
            self.url("facebook", badge="coming_soon", download="1")
        )
        self.assertIn(
            'filename="fkc-dune-coming-soon-facebook.png"',
            response["Content-Disposition"],
        )

    def test_unrecognised_badge_falls_back_to_the_default(self) -> None:
        response = self.client.get(
            self.url("facebook", badge="whenever", download="1")
        )
        self.assertIn("now-playing", response["Content-Disposition"])

    def test_unknown_platform_is_a_400(self) -> None:
        response = self.client.get(
            reverse(
                "dashboard:engagement_social_card", args=[self.eng.pk, "tiktok"]
            )
        )
        self.assertEqual(response.status_code, 400)

    def test_unknown_engagement_is_a_404(self) -> None:
        response = self.client.get(
            reverse("dashboard:engagement_social_card", args=[9999, "facebook"])
        )
        self.assertEqual(response.status_code, 404)

    def test_anonymous_users_are_redirected(self) -> None:
        self.client.logout()
        self.assertEqual(self.client.get(self.url()).status_code, 302)

    def test_non_staff_users_are_forbidden(self) -> None:
        User.objects.create_user(username="u", password="pw12345")
        self.client.logout()
        self.client.login(username="u", password="pw12345")
        self.assertEqual(self.client.get(self.url()).status_code, 403)
