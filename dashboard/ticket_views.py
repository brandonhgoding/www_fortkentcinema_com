"""Staff pages for online ticket orders."""

from cinema.models import Showtime
from django.shortcuts import get_object_or_404
from django.views.generic import TemplateView

from .mixins import StaffRequiredMixin


class ShowtimeOrdersView(StaffRequiredMixin, TemplateView):
    """The online orders for one showtime."""

    template_name = "dashboard/showtime_orders.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["showtime"] = get_object_or_404(
            Showtime.objects.select_related("engagement"), pk=kwargs["pk"]
        )
        return ctx
