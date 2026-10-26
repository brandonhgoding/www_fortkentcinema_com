"""The welcome email: the membership's dates and how to use it."""

from boxoffice.site import base_url
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.urls import reverse
from web.constants import SITE_CONFIG

from join.models import MembershipOrder


def _day(day) -> str:
    return day.strftime("%b %-d, %Y")


def welcome_context(order: MembershipOrder) -> dict:
    term = order.term
    return {
        "order": order,
        "tier_name": term.tier.name,
        "started_on": _day(term.started_on),
        "expires_on": _day(term.expires_on),
        # More than one term: the buyer was a member already.
        "renewal": term.member.terms.count() > 1,
        "register_url": base_url() + reverse("register"),
        "url": base_url() + reverse("join:order", args=[order.token]),
        "cinema": SITE_CONFIG["cinema"],
    }


def send_welcome(order: MembershipOrder) -> None:
    context = welcome_context(order)
    subject = ("Your Fort Kent Cinema membership is renewed" if context["renewal"]
               else "Welcome to Fort Kent Cinema")
    message = EmailMultiAlternatives(
        subject=subject,
        body=render_to_string("join/email/welcome.txt", context),
        to=[order.email],
    )
    message.attach_alternative(
        render_to_string("join/email/welcome.html", context), "text/html"
    )
    message.send()
