import datetime
from unittest import mock

from cinema.leprinceos_import import fetch_all
from django.test import TestCase


class _Resp:
    def __init__(self, payload):
        self._p = payload

    def raise_for_status(self):
        pass

    def json(self):
        return self._p


class FetchAllTests(TestCase):
    def test_follows_pagination(self) -> None:
        page1 = {"results": [{"id": 1}, {"id": 2}], "next": "https://api/x/?page=2"}
        page2 = {"results": [{"id": 3}], "next": None}
        session = mock.Mock()
        session.get.side_effect = [_Resp(page1), _Resp(page2)]
        out = fetch_all("https://api/x", "/films/", session=session)
        self.assertEqual([r["id"] for r in out], [1, 2, 3])
        # first call hits base+path, second follows the absolute `next` url
        first_url = session.get.call_args_list[0].args[0]
        second_url = session.get.call_args_list[1].args[0]
        self.assertEqual(first_url, "https://api/x/films/")
        self.assertEqual(second_url, "https://api/x/?page=2")

    def test_unwraps_plain_list(self) -> None:
        session = mock.Mock()
        session.get.side_effect = [_Resp([{"id": 9}])]
        out = fetch_all("https://api/x", "/films/", session=session)
        self.assertEqual(out, [{"id": 9}])
