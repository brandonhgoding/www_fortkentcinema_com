from __future__ import annotations

import datetime
from collections import defaultdict
from dataclasses import dataclass

from cinema.models import Engagement, Screen, Showtime

DEFAULT_RUNTIME_MINUTES = Engagement.UNKNOWN_RUNTIME_MINUTES
DEFAULT_BUFFER_MINUTES = 30
# No showing, marathons included, runs this long, so nothing that started
# earlier can still be on the screen. Bounds the query to recent rows.
LONGEST_SHOWING = datetime.timedelta(hours=24)


@dataclass
class OverlapConflict:
    existing_showtime_id: int | None
    existing_film_title: str
    existing_starts_at: datetime.datetime
    new_starts_at: datetime.datetime
    new_film_title: str
    screen_name: str


def get_effective_end(
    starts_at: datetime.datetime,
    runtime_minutes: int | None,
    buffer: int = DEFAULT_BUFFER_MINUTES,
) -> datetime.datetime:
    runtime = runtime_minutes or DEFAULT_RUNTIME_MINUTES
    return starts_at + datetime.timedelta(minutes=runtime + buffer)


def check_overlap_against_existing(
    screen: Screen,
    starts_at: datetime.datetime,
    runtime_minutes: int | None,
    film_title: str,
    exclude_showtime_id: int | None = None,
) -> list[OverlapConflict]:
    new_end = get_effective_end(starts_at, runtime_minutes)

    # Interval overlap: existing_start < new_end AND existing_effective_end > new_start.
    # We filter starts_at < new_end in the DB (any showtime starting at or after
    # new_end cannot overlap), and skip anything that started more than
    # LONGEST_SHOWING ago. The second condition requires each film's runtime,
    # so we check effective_end > new_start in Python after fetching.
    qs = Showtime.objects.filter(
        screen=screen,
        is_cancelled=False,
        starts_at__lt=new_end,
        starts_at__gt=starts_at - LONGEST_SHOWING,
    ).select_related("screen").prefetch_related("engagement__engagement_films__film")

    if exclude_showtime_id is not None:
        qs = qs.exclude(pk=exclude_showtime_id)

    conflicts: list[OverlapConflict] = []
    for existing in qs:
        existing_runtime = existing.engagement.total_runtime_minutes
        existing_end = get_effective_end(existing.starts_at, existing_runtime)
        if existing_end > starts_at:
            conflicts.append(
                OverlapConflict(
                    existing_showtime_id=existing.pk,
                    existing_film_title=existing.engagement.display_title,
                    existing_starts_at=existing.starts_at,
                    new_starts_at=starts_at,
                    new_film_title=film_title,
                    screen_name=existing.screen.name,
                )
            )

    return conflicts


@dataclass
class _ProposedShowtime:
    index: int
    screen: Screen
    starts_at: datetime.datetime
    runtime_minutes: int | None
    film_title: str


def check_intra_batch_overlaps(
    proposed: list[_ProposedShowtime],
) -> list[OverlapConflict]:
    by_screen: dict[int, list[_ProposedShowtime]] = defaultdict(list)
    for p in proposed:
        by_screen[p.screen.pk].append(p)

    conflicts: list[OverlapConflict] = []
    for group in by_screen.values():
        sorted_group = sorted(group, key=lambda p: p.starts_at)
        for i, a in enumerate(sorted_group):
            a_end = get_effective_end(a.starts_at, a.runtime_minutes)
            for b in sorted_group[i + 1 :]:
                if b.starts_at >= a_end:
                    break
                conflicts.append(
                    OverlapConflict(
                        existing_showtime_id=None,
                        existing_film_title=a.film_title,
                        existing_starts_at=a.starts_at,
                        new_starts_at=b.starts_at,
                        new_film_title=b.film_title,
                        screen_name=a.screen.name,
                    )
                )

    return conflicts


def format_overlap_error(conflict: OverlapConflict) -> str:
    time_fmt = "%b %d %I:%M %p"
    if conflict.existing_showtime_id is not None:
        return (
            f'"{conflict.new_film_title}" at '
            f"{conflict.new_starts_at.strftime(time_fmt)} overlaps with "
            f'"{conflict.existing_film_title}" at '
            f"{conflict.existing_starts_at.strftime(time_fmt)} "
            f"on {conflict.screen_name}."
        )
    return (
        f'"{conflict.new_film_title}" at '
        f"{conflict.new_starts_at.strftime(time_fmt)} overlaps with "
        f'"{conflict.existing_film_title}" at '
        f"{conflict.existing_starts_at.strftime(time_fmt)} "
        f"on {conflict.screen_name} (within this batch)."
    )
