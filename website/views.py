from django.conf import settings
from django.contrib import messages
from django.core.mail import send_mail
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.generic import DetailView, ListView, TemplateView

from blog.models import BlogPost
from cinema.models import Booking, TicketRate, Film
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
        context["upcoming_films"] = Film.objects.filter(bookings__booking_start_date__gt=now).order_by("bookings__booking_start_date")[:4]
        return context


class BlogListView(ListView):
    model = BlogPost
    template_name = "website/blog_list.html"

    def get_queryset(self):
        return BlogPost.objects.all().order_by("-post_date")


class BlogDetailView(DetailView):
    model = BlogPost
    template_name = "website/blog_detail.html"


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
            return redirect(reverse("website:contact"))
    else:
        form = ContactForm()

    return render(request, "website/contact.html", {"form": form})
