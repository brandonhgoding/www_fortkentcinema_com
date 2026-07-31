import datetime

from django.test import TestCase

from cinema.models import Engagement, EngagementFilm, Film, Screen
from cinema.social_cards import card as card_mod
from cinema.social_cards.card import (
    BADGE_COMING_SOON,
    BADGE_NOW_PLAYING,
    FACEBOOK,
    INSTAGRAM,
    Artwork,
    CardData,
    default_badge,
    format_date_line,
    resolve_artwork,
)

JULY_1 = datetime.date(2026, 7, 1)
JULY_7 = datetime.date(2026, 7, 7)


def make_film(title: str, **over: str) -> Film:
    defaults = {"poster_url": "", "backdrop_url": ""}
    defaults.update(over)
    return Film.objects.create(title=title, **defaults)


class DateLineTests(TestCase):
    def test_now_playing_multi_day(self) -> None:
        self.assertEqual(
            format_date_line(JULY_1, JULY_7, BADGE_NOW_PLAYING),
            "NOW THROUGH JULY 7",
        )

    def test_coming_soon_multi_day(self) -> None:
        self.assertEqual(
            format_date_line(JULY_1, JULY_7, BADGE_COMING_SOON),
            "STARTS JULY 1",
        )

    def test_single_day_is_the_same_for_both_badges(self) -> None:
        for badge in (BADGE_NOW_PLAYING, BADGE_COMING_SOON):
            self.assertEqual(
                format_date_line(JULY_1, JULY_1, badge),
                "ONE NIGHT ONLY · JULY 1",
            )

    def test_run_crossing_a_month_boundary(self) -> None:
        self.assertEqual(
            format_date_line(
                datetime.date(2026, 8, 29),
                datetime.date(2026, 9, 4),
                BADGE_NOW_PLAYING,
            ),
            "NOW THROUGH SEPTEMBER 4",
        )

    def test_no_year_is_shown(self) -> None:
        self.assertNotIn("2026", format_date_line(JULY_1, JULY_7, BADGE_NOW_PLAYING))


class BadgeDefaultTests(TestCase):
    def setUp(self) -> None:
        self.screen = Screen.objects.create(name="Screen 1", capacity=100)

    def _eng(self) -> Engagement:
        return Engagement.objects.create(
            screen=self.screen, start_date=JULY_1, end_date=JULY_7
        )

    def test_future_run_is_coming_soon(self) -> None:
        eng = self._eng()
        self.assertEqual(
            default_badge(eng, today=datetime.date(2026, 6, 30)), BADGE_COMING_SOON
        )

    def test_on_the_start_date_it_is_now_playing(self) -> None:
        eng = self._eng()
        self.assertEqual(default_badge(eng, today=JULY_1), BADGE_NOW_PLAYING)

    def test_mid_run_is_now_playing(self) -> None:
        eng = self._eng()
        self.assertEqual(
            default_badge(eng, today=datetime.date(2026, 7, 4)), BADGE_NOW_PLAYING
        )

    def test_past_run_is_now_playing(self) -> None:
        # Deliberate: the operator decides how to label a finished run.
        eng = self._eng()
        self.assertEqual(
            default_badge(eng, today=datetime.date(2026, 12, 1)), BADGE_NOW_PLAYING
        )


class ResolveArtworkTests(TestCase):
    def test_facebook_single_film_uses_poster_centred(self) -> None:
        film = make_film("Dune", poster_url="https://img/p.jpg",
                         backdrop_url="https://img/b.jpg")
        self.assertEqual(
            resolve_artwork([film], FACEBOOK),
            (Artwork("https://img/p.jpg", card_mod.CENTRE_CROP),),
        )

    def test_instagram_single_film_prefers_backdrop(self) -> None:
        film = make_film("Dune", poster_url="https://img/p.jpg",
                         backdrop_url="https://img/b.jpg")
        self.assertEqual(
            resolve_artwork([film], INSTAGRAM),
            (Artwork("https://img/b.jpg", card_mod.CENTRE_CROP),),
        )

    def test_instagram_falls_back_to_top_biased_poster(self) -> None:
        film = make_film("Dune", poster_url="https://img/p.jpg")
        self.assertEqual(
            resolve_artwork([film], INSTAGRAM),
            (Artwork("https://img/p.jpg", card_mod.TOP_CROP),),
        )

    def test_no_artwork_at_all(self) -> None:
        self.assertEqual(resolve_artwork([make_film("Dune")], INSTAGRAM), ())

    def test_no_films(self) -> None:
        self.assertEqual(resolve_artwork([], FACEBOOK), ())

    def test_two_films_split_into_two_posters(self) -> None:
        a = make_film("A", poster_url="https://img/a.jpg")
        b = make_film("B", poster_url="https://img/b.jpg")
        self.assertEqual(
            resolve_artwork([a, b], INSTAGRAM),
            (
                Artwork("https://img/a.jpg", card_mod.CENTRE_CROP),
                Artwork("https://img/b.jpg", card_mod.CENTRE_CROP),
            ),
        )

    def test_two_films_but_only_one_poster_falls_back_to_single(self) -> None:
        a = make_film("A", poster_url="https://img/a.jpg")
        b = make_film("B")
        self.assertEqual(
            resolve_artwork([a, b], FACEBOOK),
            (Artwork("https://img/a.jpg", card_mod.CENTRE_CROP),),
        )

    def test_three_films_use_the_first_two(self) -> None:
        films = [
            make_film(name, poster_url=f"https://img/{name}.jpg")
            for name in ("A", "B", "C")
        ]
        self.assertEqual(
            resolve_artwork(films, FACEBOOK),
            (
                Artwork("https://img/A.jpg", card_mod.CENTRE_CROP),
                Artwork("https://img/B.jpg", card_mod.CENTRE_CROP),
            ),
        )

    def test_three_films_first_two_no_artwork_ignores_third(self) -> None:
        # First two have no artwork, third does — should return empty
        # (contract: only use first two films)
        a = make_film("A")
        b = make_film("B")
        c = make_film("C", poster_url="https://img/c.jpg")
        self.assertEqual(resolve_artwork([a, b, c], FACEBOOK), ())


class CardDataTests(TestCase):
    def setUp(self) -> None:
        self.screen = Screen.objects.create(name="Screen 1", capacity=100)

    def _eng(self, films: list[Film], **over: object) -> Engagement:
        defaults: dict[str, object] = {
            "screen": self.screen,
            "start_date": JULY_1,
            "end_date": JULY_7,
        }
        defaults.update(over)
        eng = Engagement.objects.create(**defaults)
        for i, film in enumerate(films, start=1):
            EngagementFilm.objects.create(engagement=eng, film=film, position=i)
        return eng

    def test_single_film_headline_and_slug(self) -> None:
        eng = self._eng([make_film("Dune", poster_url="https://img/p.jpg")])
        data = CardData.from_engagement(eng, FACEBOOK, today=JULY_1)
        self.assertEqual(data.headline, "DUNE")
        self.assertEqual(data.slug, "dune")
        self.assertEqual(data.badge, BADGE_NOW_PLAYING)
        self.assertEqual(data.date_line, "NOW THROUGH JULY 7")
        self.assertEqual(data.wordmark, "FORT KENT CINEMA")
        self.assertEqual(
            data.footer, "VISIT WWW.FORTKENTCINEMA.COM FOR SHOWTIMES"
        )

    def test_two_films_join_in_the_headline(self) -> None:
        eng = self._eng([make_film("Alien"), make_film("Aliens")])
        data = CardData.from_engagement(eng, FACEBOOK, today=JULY_1)
        self.assertEqual(data.headline, "ALIEN + ALIENS")

    def test_event_title_overrides_the_film_names(self) -> None:
        eng = self._eng(
            [make_film("Alien"), make_film("Aliens")],
            event_title="Xenomorph Double Feature",
        )
        data = CardData.from_engagement(eng, FACEBOOK, today=JULY_1)
        self.assertEqual(data.headline, "XENOMORPH DOUBLE FEATURE")
        self.assertEqual(data.slug, "xenomorph-double-feature")

    def test_engagement_with_no_films_falls_back(self) -> None:
        eng = self._eng([])
        data = CardData.from_engagement(eng, FACEBOOK, today=JULY_1)
        self.assertEqual(data.headline, "FORT KENT CINEMA")
        self.assertEqual(data.slug, f"engagement-{eng.pk}")
        self.assertEqual(data.artwork, ())

    def test_explicit_badge_overrides_the_date_derived_default(self) -> None:
        eng = self._eng([make_film("Dune")])
        data = CardData.from_engagement(
            eng, FACEBOOK, badge=BADGE_COMING_SOON,
            today=datetime.date(2026, 7, 4),
        )
        self.assertEqual(data.badge, BADGE_COMING_SOON)
        self.assertEqual(data.date_line, "STARTS JULY 1")
