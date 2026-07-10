from __future__ import annotations

import datetime

import requests
from django.db import transaction

from .models import Engagement, EngagementFilm, Film, Screen, Showtime

REQUEST_TIMEOUT = 15


def fetch_all(base_url: str, path: str, *, session=None) -> list[dict]:
    """GET base_url+path and follow DRF `next` pagination, returning all records.

    `session` is any object with a `.get(url, timeout=...)` method (a
    requests.Session in production, a mock in tests); defaults to `requests`.
    """
    client = session or requests
    url = f"{base_url.rstrip('/')}/{path.lstrip('/')}"
    records: list[dict] = []
    while url:
        resp = client.get(url, timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
        data = resp.json()
        if isinstance(data, dict) and "results" in data:
            records.extend(data["results"])
            url = data.get("next")
        else:
            records.extend(data)
            url = None
    return records
