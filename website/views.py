from datetime import timedelta

from django.conf import settings
from django.contrib import messages
from django.core.mail import send_mail
from django.shortcuts import redirect, render
from django.urls import reverse, reverse_lazy
from django.utils import timezone
from django.views.generic import DetailView, ListView, TemplateView
from rest_framework.response import Response
from rest_framework.views import APIView

from blog.models import BlogPost
from cinema.models import Booking, Event, Film, TicketRate
from cinema.utils import get_current_or_next_films
from website.forms import ContactForm


class HomePageTemplateView(TemplateView):
    template_name = "website/index.html"
    NOW_PLAYING_LIMIT = 2

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        now = timezone.now()
        context["ticket_rates"] = TicketRate.objects.all()
        context["now_playing"] = get_current_or_next_films(limit=self.NOW_PLAYING_LIMIT, now=now)
        return context


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
        for cinema_event in Event.objects.all():
            new_event = {
                "title": cinema_event.name,
                "start": cinema_event.event_start_date.isoformat(),
                "end": (cinema_event.event_end_date + timedelta(days=1)).isoformat(),
                "allDay": True,
                "color": "teal",
            }
            if cinema_event.slug is not None:
                new_event["url"] = reverse_lazy("website:event_detail", args=[cinema_event.slug])
            events.append(new_event)
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


class EventDetailView(DetailView):
    model = Event

    def get_object(self, queryset=None):
        return Event.objects.filter(slug=self.kwargs["slug"]).first()

    def get_template_names(self):
        # Ensure the object is loaded
        obj = self.get_object()
        # Use the slug to build the template name
        return [f"website/{obj.slug}.html"]
