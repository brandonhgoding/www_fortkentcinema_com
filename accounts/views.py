from axes.utils import reset as reset_lockout
from django.contrib.auth import get_user_model
from django.contrib.auth.hashers import make_password
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.views import (
    LoginView,
    PasswordChangeView,
    PasswordResetConfirmView,
)
from django.contrib.messages.views import SuccessMessageMixin
from django.conf import settings
from django.db import IntegrityError, transaction
from django.shortcuts import render
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.views import View
from django.views.decorators.cache import never_cache

from accounts import lockout, verification
from accounts.client_ip import request_ip
from accounts.forms import EmailAuthenticationForm, RegisterForm, ResendForm


class LockoutClearingPasswordResetConfirmView(PasswordResetConfirmView):
    """Sets the new password, then lifts any sign-in lockout on the account
    (see AXES_* in settings), so someone who locked themselves out and reset
    can sign in straight away rather than wait out the cool-off."""

    def form_valid(self, form):
        response = super().form_valid(form)
        # Following the emailed link proves the address, so a member who
        # reset instead of confirming can sign in.
        if self.user.email_verified_at is None:
            self.user.email_verified_at = timezone.now()
            self.user.save(update_fields=["email_verified_at"])
        # Stored emails are already the lowercased form axes counts against.
        reset_lockout(username=self.user.email)
        return response


class ChangePasswordView(LoginRequiredMixin, SuccessMessageMixin, PasswordChangeView):
    """A signed-in user, staff or member, picks a new password by proving
    the current one. Django keeps this session signed in and, since the
    session hash changes, signs out every other session for the account.
    Someone who has forgotten their password uses the emailed reset instead.
    """

    template_name = "dashboard/password_change.html"
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

    def post(self, request, *args, **kwargs):
        # Too many failed sign-ins from this address, whatever the emails:
        # the same page axes shows, before the password is even checked.
        if lockout.ip_locked(request):
            return render(request, settings.AXES_LOCKOUT_TEMPLATE, status=429)
        return super().post(request, *args, **kwargs)


class _GatedEmailView(View):
    """Shared by register and resend: honeypot, form, per-IP cap and
    per-address throttle, in that order. Every outcome that is not a form
    error shows the same "check your email" page."""

    form_class = ResendForm
    form_template = "dashboard/register.html"
    sent_template = "dashboard/register_sent.html"
    http_method_names = ["post"]

    def post(self, request):
        # The honeypot comes first, before validation, so a bot learns nothing.
        if request.POST.get("website"):
            return render(
                request,
                self.sent_template,
                {"email": request.POST.get("email", "").strip()},
            )
        form = self.form_class(request.POST)
        if not form.is_valid():
            return render(request, self.form_template, {"form": form})
        email = form.cleaned_data["email"]
        ctx = {"email": email}
        if not verification.ip_allowed(request_ip(request)):
            ctx["too_many"] = True
            return render(request, self.sent_template, ctx, status=429)
        retry = verification.claim_address(email)
        if retry is not None:
            ctx["retry"] = retry
        else:
            self.act(request, form, email)
        return render(request, self.sent_template, ctx)

    def act(self, request, form, email):
        raise NotImplementedError


class RegisterView(_GatedEmailView):
    form_class = RegisterForm
    http_method_names = ["get", "post"]

    def get(self, request):
        return render(request, self.form_template, {"form": RegisterForm()})

    def act(self, request, form, email):
        password = form.cleaned_data["password2"]
        users = get_user_model().objects
        user = users.filter(email__iexact=email).first()
        if user is None:
            try:
                with transaction.atomic():
                    user = users.create_user(email, password, is_staff=False)
            except IntegrityError:
                # Someone registered the same address a moment ago.
                user = users.filter(email__iexact=email).first()
                if user is None:
                    return
            else:
                verification.send_verification(request, user)
                return
        if not user.is_active or user.is_staff or user.email_verified_at is not None:
            # Nothing is set on these branches; hash anyway so the response
            # takes as long as a new registration and says nothing about
            # whether this address already has a confirmed account.
            make_password(password)
            if user.is_active:
                verification.send_already_registered(request, email)
            return
        user.set_password(password)
        # The 7-day cleanup counts from the latest link sent.
        user.date_joined = timezone.now()
        user.save(update_fields=["password", "date_joined"])
        verification.send_verification(request, user)


class ResendVerificationView(_GatedEmailView):
    def act(self, request, form, email):
        user = get_user_model().objects.filter(email__iexact=email).first()
        if (
            user is not None
            and user.is_active
            and not user.is_staff
            and user.email_verified_at is None
        ):
            user.date_joined = timezone.now()
            user.save(update_fields=["date_joined"])
            verification.send_verification(request, user)


@method_decorator(never_cache, name="dispatch")
class VerifyEmailView(View):
    """Opening the link shows a password field; verifying happens on the
    POST, once the password matches. So a mail scanner fetching the URL
    spends nothing, and whoever clicks a link for an address they did not
    register cannot confirm it (owner, 2026-10-24, after the accounts
    security audit). It does not sign the person in."""

    def get(self, request, token):
        user = self._user(token)
        if user is None:
            return self._expired(request)
        if user.email_verified_at is not None:
            return render(request, "dashboard/verify_done.html")
        return render(request, "dashboard/verify_confirm.html", {"email": user.email})

    def post(self, request, token):
        user = self._user(token)
        if user is None:
            return self._expired(request)
        if user.email_verified_at is not None:
            return render(request, "dashboard/verify_done.html")
        if not user.check_password(request.POST.get("password", "")):
            verification.record_wrong_password(user)
            return render(
                request,
                "dashboard/verify_confirm.html",
                {"email": user.email, "wrong_password": True},
            )
        user.email_verified_at = timezone.now()
        user.save(update_fields=["email_verified_at"])
        return render(request, "dashboard/verify_done.html")

    def _user(self, token):
        user = verification.read_token(token)
        if user is None or verification.link_locked(user):
            return None
        return user

    def _expired(self, request):
        return render(request, "dashboard/verify_expired.html", status=410)
