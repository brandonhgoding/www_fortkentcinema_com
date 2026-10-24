from audience.models import Member, MemberStatus
from audience.terms import latest_term
from django.contrib.auth.mixins import LoginRequiredMixin
from django.utils import timezone
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
        ctx["tier_name"] = None
        ctx["starts_on"] = None
        ctx["expired_on"] = None
        if member:
            terms = list(member.terms.all())
            term = member.current_term or latest_term(terms)
            if term:
                ctx["tier_name"] = term.tier.name
            status = member.status
            if status == MemberStatus.UPCOMING:
                today = timezone.localdate()
                ctx["starts_on"] = min(
                    (t.started_on for t in terms if t.started_on > today),
                    default=None,
                )
            elif status == MemberStatus.LAPSED:
                last = latest_term(terms)
                ctx["expired_on"] = last.expires_on if last else None
        return ctx
