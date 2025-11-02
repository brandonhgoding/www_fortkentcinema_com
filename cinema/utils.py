from datetime import datetime

from django.db.models import Min

from cinema.models import Film


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
