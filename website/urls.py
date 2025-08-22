from django.urls import path
from website import views as website_views

app_name = "website"

urlpatterns = [
    path("", website_views.HomePageTemplateView.as_view(), name="index"),
    path("archive/", website_views.ArchiveListView.as_view(), name="archive"),
    path("archive/<slug:slug>/", website_views.FilmDetailView.as_view(), name="film_detail"),
    path("coming-soon/", website_views.ComingSoonTemplateView.as_view(), name="coming_soon"),
    path("coming-soon/calendar/", website_views.CalendarEventsAPIView.as_view(), name="calendar_events"),
    path("fort-kent-cinema-blog/", website_views.BlogListView.as_view(), name="blog_list"),
    path("fort-kent-cinema-blog/<slug:slug>/", website_views.BlogDetailView.as_view(), name="blog_detail"),
]
