from django import template
from django.urls import resolve
from phone.models import Voicemail, VoicemailStatus

register = template.Library()


@register.simple_tag
def nav_active(request, url_name: str) -> str:
    """Return 'active' when the request's resolved URL name matches url_name.

    url_name is the fully-qualified name, e.g. 'dashboard:home'.
    """
    try:
        match = resolve(request.path_info)
    except Exception:
        return ""
    current = (
        f"{match.namespace}:{match.url_name}" if match.namespace else match.url_name
    )
    return "active" if current == url_name else ""


@register.simple_tag
def new_voicemail_count() -> int:
    """NEW voicemails, for the sidebar badge on every dashboard page."""
    return Voicemail.objects.filter(status=VoicemailStatus.NEW).count()
