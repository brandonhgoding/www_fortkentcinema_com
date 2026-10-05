from io import BytesIO
from unittest import mock

import requests
from django.core.cache import caches
from django.test import TestCase
from PIL import Image

from cinema.social_cards import posters

cache = caches["social_cards"]


def png_bytes(width: int = 40, height: int = 60) -> bytes:
    buffer = BytesIO()
    Image.new("RGB", (width, height), (200, 30, 30)).save(buffer, format="PNG")
    return buffer.getvalue()


class FakeResponse:
    def __init__(self, content: bytes, status: int = 200) -> None:
        self.content = content
        self.status_code = status
        self.headers = {"Content-Length": str(len(content))}

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise requests.HTTPError(f"status {self.status_code}")

    def iter_content(self, chunk_size: int = 8192) -> object:
        """Iterate over response content in chunks."""
        for i in range(0, len(self.content), chunk_size):
            yield self.content[i : i + chunk_size]

    def __enter__(self) -> "FakeResponse":
        return self

    def __exit__(
        self, exc_type: object, exc_val: object, exc_tb: object
    ) -> None:
        pass


class UpsizeTests(TestCase):
    def test_w500_becomes_original(self) -> None:
        self.assertEqual(
            posters.upsize_tmdb_url(
                "https://image.tmdb.org/t/p/w500/abc.jpg"
            ),
            "https://image.tmdb.org/t/p/original/abc.jpg",
        )

    def test_already_original_is_unchanged(self) -> None:
        url = "https://image.tmdb.org/t/p/original/abc.jpg"
        self.assertEqual(posters.upsize_tmdb_url(url), url)

    def test_non_tmdb_url_passes_through(self) -> None:
        url = "https://example.com/images/w500/abc.jpg"
        self.assertEqual(posters.upsize_tmdb_url(url), url)

    def test_empty_string(self) -> None:
        self.assertEqual(posters.upsize_tmdb_url(""), "")

    def test_tmdb_pattern_embedded_in_query_string_is_not_rewritten(
        self,
    ) -> None:
        # The pattern must be anchored: unanchored, this would rewrite the
        # embedded TMDB URL mid-query-string, mangling an unrelated URL.
        url = "https://example.com/?u=https://image.tmdb.org/t/p/w500/x.jpg"
        self.assertEqual(posters.upsize_tmdb_url(url), url)


class FetchArtworkTests(TestCase):
    def setUp(self) -> None:
        cache.clear()

    def test_empty_url_returns_none_without_a_request(self) -> None:
        with mock.patch.object(posters.requests, "get") as get:
            self.assertIsNone(posters.fetch_artwork(""))
        get.assert_not_called()

    def test_successful_fetch_returns_rgb_image(self) -> None:
        with mock.patch.object(
            posters.requests, "get", return_value=FakeResponse(png_bytes())
        ):
            image = posters.fetch_artwork("https://img/a.png")
        assert image is not None
        self.assertEqual(image.mode, "RGB")
        self.assertEqual(image.size, (40, 60))

    def test_fetch_upsizes_tmdb_urls(self) -> None:
        with mock.patch.object(
            posters.requests, "get", return_value=FakeResponse(png_bytes())
        ) as get:
            posters.fetch_artwork("https://image.tmdb.org/t/p/w500/a.png")
        self.assertEqual(
            get.call_args.args[0], "https://image.tmdb.org/t/p/original/a.png"
        )

    def test_falls_back_to_the_stored_size_when_original_is_too_big(self) -> None:
        big = FakeResponse(b"x" * (posters.MAX_BYTES + 1))
        small = FakeResponse(png_bytes())
        with mock.patch.object(
            posters.requests, "get", side_effect=[big, small]
        ) as get:
            image = posters.fetch_artwork("https://image.tmdb.org/t/p/w500/a.png")
        self.assertIsNotNone(image)
        self.assertEqual(
            [call.args[0] for call in get.call_args_list],
            [
                "https://image.tmdb.org/t/p/original/a.png",
                "https://image.tmdb.org/t/p/w500/a.png",
            ],
        )

    def test_undecodable_body_is_not_cached(self) -> None:
        with mock.patch.object(
            posters.requests, "get", return_value=FakeResponse(b"not an image")
        ) as get:
            posters.fetch_artwork("https://img/a.png")
            posters.fetch_artwork("https://img/a.png")
        self.assertEqual(get.call_count, 2)

    def test_second_fetch_is_served_from_cache(self) -> None:
        with mock.patch.object(
            posters.requests, "get", return_value=FakeResponse(png_bytes())
        ) as get:
            posters.fetch_artwork("https://img/a.png")
            posters.fetch_artwork("https://img/a.png")
        self.assertEqual(get.call_count, 1)

    def test_timeout_returns_none(self) -> None:
        with mock.patch.object(
            posters.requests, "get", side_effect=requests.Timeout("slow")
        ):
            self.assertIsNone(posters.fetch_artwork("https://img/a.png"))

    def test_http_error_returns_none(self) -> None:
        with mock.patch.object(
            posters.requests, "get", return_value=FakeResponse(b"nope", 404)
        ):
            self.assertIsNone(posters.fetch_artwork("https://img/a.png"))

    def test_oversize_response_returns_none(self) -> None:
        big = b"x" * (posters.MAX_BYTES + 1)
        with mock.patch.object(
            posters.requests, "get", return_value=FakeResponse(big)
        ):
            self.assertIsNone(posters.fetch_artwork("https://img/a.png"))

    def test_undecodable_body_returns_none(self) -> None:
        with mock.patch.object(
            posters.requests, "get", return_value=FakeResponse(b"not an image")
        ):
            self.assertIsNone(posters.fetch_artwork("https://img/a.png"))

    def test_absurdly_large_image_returns_none(self) -> None:
        oversized = png_bytes()
        with mock.patch.object(
            posters.requests, "get", return_value=FakeResponse(oversized)
        ):
            with mock.patch.object(
                posters.Image, "open"
            ) as opener:
                opener.return_value.size = (
                    posters.MAX_PIXELS_PER_AXIS + 1,
                    10,
                )
                self.assertIsNone(posters.fetch_artwork("https://img/a.png"))

    def test_failed_fetch_is_not_cached(self) -> None:
        with mock.patch.object(
            posters.requests, "get", side_effect=requests.Timeout("slow")
        ) as get:
            posters.fetch_artwork("https://img/a.png")
            posters.fetch_artwork("https://img/a.png")
        self.assertEqual(get.call_count, 2)

    def test_redirects_are_not_followed_and_return_none(self) -> None:
        with mock.patch.object(
            posters.requests, "get", return_value=FakeResponse(b"", 302)
        ) as get:
            self.assertIsNone(posters.fetch_artwork("https://img/a.png"))
        self.assertFalse(get.call_args.kwargs.get("allow_redirects", True))

    def test_non_https_url_returns_none_without_a_request(self) -> None:
        with mock.patch.object(posters.requests, "get") as get:
            self.assertIsNone(posters.fetch_artwork("http://img/a.png"))
        get.assert_not_called()

    def test_file_scheme_url_returns_none_without_a_request(self) -> None:
        with mock.patch.object(posters.requests, "get") as get:
            self.assertIsNone(posters.fetch_artwork("file:///etc/passwd"))
        get.assert_not_called()
