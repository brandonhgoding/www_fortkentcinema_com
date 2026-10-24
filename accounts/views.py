from axes.utils import reset as reset_lockout
from django.contrib.auth import get_user_model
from django.contrib.auth.views import LoginView, PasswordResetConfirmView
from django.db import IntegrityError, transaction
from django.shortcuts import render
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.views import View
from django.views.decorators.cache import never_cache

from accounts import verification
from accounts.client_ip import request_ip
from accounts.forms import EmailAuthenticationForm, RegisterForm, ResendForm


class LockoutClearingPasswordResetConfirmView(PasswordResetConfirmView):
    """Sets the new password, then lifts any sign-in lockout on the account
    (see AXES_* in settings), so someone who locked themselves out and reset
    can sign in straight away rather than wait out the cool-off."""

    def form_valid(self, form):
        response = super().form_valid(form)
        # Stored emails are already the lowercased form axes counts against.
        reset_lockout(username=self.user.email)
        return response


class SignInView(LoginView):
    """The sign-in screen: email and password."""

    template_name = "dashboard/login.html"
    authentication_form = EmailAuthenticationForm


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
        if not user.is_active:
            return
        if user.is_staff or user.email_verified_at is not None:
            verification.send_already_registered(request, email)
            return
        user.set_password(password)
        user.save(update_fields=["password"])
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
            verification.send_verification(request, user)


@method_decorator(never_cache, name="dispatch")
class VerifyEmailView(View):
    """Opening the link only shows a confirm button; verifying happens on the
    POST, so mail scanners and link previews that fetch the URL spend
    nothing. It does not sign the person in."""

    def get(self, request, token):
        user = verification.read_token(token)
        if user is None:
            return self._expired(request)
        return render(request, "dashboard/verify_confirm.html", {"email": user.email})

    def post(self, request, token):
        user = verification.read_token(token)
        if user is None:
            return self._expired(request)
        user.email_verified_at = timezone.now()
        user.save(update_fields=["email_verified_at"])
        return render(request, "dashboard/verify_done.html")

    def _expired(self, request):
        return render(request, "dashboard/verify_expired.html", status=410)
