import datetime
import json
from zoneinfo import ZoneInfo

from cinema.models import Engagement, EngagementFilm, Film, Screen, Showtime
from cinema.services import import_film_from_tmdb
from cinema.showtimes_overlap import (
    _ProposedShowtime,
    check_intra_batch_overlaps,
    check_overlap_against_existing,
    format_overlap_error,
)
from cinema.social_cards import BADGE_BY_PARAM, PLATFORMS, render_card
from cinema.tmdb import TMDBAPIError
from cinema.tmdb.services import TMDBService
from django.db import transaction
from django.db.models import ProtectedError
from django.http import HttpRequest, HttpResponse, HttpResponseBadRequest
from django.shortcuts import get_object_or_404, render
from django.urls import reverse
from django.utils import timezone
from django.views.generic import TemplateView, View

from .forms import EngagementForm, ScreenForm
from .mixins import StaffRequiredMixin
from .smart_alerts import build_smart_alerts


class HomeView(StaffRequiredMixin, TemplateView):
    template_name = "dashboard/home.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        today = timezone.localdate()
        tomorrow = today + datetime.timedelta(days=1)
        day_after = today + datetime.timedelta(days=2)

        def day_range(d1, d2):
            start = timezone.make_aware(datetime.datetime.combine(d1, datetime.time.min))
            end = timezone.make_aware(datetime.datetime.combine(d2, datetime.time.min))
            return start, end

        today_start, today_end = day_range(today, tomorrow)
        tomo_start, tomo_end = day_range(tomorrow, day_after)

        today_showtimes = (
            Showtime.objects.filter(starts_at__gte=today_start, starts_at__lt=today_end)
            .select_related("screen")
            .prefetch_related("engagement__engagement_films__film")
            .order_by("starts_at")
        )
        tomorrow_count = Showtime.objects.filter(
            starts_at__gte=tomo_start, starts_at__lt=tomo_end).count()

        engagements = list(
            Engagement.objects.prefetch_related("engagement_films__film"))

        user = self.request.user
        ctx.update({
            "active_engagements_count": sum(1 for e in engagements if e.status == "CONFIRMED"),
            "screens_count": Screen.objects.count(),
            "today_showtimes": today_showtimes,
            "today_showtimes_count": today_showtimes.count(),
            "alerts": build_smart_alerts(engagements, tomorrow_count, today),
            "display_name": user.get_short_name() or user.get_username(),
        })
        return ctx


SCREEN_TYPE_LABELS = {"standard": "Standard", "imax": "IMAX", "dolby_cinema": "Dolby Cinema"}
ASPECT_RATIO_LABELS = {
    "flat": "Flat (1.85:1)", "scope": "Scope (2.39:1)",
    "imax_190": "IMAX 1.90:1", "imax_143": "IMAX 1.43:1",
}
SOUND_SYSTEM_LABELS = {"standard": "Standard", "dolby_digital": "Dolby Digital", "dolby_atmos": "Dolby Atmos"}


def screen_labels() -> dict:
    return {
        "SCREEN_TYPE_LABELS": SCREEN_TYPE_LABELS,
        "ASPECT_RATIO_LABELS": ASPECT_RATIO_LABELS,
        "SOUND_SYSTEM_LABELS": SOUND_SYSTEM_LABELS,
    }


class ScreenListView(StaffRequiredMixin, TemplateView):
    template_name = "dashboard/screens.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["screens"] = Screen.objects.all()
        ctx.update(screen_labels())
        return ctx


def _render_screen_form(request, form, action_url, submit_label):
    return render(request, "dashboard/_screen_form.html",
                  {"form": form, "form_action": action_url, "submit_label": submit_label})


def _screen_list_response(request, toast_message):
    """Success response: OOB-swap the list, close the drawer, and toast."""
    html = render(request, "dashboard/_screen_list.html",
                  {"screens": Screen.objects.all(), **screen_labels()}).content.decode()
    # mark the list for out-of-band swap so it replaces #screen-list on the page
    html = html.replace('<div id="screen-list">', '<div id="screen-list" hx-swap-oob="true">', 1)
    resp = HttpResponse(html)
    resp["HX-Trigger"] = json.dumps({
        "close-drawer": True,
        "dashboard-toast": {"kind": "success", "message": toast_message},
    })
    return resp


def _screen_list_response_error(request, message):
    """Re-render the (unchanged) list OOB and fire an error toast; keep the row."""
    html = render(request, "dashboard/_screen_list.html",
                  {"screens": Screen.objects.all(), **screen_labels()}).content.decode()
    html = html.replace('<div id="screen-list">', '<div id="screen-list" hx-swap-oob="true">', 1)
    resp = HttpResponse(html)
    resp["HX-Trigger"] = json.dumps({"dashboard-toast": {"kind": "error", "message": message}})
    return resp


class ScreenCreateView(StaffRequiredMixin, View):
    def get(self, request):
        return _render_screen_form(request, ScreenForm(),
                                   reverse("dashboard:screen_create"), "Create Screen")

    def post(self, request):
        form = ScreenForm(request.POST)
        if form.is_valid():
            form.save()
            return _screen_list_response(request, "Screen created")
        return _render_screen_form(request, form,
                                   reverse("dashboard:screen_create"), "Create Screen")


class ScreenEditView(StaffRequiredMixin, View):
    def get(self, request, pk):
        screen = get_object_or_404(Screen, pk=pk)
        return _render_screen_form(request, ScreenForm(instance=screen),
                                   reverse("dashboard:screen_edit", args=[pk]), "Save Changes")

    def post(self, request, pk):
        screen = get_object_or_404(Screen, pk=pk)
        form = ScreenForm(request.POST, instance=screen)
        if form.is_valid():
            form.save()
            return _screen_list_response(request, "Screen updated")
        return _render_screen_form(request, form,
                                   reverse("dashboard:screen_edit", args=[pk]), "Save Changes")


class ScreenDeleteView(StaffRequiredMixin, View):
    def post(self, request, pk):
        screen = get_object_or_404(Screen, pk=pk)
        name = screen.name
        try:
            screen.delete()
        except ProtectedError:
            eng = screen.engagements.count()
            shows = screen.showtimes.count()
            msg = (
                f"Can't delete \"{name}\" — it's used by "
                f"{eng} engagement(s) and {shows} showtime(s)."
            )
            return _screen_list_response_error(request, msg)
        return _screen_list_response(request, "Screen deleted")


class FilmSearchView(StaffRequiredMixin, View):
    def get(self, request):
        q = request.GET.get("q", "").strip()
        films = Film.objects.filter(title__icontains=q)[:8] if q else Film.objects.none()
        return render(request, "dashboard/_film_options.html", {"q": q, "films": films})


class FilmSearchTMDBView(StaffRequiredMixin, View):
    def get(self, request):
        q = request.GET.get("q", "").strip()
        ctx = {"q": q, "results": [], "error": False}
        if q:
            try:
                ctx["results"] = TMDBService().search_films(q)
            except (TMDBAPIError, ValueError):
                ctx["error"] = True
        return render(request, "dashboard/_tmdb_options.html", ctx)


class FilmFromTMDBView(StaffRequiredMixin, View):
    def post(self, request):
        tmdb_id = request.POST.get("tmdb_id")
        resp = HttpResponse(status=204)
        try:
            film = import_film_from_tmdb(int(tmdb_id))
        except (TMDBAPIError, ValueError, TypeError):
            resp["HX-Trigger"] = json.dumps(
                {"dashboard-toast": {"kind": "error", "message": "Failed to add film from TMDB."}}
            )
            return resp
        resp["HX-Trigger"] = json.dumps({
            "film-selected": {"id": film.id, "title": film.title, "poster": film.poster_url},
            "dashboard-toast": {"kind": "success", "message": f"Added {film.title}"},
        })
        return resp


KIND_LABELS = {"REGULAR": "Regular", "SPECIAL_EVENT": "Event", "CLASSIC": "Classic",
               "DOUBLE_FEATURE": "Double Feature"}
ENGAGEMENT_TABS = ["CURRENT", "UPCOMING", "DRAFT", "ENDED", "CANCELLED"]


def engagement_queryset(tab: str):
    today = timezone.localdate()
    qs = Engagement.objects.select_related("screen").prefetch_related("engagement_films__film")
    if tab == "UPCOMING":
        return qs.filter(status="CONFIRMED", start_date__gt=today)
    if tab == "ENDED":
        return qs.filter(end_date__lt=today)
    if tab == "DRAFT":
        return qs.filter(status="DRAFT")
    if tab == "CANCELLED":
        return qs.filter(status="CANCELLED")
    # CURRENT (default)
    return qs.filter(status="CONFIRMED", start_date__lte=today, end_date__gte=today)


def engagement_list_context(request):
    tab = request.GET.get("tab") or "CURRENT"
    if tab not in ENGAGEMENT_TABS:
        tab = "CURRENT"
    return {
        "engagements": engagement_queryset(tab),
        "tab": tab,
        "tabs": ENGAGEMENT_TABS,
        "KIND_LABELS": KIND_LABELS,
        "today": timezone.localdate(),
        "status_options": [("DRAFT", "Draft"), ("CONFIRMED", "Confirmed"), ("CANCELLED", "Cancelled")],
        "status_descriptions": {"DRAFT": "Not yet confirmed", "CONFIRMED": "Active engagement",
                                "CANCELLED": "Engagement cancelled", "ENDED": "Engagement has ended"},
    }


class EngagementListView(StaffRequiredMixin, TemplateView):
    def get_template_names(self):
        # A tab click is an HTMX GET that swaps only the #engagement-list region,
        # so return the partial (not the full base-extending page) for HX requests.
        if self.request.headers.get("HX-Request"):
            return ["dashboard/_engagement_list.html"]
        return ["dashboard/engagements.html"]

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx.update(engagement_list_context(self.request))
        return ctx


class EngagementDetailView(StaffRequiredMixin, TemplateView):
    template_name = "dashboard/engagement_detail.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        engagement = get_object_or_404(
            Engagement.objects.select_related("screen").prefetch_related("engagement_films__film"),
            pk=kwargs["pk"],
        )
        ctx["engagement"] = engagement
        ctx["films"] = [ef.film for ef in engagement.engagement_films.all()]
        ctx["showtimes"] = engagement.showtimes.select_related("screen")
        ctx["KIND_LABELS"] = KIND_LABELS
        ctx["STATUS_BADGE_CLASSES"] = {
            "DRAFT": "statusDraft", "CONFIRMED": "statusConfirmed",
            "CANCELLED": "statusCancelled", "ENDED": "statusEnded",
        }
        return ctx


def _engagement_list_response(request, tab, toast=None, status_code=200):
    ctx = {**engagement_list_context(request), "tab": tab, "engagements": engagement_queryset(tab)}
    html = render(request, "dashboard/_engagement_list.html", ctx).content.decode()
    html = html.replace('<div id="engagement-list"', '<div id="engagement-list" hx-swap-oob="true"', 1)
    resp = HttpResponse(html, status=status_code)
    trigger = {}
    if toast:
        trigger["dashboard-toast"] = toast
    if trigger:
        resp["HX-Trigger"] = json.dumps(trigger)
    return resp


def save_engagement_films(engagement, film_ids):
    engagement.engagement_films.all().delete()
    for pos, fid in enumerate(film_ids, start=1):
        EngagementFilm.objects.create(engagement=engagement, film_id=fid, position=pos)


def _film_ids(request):
    ids = []
    for raw in request.POST.getlist("films"):
        try:
            ids.append(int(raw))
        except (TypeError, ValueError):
            continue
    # preserve order, drop duplicates
    seen = set()
    return [i for i in ids if not (i in seen or seen.add(i))]


def _validate_film_set(kind, film_ids):
    if kind == "DOUBLE_FEATURE":
        return None if len(film_ids) >= 2 else "Add at least two films for a double feature."
    return None if len(film_ids) == 1 else "Select a film for this engagement."


def _render_engagement_form(request, form, action_url, submit_label, film_ids, film_error=None):
    from .forms import KIND_OPTIONS
    initial = [{"id": f.id, "title": f.title, "poster": f.poster_url}
               for f in Film.objects.filter(id__in=film_ids)]
    # keep submitted order
    order = {fid: i for i, fid in enumerate(film_ids)}
    initial.sort(key=lambda d: order.get(d["id"], 0))
    return render(request, "dashboard/_engagement_form.html", {
        "form": form, "form_action": action_url, "submit_label": submit_label,
        "kind_options": KIND_OPTIONS, "film_error": film_error,
        "initial_films": initial,
    })


class EngagementCreateView(StaffRequiredMixin, View):
    def get(self, request):
        return _render_engagement_form(request, EngagementForm(),
                                       reverse("dashboard:engagement_create"), "Create Engagement", [])

    def post(self, request):
        form = EngagementForm(request.POST)
        film_ids = _film_ids(request)
        film_error = _validate_film_set(request.POST.get("kind", "REGULAR"), film_ids)
        # validate film films exist
        if film_ids and Film.objects.filter(id__in=film_ids).count() != len(film_ids):
            film_error = "One or more selected films no longer exist."
        if form.is_valid() and not film_error:
            with transaction.atomic():
                engagement = form.save()
                save_engagement_films(engagement, film_ids)
            tab = request.GET.get("tab") or "CURRENT"
            resp = _engagement_list_response(request, tab, toast={"kind": "success", "message": "Engagement created"})
            existing = resp["HX-Trigger"]
            trigger = json.loads(existing) if existing else {}
            trigger["close-drawer"] = True
            resp["HX-Trigger"] = json.dumps(trigger)
            return resp
        return _render_engagement_form(request, form, reverse("dashboard:engagement_create"),
                                       "Create Engagement", film_ids, film_error)


class EngagementEditView(StaffRequiredMixin, View):
    def get(self, request, pk):
        engagement = get_object_or_404(Engagement, pk=pk)
        film_ids = list(engagement.engagement_films.order_by("position").values_list("film_id", flat=True))
        return _render_engagement_form(request, EngagementForm(instance=engagement),
                                       reverse("dashboard:engagement_edit", args=[pk]), "Save Changes", film_ids)

    def post(self, request, pk):
        engagement = get_object_or_404(Engagement, pk=pk)
        form = EngagementForm(request.POST, instance=engagement)
        film_ids = _film_ids(request)
        film_error = _validate_film_set(request.POST.get("kind", "REGULAR"), film_ids)
        if film_ids and Film.objects.filter(id__in=film_ids).count() != len(film_ids):
            film_error = "One or more selected films no longer exist."
        if form.is_valid() and not film_error:
            with transaction.atomic():
                engagement = form.save()
                save_engagement_films(engagement, film_ids)
            tab = request.GET.get("tab") or "CURRENT"
            resp = _engagement_list_response(request, tab, toast={"kind": "success", "message": "Engagement updated"})
            trigger = json.loads(resp["HX-Trigger"]) if resp.get("HX-Trigger") else {}
            trigger["close-drawer"] = True
            resp["HX-Trigger"] = json.dumps(trigger)
            return resp
        return _render_engagement_form(request, form, reverse("dashboard:engagement_edit", args=[pk]),
                                       "Save Changes", film_ids, film_error)


class EngagementStatusView(StaffRequiredMixin, View):
    def post(self, request, pk):
        engagement = get_object_or_404(Engagement, pk=pk)
        new_status = request.POST.get("status")
        if new_status not in {"DRAFT", "CONFIRMED", "CANCELLED"}:
            return HttpResponse(status=400)
        engagement.status = new_status
        engagement.save(update_fields=["status"])
        tab = request.GET.get("tab") or "CURRENT"
        return _engagement_list_response(request, tab, toast={"kind": "success", "message": "Status updated"})


class EngagementDeleteView(StaffRequiredMixin, View):
    def post(self, request, pk):
        engagement = get_object_or_404(Engagement, pk=pk)
        engagement.delete()
        tab = request.GET.get("tab") or "CURRENT"
        return _engagement_list_response(request, tab, toast={"kind": "success", "message": "Engagement deleted"})


CINEMA_TZ = ZoneInfo("America/New_York")


def _showtime_list_response(request, engagement, toast, close_drawer=False):
    ctx = {"engagement": engagement, "showtimes": engagement.showtimes.select_related("screen")}
    html = render(request, "dashboard/_showtime_list.html", ctx).content.decode()
    html = html.replace('<div id="showtime-list">', '<div id="showtime-list" hx-swap-oob="true">', 1)
    resp = HttpResponse(html)
    trigger = {"dashboard-toast": toast}
    if close_drawer:
        trigger["close-drawer"] = True
    resp["HX-Trigger"] = json.dumps(trigger)
    return resp


def _parse_starts_at(date_str, time_str):
    d = datetime.date.fromisoformat(date_str)
    t = datetime.time.fromisoformat(time_str)
    return datetime.datetime.combine(d, t, tzinfo=CINEMA_TZ)


def _render_showtime_form(request, engagement, action_url, submit_label, mode,
                          date="", time="", captions="", is_cancelled=False, errors=None):
    return render(request, "dashboard/_showtime_form.html", {
        "engagement": engagement, "form_action": action_url, "submit_label": submit_label,
        "mode": mode, "date": date, "time": time, "captions": captions or "",
        "is_cancelled": is_cancelled, "errors": errors or [],
    })


class ShowtimeCreateView(StaffRequiredMixin, View):
    def get(self, request, eng_pk):
        engagement = get_object_or_404(Engagement, pk=eng_pk)
        return _render_showtime_form(
            request, engagement, reverse("dashboard:showtime_create", args=[eng_pk]),
            "Add Showtime", "create", date=engagement.start_date.isoformat())

    def post(self, request, eng_pk):
        engagement = get_object_or_404(Engagement, pk=eng_pk)
        date_str, time_str = request.POST.get("date", ""), request.POST.get("time", "")
        captions = request.POST.get("captions") or None
        action = reverse("dashboard:showtime_create", args=[eng_pk])
        if not date_str or not time_str:
            return _render_showtime_form(request, engagement, action, "Add Showtime", "create",
                                         date=date_str, time=time_str, captions=captions,
                                         errors=["Date and time are required."])
        starts_at = _parse_starts_at(date_str, time_str)
        conflicts = check_overlap_against_existing(
            engagement.screen, starts_at, engagement.total_runtime_minutes, engagement.display_title)
        if conflicts:
            return _render_showtime_form(request, engagement, action, "Add Showtime", "create",
                                         date=date_str, time=time_str, captions=captions,
                                         errors=[format_overlap_error(c) for c in conflicts])
        Showtime.objects.create(engagement=engagement, starts_at=starts_at, captions=captions)
        return _showtime_list_response(request, engagement,
                                       {"kind": "success", "message": "Showtime added"}, close_drawer=True)


class ShowtimeEditView(StaffRequiredMixin, View):
    def get(self, request, pk):
        st = get_object_or_404(Showtime.objects.select_related("engagement"), pk=pk)
        local = st.starts_at.astimezone(CINEMA_TZ)
        return _render_showtime_form(
            request, st.engagement, reverse("dashboard:showtime_edit", args=[pk]),
            "Save Changes", "edit", date=local.date().isoformat(),
            time=local.strftime("%H:%M"), captions=st.captions or "", is_cancelled=st.is_cancelled)

    def post(self, request, pk):
        st = get_object_or_404(Showtime.objects.select_related("engagement"), pk=pk)
        engagement = st.engagement
        date_str, time_str = request.POST.get("date", ""), request.POST.get("time", "")
        captions = request.POST.get("captions") or None
        is_cancelled = request.POST.get("is_cancelled") == "on"
        action = reverse("dashboard:showtime_edit", args=[pk])
        if not date_str or not time_str:
            return _render_showtime_form(request, engagement, action, "Save Changes", "edit",
                                         date=date_str, time=time_str, captions=captions,
                                         is_cancelled=is_cancelled, errors=["Date and time are required."])
        starts_at = _parse_starts_at(date_str, time_str)
        if not is_cancelled:  # cancelling skips the overlap check (matches source)
            conflicts = check_overlap_against_existing(
                engagement.screen, starts_at, engagement.total_runtime_minutes,
                engagement.display_title, exclude_showtime_id=st.pk)
            if conflicts:
                return _render_showtime_form(request, engagement, action, "Save Changes", "edit",
                                             date=date_str, time=time_str, captions=captions,
                                             is_cancelled=is_cancelled,
                                             errors=[format_overlap_error(c) for c in conflicts])
        st.starts_at = starts_at
        st.captions = captions
        st.is_cancelled = is_cancelled
        st.save()
        return _showtime_list_response(request, engagement,
                                       {"kind": "success", "message": "Showtime updated"}, close_drawer=True)


class ShowtimeDeleteView(StaffRequiredMixin, View):
    def post(self, request, pk):
        st = get_object_or_404(Showtime.objects.select_related("engagement"), pk=pk)
        engagement = st.engagement
        st.delete()
        return _showtime_list_response(request, engagement,
                                       {"kind": "success", "message": "Showtime deleted"})


def _render_bulk_form(request, engagement, start_date="", end_date="", captions="", errors=None):
    return render(request, "dashboard/_showtime_bulk_form.html", {
        "engagement": engagement,
        "form_action": reverse("dashboard:showtime_bulk", args=[engagement.pk]),
        "start_date": start_date, "end_date": end_date, "captions": captions or "",
        "errors": errors or [],
    })


class ShowtimeBulkView(StaffRequiredMixin, View):
    def get(self, request, eng_pk):
        engagement = get_object_or_404(Engagement, pk=eng_pk)
        return _render_bulk_form(request, engagement,
                                 start_date=engagement.start_date.isoformat(),
                                 end_date=engagement.end_date.isoformat())

    def post(self, request, eng_pk):
        engagement = get_object_or_404(Engagement, pk=eng_pk)
        start_str, end_str = request.POST.get("start_date", ""), request.POST.get("end_date", "")
        captions = request.POST.get("captions") or None
        times = [t for t in request.POST.getlist("times") if t.strip()]

        def again(errors):
            return _render_bulk_form(request, engagement, start_date=start_str,
                                     end_date=end_str, captions=captions, errors=errors)

        if not start_str or not end_str:
            return again(["Start and end date are required."])
        if not times:
            return again(["Add at least one time."])
        start_date = datetime.date.fromisoformat(start_str)
        end_date = datetime.date.fromisoformat(end_str)
        if end_date < start_date:
            return again(["End date cannot be before start date."])

        screen = engagement.screen
        runtime = engagement.total_runtime_minutes
        title = engagement.display_title
        proposed_showtimes = []
        current = start_date
        one_day = datetime.timedelta(days=1)
        while current <= end_date:
            for t in times:
                starts_at = datetime.datetime.combine(current, datetime.time.fromisoformat(t), tzinfo=CINEMA_TZ)
                proposed_showtimes.append(starts_at)
            current += one_day

        with transaction.atomic():
            Screen.objects.select_for_update().get(pk=screen.pk)
            errors = []
            for starts_at in proposed_showtimes:
                errors += [format_overlap_error(c) for c in check_overlap_against_existing(
                    screen, starts_at, runtime, title)]
            proposed = [_ProposedShowtime(i, screen, s, runtime, title)
                        for i, s in enumerate(proposed_showtimes)]
            errors += [format_overlap_error(c) for c in check_intra_batch_overlaps(proposed)]
            if errors:
                seen, unique = set(), []
                for e in errors:
                    if e not in seen:
                        seen.add(e); unique.append(e)
                return again(unique)
            Showtime.objects.bulk_create([
                Showtime(engagement=engagement, screen=screen, starts_at=s, captions=captions)
                for s in proposed_showtimes])

        return _showtime_list_response(
            request, engagement,
            {"kind": "success", "message": f"Created {len(proposed_showtimes)} showtimes"}, close_drawer=True)


class EngagementSocialCardView(StaffRequiredMixin, View):
    """Render an engagement's promo image as a PNG.

    Served inline for the dashboard preview; with ?download=1 as an
    attachment for the download buttons.
    """

    def get(
        self, request: HttpRequest, pk: int, platform: str
    ) -> HttpResponse:
        if platform not in PLATFORMS:
            return HttpResponseBadRequest("Unknown platform")
        engagement = get_object_or_404(
            Engagement.objects.prefetch_related("engagement_films__film"),
            pk=pk,
        )
        badge = BADGE_BY_PARAM.get(request.GET.get("badge", ""))
        png, filename = render_card(engagement, platform, badge)
        disposition = "attachment" if "download" in request.GET else "inline"

        response = HttpResponse(png, content_type="image/png")
        response["Content-Disposition"] = (
            f'{disposition}; filename="{filename}"'
        )
        return response
