from datetime import timedelta

from django.http import JsonResponse
from django.urls import reverse
from django.utils import timezone
from django.views.generic import TemplateView, ListView, DetailView
from rest_framework.response import Response
from rest_framework.views import APIView

from cinema.models import Film, Booking
from blog.models import BlogPost


class HomePageTemplateView(TemplateView):
    template_name = "website/index.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        now = timezone.now()
        context['now_playing'] = Film.objects.filter(
            bookings__booking_start_date__lte=now, bookings__booking_end_date__gte=now
        ).order_by("bookings__booking_start_date")[:2]
        return context


class ArchiveListView(ListView):
    model = Film
    template_name = "website/archive.html"

    def get_queryset(self):
        now = timezone.now()
        return Film.objects.filter(
            bookings__booking_end_date__lt=now
        ).order_by("-bookings__booking_end_date").distinct()


class BlogListView(ListView):
    model = BlogPost
    template_name = "website/blog_list.html"

    def get_queryset(self):
        return BlogPost.objects.all().order_by("-post_date")


class BlogDetailView(DetailView):
    model = BlogPost
    template_name = "website/blog_detail.html"


class ComingSoonTemplateView(TemplateView):
    template_name = "website/coming_soon.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        now = timezone.now()
        context['next_films'] = Film.objects.filter(
            bookings__booking_start_date__gt=now, bookings__confirmed=True
        ).order_by("bookings__booking_start_date")[:3]
        return context


class FilmDetailView(DetailView):
    model = Film
    template_name = "website/film_detail.html"


class CalendarEventsAPIView(APIView):
    def get(self, request, *args, **kwargs):
        qs = (
            Booking.objects
            .select_related("film")
            # .filter(starts_at__gte=now() - timedelta(days=14),
            #         starts_at__lte=now() + timedelta(days=90))
            .order_by("booking_start_date")
        )

        events = []
        for s in qs:
            end_date = s.booking_end_date + timedelta(days=1)

            events.append({
                "title": s.film.title,  # or f"{s.film.title} — {s.screen.name}"
                "start": s.booking_start_date.isoformat(),  # FullCalendar handles ISO 8601
                "end": end_date.isoformat(),
                "allDay": True,
                "extendedProps": {
                    "filmId": s.film_id,
                    "active": s.is_active,
                    "confirmed": s.is_confirmed,
                },
                # "url": reverse("showtime-detail", args=[s.id]),
            })
        return Response(events)
