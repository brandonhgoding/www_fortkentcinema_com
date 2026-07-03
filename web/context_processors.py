from .constants import SITE_CONFIG


def site_config(request):
    return {"site_config": SITE_CONFIG}
