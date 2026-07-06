from django.views.generic import TemplateView

from .mixins import StaffRequiredMixin


class HomeView(StaffRequiredMixin, TemplateView):
    template_name = "dashboard/home.html"


class ScreensStubView(StaffRequiredMixin, TemplateView):
    template_name = "dashboard/_stub_page.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["page_title"] = "Screens"
        return ctx


class EngagementsStubView(StaffRequiredMixin, TemplateView):
    template_name = "dashboard/_stub_page.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["page_title"] = "Engagements"
        return ctx
