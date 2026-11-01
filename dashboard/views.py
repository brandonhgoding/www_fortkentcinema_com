import datetime
import json

from boxoffice.gateway import GatewayError, square_enabled
from boxoffice.models import SquareItem
from boxoffice.reports import pull_status, sales_panel
from boxoffice.sync import delete, live_item, schedule, sync
from cinema.dates import CINEMA_TZ
from cinema.models import (
    AdInquiry,
    Engagement,
    EngagementFilm,
    EngagementStatus,
    Film,
    InquiryStatus,
    RentalInquiry,
    Screen,
    Showtime,
)
from cinema.services import import_film_from_tmdb
from cinema.showtimes_overlap import (
    _ProposedShowtime,
    check_intra_batch_overlaps,
    check_overlap_against_existing,
    format_overlap_error,
)
from cinema.tmdb import TMDBAPIError
from cinema.tmdb.services import TMDBService
from django.db import transaction
from django.db.models import Q
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.generic import TemplateView, View
from phone.models import Voicemail, VoicemailStatus

from .forms import EngagementForm
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

        user = self.request.user

        today_showtimes = []
        # Any non-zero value suppresses the no-showtimes alert, which is
        # filtered out for this user anyway.
        tomorrow_count = 1
        if user.has_perm("cinema.view_showtime"):
            today_showtimes = list(
                Showtime.objects.filter(
                    starts_at__gte=today_start, starts_at__lt=today_end)
                .select_related("screen")
                .prefetch_related("engagement__engagement_films__film")
                .order_by("starts_at")
            )
            tomorrow_count = Showtime.objects.filter(
                starts_at__gte=tomo_start, starts_at__lt=tomo_end,
                is_cancelled=False).count()

        # Only what the alerts can mention: drafts, and runs not over yet.
        engagements = list(
            Engagement.objects.filter(Q(status=EngagementStatus.DRAFT) | Q(end_date__gte=today))
            .prefetch_related("engagement_films__film"))

        can_pulls = user.has_perm("boxoffice.view_salespull")
        ctx.update({
            # Same rule as the engagements page's Current tab.
            "active_engagements_count": sum(1 for e in engagements if e.is_active),
            "today_showtimes": today_showtimes,
            "today_showtimes_count": sum(1 for st in today_showtimes if not st.is_cancelled),
            "alerts": [
                alert for alert in build_smart_alerts(
                    engagements,
                    tomorrow_count,
                    today,
                    new_rental_inquiries=(
                        RentalInquiry.objects.filter(status=InquiryStatus.NEW).count()
                        if user.has_perm("cinema.view_rentalinquiry") else 0),
                    new_ad_inquiries=(
                        AdInquiry.objects.filter(status=InquiryStatus.NEW).count()
                        if user.has_perm("cinema.view_adinquiry") else 0),
                    new_voicemails=(
                        Voicemail.objects.filter(status=VoicemailStatus.NEW).count()
                        if user.has_perm("phone.view_voicemail") else 0),
                    square_pull_status=(
                        pull_status(today - datetime.timedelta(days=1))
                        if can_pulls and square_enabled() else None),
                    square_sync_failures=(
                        SquareItem.objects.filter(
                            deleted_at__isnull=True).exclude(last_error="").count()
                        if user.has_perm("cinema.view_engagement") else 0),
                )
                if user.has_perm(alert["perm"])
            ],
            "sales_panel": sales_panel(today) if can_pulls else None,
            "display_name": user.get_short_name() or user.get_username(),
        })
        return ctx


class FilmSearchView(StaffRequiredMixin, View):
    permission_required = "cinema.view_film"

    def get(self, request):
        q = request.GET.get("q", "").strip()
        films = Film.objects.filter(title__icontains=q)[:8] if q else Film.objects.none()
        return render(request, "dashboard/_film_options.html", {"q": q, "films": films})


class FilmSearchTMDBView(StaffRequiredMixin, View):
    permission_required = "cinema.add_film"

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
    permission_required = "cinema.add_film"

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


KIND_LABELS = {"REGULAR": "Regular", "CLASSIC": "Classic",
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
                                "CANCELLED": "Cancels its upcoming showtimes", "ENDED": "Engagement has ended"},
    }


class EngagementListView(StaffRequiredMixin, TemplateView):
    permission_required = "cinema.view_engagement"

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
    permission_required = "cinema.view_engagement"
    template_name = "dashboard/engagement_detail.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        engagement = get_object_or_404(
            Engagement.objects.select_related("screen").prefetch_related("engagement_films__film"),
            pk=kwargs["pk"],
        )
        ctx["engagement"] = engagement
        ctx["films"] = [ef.film for ef in engagement.engagement_films.all()]
        ctx["showtimes"] = engagement_showtimes(engagement)
        ctx["KIND_LABELS"] = KIND_LABELS
        ctx["square_enabled"] = square_enabled()
        ctx["square_item"] = live_item(engagement)
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


def _save_toast(engagement, message):
    # The on-commit Square sync has run by now (the atomic block has exited).
    item = live_item(engagement) if square_enabled() else None
    if item is not None and item.last_error:
        return {"kind": "error", "message": "Saved. Square sync failed — see the run"}
    return {"kind": "success", "message": message}


class EngagementCreateView(StaffRequiredMixin, View):
    permission_required = "cinema.add_engagement"

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
                schedule(engagement)
            tab = request.GET.get("tab") or "CURRENT"
            resp = _engagement_list_response(request, tab, toast=_save_toast(engagement, "Engagement created"))
            existing = resp["HX-Trigger"]
            trigger = json.loads(existing) if existing else {}
            trigger["close-drawer"] = True
            resp["HX-Trigger"] = json.dumps(trigger)
            return resp
        return _render_engagement_form(request, form, reverse("dashboard:engagement_create"),
                                       "Create Engagement", film_ids, film_error)


class EngagementEditView(StaffRequiredMixin, View):
    permission_required = "cinema.change_engagement"

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
                schedule(engagement)
            tab = request.GET.get("tab") or "CURRENT"
            resp = _engagement_list_response(request, tab, toast=_save_toast(engagement, "Engagement updated"))
            trigger = json.loads(resp["HX-Trigger"]) if resp.get("HX-Trigger") else {}
            trigger["close-drawer"] = True
            resp["HX-Trigger"] = json.dumps(trigger)
            return resp
        return _render_engagement_form(request, form, reverse("dashboard:engagement_edit", args=[pk]),
                                       "Save Changes", film_ids, film_error)


class EngagementStatusView(StaffRequiredMixin, View):
    permission_required = "cinema.change_engagement"

    def post(self, request, pk):
        engagement = get_object_or_404(Engagement, pk=pk)
        new_status = request.POST.get("status")
        if new_status not in {"DRAFT", "CONFIRMED", "CANCELLED"}:
            return HttpResponse(status=400)
        engagement.status = new_status
        with transaction.atomic():
            engagement.save(update_fields=["status"])
            schedule(engagement)
        tab = request.GET.get("tab") or "CURRENT"
        return _engagement_list_response(request, tab, toast=_save_toast(engagement, "Status updated"))


class EngagementDeleteView(StaffRequiredMixin, View):
    permission_required = "cinema.delete_engagement"

    def post(self, request, pk):
        engagement = get_object_or_404(Engagement, pk=pk)
        tab = request.GET.get("tab") or "CURRENT"
        try:
            delete(engagement)
        except GatewayError as exc:
            return _engagement_list_response(request, tab, toast={
                "kind": "error",
                "message": f"Square refused to delete the ticket item ({exc}). The engagement was kept.",
            })
        engagement.delete()
        return _engagement_list_response(request, tab, toast={"kind": "success", "message": "Engagement deleted"})


class EngagementSquareRetryView(StaffRequiredMixin, View):
    permission_required = "cinema.change_engagement"

    def post(self, request, pk):
        engagement = get_object_or_404(Engagement, pk=pk)
        sync(engagement)
        return redirect("dashboard:engagement_detail", pk=pk)


def engagement_showtimes(engagement):
    """The engagement's showtimes, for the list."""
    return list(engagement.showtimes.select_related("screen", "engagement"))


def _showtime_list_response(request, engagement, toast, close_drawer=False):
    ctx = {"engagement": engagement, "showtimes": engagement_showtimes(engagement)}
    html = render(request, "dashboard/_showtime_list.html", ctx).content.decode()
    html = html.replace('<div id="showtime-list">', '<div id="showtime-list" hx-swap-oob="true">', 1)
    resp = HttpResponse(html)
    trigger = {"dashboard-toast": toast}
    if close_drawer:
        trigger["close-drawer"] = True
    resp["HX-Trigger"] = json.dumps(trigger)
    return resp


def _parse_starts_at(date_str, time_str):
    """The local start as an aware datetime, or None if either part is malformed."""
    try:
        d = datetime.date.fromisoformat(date_str)
        t = datetime.time.fromisoformat(time_str)
    except ValueError:
        return None
    return datetime.datetime.combine(d, t, tzinfo=CINEMA_TZ)


INVALID_DATE_TIME = "Enter a valid date and time."
CANCELLED_ENGAGEMENT = "This engagement is cancelled. Confirm it before adding showtimes."


def _render_showtime_form(request, engagement, action_url, submit_label, mode,
                          date="", time="", captions="", is_cancelled=False,
                          errors=None):
    return render(request, "dashboard/_showtime_form.html", {
        "engagement": engagement, "form_action": action_url, "submit_label": submit_label,
        "mode": mode, "date": date, "time": time, "captions": captions or "",
        "is_cancelled": is_cancelled, "errors": errors or [],
    })


class ShowtimeCreateView(StaffRequiredMixin, View):
    permission_required = "cinema.add_showtime"

    def get(self, request, eng_pk):
        engagement = get_object_or_404(Engagement, pk=eng_pk)
        return _render_showtime_form(
            request, engagement, reverse("dashboard:showtime_create", args=[eng_pk]),
            "Create Showtime", "create", date=engagement.start_date.isoformat())

    def post(self, request, eng_pk):
        engagement = get_object_or_404(Engagement, pk=eng_pk)
        date_str, time_str = request.POST.get("date", ""), request.POST.get("time", "")
        captions = request.POST.get("captions") or None
        action = reverse("dashboard:showtime_create", args=[eng_pk])

        def again(errors):
            return _render_showtime_form(request, engagement, action, "Create Showtime", "create",
                                         date=date_str, time=time_str, captions=captions,
                                         errors=errors)

        if engagement.status == EngagementStatus.CANCELLED:
            return again([CANCELLED_ENGAGEMENT])
        if not date_str or not time_str:
            return again(["Date and time are required."])
        starts_at = _parse_starts_at(date_str, time_str)
        if starts_at is None:
            return again([INVALID_DATE_TIME])
        with transaction.atomic():
            # Same lock as the bulk view, so two quick submits for one slot
            # can't both pass the overlap check.
            Screen.objects.select_for_update().get(pk=engagement.screen_id)
            conflicts = check_overlap_against_existing(
                engagement.screen, starts_at, engagement.total_runtime_minutes,
                engagement.title)
            if conflicts:
                return again([format_overlap_error(c) for c in conflicts])
            Showtime.objects.create(engagement=engagement, starts_at=starts_at,
                                    captions=captions)
        return _showtime_list_response(request, engagement,
                                       {"kind": "success", "message": "Showtime created"}, close_drawer=True)


class ShowtimeEditView(StaffRequiredMixin, View):
    permission_required = "cinema.change_showtime"

    def get(self, request, pk):
        st = get_object_or_404(
            Showtime.objects.select_related("engagement", "screen"), pk=pk)
        local = st.starts_at.astimezone(CINEMA_TZ)
        return _render_showtime_form(
            request, st.engagement, reverse("dashboard:showtime_edit", args=[pk]),
            "Save Changes", "edit", date=local.date().isoformat(),
            time=local.strftime("%H:%M"), captions=st.captions or "",
            is_cancelled=st.is_cancelled)

    def post(self, request, pk):
        st = get_object_or_404(Showtime.objects.select_related("engagement", "screen"), pk=pk)
        engagement = st.engagement
        date_str, time_str = request.POST.get("date", ""), request.POST.get("time", "")
        captions = request.POST.get("captions") or None
        is_cancelled = request.POST.get("is_cancelled") == "on"
        action = reverse("dashboard:showtime_edit", args=[pk])

        def again(errors):
            return _render_showtime_form(request, engagement, action, "Save Changes", "edit",
                                         date=date_str, time=time_str, captions=captions,
                                         is_cancelled=is_cancelled, errors=errors)

        if not date_str or not time_str:
            return again(["Date and time are required."])
        starts_at = _parse_starts_at(date_str, time_str)
        if starts_at is None:
            return again([INVALID_DATE_TIME])
        with transaction.atomic():
            # The showtime's own screen, which can differ from the
            # engagement's after the engagement is moved to another screen.
            Screen.objects.select_for_update().get(pk=st.screen_id)
            if not is_cancelled:  # cancelling skips the overlap check (matches source)
                conflicts = check_overlap_against_existing(
                    st.screen, starts_at, engagement.total_runtime_minutes,
                    engagement.title, exclude_showtime_id=st.pk)
                if conflicts:
                    return again([format_overlap_error(c) for c in conflicts])
            st.starts_at = starts_at
            st.captions = captions
            st.is_cancelled = is_cancelled
            st.save()
        return _showtime_list_response(request, engagement,
                                       {"kind": "success", "message": "Showtime updated"},
                                       close_drawer=True)


class ShowtimeDeleteView(StaffRequiredMixin, View):
    permission_required = "cinema.delete_showtime"

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
    permission_required = "cinema.add_showtime"

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

        if engagement.status == EngagementStatus.CANCELLED:
            return again([CANCELLED_ENGAGEMENT])
        if not start_str or not end_str:
            return again(["Start and end date are required."])
        if not times:
            return again(["Add at least one time."])
        try:
            start_date = datetime.date.fromisoformat(start_str)
            end_date = datetime.date.fromisoformat(end_str)
            parsed_times = [datetime.time.fromisoformat(t) for t in times]
        except ValueError:
            return again(["Enter valid dates and times."])
        if end_date < start_date:
            return again(["End date cannot be before start date."])

        screen = engagement.screen
        runtime = engagement.total_runtime_minutes
        title = engagement.title
        proposed_showtimes = []
        current = start_date
        one_day = datetime.timedelta(days=1)
        while current <= end_date:
            for t in parsed_times:
                starts_at = datetime.datetime.combine(current, t, tzinfo=CINEMA_TZ)
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
