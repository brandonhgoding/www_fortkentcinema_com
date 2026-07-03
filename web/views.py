from django.views.generic import TemplateView


class HomeView(TemplateView):
    # Placeholder shell — Plan 2 replaces this with the real homepage
    # (Hero, NowShowing, ComingSoon, Membership) backed by the leprinceos service.
    template_name = "web/home.html"
