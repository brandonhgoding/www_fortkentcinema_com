"""Emails to ticket buyers: the ticket itself (with a QR code) and a refund note."""

import io
from email.mime.image import MIMEImage

import qrcode
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.urls import reverse
from web.constants import SITE_CONFIG
from web.services.cinema_data import CINEMA_TZ

from tickets.models import TicketOrder
from tickets.spec import base_url

QR_CID = "ticket-qr"


def qr_png(url: str) -> bytes:
    buffer = io.BytesIO()
    qrcode.make(url).save(buffer, format="PNG")
    return buffer.getvalue()


def ticket_context(order: TicketOrder) -> dict:
    showtime = order.showtime
    starts_at = showtime.starts_at.astimezone(CINEMA_TZ)
    lines = sorted(
        order.lines.all(), key=lambda line: TicketOrder.TIERS.index(line.tier)
    )
    return {
        "order": order,
        "title": showtime.engagement.title,
        "day": starts_at.strftime("%a %b %-d"),
        "time": starts_at.strftime("%-I:%M %p"),
        "screen": showtime.screen.name,
        "lines": [
            f"{line.quantity} × {line.tier.capitalize()} "
            f"${line.quantity * line.unit_cents / 100:.2f}"
            for line in lines
        ],
        "total": f"${order.total_dollars:.2f}",
        "url": base_url() + reverse("tickets:order", args=[order.token]),
        "cinema": SITE_CONFIG["cinema"],
    }


def send_ticket(order: TicketOrder) -> None:
    context = ticket_context(order)
    when = f"{context['day']} at {context['time']}"
    message = EmailMultiAlternatives(
        subject=f"Your tickets: {context['title']}, {when}",
        body=render_to_string("tickets/email/ticket.txt", context),
        to=[order.email],
    )
    message.attach_alternative(
        render_to_string("tickets/email/ticket.html", context), "text/html"
    )
    image = MIMEImage(qr_png(context["url"]), "png")
    image.add_header("Content-ID", f"<{QR_CID}>")
    image.add_header("Content-Disposition", "inline", filename="ticket-qr.png")
    message.attach(image)
    message.send()


def send_refund(order: TicketOrder) -> None:
    context = ticket_context(order)
    message = EmailMultiAlternatives(
        subject=f"Refunded: {context['title']}, {context['day']}",
        body=render_to_string("tickets/email/refund.txt", context),
        to=[order.email],
    )
    message.send()
