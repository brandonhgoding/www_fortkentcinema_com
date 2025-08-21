from django.utils import timezone
from django.views.generic import TemplateView, ListView, DetailView
from cinema.models import Film
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


class FilmDetailView(DetailView):
    model = Film
    template_name = "website/film_detail.html"
