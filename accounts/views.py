from axes.utils import reset as reset_lockout
from django.contrib.auth.views import PasswordResetConfirmView
from django.http import HttpResponseNotFound
from django.views import View


class LockoutClearingPasswordResetConfirmView(PasswordResetConfirmView):
    """Sets the new password, then lifts any sign-in lockout on the account
    (see AXES_* in settings), so someone who locked themselves out and reset
    can sign in straight away rather than wait out the cool-off."""

    def form_valid(self, form):
        response = super().form_valid(form)
        # Stored emails are already the lowercased form axes counts against.
        reset_lockout(username=self.user.email)
        return response


class MagicLinkSignInView(View):
    """Stub: the sign-in view arrives in a later task."""

    def get(self, request, token):
        return HttpResponseNotFound()
