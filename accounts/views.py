from axes.utils import reset as reset_lockout
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.views import (
    LoginView,
    PasswordChangeView,
    PasswordResetConfirmView,
)
from django.contrib.messages.views import SuccessMessageMixin

from accounts.forms import DashboardPasswordChangeForm, EmailAuthenticationForm


class LockoutClearingPasswordResetConfirmView(PasswordResetConfirmView):
    """Sets the new password, then lifts any sign-in lockout on the account
    (see AXES_* in settings), so someone who locked themselves out and reset
    can sign in straight away rather than wait out the cool-off."""

    def form_valid(self, form):
        response = super().form_valid(form)
        # Stored emails are already the lowercased form axes counts against.
        reset_lockout(username=self.user.email)
        return response


class ChangePasswordView(LoginRequiredMixin, SuccessMessageMixin, PasswordChangeView):
    """A signed-in staff user picks a new password by proving
    the current one. Django keeps this session signed in and, since the
    session hash changes, signs out every other session for the account.
    Someone who has forgotten their password uses the emailed reset instead.
    """

    template_name = "dashboard/password_change.html"
    form_class = DashboardPasswordChangeForm
    success_url = "/dashboard/"
    success_message = "Password changed."


class SignInView(LoginView):
    """The sign-in screen: email and password."""

    template_name = "dashboard/login.html"
    authentication_form = EmailAuthenticationForm

    def dispatch(self, request, *args, **kwargs):
        # Someone already signed in goes on to the dashboard, unless sent
        # here with a "next" (say, to reach a page their account may not
        # open), in which case they see the form to sign in as someone else.
        self.redirect_authenticated_user = not (
            request.POST.get("next") or request.GET.get("next")
        )
        return super().dispatch(request, *args, **kwargs)
