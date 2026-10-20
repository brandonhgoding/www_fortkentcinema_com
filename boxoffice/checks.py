"""Report a half-configured Square at startup, not on every page view."""
from django.conf import settings
from django.core import checks

from boxoffice.gateway import disabled_reason


@checks.register("boxoffice")
def check_square_settings(app_configs, **kwargs) -> list[checks.CheckMessage]:
    """A token with a blank id or an unknown environment keeps the sync off.

    A blank token is the deliberate off switch and says nothing. A Warning,
    not an Error, so a half-set deployment can still run migrate and the
    nightly commands, which print what is wrong themselves.
    """
    reason = disabled_reason()
    if reason is None or not settings.SQUARE_ACCESS_TOKEN:
        return []
    return [checks.Warning(
        f"Square sync is off: {reason}.",
        hint="Set every SQUARE_* setting, or blank SQUARE_ACCESS_TOKEN to turn "
             "the sync off on purpose.",
        id="boxoffice.W001",
    )]
