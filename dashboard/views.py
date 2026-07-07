import json

from cinema.models import Film, Screen
from cinema.tmdb import TMDBAPIError
from cinema.tmdb.services import TMDBService
from django.db.models import ProtectedError
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, render
from django.urls import reverse
from django.views.generic import TemplateView, View

from .forms import ScreenForm
from .mixins import StaffRequiredMixin


class HomeView(StaffRequiredMixin, TemplateView):
    template_name = "dashboard/home.html"


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
    """Placeholder route target so `{% url 'dashboard:film_from_tmdb' %}` resolves
    from _tmdb_options.html; the real import-from-TMDB behavior lands in the next task."""

    def post(self, request):
        return HttpResponse(status=204)


class EngagementsStubView(StaffRequiredMixin, TemplateView):
    template_name = "dashboard/_stub_page.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["page_title"] = "Engagements"
        return ctx
