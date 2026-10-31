from django.core.exceptions import PermissionDenied

from accounts import lockout


class IpLockoutBackend:
    """Refuses every password check from an address that has failed
    LOGIN_IP_FAILURE_LIMIT sign-ins within the cool-off (accounts/lockout.py).

    First in AUTHENTICATION_BACKENDS, so it covers every form that calls
    authenticate(): the site's sign-in page and the admin's own login alike.
    Raising PermissionDenied stops the later backends from checking the
    password at all, and the axes middleware turns the flag into the same
    "too many attempts" page axes shows for its own lockouts.
    """

    def authenticate(self, request, **credentials):
        if request is not None and lockout.ip_locked(request):
            request.axes_locked_out = True
            raise PermissionDenied
        return None

    # No get_user(): this backend never signs anyone in, so no session names
    # it, and the test client's force_login() skips it for a backend that can.
