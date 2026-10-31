"""Fixed-window counters on the default cache.

cache.incr looks like the tool for these, but on the database cache
(production) it is a plain get + set, which puts the key's expiry back to
the cache's default five minutes on every bump. So each counter stores
when its window ends alongside the count, and keeps that end on every
bump: a window starts at the first event and lasts exactly `window`
seconds, whatever happens in between. The counters are soft limits, not
atomic: two workers bumping at once may lose a count.
"""

import time

from django.core.cache import cache


def bump(key: str, window: int) -> int:
    """Count one more event against key; the count so far in this window."""
    now = time.time()
    stored = cache.get(key)
    if not stored or stored["until"] <= now:
        cache.set(key, {"n": 1, "until": now + window}, window)
        return 1
    stored["n"] += 1
    cache.set(key, stored, max(stored["until"] - now, 1))
    return stored["n"]


def count(key: str) -> int:
    """Events counted against key in its current window, or 0."""
    stored = cache.get(key)
    if not stored or stored["until"] <= time.time():
        return 0
    return stored["n"]
