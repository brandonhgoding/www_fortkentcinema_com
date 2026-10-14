"""Repair placeholder Screen.capacity values.

Both screens shipped with capacity=1, which is not a seat count — it makes
any house-size reasoning nonsense. Capacity is the screen's seat count.

100 is the working figure until the seats are actually counted.

Lives here rather than inside the migration so it can be tested: a migration
runs while building the test database, against an empty table, so there is
nothing left for a test to observe by the time it runs.
"""

PLACEHOLDER_CAPACITY = 100


def backfill_placeholder_capacity(manager) -> int:
    """Set every placeholder capacity to PLACEHOLDER_CAPACITY.

    `manager` is Screen.objects, or the historical model's manager when
    called from a migration. Guarded to capacity <= 1 so a real seat count
    that production may already carry is never clobbered.

    Returns the number of rows changed.
    """
    return manager.filter(capacity__lte=1).update(capacity=PLACEHOLDER_CAPACITY)
