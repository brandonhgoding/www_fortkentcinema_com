from unittest import mock

import httpx
from boxoffice.posters import fetch_poster
from django.test import SimpleTestCase

URL = "https://image.tmdb.org/t/p/w500/dune.jpg"


def _response(content=b"jpg", content_type="image/jpeg", status=200):
    request = httpx.Request("GET", URL)
    return httpx.Response(status, content=content,
                          headers={"content-type": content_type}, request=request)


class FetchPosterTests(SimpleTestCase):
    def test_returns_image_bytes(self) -> None:
        with mock.patch("boxoffice.posters.httpx.get", return_value=_response()) as get:
            self.assertEqual(fetch_poster(URL), b"jpg")
        self.assertEqual(get.call_args.args, (URL,))
        self.assertTrue(get.call_args.kwargs["follow_redirects"])

    def test_blank_url_is_none_without_a_request(self) -> None:
        with mock.patch("boxoffice.posters.httpx.get") as get:
            self.assertIsNone(fetch_poster(""))
        get.assert_not_called()

    def test_http_error_is_none_and_logged(self) -> None:
        with mock.patch("boxoffice.posters.httpx.get",
                        return_value=_response(status=404)), \
                self.assertLogs("boxoffice.posters", "WARNING"):
            self.assertIsNone(fetch_poster(URL))

    def test_transport_error_is_none_and_logged(self) -> None:
        with mock.patch("boxoffice.posters.httpx.get",
                        side_effect=httpx.ConnectError("refused")), \
                self.assertLogs("boxoffice.posters", "WARNING"):
            self.assertIsNone(fetch_poster(URL))

    def test_non_image_body_is_none(self) -> None:
        with mock.patch("boxoffice.posters.httpx.get",
                        return_value=_response(b"<html>", "text/html")), \
                self.assertLogs("boxoffice.posters", "WARNING"):
            self.assertIsNone(fetch_poster(URL))
