from django.utils import timezone
from django.views.generic import TemplateView
from cinema.models import Film


class HomePageTemplateView(TemplateView):
    template_name = "website/index.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        now = timezone.now()
        context['now_playing'] = Film.objects.filter(
            bookings__booking_start_date__lte=now, bookings__booking_end_date__gte=now
        ).order_by("bookings__booking_start_date")[:2]
        return context
