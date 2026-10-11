from django.conf import settings

from .constants import SITE_CONFIG, TICKET_PRICES


def site_config(request):
    return {
        "site_config": SITE_CONFIG,
        # For partials/ticket_info.html — the same numbers the phone line
        # reads, so the site and the phone can't quote different prices.
        "ticket_prices": TICKET_PRICES,
        # Empty outside production — that's what keeps dev traffic out of GA4.
        "ga_measurement_id": settings.GA_MEASUREMENT_ID,
    }
