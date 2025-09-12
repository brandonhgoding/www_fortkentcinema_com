from django.conf import settings


def analytics(request):
    enabled = (
        getattr(settings, "GA_ENABLED", False)
        and not (request.user.is_authenticated and (request.user.is_staff or request.user.is_superuser))
    )
    return {"GA_MEASUREMENT_ID": settings.GA_MEASUREMENT_ID, "GA_ENABLED": enabled}
