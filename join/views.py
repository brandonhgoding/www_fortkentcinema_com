"""The public membership checkout: the join page, then the order's own page."""

import datetime

from audience.models import Member, MembershipTier
from boxoffice.gateway import get_gateway, square_enabled
from django.http import HttpResponseRedirect
from django.shortcuts import get_object_or_404, render
from django.urls import reverse
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.views import View
from django.views.decorators.cache import never_cache

from join import orders
from join.forms import JoinForm
from join.models import MembershipOrder
from join.orders import NotSoldOnline, recover_pending

BOX_OFFICE = "Join at the box office before any show."
UNAVAILABLE = f"Online membership sign-up isn't available right now. {BOX_OFFICE}"
NOT_ONLINE = f"This tier isn't sold online. {BOX_OFFICE}"
CHECKOUT_FAILED = "We couldn't start checkout. Please try again, or join at the box office."

# The order page refreshes itself this long while Square confirms the payment.
CONFIRMING_FOR = datetime.timedelta(minutes=2)
# A PENDING order this old asks Square directly, in case the webhook was lost.
RECOVER_AFTER = datetime.timedelta(seconds=60)


def _see_other(url: str) -> HttpResponseRedirect:
    """A 303: the browser follows a POST's redirect with a GET."""
    response = HttpResponseRedirect(url)
    response.status_code = 303
    return response


def _dollars(cents: int) -> str:
    return f"${cents // 100}" if cents % 100 == 0 else f"${cents / 100:.2f}"


def _day(day: datetime.date) -> str:
    return day.strftime("%b %-d, %Y")


def closed_sentence(tier: MembershipTier, square_on: bool) -> str:
    """Why the tier cannot be bought here right now, or "" when it can."""
    if not square_on:
        return UNAVAILABLE
    if not tier.square_variation_id:
        return NOT_ONLINE
    return ""


class JoinView(View):
    """GET /membership/join/<slug>/ shows the form; POST records the order and
    sends the buyer to Square's checkout."""

    def get(self, request, slug):
        tier = self._tier(slug)
        form = JoinForm(initial=self._initial(request))
        return self._render(request, tier, form, square_on=square_enabled())

    def post(self, request, slug):
        tier = self._tier(slug)
        form = JoinForm(request.POST)
        if form.is_bot:
            return _see_other(reverse("join:start", args=[slug]))
        gateway = get_gateway()
        square_on = square_enabled() and gateway is not None
        if not square_on or not form.is_valid():
            return self._render(request, tier, form, square_on=square_on)
        try:
            order = orders.start(
                tier,
                first_name=form.cleaned_data["first_name"],
                last_name=form.cleaned_data["last_name"],
                email=form.cleaned_data["email"],
                gateway=gateway,
            )
        except NotSoldOnline:
            return self._render(request, tier, form, square_on=square_on)
        if order.status == MembershipOrder.Status.ABANDONED:
            return self._render(request, tier, form, square_on=square_on,
                                error=CHECKOUT_FAILED)
        return _see_other(order.square_checkout_url)

    def _tier(self, slug) -> MembershipTier:
        return get_object_or_404(
            MembershipTier.objects.prefetch_related("benefits"),
            slug=slug, show_on_membership_page=True)

    def _initial(self, request) -> dict:
        """A signed-in visitor's email, and their roster names when known."""
        user = request.user
        if not user.is_authenticated:
            return {}
        initial = {"email": user.email}
        member = Member.objects.filter(email=user.email).first()
        if member is not None:
            initial.update(first_name=member.first_name, last_name=member.last_name)
        return initial

    def _render(self, request, tier, form, *, square_on, error=""):
        context = {
            "tier": tier,
            "form": form,
            "fields": [form["first_name"], form["last_name"], form["email"]],
            "price": _dollars(tier.price * 100),
            "closed_sentence": closed_sentence(tier, square_on),
            "error": error,
        }
        return render(request, "join/start.html", context)


def order_state(order: MembershipOrder, now: datetime.datetime) -> str:
    """Which version of the order page to show."""
    if order.status == MembershipOrder.Status.PENDING:
        return "pending" if order.created_at > now - CONFIRMING_FOR else "waiting"
    return order.status.lower()


@method_decorator(never_cache, name="dispatch")
class OrderView(View):
    """GET /membership/order/<token>/: the welcome once paid, else where it stands."""

    def get(self, request, token):
        order = get_object_or_404(
            MembershipOrder.objects.select_related("tier", "term__tier", "term__member"),
            token=token)
        now = timezone.now()
        if (order.status == MembershipOrder.Status.PENDING
                and order.created_at <= now - RECOVER_AFTER):
            recover_pending(order, gateway=get_gateway())
        term = order.term
        user = request.user
        context = {
            "order": order,
            "tier": order.tier,
            "state": order_state(order, now),
            "tier_name": term.tier.name if term else order.tier.name,
            "started_on": _day(term.started_on) if term else "",
            "expires_on": _day(term.expires_on) if term else "",
            "renewal": bool(term) and term.member.terms.count() > 1,
            "mine": user.is_authenticated and user.email.lower() == order.email,
            "register_url": reverse("register"),
        }
        return render(request, "join/order.html", context)
