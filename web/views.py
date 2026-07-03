from django.views.generic import TemplateView

from web.services.leprinceos import get_now_showing, get_coming_soon


class HomeView(TemplateView):
    template_name = "web/home.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["now_showing"] = get_now_showing()
        ctx["coming_soon"] = get_coming_soon()
        return ctx
