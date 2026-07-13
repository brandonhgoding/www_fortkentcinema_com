from django.conf import settings

from .constants import SITE_CONFIG


def site_config(request):
    return {
        "site_config": SITE_CONFIG,
        # Empty outside production — that's what keeps dev traffic out of GA4.
        "ga4_measurement_id": settings.GA4_MEASUREMENT_ID,
    }
