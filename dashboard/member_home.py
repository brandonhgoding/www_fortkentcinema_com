from audience.models import (
    LinkRequestStatus,
    Member,
    MembershipLinkRequest,
    MemberStatus,
)
from audience.terms import latest_term
from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import redirect
from django.utils import timezone
from django.views.generic import TemplateView

from .forms import MembershipLinkRequestForm
from .member_views import this_month


class MemberHomeView(LoginRequiredMixin, TemplateView):
    """What a signed-in non-staff user sees at /dashboard/.

    The membership shown is the roster row whose email is the account's.
    Without one, the page offers to ask staff to link a membership held
    under another address (MembershipLinkRequest); POST saves that ask.
    """

    template_name = "dashboard/member_home.html"

    def member(self):
        return (
            Member.objects.filter(email=self.request.user.email)
            .prefetch_related("terms__tier", "free_admissions")
            .first()
        )

    def open_requests(self):
        return MembershipLinkRequest.objects.filter(
            user=self.request.user, status=LinkRequestStatus.NEW
        )

    def post(self, request, *args, **kwargs):
        if self.member() is not None or self.open_requests().exists():
            # Nothing to ask for, or already asked: the page says which.
            return redirect("dashboard:home")
        form = MembershipLinkRequestForm(request.POST)
        if form.is_valid():
            ask = form.save(commit=False)
            ask.user = request.user
            ask.save()
            return redirect("dashboard:home")
        return self.render_to_response(self.get_context_data(link_form=form))

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        member = self.member()
        ctx["member"] = member
        ctx["free_used"] = member.free_admissions_in(*this_month()) if member else 0
        ctx["tier_name"] = None
        ctx["starts_on"] = None
        ctx["expired_on"] = None
        ctx["link_request"] = None
        if member:
            # Staff linked it (or the member joined): the ask is answered.
            for ask in self.open_requests():
                ask.mark_done()
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
        else:
            ctx["link_request"] = self.open_requests().first()
            ctx.setdefault("link_form", MembershipLinkRequestForm())
        return ctx
