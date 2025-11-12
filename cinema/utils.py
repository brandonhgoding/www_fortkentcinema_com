from datetime import datetime, timedelta

from django.db.models import Min
from django.utils import timezone

from cinema.models import Film, ScreeningTime


def get_currently_playing_films(limit: int, now: datetime) -> list[Film]:
    return list(
        Film.objects.filter(
            bookings__booking_start_date__lte=now,
            bookings__booking_end_date__gte=now,
        )
        .annotate(first_start=Min("bookings__booking_start_date"))
        .order_by("first_start")
        .distinct()[:limit]
    )


def get_upcoming_films(now: datetime, current_list: list[Film], needed: int) -> list[Film]:
    exclude_ids = [film.id for film in current_list]
    return list(
        Film.objects.filter(bookings__booking_start_date__gt=now)
        .exclude(id__in=exclude_ids)
        .annotate(next_start=Min("bookings__booking_start_date"))
        .order_by("next_start")
        .distinct()[:needed]
    )


def get_current_or_next_films(limit: int, now: datetime) -> list[Film]:
    current_list = get_currently_playing_films(limit, now)

    if len(current_list) < limit:
        needed = limit - len(current_list)
        upcoming_list = get_upcoming_films(now, current_list, needed)
        current_list.extend(upcoming_list)

    return current_list


def get_show_start(show_time: ScreeningTime):
    show_date = show_time.date
    show_time = show_time.time
    return datetime.combine(show_date, show_time)


def is_showtime_expired(show_time: ScreeningTime):
    """
    True if 20 minutes past showtime is in the past.
    """
    start = get_show_start(show_time)
    if not start:
        # If we can't resolve a start, be conservative and treat as not expired.
        return False

    cutoff = start + timedelta(minutes=20)
    return cutoff < timezone.now()
