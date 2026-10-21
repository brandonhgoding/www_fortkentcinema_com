"""Seed local demo data for the online-ticket sandbox QA (docs/qa Part A5).

Run with:  python manage.py shell < seed_sandbox_demo.py  STAGE=local|no_item
Idempotent: everything is looked up before it is created.

STAGE=local   screens, films (TMDB), engagements that SHOULD get Square items,
              daily matinee + evening showtimes, report recipients.
STAGE=no_item one more confirmed engagement that must NOT have a Square item;
              run it only AFTER `sync_square_catalog` so the sync never saw it.
"""
import datetime
import os

from boxoffice.models import EmailRecipient, EmailReport
from cinema.models import Engagement, EngagementFilm, EngagementStatus, Screen, Showtime
from cinema.services import import_film_from_tmdb
from cinema.showtimes_overlap import check_overlap_against_existing
from cinema.tmdb.services import TMDBService
from django.utils import timezone
from web.services.cinema_data import CINEMA_TZ

STAGE = os.environ.get("STAGE", "local")
TODAY = timezone.localdate()


def film_by_title(title, year):
    svc = TMDBService()
    hits = [h for h in svc.search_films(title)
            if h["title"].lower() == title.lower()
            and (h.get("release_date") or "").startswith(str(year))]
    if not hits:
        raise SystemExit(f"TMDB: no exact hit for {title!r} ({year})")
    film = import_film_from_tmdb(hits[0]["tmdb_id"])
    print(f"film  {film.pk:>3}  {film.title}  poster={'yes' if film.poster_url else 'no'}")
    return film


def engagement(film, screen, start, end, kind=Engagement.Kind.REGULAR):
    eng = Engagement.objects.filter(engagement_films__film=film,
                                    start_date=start, end_date=end).first()
    if eng is None:
        eng = Engagement.objects.create(
            screen=screen, start_date=start, end_date=end, kind=kind,
            status=EngagementStatus.CONFIRMED, show_in_main_listings=True)
        EngagementFilm.objects.create(engagement=eng, film=film, position=0)
        print(f"eng   {eng.pk:>3}  {eng.title}  {start} -> {end}  NEW")
    else:
        print(f"eng   {eng.pk:>3}  {eng.title}  {start} -> {end}  exists")
    return eng


def showtimes(eng, times):
    """One showtime per (day, time) of the run; skips any that would overlap."""
    made = skipped = 0
    day = eng.start_date
    runtime = eng.total_runtime_minutes
    while day <= eng.end_date:
        for hh, mm in times:
            starts_at = datetime.datetime.combine(day, datetime.time(hh, mm), CINEMA_TZ)
            if Showtime.objects.filter(engagement=eng, starts_at=starts_at).exists():
                continue
            if check_overlap_against_existing(eng.screen, starts_at, runtime, eng.title):
                skipped += 1
                continue
            Showtime.objects.create(engagement=eng, screen=eng.screen, starts_at=starts_at)
            made += 1
        day += datetime.timedelta(days=1)
    print(f"      showtimes created={made} skipped_overlap={skipped} "
          f"total={eng.showtimes.count()}")


screen1 = Screen.objects.order_by("pk").first()
screen2, created = Screen.objects.get_or_create(
    name="Screen 2", defaults={"capacity": screen1.capacity})
print(f"screens: {screen1.name} cap={screen1.capacity}; "
      f"{screen2.name} cap={screen2.capacity} {'NEW' if created else 'exists'}")

if STAGE == "local":
    # Existing run on screen 1 (4:00 PM is exactly the matinee cut-off, 7:30 PM evening).
    # A clear matinee (1:30 PM) and a clear evening (7:00 PM) on screen 2:
    hocus = film_by_title("Hocus Pocus", 1993)
    eng_b = engagement(hocus, screen2, TODAY + datetime.timedelta(days=2),
                       TODAY + datetime.timedelta(days=12), Engagement.Kind.CLASSIC)
    showtimes(eng_b, [(13, 30), (19, 0)])

    for kind, address in ((EmailReport.Kind.OWNER_SUMMARY, "owner@example.com"),
                          (EmailReport.Kind.TICKET_REPORT, "booker@example.com")):
        report = EmailReport.objects.get(kind=kind)
        _, made = EmailRecipient.objects.get_or_create(report=report, address=address)
        print(f"recipient {kind}: {address} {'NEW' if made else 'exists'}")

elif STAGE == "no_item":
    # Confirmed and listed, but created after the sync: no Square item (QA B10/C7).
    bride = film_by_title("The Princess Bride", 1987)
    eng_c = engagement(bride, screen2, TODAY + datetime.timedelta(days=13),
                       TODAY + datetime.timedelta(days=19), Engagement.Kind.CLASSIC)
    showtimes(eng_c, [(13, 30), (19, 0)])
    print("NOTE: a dashboard save or `sync_square_catalog` will push this run; "
          "leave it alone to keep the no-item case.")
else:
    raise SystemExit(f"unknown STAGE {STAGE!r}")
