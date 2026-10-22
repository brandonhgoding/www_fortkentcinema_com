import io
from unittest import mock

import httpx
from boxoffice.posters import MAX_BYTES, fetch_poster
from django.test import SimpleTestCase
from PIL import Image

URL = "https://image.tmdb.org/t/p/w500/dune.jpg"


def png(size=(4, 4)) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", size, "red").save(buf, format="PNG")
    return buf.getvalue()


def _response(content=None, content_type="image/png", status=200, url=URL):
    request = httpx.Request("GET", url)
    return httpx.Response(status, content=png() if content is None else content,
                          headers={"content-type": content_type}, request=request)


def _stream(response=None, side_effect=None):
    """httpx.stream() is a context manager yielding the response."""
    cm = mock.MagicMock()
    cm.__enter__.return_value = response
    return mock.patch("boxoffice.posters.httpx.stream", return_value=cm,
                      side_effect=side_effect)


class FetchPosterTests(SimpleTestCase):
    """The URL is Film.poster_url: TMDB's normally, but a URLField anyone with
    the Film admin can edit, fetched from the server's network position by a
    nightly job. The guard is the social-card fetcher's: https only, no
    redirects, a size cap, and the bytes must decode as an image."""

    def test_returns_image_bytes(self) -> None:
        data = png()
        with _stream(_response(data)) as stream:
            self.assertEqual(fetch_poster(URL), data)
        self.assertEqual(stream.call_args.args, ("GET", URL))
        self.assertFalse(stream.call_args.kwargs["follow_redirects"])

    def test_blank_url_is_none_without_a_request(self) -> None:
        with _stream() as stream:
            self.assertIsNone(fetch_poster(""))
        stream.assert_not_called()

    def test_plain_http_is_refused_without_a_request(self) -> None:
        with _stream() as stream, self.assertLogs("boxoffice.posters", "WARNING"):
            self.assertIsNone(fetch_poster("http://10.0.0.5:8080/internal.png"))
        stream.assert_not_called()

    def test_redirect_is_not_followed(self) -> None:
        bounce = _response(b"", "text/html", status=302)
        bounce.headers["location"] = "http://169.254.169.254/latest/meta-data/"
        with _stream(bounce), self.assertLogs("boxoffice.posters", "WARNING"):
            self.assertIsNone(fetch_poster(URL))

    def test_http_error_is_none_and_logged(self) -> None:
        with _stream(_response(status=404)), \
                self.assertLogs("boxoffice.posters", "WARNING"):
            self.assertIsNone(fetch_poster(URL))

    def test_transport_error_is_none_and_logged(self) -> None:
        with _stream(side_effect=httpx.ConnectError("refused")), \
                self.assertLogs("boxoffice.posters", "WARNING"):
            self.assertIsNone(fetch_poster(URL))

    def test_non_image_body_is_none(self) -> None:
        with _stream(_response(b"<html>", "text/html")), \
                self.assertLogs("boxoffice.posters", "WARNING"):
            self.assertIsNone(fetch_poster(URL))

    def test_image_content_type_with_a_body_that_is_not_one_is_none(self) -> None:
        with _stream(_response(b"not really a png", "image/png")), \
                self.assertLogs("boxoffice.posters", "WARNING"):
            self.assertIsNone(fetch_poster(URL))

    def test_oversized_body_is_none(self) -> None:
        with _stream(_response(b"x" * (MAX_BYTES + 1), "image/png")), \
                self.assertLogs("boxoffice.posters", "WARNING"):
            self.assertIsNone(fetch_poster(URL))
