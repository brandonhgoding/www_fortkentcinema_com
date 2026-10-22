import json

from django.contrib.auth.mixins import AccessMixin
from django.core.exceptions import PermissionDenied
from django.http import HttpRequest, HttpResponse, HttpResponseForbidden

DENIED_MESSAGE = "You don't have permission to do that."


class StaffRequiredMixin(AccessMixin):
    """Anonymous users are redirected to login; authenticated non-staff get 403.

    Staff must also hold every permission in `permission_required` (a codename
    string or tuple of them); views declaring none stay open to all staff.
    """

    permission_required: str | tuple[str, ...] = ()

    def permissions_tuple(self) -> tuple[str, ...]:
        if isinstance(self.permission_required, str):
            return (self.permission_required,)
        return tuple(self.permission_required)

    def has_dashboard_permission(self) -> bool:
        return self.request.user.has_perms(self.permissions_tuple())

    def permission_denied_response(self, request: HttpRequest) -> HttpResponse:
        if request.headers.get("HX-Request"):
            resp = HttpResponseForbidden()
            resp["HX-Trigger"] = json.dumps(
                {"dashboard-toast": {"kind": "error", "message": DENIED_MESSAGE}}
            )
            return resp
        raise PermissionDenied

    def dispatch(self, request: HttpRequest, *args, **kwargs) -> HttpResponse:
        if not request.user.is_authenticated:
            return self.handle_no_permission()
        if not request.user.is_staff:
            raise PermissionDenied
        if not self.has_dashboard_permission():
            return self.permission_denied_response(request)
        return super().dispatch(request, *args, **kwargs)
