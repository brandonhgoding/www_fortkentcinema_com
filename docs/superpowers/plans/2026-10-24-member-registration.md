# Member Registration with Email Verification Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Members register with email + password, confirm their address by a 24-hour single-use link, then sign in with their password on the shared `/login`; the branch's magic-link sign-in is removed.

**Architecture:** Builds on branch `feat/member-magic-link` (member home, member sidebar, public links and throttle helpers already there). `accounts/client_ip.py` becomes the one client-IP source (throttles and axes). `accounts/verification.py` replaces `accounts/magic_link.py`: throttles, the verify token and the two emails. Views `RegisterView`, `ResendVerificationView`, `VerifyEmailView` live in `accounts/views.py`; `EmailAuthenticationForm.confirm_login_allowed` blocks unverified members. A nullable `User.email_verified_at` plus a nightly cleanup command complete it.

**Tech Stack:** Django 5.2, `django.core.signing`, LocMemCache, django-axes 8, Django templates; tests via `python manage.py test`.

**Spec:** `docs/superpowers/specs/2026-10-24-member-registration-design.md`

## Global Constraints

- Verify link lifetime: 24 hours (`VERIFY_MAX_AGE = 24 * 60 * 60` in `accounts/verification.py`), signing salt `accounts.verify-email`, single use.
- Per-address throttle: 300 s (`settings.PASSWORD_RESET_TIMEOUT`); per-IP cap: 5 per 3600 s, counted for register and resend together; IP only from `accounts.client_ip.request_ip`.
- Unverified accounts deleted after 7 days by `manage.py delete_unverified_accounts`.
- Verification applies to non-staff only; staff behaviour unchanged.
- GET of a verify link changes nothing; POST verifies and does not sign in.
- Honeypot field `website`, checked before form validation.
- Copy, verbatim:
  - login: `Sign in`, `Forgot password?`, `Create an account`
  - unverified login: `Please confirm your email first. We can send a new link.` with button `Send a new link`
  - register page heading `Create an account`, button `Create account`
  - sent page: `Check your email to confirm your address`
  - throttle: `We sent an email to this address in the last 5 minutes. Check your inbox (and spam), or try again after {time}.` (`g:i A`, America/New_York)
  - IP cap: `Too many requests from this connection. Try again later.`
  - confirm page: `Confirm your email, {email}` and button `Confirm my email`
  - confirmed: `Email confirmed. You can sign in now.`
  - expired: `This confirmation link has expired or was already used.`
  - verify email subject `Confirm your Fort Kent Cinema account`; already-registered subject `Your Fort Kent Cinema account`
- Lint gate: no new flake8 findings on changed lines. Commit per task on `feat/member-magic-link`; never merge or push. The ansible edit (Task 2) stays uncommitted.

## Review Focus

1. **Someone registers an address they don't own.** The owner's mail scanner fetching the link must not verify it (GET inert). The attacker's password must not be replaced silently on a verified account, and a verified account's password is never changed by `/register`. Tested in Task 3 and Task 4.
2. **Production client IP.** With `REMOTE_ADDR=""` and nginx's `X-Real-IP`, each visitor gets their own bucket, and a forged `X-Forwarded-For` changes nothing. Tested in Task 1.
3. **A member with the right password but unverified** must never get a session, including through axes' success handler. Tested in Task 5.
4. **Re-registering an unverified address** resets the password and sends a fresh link. The older link still verifies the same account, which is acceptable. Re-registering a staff or verified address changes nothing. Tested in Task 4.
5. **Back button and double-click on "Confirm my email"** never show a bare CSRF 403 or a confusing error (never_cache, button disabled). Tested in Task 4.

---

### Task 1: One client-IP source (`accounts/client_ip.py`)

**Files:**
- Create: `accounts/client_ip.py`, `accounts/tests/test_client_ip.py`
- Modify: `fortkentcinema/settings.py:283-287` (define `USE_PROXY_HEADERS = config("USE_PROXY_HEADERS", default=False, cast=bool)` as a setting; replace the `AXES_IPWARE_*` block with `AXES_CLIENT_IP_CALLABLE = "accounts.client_ip.request_ip"`), `accounts/views.py` (the request view's `get_client_ip_address` → `request_ip`)

**Interfaces:**
- Produces: `request_ip(request) -> str | None` — `X-Real-IP` when `settings.USE_PROXY_HEADERS`, else `REMOTE_ADDR`; stripped; `None` if empty or not a valid IP (`ipaddress.ip_address`).

- [ ] **Step 1: Failing tests** (`RequestFactory`):
  - `test_proxy_mode_reads_x_real_ip`: `override_settings(USE_PROXY_HEADERS=True)`, `REMOTE_ADDR=""`, `HTTP_X_REAL_IP="203.0.113.7"` → `"203.0.113.7"`.
  - `test_proxy_mode_ignores_forwarded_for`: same plus `HTTP_X_FORWARDED_FOR="1.2.3.4"` → `"203.0.113.7"`.
  - `test_direct_mode_uses_remote_addr`: `USE_PROXY_HEADERS=False`, `REMOTE_ADDR="198.51.100.2"`, `HTTP_X_REAL_IP="1.2.3.4"` → `"198.51.100.2"`.
  - `test_empty_or_garbage_is_none`: `""` and `"not-an-ip"` → `None`.
  - `test_axes_uses_it`: `axes.helpers.get_client_ip_address(req)` equals `request_ip(req)` in proxy mode.
- [ ] **Step 2: Run** `python manage.py test accounts.tests.test_client_ip` — expect failures.
- [ ] **Step 3: Implement** the helper, settings and the view swap. Keep the settings comment explaining why: gunicorn sits on a unix socket, `REMOTE_ADDR` is empty, nginx `proxy_params` sets `X-Real-IP`, and django-ipware is not installed.
- [ ] **Step 4: Run** `python manage.py test accounts dashboard.tests.test_login` — expect OK (lockout tests live in `accounts/tests/test_lockout.py`).
- [ ] **Step 5: Commit** `fix(accounts): one client-IP source for throttles and lockout`.

### Task 2: `email_verified_at`, cleanup command, cron

**Files:**
- Modify: `accounts/models.py` (field `email_verified_at = models.DateTimeField(null=True, blank=True)`), `accounts/admin.py` (show it read-only in the list and change form)
- Create: `accounts/migrations/0004_user_email_verified_at.py` (AddField, then a `RunPython` that sets `email_verified_at=timezone.now()` on every existing user; the reverse is a no-op), `accounts/management/commands/delete_unverified_accounts.py`, `accounts/tests/test_unverified_cleanup.py`
- Modify (ansible, leave uncommitted): `../ansible/roles/django_app/tasks/main.yml` (cron task `{{ app.name }}_delete_unverified_accounts`, hour 3, minute 15, `flock`, `when: app.cron_unverified_cleanup | default(false)`, copying the `cron_ticket_expire` task and adding the flag to the CRON_TZ condition at line ~392), `../ansible/group_vars/webservers.yml` (`cron_unverified_cleanup: true` beside `cron_ticket_expire: true`), `../ansible/CLAUDE.md` (add the flag to the cron list)

**Interfaces:**
- Produces: `User.email_verified_at`; the command `delete_unverified_accounts` deletes users with `is_staff=False`, `email_verified_at__isnull=True`, `date_joined__lt=now - 7 days`, and writes `Deleted N unverified accounts.` to stdout.

- [ ] **Step 1: Failing tests:** `test_migration_marks_existing_users_verified` (use the repo's migration-test pattern in `accounts/tests/test_migration_0002.py`); `test_deletes_only_old_unverified_members` (a member unverified 8 days old is deleted; unverified 6 days kept; verified 30 days kept; unverified staff 30 days kept; stdout `Deleted 1 unverified accounts.`).
- [ ] **Step 2: Run** `python manage.py test accounts.tests.test_unverified_cleanup` (plus the migration test) — expect failures.
- [ ] **Step 3: Implement** with `makemigrations accounts -n user_email_verified_at`, then add the RunPython.
- [ ] **Step 4: Run** the same command and `python manage.py makemigrations --check --dry-run` — expect OK and `No changes detected`.
- [ ] **Step 5: Commit** (app repo only) `feat(accounts): email_verified_at and nightly cleanup of unverified accounts`.

### Task 3: Verification core (`accounts/verification.py`)

**Files:**
- Create: `accounts/verification.py`, `accounts/tests/test_verification.py`, `dashboard/templates/dashboard/verify_email.txt`, `verify_subject.txt`, `already_registered_email.txt`, `already_registered_subject.txt`
- Delete: `accounts/magic_link.py`, `accounts/tests/test_magic_link.py`, `dashboard/templates/dashboard/magic_link_email.txt`, `magic_link_subject.txt` (after moving the throttle helpers)

**Interfaces:**
- Consumes: `User.email_verified_at` (Task 2).
- Produces (move `normalise`, `ip_allowed`, `claim_address`, `IP_CAP`, `IP_WINDOW` over unchanged except cache-key prefix `register:`):
  - `make_token(user) -> str` — signs `{"u": user.pk, "e": user.email}` with salt `accounts.verify-email`.
  - `read_token(token: str) -> User | None` — valid signature younger than `VERIFY_MAX_AGE`; the user exists, `email` unchanged, `is_active`, not staff, `email_verified_at is None`.
  - `send_verification(request, user) -> None` and `send_already_registered(request, email: str) -> None` — `EmailMessage` sends; failures logged with `logger.exception` and swallowed. The verify URL is `reverse("verify_email", args=[token])`. The already-registered email links absolute `/login` and `/password-reset`.

- [ ] **Step 1: Failing tests:** `test_round_trip`; `test_still_valid_just_inside_24h` (+86399 s) and `test_expired_after_24h` (+86401 s) using `mock.patch("time.time", ...)`; `test_spent_once_verified`; `test_refused_if_email_changed_user_deleted_staff_or_inactive`; `test_tampered`; `test_verify_email_content` (subject, recipient, link to `/register/verify/`, `24 hours`, `ignore`); `test_already_registered_email_content` (subject, `/login`, `/password-reset`); `test_send_failure_logged` (`assertLogs("accounts.verification", "ERROR")`); move the throttle and IP-cap tests from `test_magic_link.py` and point them at the new module.
- [ ] **Step 2: Run** `python manage.py test accounts.tests.test_verification` — expect failures. (The `verify_email` URL name comes in Task 4; add it now as `path("register/verify/<str:token>", VerifyEmailView.as_view(), name="verify_email")` with a stub `VerifyEmailView` returning `HttpResponseNotFound()`, as the magic-link plan did.)
- [ ] **Step 3: Implement.** Wrap the email templates in `{% autoescape off %}`, as `magic_link_email.txt` did.
- [ ] **Step 4: Run** the same command — expect OK.
- [ ] **Step 5: Commit** `feat(accounts): email verification token and emails`.

### Task 4: Register, resend and verify views; remove magic-link sign-in

**Files:**
- Modify: `accounts/forms.py` (replace `MagicLinkForm` with `RegisterForm` and `ResendForm`), `accounts/views.py` (replace `MagicLinkRequestView` and `MagicLinkSignInView` with `RegisterView`, `ResendVerificationView`, `VerifyEmailView`), `fortkentcinema/urls.py` (drop the `login/link*` paths; add `register`, `register/resend`, `register/verify/<str:token>`)
- Create: templates `dashboard/register.html`, `dashboard/register_sent.html`, `dashboard/verify_confirm.html`, `dashboard/verify_done.html`, `dashboard/verify_expired.html` (all extend `login_base.html`); tests `accounts/tests/test_register.py`, `accounts/tests/test_verify_email.py`
- Delete: `magic_link_confirm.html`, `magic_link_expired.html`, `magic_link_sent.html`, `_magic_link_form.html`, `accounts/tests/test_magic_link_request.py`, `accounts/tests/test_magic_link_sign_in.py`

**Interfaces:**
- Consumes: Task 1 `request_ip`; Task 3 functions.
- Produces:
  - `RegisterForm(forms.Form)`: `email` (normalised), `password1`, `password2` (must match; `password_validation.validate_password(password1)` errors on `password2` the way Django's `SetPasswordForm` does), `website`.
  - `ResendForm(forms.Form)`: `email` (normalised), `website`.
  - `RegisterView` — GET renders `register.html`. POST in this order: honeypot (`request.POST.get("website")`) → sent page; invalid → form again; IP cap → 429 sent-page variant; throttle → sent-page variant with the retry time; else the account branch from spec §1.5. New users are created with `create_user(email, password, is_staff=False)` inside `atomic()`, with `IntegrityError` handled as the "unverified exists" case.
  - `ResendVerificationView` — POST only, same order; sends only to an active unverified member; always the sent page.
  - `VerifyEmailView` — `never_cache` on both methods. GET → confirm page or 410 expired. POST → re-read; `None` → 410; else set `email_verified_at=timezone.now()` (`save(update_fields=[...])`) → `verify_done.html`. The confirm form has `onsubmit` disabling its button.

- [ ] **Step 1: Failing tests** (`cache.clear()` in setUp):
  - `test_register_page`: heading `Create an account`.
  - `test_honeypot_checked_first`: `website` filled together with an invalid email → sent page, no user, no mail.
  - `test_invalid_and_weak_and_mismatched`: field errors, no user.
  - `test_new_address_creates_unverified_member`: one user, `is_staff=False`, `email_verified_at` None, `check_password` true; one mail with subject `Confirm your Fort Kent Cinema account`.
  - `test_unverified_address_resets_password_and_resends`.
  - `test_verified_and_staff_get_already_registered_and_are_unchanged`: password hash unchanged; subject `Your Fort Kent Cinema account`.
  - `test_inactive_gets_nothing`.
  - `test_same_page_every_case`: compare the response text with the address removed.
  - `test_throttle_message_exact_time`: patch `accounts.verification.timezone.now`.
  - `test_ip_cap_429_after_five_across_register_and_resend`.
  - `test_cap_buckets_per_visitor_in_production_shape`: `override_settings(USE_PROXY_HEADERS=True)`, six register POSTs with `REMOTE_ADDR=""` and six distinct `HTTP_X_REAL_IP` values → none is 429; six with one `X-Real-IP` and varying forged `HTTP_X_FORWARDED_FOR` → the sixth is 429.
  - `test_resend_only_for_unverified_member`.
  - Verify: `test_get_changes_nothing`; `test_post_verifies_and_does_not_sign_in` (`Email confirmed. You can sign in now.`, no `_auth_user_id`); `test_second_post_and_bad_tokens_410`; `test_never_cache_headers` (`Cache-Control` contains `no-cache` on GET and POST); `test_button_disables_on_submit` (`onsubmit` present).
  - `test_magic_link_urls_gone`: `/login/link` is 404.
- [ ] **Step 2: Run** `python manage.py test accounts.tests.test_register accounts.tests.test_verify_email` — expect failures.
- [ ] **Step 3: Implement**, then delete the magic-link views, templates, URLs and tests listed above.
- [ ] **Step 4: Run** `python manage.py test accounts dashboard.tests.test_login dashboard.tests.test_password_reset` — expect OK.
- [ ] **Step 5: Commit** `feat(accounts): register with a password and confirm by email`.

### Task 5: Sign-in screen and password reset

**Files:**
- Modify: `accounts/forms.py` (`EmailAuthenticationForm.confirm_login_allowed`), `accounts/views.py` (`SignInView`: drop `link_form`; redirect an authenticated visitor to `/dashboard/` when no `next`; `LockoutClearingPasswordResetConfirmView.form_valid` sets `email_verified_at` if None), `dashboard/templates/dashboard/login.html` (one form, no `<details>`; `Create an account` link to `/register`; the unverified block with a `ResendForm` POST to `/register/resend` carrying the typed email in a hidden field), `dashboard/static/dashboard/css/login.css` (remove the now-unused toggle styles)
- Test: `dashboard/tests/test_login.py`, `dashboard/tests/test_password_reset.py`

**Interfaces:**
- Consumes: `User.email_verified_at`; `ResendForm` and `/register/resend` (Task 4).
- Produces: `confirm_login_allowed(user)` calls super, then raises `ValidationError(UNVERIFIED_MESSAGE, code="unverified")` for a non-staff user with `email_verified_at is None`. `UNVERIFIED_MESSAGE` is the verbatim copy.

- [ ] **Step 1: Failing tests:**
  - `test_login_single_form`: no `<details`, no `Email me a sign-in link`; `Create an account` links to `/register`.
  - `test_unverified_member_not_signed_in_sees_resend`: right password → 200; message and `Send a new link`; the hidden email; no `_auth_user_id`; also run with `@override_settings(AXES_ENABLED=True, AUTHENTICATION_BACKENDS=[<the production list from settings>])`.
  - `test_unverified_wrong_password_says_invalid`.
  - `test_verified_member_signs_in_to_dashboard`.
  - `test_signed_in_visitor_redirected_from_login`, and `?next=` still renders the form.
  - The existing staff tests (`next`, lockout) still pass.
  - In `test_password_reset.py`: `test_reset_marks_member_verified`.
- [ ] **Step 2: Run** `python manage.py test dashboard.tests.test_login dashboard.tests.test_password_reset` — expect failures.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run** `python manage.py test accounts dashboard.tests.test_login dashboard.tests.test_password_reset dashboard.tests.test_member_home` — expect OK.
- [ ] **Step 5: Commit** `feat(accounts): one sign-in form; unverified members confirm first`.

### Task 6: Member-home copy fix, visual check, full suite

**Files:**
- Modify: `dashboard/templates/dashboard/member_home.html` (the `Starts` and `Expired` blocks: the label is `Starts` / `Expired` and the value is the date alone, so the text no longer repeats; add a little spacing between each value and the next label, using existing spacing tokens), `dashboard/tests/test_member_home.py` (assert `Starts</` … date, not `Starts Starts`)

- [ ] **Step 1: Failing test** for the repeated label, then fix it.
- [ ] **Step 2: Visual check.** Take headless Firefox screenshots, each with a fresh `--profile` directory, of `/login`, `/register`, a verify confirm page and the member home, at 1280 px and 375 px wide. Render through the Django test client with `/static/` rewritten to `file://` paths, as Task 5 of the magic-link plan did. Fix anything cramped.
- [ ] **Step 3: Full suite.** `python manage.py test` → OK. `flake8` on changed files: no findings on changed lines. `python manage.py makemigrations --check --dry-run` → `No changes detected`. Confirm no `magic_link` reference remains (`grep -rn magic_link --include=*.py --include=*.html . | grep -v .venv | grep -v docs/`).
- [ ] **Step 4: Commit** `fix(dashboard): member home date labels`.
