from datetime import timedelta
from django.contrib import messages
from django.core.mail import send_mail
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.urls import reverse, reverse_lazy
from django.utils import timezone
from django.views.generic import TemplateView, ListView, DetailView, FormView
from rest_framework.response import Response
from rest_framework.views import APIView
from django.conf import settings
from cinema.models import Film, Booking
from blog.models import BlogPost
from website.forms import ContactForm


class HomePageTemplateView(TemplateView):
    template_name = "website/index.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        now = timezone.now()
        context["now_playing"] = Film.objects.filter(
            bookings__booking_start_date__lte=now, bookings__booking_end_date__gte=now
        ).order_by("bookings__booking_start_date")[:2]
        return context


class ArchiveListView(ListView):
    model = Film
    template_name = "website/archive.html"

    def get_queryset(self):
        now = timezone.now()
        return (
            Film.objects.filter(bookings__booking_end_date__lt=now)
            .order_by("-bookings__booking_end_date")
            .distinct()
        )


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
        context["next_films"] = Film.objects.filter(
            bookings__booking_start_date__gt=now, bookings__confirmed=True
        ).order_by("bookings__booking_start_date")[:3]
        return context


class FilmDetailView(DetailView):
    model = Film
    template_name = "website/film_detail.html"


class CalendarEventsAPIView(APIView):
    def get(self, request, *args, **kwargs):
        qs = (
            Booking.objects.select_related("film")
            # .filter(starts_at__gte=now() - timedelta(days=14),
            #         starts_at__lte=now() + timedelta(days=90))
            .order_by("booking_start_date")
        )

        events = []
        for s in qs:
            end_date = s.booking_end_date + timedelta(days=1)

            events.append(
                {
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
                }
            )
        events.append({
            "title": "Closed For Vacation",
            "start": "2025-11-01",
            "end": "2025-11-20",
            "allDay": True,
            "color": "red",
        })
        return Response(events)


def contact_view(request):
    if request.method == "POST":
        form = ContactForm(request.POST)
        if form.is_valid() and settings.USE_GMAIL:
            data = form.cleaned_data
            subject = f"[Contact] {data['subject']}"
            body = (
                f"Name: {data['name']}\n"
                f"Email: {data['email']}\n"
                f"Phone: {data.get('phone','')}\n\n"
                f"Message:\n{data['message']}"
            )

            to_emails = settings.CONTACT_FORM_TO_ADDRESS

            send_mail(
                subject=subject,
                message=body,
                from_email=settings.EMAIL_HOST_USER,
                recipient_list=to_emails,
                fail_silently=False,
            )

            # Flash success and redirect to the same page (PRG)
            messages.success(request, "Thanks! Your message has been sent.")
            return redirect(reverse("contact"))
    else:
        form = ContactForm()

    return render(request, "website/contact.html", {"form": form})
