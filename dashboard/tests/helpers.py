"""Test helpers for the dashboard's per-view permissions."""

from typing import Iterable

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission

User = get_user_model()

ALL = object()

# Every permission the dashboard spec names, as "app.codename".
SPEC_PERMISSIONS = frozenset(
    {
        # cinema
        "cinema.view_showtime",  # template/home gating only, no view declares it
        "cinema.view_screen",
        "cinema.add_screen",
        "cinema.change_screen",
        "cinema.delete_screen",
        "cinema.view_film",
        "cinema.add_film",
        "cinema.view_engagement",
        "cinema.add_engagement",
        "cinema.change_engagement",
        "cinema.delete_engagement",
        "cinema.add_showtime",
        "cinema.change_showtime",
        "cinema.delete_showtime",
        "cinema.view_poll",
        "cinema.add_poll",
        "cinema.change_poll",
        "cinema.delete_poll",
        "cinema.add_polloption",
        "cinema.change_polloption",
        "cinema.delete_polloption",
        "cinema.delete_vote",
        "cinema.view_rentalinquiry",
        "cinema.change_rentalinquiry",
        "cinema.view_adinquiry",
        "cinema.change_adinquiry",
        # tickets
        "tickets.view_ticketorder",
        "tickets.change_ticketorder",
        # audience
        "audience.view_member",
        "audience.add_member",
        "audience.change_member",
        "audience.delete_member",
        "audience.view_membershipterm",
        "audience.add_membershipterm",
        "audience.change_membershipterm",
        "audience.delete_membershipterm",
        "audience.add_freeadmission",
        "audience.delete_freeadmission",
        "audience.view_membershiptier",
        "audience.add_membershiptier",
        "audience.change_membershiptier",
        "audience.delete_membershiptier",
        "audience.add_membershipbenefit",
        "audience.change_membershipbenefit",
        "audience.delete_membershipbenefit",
        "audience.view_subscriber",
        # boxoffice
        "boxoffice.view_membershipsale",
        "boxoffice.view_salespull",  # template/home gating only
        "boxoffice.change_membershipsale",
        # blog
        "blog.view_blogpost",
        "blog.view_blogauthor",  # template gating only
        "blog.view_blogcategory",  # template gating only
        "blog.add_blogpost",
        "blog.change_blogpost",
        "blog.delete_blogpost",
        "blog.add_blogauthor",
        "blog.change_blogauthor",
        "blog.delete_blogauthor",
        "blog.add_blogcategory",
        "blog.change_blogcategory",
        "blog.delete_blogcategory",
        # phone
        "phone.view_voicemail",
        "phone.change_voicemail",
        "phone.delete_voicemail",
    }
)


def _declared_by_views() -> frozenset[str]:
    from dashboard import urls

    found: set[str] = set()
    for pattern in urls.urlpatterns:
        view_class = getattr(pattern.callback, "view_class", None)
        declared = getattr(view_class, "permission_required", ())
        if isinstance(declared, str):
            declared = (declared,)
        found.update(declared)
    return frozenset(found)


DASHBOARD_PERMISSIONS = SPEC_PERMISSIONS | _declared_by_views()


def make_staff(
    username: str = "staffer",
    password: str = "pw12345",
    perms: object | Iterable[str] = ALL,
    **extra,
) -> User:
    """Create an is_staff user holding exactly the given permissions.

    The default holds every dashboard permission.
    """
    wanted = DASHBOARD_PERMISSIONS if perms is ALL else frozenset(perms)
    user = User.objects.create_user(
        username=username, password=password, is_staff=True, **extra
    )
    rows = []
    for label in sorted(wanted):
        app, codename = label.split(".", 1)
        try:
            rows.append(
                Permission.objects.get(content_type__app_label=app, codename=codename)
            )
        except Permission.DoesNotExist:
            raise ValueError(f"No such permission: {label}") from None
    user.user_permissions.set(rows)
    return user


def permissions_except(*codenames: str) -> set[str]:
    """Every dashboard permission except the given "app.codename" ones."""
    return set(DASHBOARD_PERMISSIONS) - set(codenames)
