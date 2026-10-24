from axes.helpers import get_client_ip_address
from axes.utils import reset as reset_lockout
from django.contrib.auth import get_user_model, login
from django.contrib.auth.views import LoginView, PasswordResetConfirmView
from django.db import IntegrityError, transaction
from django.shortcuts import redirect, render
from django.views import View

from accounts import magic_link
from accounts.forms import EmailAuthenticationForm, MagicLinkForm


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
    """The sign-in screen: an emailed link first, the staff password form
    behind a toggle."""

    template_name = "dashboard/login.html"
    authentication_form = EmailAuthenticationForm

    def get_context_data(self, **kwargs):
        kwargs.setdefault("link_form", MagicLinkForm())
        return super().get_context_data(**kwargs)


class MagicLinkRequestView(View):
    """Emails a sign-in link. Every outcome shows the same "check your email"
    page (never a redirect, so the address can be shown), whether or not the
    address has an account or may be sent one."""

    http_method_names = ["post"]

    def post(self, request):
        form = MagicLinkForm(request.POST)
        if not form.is_valid():
            return render(
                request,
                "dashboard/login.html",
                {"link_form": form, "form": EmailAuthenticationForm(request)},
            )
        email = form.cleaned_data["email"]
        ctx = {"email": email}
        if form.cleaned_data["website"]:
            return render(request, "dashboard/magic_link_sent.html", ctx)
        if not magic_link.ip_allowed(get_client_ip_address(request)):
            ctx["too_many"] = True
            return render(request, "dashboard/magic_link_sent.html", ctx, status=429)
        retry = magic_link.claim_address(email)
        if retry is not None:
            ctx["retry"] = retry
        else:
            user = get_user_model().objects.filter(email__iexact=email).first()
            if magic_link.link_allowed_for(user):
                magic_link.send_link(request, email)
        return render(request, "dashboard/magic_link_sent.html", ctx)


class MagicLinkSignInView(View):
    """Opening a link only shows a confirm button; signing in (and creating
    the member account on first use) happens on the POST, so mail scanners
    and link previews that fetch the URL spend nothing."""

    def get(self, request, token):
        if request.user.is_authenticated:
            return redirect("/dashboard/")
        email = magic_link.read_token(token)
        if email is None:
            return self._expired(request)
        return render(request, "dashboard/magic_link_confirm.html", {"email": email})

    def post(self, request, token):
        if request.user.is_authenticated:
            return redirect("/dashboard/")
        email = magic_link.read_token(token)
        if email is None:
            return self._expired(request)
        users = get_user_model().objects
        user = users.filter(email__iexact=email).first()
        if user is None:
            try:
                with transaction.atomic():
                    user = users.create_user(email, password=None, is_staff=False)
            except IntegrityError:
                return self._expired(request)
        login(request, user, backend="django.contrib.auth.backends.ModelBackend")
        return redirect("/dashboard/")

    def _expired(self, request):
        return render(
            request,
            "dashboard/magic_link_expired.html",
            {"link_form": MagicLinkForm()},
            status=410,
        )
