# Member Sign-in by Magic Link Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Members sign in (and so register) by an emailed one-time link and land on a member home inside `/dashboard/`; staff sign-in is unchanged.

**Architecture:** A small `accounts/magic_link.py` owns the signed token, the two throttles and the email. Two views in `accounts/views.py` serve `/login/link` (request) and `/login/link/<token>` (confirm page + sign-in). `/login` becomes one screen with the link form first and the staff password form in a `<details>` toggle. `dashboard.views.HomeView` hands non-staff users to a new `MemberHomeView`; the sidebar renders staff navigation only for staff.

**Tech Stack:** Django 5.2, `django.core.signing`, default (locmem) cache, django-axes helpers, Django templates; tests with `django.test.TestCase` via `python manage.py test`.

**Spec:** `docs/superpowers/specs/2026-10-24-member-magic-link-design.md`

## Global Constraints

- Link lifetime and per-address throttle: `settings.PASSWORD_RESET_TIMEOUT` (300 s). Do not add a new setting.
- Per-IP cap: 5 link requests per IP per 3600 s; IP from `axes.helpers.get_client_ip_address(request)`, never `cinema.voting.client_ip`.
- Member accounts: `accounts.User`, `is_staff=False`, unusable password, created only on the sign-in POST. No schema change, no migration.
- Staff and inactive accounts never receive a link and are never signed in by one; the page they see is the same as for anyone else.
- `GET` of a link never signs in or creates anything.
- Copy, verbatim:
  - button: `Email me a sign-in link`; toggle: `Staff: sign in with password`
  - sent page heading: `Check your email`
  - throttle: `We sent a sign-in link to this address in the last 5 minutes. Check your inbox (and spam), or try again after {time}.` with `{time}` as `g:i A` in `America/New_York`
  - IP cap: `Too many sign-in requests from this connection. Try again later.`
  - confirm button: `Sign in as {email}`
  - expired: `This sign-in link has expired or was already used.`
  - email subject: `Your Fort Kent Cinema sign-in link`
  - no roster match: `No membership on file for this email. Join at the box office before any show.`
  - footer label `Member sign in`, note `See your membership`; membership page: `Already a member? Sign in to see your membership.`
- Honeypot field name `website`, hidden like the site's other forms.
- Lint gate: no new flake8 findings on changed lines (repo baseline is dirty). Commit per task on `feat/member-magic-link`; do not merge or push.

## Review Focus

1. **Email typed with different case or spaces** (`" Ann@Example.com "`) must hit the same throttle key, token and account as `ann@example.com`. Tested in Task 1 and Task 3.
2. **Double-click or two tabs on "Sign in as…"** must give one account and one session. The second POST shows the expired page, and an `IntegrityError` from a racing create is treated the same way. Tested in Task 3.
3. **A staff member signed in on the box-office machine opens a member's link.** The signed-in user is redirected to `/dashboard/` and the member is not signed in over them. Tested in Task 3.
4. **A member following an old bookmark or HTMX call to a staff page** gets 403 (the HTMX toast path included), never staff data. Tested in Task 4.
5. **`?next=` on `/login`** must not leak into the magic-link flow. Members always land on `/dashboard/`, and the staff password form keeps honouring `next`. Tested in Task 2.

---

### Task 1: Token, throttles and email (`accounts/magic_link.py`)

**Files:**
- Create: `accounts/magic_link.py`
- Create: `dashboard/templates/dashboard/magic_link_email.txt`, `dashboard/templates/dashboard/magic_link_subject.txt`
- Modify: `accounts/views.py` (stub `MagicLinkSignInView`), `fortkentcinema/urls.py` (`path("login/link/<str:token>", MagicLinkSignInView.as_view(), name="magic_link_sign_in")`)
- Test: `accounts/tests/test_magic_link.py`

**Interfaces:**
- Produces:
  - `normalise(email: str) -> str` — strip + lower.
  - `make_token(email: str) -> str` — signs `{"e": email, "l": <user.last_login isoformat or "">}` with `signing.dumps(..., salt="accounts.magic-link")`.
  - `read_token(token: str) -> str | None` — the email if the signature is good, younger than `PASSWORD_RESET_TIMEOUT`, the stored `last_login` still matches, and the account (if any) is active and not staff; else `None`.
  - `link_allowed_for(user: User | None) -> bool` — `True` for no account or an active non-staff account.
  - `ip_allowed(ip: str | None) -> bool` — counts this request; `False` once the count for that IP in the hour exceeds 5; `True` when `ip` is `None`.
  - `claim_address(email: str) -> datetime | None` — `None` if the address was free (and claims it for 300 s, storing the retry time); otherwise the stored retry `datetime` (aware).
  - `send_link(request, email: str) -> None` — builds the absolute URL to `magic_link_sign_in` with `make_token`, renders the two templates, sends with `EmailMessage`; any exception is logged with `logger.exception` and swallowed.
  - Constants `IP_CAP = 5`, `IP_WINDOW = 3600`.

- [ ] **Step 1: Write the failing tests** in `accounts/tests/test_magic_link.py` (`TestCase`, `cache.clear()` in `setUp`):
  - `test_round_trip_for_new_address`: `read_token(make_token("ann@example.com")) == "ann@example.com"`.
  - `test_expires_after_five_minutes`: make the token, then `mock.patch("time.time", return_value=time.time() + 301)` around `read_token` → `None`.
  - `test_spent_once_account_signs_in`: make a token for an existing member user, then set `last_login = timezone.now()` and save → `None`.
  - `test_spent_once_account_created`: token for an unknown address, then `make_user("ann@example.com", is_staff=False)` with `last_login` set → `None`.
  - `test_tampered_token`: `read_token(make_token("a@example.com") + "x") is None`.
  - `test_staff_and_inactive_refused`: tokens for a `make_staff(...)` address and an `is_active=False` user both read `None`; `link_allowed_for` is `False` for both, `True` for `None` and a member.
  - `test_normalise`: `normalise(" Ann@Example.com ") == "ann@example.com"`.
  - `test_claim_address_once_per_five_minutes`: first `claim_address` → `None`; second → a datetime ≈ now + 300 s (within 2 s).
  - `test_ip_cap`: five `ip_allowed("203.0.113.9")` → `True`, sixth → `False`; another IP still `True`; `ip_allowed(None)` → `True`.
  - `test_send_link_email`: with `rf` request (`RequestFactory().post("/login/link")`), `send_link(req, "ann@example.com")` puts one message in `mail.outbox` with subject `Your Fort Kent Cinema sign-in link`, the address as recipient, a body containing `http://testserver/login/link/`, `5 minutes` and `ignore`.
  - `test_send_failure_is_logged_not_raised`: patch `EmailMessage.send` to raise; `assertLogs("accounts.magic_link", "ERROR")`; no exception.

- [ ] **Step 2: Run** `python manage.py test accounts.tests.test_magic_link` — expect ImportError/failures.

- [ ] **Step 3: Implement `accounts/magic_link.py`** to the interfaces above. Cache keys `magic-link:addr:<email>` and `magic-link:ip:<ip>`; the IP counter uses `cache.add(key, 0, IP_WINDOW)` then `cache.incr(key)`. Add the `magic_link_sign_in` URL now, pointing at a stub `MagicLinkSignInView(View)` whose `get` returns `HttpResponseNotFound()`, so `reverse` works; Task 3 replaces the stub's body. The email body (template `magic_link_email.txt`):

```
Here is your link to sign in to Fort Kent Cinema:

{{ url }}

It works once and expires in 5 minutes. If you didn't ask to sign in, you can ignore this email.
```

- [ ] **Step 4: Run** the same command — expect OK.

- [ ] **Step 5: Commit** `feat(accounts): magic-link token, throttles and email`.

### Task 2: Login screen and link request (`/login`, `/login/link`)

**Files:**
- Modify: `accounts/forms.py` (add `MagicLinkForm`), `accounts/views.py` (add `SignInView`, `MagicLinkRequestView`), `fortkentcinema/urls.py` (use `SignInView` for `login`; add `path("login/link", ..., name="magic_link_request")`), `dashboard/templates/dashboard/login.html`, `dashboard/static/dashboard/css/login.css`
- Create: `dashboard/templates/dashboard/magic_link_sent.html`, `dashboard/templates/dashboard/_magic_link_form.html`
- Test: `accounts/tests/test_magic_link_request.py`; keep `dashboard/tests/test_login.py` green

**Interfaces:**
- Consumes: Task 1 functions.
- Produces:
  - `MagicLinkForm(forms.Form)`: `email = EmailField(max_length=254)` with `autocomplete="email"`; `website = CharField(required=False)`; `clean_email` returns `normalise(...)`.
  - `SignInView(LoginView)` — same `template_name`/`authentication_form` as today; adds `link_form` (an empty `MagicLinkForm`) to context.
  - `MagicLinkRequestView(View)` — `post` only. Order: invalid form → re-render `login.html` with `link_form` errors (status 200); honeypot → sent page, nothing sent; `not ip_allowed(...)` → sent page variant with the IP-cap message (status 429); `claim_address` returned a time → sent page variant with the throttle message; else `send_link` only if `link_allowed_for(user)`, then the sent page. Never redirects (so the email can be shown).
  - `_magic_link_form.html` — the email box, hidden `website` field, button `Email me a sign-in link`; reused by Task 3's expired page.

- [ ] **Step 1: Write failing tests** in `accounts/tests/test_magic_link_request.py` (`cache.clear()` in `setUp`; URL `/login/link`):
  - `test_login_page_leads_with_link_form`: GET `/login` contains `Email me a sign-in link` before `Staff: sign in with password`, and the password field sits inside `<details`.
  - `test_password_errors_open_the_staff_toggle`: a wrong-password POST to `/login` renders `<details` with `open`.
  - `test_unknown_address_gets_link`: POST `{"email": "New@Example.com"}` → 200, `Check your email`, `new@example.com` in page; one mail to `new@example.com`; no `User` created.
  - `test_member_gets_link_staff_and_inactive_do_not`: member account → 1 mail; staff and inactive accounts → 0 mail but the same `Check your email` page.
  - `test_honeypot`: `website` filled → `Check your email`, 0 mail.
  - `test_invalid_email_redisplays`: `{"email": "nope"}` → 200 with the field error and the link form.
  - `test_second_request_within_five_minutes_says_so`: two POSTs for `ghost@example.com` (no account) → 1 mail; second page contains `We sent a sign-in link to this address in the last 5 minutes` and the retry time formatted `g:i A` in local time.
  - `test_ip_cap_after_five`: six POSTs for six different addresses with `REMOTE_ADDR="203.0.113.9"` → sixth is 429 with `Too many sign-in requests from this connection. Try again later.` and only 5 mails.
  - `test_next_is_ignored_by_link_flow`: POST to `/login/link?next=/dashboard/members` → the sent email's link and later sign-in do not carry `next` (assert `next` not in the mail body).
  - In `dashboard/tests/test_login.py`, keep the existing staff tests passing and add `test_staff_password_login_still_honours_next`.

- [ ] **Step 2: Run** `python manage.py test accounts.tests.test_magic_link_request dashboard.tests.test_login` — expect failures.

- [ ] **Step 3: Implement** the form, views, URLs and templates. `login.html`: link form first (via `_magic_link_form.html`), then `<details class="login-staff"{% if form.errors %} open{% endif %}><summary>Staff: sign in with password</summary>` around the existing password form and "Forgot password?" link. `magic_link_sent.html` extends `login_base.html` and shows either `Check your email` + the address + "The link works once and expires in 5 minutes." or the throttle/IP message, with a "Back to sign in" link to `/login`. In `login.css`, style `.login-staff summary` as a quiet text button under the primary form, and hide the `website` field the way the site's other honeypots do.

- [ ] **Step 4: Run** the same command — expect OK.

- [ ] **Step 5: Commit** `feat(accounts): ask for a sign-in link from /login`.

### Task 3: Opening the link and signing in (`/login/link/<token>`)

**Files:**
- Modify: `accounts/views.py` (fill in the Task 1 stub `MagicLinkSignInView`), `fortkentcinema/urls.py` (the `magic_link_sign_in` URL already exists from Task 1)
- Create: `dashboard/templates/dashboard/magic_link_confirm.html`, `dashboard/templates/dashboard/magic_link_expired.html`
- Test: `accounts/tests/test_magic_link_sign_in.py`; `dashboard/tests/test_password_reset.py` (one new test)

**Interfaces:**
- Consumes: `read_token`, `normalise`, `_magic_link_form.html`, `MagicLinkForm`.
- Produces: `MagicLinkSignInView(View)`:
  - `get`: an authenticated user → redirect `/dashboard/`. `read_token` → `None` → render the expired page (status 410) with an empty `MagicLinkForm`. Otherwise render the confirm page with the `Sign in as {email}` button (a POST form with CSRF).
  - `post`: an authenticated user → redirect `/dashboard/`. Re-run `read_token`; `None` → expired page. Then fetch the user by email, or create one with `User.objects.create_user(email, password=None, is_staff=False)` inside `transaction.atomic()`, catching `IntegrityError` → expired page. Then `login(request, user, backend="django.contrib.auth.backends.ModelBackend")` and redirect to `/dashboard/`.

- [ ] **Step 1: Write failing tests** in `accounts/tests/test_magic_link_sign_in.py`:
  - `test_get_shows_button_and_changes_nothing`: GET a fresh token for `ann@example.com` → 200 with `Sign in as ann@example.com`; `User.objects.count() == 0`; the client is not authenticated.
  - `test_post_creates_member_and_signs_in`: POST → 302 to `/dashboard/`; the user exists with `is_staff=False`, `has_usable_password()` is False and `last_login` set; the session is authenticated as them.
  - `test_existing_member_signs_in_without_duplicate`.
  - `test_second_post_is_expired`: POST twice with the same token → second renders `This sign-in link has expired or was already used.`; one user.
  - `test_expired_and_tampered_show_expired_page_with_form`: status 410 and the `Email me a sign-in link` button present.
  - `test_mixed_case_link_matches_existing_account`: a token made from `normalise(" Ann@Example.com ")` signs into the existing `ann@example.com` account.
  - `test_signed_in_staff_opening_member_link_stays_staff`: staff client logged in, GET and POST a member token → redirect `/dashboard/`, session user still staff, member not created.
  - `test_integrity_error_on_create_shows_expired`: patch `create_user` to raise `IntegrityError` → expired page.
  - In `dashboard/tests/test_password_reset.py`: `test_member_account_gets_no_reset_email` — a user with an unusable password POSTs to `/password-reset` → 0 mail.

- [ ] **Step 2: Run** `python manage.py test accounts.tests.test_magic_link_sign_in dashboard.tests.test_password_reset` — expect failures (the reset test may already pass; it pins existing behaviour).

- [ ] **Step 3: Implement** the view and two templates (both extend `login_base.html`).

- [ ] **Step 4: Run** the same command — expect OK.

- [ ] **Step 5: Commit** `feat(accounts): sign in, or register, from a magic link`.

### Task 4: Member home in the dashboard

**Files:**
- Create: `dashboard/member_home.py` (`MemberHomeView`), `dashboard/templates/dashboard/member_home.html`
- Modify: `dashboard/views.py` (`HomeView.dispatch`), `dashboard/templates/dashboard/_sidebar.html`
- Test: `dashboard/tests/test_member_home.py`

**Interfaces:**
- Consumes: `audience.models.Member` properties `current_term`, `status_label`, `covered_through`, `free_admission_allowance`, `free_admissions_in(year, month)`; `dashboard.member_views.this_month()`.
- Produces:
  - `MemberHomeView(LoginRequiredMixin, TemplateView)` with template `dashboard/member_home.html`; context `member` (the `Member` with `email == request.user.email` and `prefetch_related("terms__tier", "free_admissions")`, or `None`) and `free_used` (an int from `free_admissions_in(*this_month())`).
  - `HomeView.dispatch`: if `request.user.is_authenticated` and not `is_staff`, return `MemberHomeView.as_view()(request)`; otherwise the current behaviour.

- [ ] **Step 1: Write failing tests** in `dashboard/tests/test_member_home.py` (members made with `make_user(..., is_staff=False)` then `self.client.force_login`):
  - `test_member_with_roster_match_sees_membership`: a `Member` + an active `MembershipTerm` with a tier allowing 2 free admissions and one redemption this month → the page shows the email, tier name, `Active`, the covered-through date (`M j, Y`) and `1 / 2`.
  - `test_member_without_match_sees_join_prompt`: shows `No membership on file for this email. Join at the box office before any show.` and a link to `/membership/`.
  - `test_member_sidebar_has_no_staff_links`: inside `data-cy="sidebar-nav"` the only link label is `Home`; `fkc-logo-white.png`, `powered by` and `LeprinceOS` are present; `data-cy="logout-button"` is present.
  - `test_member_gets_403_on_staff_pages`: GET `dashboard:members` → 403; the same with `HTTP_HX_REQUEST="true"` → 403.
  - `test_staff_home_unchanged`: staff GET `dashboard:home` uses `dashboard/home.html` and has `display_name` in context.
  - `test_anonymous_redirected_to_login`.

- [ ] **Step 2: Run** `python manage.py test dashboard.tests.test_member_home` — expect failures.

- [ ] **Step 3: Implement** the view, dispatch and template. `member_home.html` extends `dashboard/base_dashboard.html`, with page title `Your membership`. In `_sidebar.html`, wrap every nav link after Home in `{% if request.user.is_staff %}…{% endif %}`.

- [ ] **Step 4: Run** `python manage.py test dashboard.tests.test_member_home dashboard.tests.test_chrome dashboard.tests.test_home` — expect OK.

- [ ] **Step 5: Commit** `feat(dashboard): member home for signed-in members`.

### Task 5: Public links and visual check

**Files:**
- Modify: `web/constants.py` (`footer_navigation`, alphabetical position for `Member sign in`), `web/templates/web/membership.html` (line under `membership-tiers__note`)
- Test: `web/tests/test_membership_wording.py`, and whichever existing footer-order test pins `footer_navigation` (search `footer_navigation` in `web/tests`)

**Interfaces:** none new.

- [ ] **Step 1: Write failing tests**: the membership page's tiers section contains `Already a member? Sign in to see your membership.` linking to `/login`; the footer contains a `/login` link labelled `Member sign in` with note `See your membership`; the footer labels stay alphabetical (extend the existing order test if there is one).

- [ ] **Step 2: Run** `python manage.py test web` — expect failures.

- [ ] **Step 3: Implement** the constant entry and template line.

- [ ] **Step 4: Run** `python manage.py test web` — expect OK.

- [ ] **Step 5: Visual check.** Run the dev server and take headless Firefox screenshots (fresh `--profile`) of `/login` at 1280 px and 375 px. Then sign in as a member through the link (send mail to the console or locmem backend; read the link from the outbox in a shell) and screenshot `/dashboard/` at both widths. Fix anything cramped.

- [ ] **Step 6: Full suite and lint.** `python manage.py test` → OK. `flake8` on changed files shows no findings on changed lines. `python manage.py makemigrations --check --dry-run` → `No changes detected`.

- [ ] **Step 7: Commit** `feat(web): member sign-in links in the footer and membership page`.
