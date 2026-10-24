from audience.models import Member
from django.contrib.auth.mixins import LoginRequiredMixin
from django.views.generic import TemplateView

from .member_views import this_month


class MemberHomeView(LoginRequiredMixin, TemplateView):
    """What a signed-in non-staff user sees at /dashboard/."""

    template_name = "dashboard/member_home.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        member = (
            Member.objects.filter(email=self.request.user.email)
            .prefetch_related("terms__tier", "free_admissions")
            .first()
        )
        ctx["member"] = member
        ctx["free_used"] = member.free_admissions_in(*this_month()) if member else 0
        return ctx
