# Mailing-list signup Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A confirmed (double opt-in) mailing-list signup under the home-page showtimes and on every `/movies/<slug>` page, with the vote thanks-screen ask moved onto the same confirmation.

**Architecture:** `audience.Subscriber` gains a `PENDING` status and two timestamps; the manager decides whether a confirmation email is due. A new focused module, `web/list_signup.py`, owns the signed confirm token, the email, and the two public views; the existing vote view calls into it. One template partial renders the form in four placements.

**Tech Stack:** Django 5.2, htmx, Django `signing` and `EmailMessage`, `manage.py test`, flake8/black, `npm run build` for the CSS bundle.

**Spec:** `docs/superpowers/specs/2026-10-11-mailing-list-signup-design.md`

## Global Constraints

- Tests: `.venv/bin/python manage.py test <label> -v 2`. Full suite: `.venv/bin/python manage.py test --parallel 4`. Lint: `.venv/bin/flake8` and `.venv/bin/black --check .` (line length 88).
- Branch `feat/mailing-list-signup`. Commits end with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.
- Confirm token salt `"list-confirm"`, valid 7 days. Resend limit: one confirmation per address per hour.
- Sources: `home_showtimes`, `home_empty`, `movie_page`, anything else → `site`; vote stays `poll_vote`.
- Exact copy (do not reword):
  - Lead: `<strong>This weekend at the Cinema</strong>: get the weekend's showtimes by email every Thursday.`
  - Empty-state lead: `Get an email the moment new runs are booked.`
  - Button: `Sign me up`
  - Done: `Almost there: check your inbox for a link to confirm.`
  - Error: `That doesn't look like an email address.`
  - Email subject: `Confirm your Fort Kent Cinema emails`
  - Confirmed: `You're on the list. The first Thursday email is on its way soon.`
  - Already: `You're already on the list.`
  - Expired: `That link has expired`
- The vote ballot and vote pages must still never say "newsletter" or "weekly" (existing tests in `web/tests/test_vote_contact.py`).
- **CSS deviation from the spec:** the site has one bundle. Create `static/css/ListSignup.css` and `@import` it in the components group of `frontend/styles/main.css`, then `npm run build`. No per-page `<link>`.

## Review Focus

1. **An old confirmation link clicked after the person unsubscribed** must not re-add them: the token carries its issue time, and a token issued before `unsubscribed_at` gets the expired page. (Spec gap: the spec's 7-day token alone would allow it.) Test in Task 3.
2. **Double-clicking Confirm** (two POSTs) must leave one `ACTIVE` row and exactly one new `SubscriptionChange`, and the second response says "already on the list". Test in Task 3.
3. **An overlong or malformed address** (e.g. 300 characters, `a@b`, `x@example.com\nBcc: y@example.com`) re-renders the error, creates no row, sends no email. Test in Task 2.
4. **Resubmitting with different case/spaces** (`" Fan@Example.com "` after `fan@example.com`) hits the same row and the hourly limit. Test in Task 1.
5. **The confirm link is absolute `https://` behind the proxy**: built with `request.build_absolute_uri` (settings already trust `X-Forwarded-Proto`/host); the test asserts the link in the email starts with `http://testserver/subscribe/confirm/` and round-trips. Test in Task 2.

---

### Task 1: Pending subscribers

**Files:**
- Modify: `audience/models/subscriber.py`
- Create: `audience/migrations/0015_subscriber_pending.py` (schema + data migration)
- Modify: `dashboard/static/dashboard/css/design-system.css` (`.status-pending` joins `.status-expiring`'s warning colours)
- Test: `audience/tests/test_signup.py`, `dashboard/tests/test_subscribers.py`

**Interfaces:**
- Produces:
  - `SubscriberStatus.PENDING = "PENDING", "Pending confirmation"`
  - `Subscriber.confirmed_at: DateTimeField(null=True, blank=True)`, `Subscriber.confirmation_sent_at: DateTimeField(null=True, blank=True)`
  - `Subscriber.CONFIRMATION_RESEND_AFTER: ClassVar[timedelta] = timedelta(hours=1)`
  - `SubscriberManager.request_signup(email: str, source: str, ip: str | None = None) -> Subscriber | None`, raising `ValueError` on blank/too long like `record()`
  - `Subscriber.confirm() -> None`

- [ ] **Step 1: Write the failing tests** in `audience/tests/test_signup.py`

```python
class RequestSignupTests(TestCase):
    def test_new_address_is_pending_and_due_an_email(self):
        sub = Subscriber.objects.request_signup(" Fan@Example.com ", "movie_page", "198.51.100.4")
        self.assertEqual((sub.email, sub.status, sub.source, sub.consent_ip),
                         ("fan@example.com", SubscriberStatus.PENDING, "movie_page", "198.51.100.4"))
        self.assertIsNone(sub.confirmed_at)
        self.assertEqual(sub.changes.get().status, SubscriberStatus.PENDING)

    def test_pending_is_due_again_only_after_an_hour(self):
        sub = Subscriber.objects.request_signup("fan@example.com", "movie_page")
        sub.confirmation_sent_at = timezone.now() - timedelta(minutes=59)
        sub.save(update_fields=["confirmation_sent_at"])
        self.assertIsNone(Subscriber.objects.request_signup("FAN@example.com ", "home_showtimes"))
        Subscriber.objects.filter(pk=sub.pk).update(confirmation_sent_at=timezone.now() - timedelta(minutes=61))
        again = Subscriber.objects.request_signup("fan@example.com", "home_showtimes")
        self.assertEqual(again.pk, sub.pk)
        self.assertEqual(again.source, "movie_page")  # not overwritten

    def test_pending_never_sent_is_due(self): ...  # confirmation_sent_at None → returns row

    def test_active_address_is_never_due(self):
        Subscriber.objects.record("fan@example.com", source="poll_vote")
        self.assertIsNone(Subscriber.objects.request_signup("fan@example.com", "movie_page"))

    def test_opted_out_address_is_due_but_stays_opted_out(self):
        sub, _ = Subscriber.objects.record("fan@example.com", source="poll_vote")
        sub.unsubscribe()
        due = Subscriber.objects.request_signup("fan@example.com", "movie_page")
        self.assertEqual(due.status, SubscriberStatus.UNSUBSCRIBED)
        # and the hourly limit applies to it too

    def test_blank_and_overlong_raise(self): ...  # "" and "a"*250 + "@x.com" → ValueError

class ConfirmTests(TestCase):
    def test_pending_becomes_active_with_a_logged_change(self):  # confirmed_at set; changes statuses [ACTIVE, PENDING]; ACTIVE change .at == confirmed_at
    def test_opted_out_becomes_active_and_keeps_its_history(self):  # changes [ACTIVE, UNSUBSCRIBED, ACTIVE]; unsubscribed_at is None
    def test_confirming_an_active_row_changes_nothing(self):  # confirmed_at unchanged, change count unchanged
    def test_pending_is_not_active(self):  # Subscriber.objects.active() excludes PENDING
```

Add to `dashboard/tests/test_subscribers.py`: `test_pending_shows_its_label_and_is_not_counted_or_exported` — one active, one pending; the page contains `Pending confirmation` and `status-pending`; the export body contains the active address and not the pending one.

- [ ] **Step 2: Run them and see them fail**

Run: `.venv/bin/python manage.py test audience.tests.test_signup dashboard.tests.test_subscribers -v 2`
Expected: FAIL / ERROR (`request_signup` and `PENDING` do not exist).

- [ ] **Step 3: Implement**

- Add the status choice, the two fields and the class var.
- `save()`: unchanged rule (only `UNSUBSCRIBED` keeps `unsubscribed_at`), so `PENDING` clears it.
- `_log_change()`: when the new status is `ACTIVE` and `confirmed_at` is set, use `confirmed_at` as `at`; otherwise the existing rules.
- `request_signup`: normalise and validate as `record()` does (extract a private `_normalise(email) -> str` both call); `get_or_create(email=…, defaults={"source": source, "consent_ip": ip, "status": PENDING})`. Created → return it. `ACTIVE` → `None`. Otherwise return the row unless `confirmation_sent_at` is within `CONFIRMATION_RESEND_AFTER` of now.
- `confirm()`: no-op if `ACTIVE`; else set `status = ACTIVE`, `confirmed_at = now`, `save(update_fields=["status", "confirmed_at"])`.
- `record()` (used by admin/tests) creates `ACTIVE` rows: set `confirmed_at` to now in its `defaults`.
- Migration `0015`: `AlterField` status choices, `AddField` ×2, then `RunPython` setting `confirmed_at = consent_at` on every existing row (reverse: no-op). Generate the schema part with `makemigrations audience --name subscriber_pending` and add the `RunPython` by hand.
- Add a migration test to `audience/tests/test_signup.py` following the pattern in `audience/tests/test_membership_term_migration.py`: a row created at `0014` has `confirmed_at == consent_at` after `0015`.
- CSS: add `.status-pending` to the `.status-expiring` rule.

- [ ] **Step 4: Run the tests and see them pass**

Run: `.venv/bin/python manage.py test audience dashboard.tests.test_subscribers -v 2`
Expected: PASS (all of `audience`, so `record()`/admin tests still hold).

- [ ] **Step 5: Commit**

```bash
git add audience dashboard
git commit -m "feat(audience): pending subscribers who confirm before joining the list"
```

---

### Task 2: The signup form and confirmation email

**Files:**
- Create: `web/list_signup.py` (token helpers, `send_confirmation`, `start_signup`, `ListSignupView`)
- Create: `templates/partials/list_signup.html`, `web/templates/web/list_signup.html`
- Modify: `web/urls.py` (`path("subscribe", ListSignupView.as_view(), name="list_signup")`)
- Test: `web/tests/test_list_signup.py`

**Interfaces:**
- Consumes: `Subscriber.objects.request_signup`, `Subscriber.confirmation_sent_at` (Task 1); `cinema.voting.client_ip(request) -> str | None`.
- Produces (in `web/list_signup.py`):
  - `SOURCES: frozenset[str] = {"home_showtimes", "home_empty", "movie_page"}`; `source_for(location: str) -> str` (unknown → `"site"`)
  - `confirm_token(subscriber: Subscriber) -> str` — `signing.dumps({"pk": pk, "at": int(time.time())}, salt="list-confirm")`
  - `load_confirm_token(token: str) -> tuple[Subscriber, datetime] | None` — `None` on bad/expired (7 days) token or deleted row; the datetime is the issue time (UTC-aware)
  - `start_signup(request, email: str, source: str) -> None` — `request_signup`, then if a row came back, `send_confirmation`
  - `send_confirmation(request, subscriber: Subscriber) -> bool` — sends; on success saves `confirmation_sent_at = now`; on any exception logs with `logger.exception` and returns `False` without saving
  - Partial context: `list_signup_location` (str), `list_signup_done` (bool), `list_signup_error` (str), `list_signup_email` (str), optional `list_signup_lead` (str; overrides the default lead)

- [ ] **Step 1: Write the failing tests** in `web/tests/test_list_signup.py`

```python
def post(client, htmx=True, **data):
    data = {"email": "fan@example.com", "location": "movie_page", "website": "", **data}
    extra = {"HTTP_HX_REQUEST": "true"} if htmx else {}
    return client.post(reverse("list_signup"), data, **extra)

DONE = "Almost there: check your inbox for a link to confirm."

class ListSignupTests(TestCase):
    def test_new_address_gets_one_email_with_a_working_link(self):
        r = post(self.client)
        self.assertContains(r, DONE)
        self.assertEqual(len(mail.outbox), 1)
        msg = mail.outbox[0]
        self.assertEqual(msg.subject, "Confirm your Fort Kent Cinema emails")
        self.assertEqual(msg.to, ["fan@example.com"])
        self.assertIn("every Thursday", msg.body)
        self.assertIn("Didn't ask for this?", msg.body)
        link = re.search(r"http://testserver(/subscribe/confirm/\S+)", msg.body).group(1)
        sub, _ = load_confirm_token(link.rsplit("/", 1)[1])
        self.assertEqual(sub.email, "fan@example.com")
        self.assertIsNotNone(Subscriber.objects.get().confirmation_sent_at)

    def test_active_address_gets_the_same_reply_and_no_email(self)
    def test_second_submit_within_the_hour_sends_nothing(self)
    def test_honeypot_gets_the_same_reply_and_nothing_happens(self):  # website="http://spam" → DONE, no row, no mail
    def test_bad_addresses_are_refused(self):
        for bad in ("", "a@b", "x" * 300 + "@example.com", "x@example.com\nBcc: y@example.com"):
            r = post(self.client, email=bad)
            self.assertContains(r, "That doesn't look like an email address.")
        self.assertFalse(Subscriber.objects.exists()); self.assertEqual(mail.outbox, [])
    def test_bad_address_keeps_what_was_typed(self):  # value="a@b" in the form
    def test_location_becomes_the_source(self):  # home_empty → source "home_empty"; "evil" → "site"
    def test_plain_post_renders_a_page(self):  # htmx=False → template web/list_signup.html, DONE, noindex
    def test_smtp_failure_still_replies_and_can_retry(self):
        with mock.patch("web.list_signup.EmailMessage.send", side_effect=OSError):
            self.assertContains(post(self.client), DONE)
        self.assertIsNone(Subscriber.objects.get().confirmation_sent_at)
        post(self.client); self.assertEqual(len(mail.outbox), 1)
    def test_get_is_not_allowed(self):  # 405
```

- [ ] **Step 2: Run them and see them fail**

Run: `.venv/bin/python manage.py test web.tests.test_list_signup -v 2`
Expected: ERROR (`web.list_signup` missing).

- [ ] **Step 3: Implement**

- Validation: a small `forms.Form` with `email = forms.EmailField(max_length=Subscriber.EMAIL_MAX_LENGTH)` and `website = forms.CharField(required=False)`. Honeypot filled → done reply, nothing else.
- `ListSignupView.post`: htmx → render `partials/list_signup.html`; plain → `web/list_signup.html` (extends `base.html`, `{% block robots %}noindex, nofollow{% endblock %}`, includes the partial, then a link back to `request.headers["Referer"]` if it is same-host per `url_has_allowed_host_and_scheme`, else home).
- Email body (plain text, `EmailMessage(subject, body, to=[email]).send()`; `DEFAULT_FROM_EMAIL` applies):

```
Click below to confirm you'd like the weekend's showtimes from Fort Kent Cinema by email every Thursday. The first one is on its way soon.

{request.build_absolute_uri(reverse("list_confirm", args=[token]))}

Didn't ask for this? Ignore this email and you won't hear from us.

Fort Kent Cinema · {SITE_CONFIG cinema street} · {SITE_CONFIG cinema phone}
```

  `list_confirm` does not exist until Task 3: add its URL now pointing at a placeholder `ListConfirmView` stub that returns 404, and Task 3 replaces it. (Keeps this task's link test real.)
- Partial `templates/partials/list_signup.html`: a `<form class="list-signup" method="post" action="{% url 'list_signup' %}" hx-post="…" hx-target="this" hx-swap="outerHTML">` with CSRF, hidden `location`, the honeypot (`<div class="list-signup__hp" aria-hidden="true"><label>Website <input name="website" tabindex="-1" autocomplete="off"></label></div>`), the lead paragraph (`list_signup_lead` or the default lead), a visually-hidden `<label for>` "Email address", `<input type="email" name="email" autocomplete="email" required>` with the kept value, the button with `data-track="list_signup" data-track-location="{{ list_signup_location }}"`, and the error in a `role="alert"` paragraph. Done state: `<p class="list-signup list-signup--done" role="status">` with the done copy. A header comment explains it (house style: say why).

- [ ] **Step 4: Run the tests and see them pass**

Run: `.venv/bin/python manage.py test web.tests.test_list_signup -v 2`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add web templates
git commit -m "feat(web): mailing-list signup form that emails a confirmation link"
```

---

### Task 3: The confirm page

**Files:**
- Modify: `web/list_signup.py` (real `ListConfirmView`)
- Create: `web/templates/web/list_confirm.html`
- Test: `web/tests/test_list_signup.py` (new class `ListConfirmTests`)

**Interfaces:**
- Consumes: `confirm_token`, `load_confirm_token` (Task 2); `Subscriber.confirm()` (Task 1).
- Produces: `ListConfirmView` at `path("subscribe/confirm/<str:token>", …, name="list_confirm")`. Template context `state` ∈ `{"ask", "confirmed", "already", "expired"}`, plus `subscriber` for `ask`.

- [ ] **Step 1: Write the failing tests**

```python
class ListConfirmTests(TestCase):
    def setUp(self):
        self.sub = Subscriber.objects.request_signup("fan@example.com", "movie_page")
        self.url = reverse("list_confirm", args=[confirm_token(self.sub)])

    def test_get_asks_and_changes_nothing(self):
        r = self.client.get(self.url)
        self.assertContains(r, "fan@example.com"); self.assertContains(r, 'method="post"')
        self.assertContains(r, "noindex")
        self.sub.refresh_from_db(); self.assertEqual(self.sub.status, SubscriberStatus.PENDING)

    def test_post_confirms(self):
        self.assertContains(self.client.post(self.url),
                            "You're on the list. The first Thursday email is on its way soon.")
        self.sub.refresh_from_db(); self.assertEqual(self.sub.status, SubscriberStatus.ACTIVE)

    def test_double_post_is_harmless(self):
        self.client.post(self.url)
        r = self.client.post(self.url)
        self.assertContains(r, "You're already on the list.")
        self.assertEqual(self.sub.changes.filter(status=SubscriberStatus.ACTIVE).count(), 1)

    def test_former_opt_out_can_rejoin(self):  # record+unsubscribe, request_signup, then token issued AFTER unsubscribe → POST → ACTIVE

    def test_link_from_before_an_unsubscribe_is_expired(self):
        self.client.post(self.url)                      # joined
        self.sub.refresh_from_db(); self.sub.unsubscribe()
        r = self.client.post(self.url)                  # same old link
        self.assertContains(r, "That link has expired")
        self.sub.refresh_from_db(); self.assertEqual(self.sub.status, SubscriberStatus.UNSUBSCRIBED)

    def test_bad_expired_and_deleted_give_a_friendly_page(self):
        # "junk", a token signed with salt "other", a token older than 7 days
        # (mock time.time in web.list_signup / signing), and a deleted row:
        # each GET and POST → 200, "That link has expired", and a form posting to list_signup with location "site"
```

The "issued before" test needs the unsubscribe to land strictly after the token's whole-second `at`: freeze the token time with `mock.patch("web.list_signup.time.time", return_value=…)` an hour in the past.

- [ ] **Step 2: Run them and see them fail**

Run: `.venv/bin/python manage.py test web.tests.test_list_signup.ListConfirmTests -v 2`
Expected: FAIL (stub returns 404).

- [ ] **Step 3: Implement `ListConfirmView` (`get`, `post`)**

Shared lookup: `load_confirm_token`; `None` → `expired`. If `subscriber.unsubscribed_at` is set and later than the token's issue time → `expired`. `ACTIVE` → `already`. Otherwise GET → `ask`, POST → `subscriber.confirm()` then `confirmed`. Always status 200. The template extends `base.html`, `noindex, nofollow`, and for `expired` includes `partials/list_signup.html` with `list_signup_location="site"`.

- [ ] **Step 4: Run the tests and see them pass**

Run: `.venv/bin/python manage.py test web.tests.test_list_signup -v 2`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add web
git commit -m "feat(web): confirm page that adds a pending address to the list"
```

---

### Task 4: Vote ask goes through confirmation

**Files:**
- Modify: `web/views.py` (`VoteSubscribeView.post`, ~line 741)
- Modify: `templates/partials/vote_subscribe.html` (done copy and header comment)
- Test: `web/tests/test_vote_contact.py`

**Interfaces:**
- Consumes: `start_signup(request, email, source)` (Task 2).

- [ ] **Step 1: Update the tests first**

In `VoteSubscribe…` tests of `web/tests/test_vote_contact.py`:
- `test_saying_yes_joins_the_list_with_the_voting_address` → rename `test_saying_yes_emails_a_confirmation_to_the_voting_address`: status `PENDING`, `consent_ip` and `source` as before, `len(mail.outbox) == 1` addressed to `fan@example.com`, response contains `"Almost there: check your inbox for a link to confirm."` and not `"You're on the list"`, still contains `"your vote for"`.
- `test_saying_yes_twice_is_not_an_error`: also `len(mail.outbox) == 1` (hourly limit).
- `test_plain_post_renders_the_whole_page`: expect the new done copy.
- New `test_ask_is_not_offered_to_a_pending_address`: `request_signup("fan@example.com", "movie_page")` first → no "Yes, add me".
- Keep `test_copy_does_not_promise_a_newsletter` passing (the email may say "Thursday"; the page must not say "weekly"/"newsletter").

- [ ] **Step 2: Run them and see them fail**

Run: `.venv/bin/python manage.py test web.tests.test_vote_contact -v 2`
Expected: the changed tests FAIL.

- [ ] **Step 3: Implement**

Replace the `Subscriber.objects.record(...)` call with `start_signup(request, vote.email, source=self.SOURCE)`; update the docstring. In the partial, done copy becomes the shared done line; the header comment drops "nothing in this project sends mail yet" and says the ask makes no newsletter promise of its own and the confirmation email does.

- [ ] **Step 4: Run the vote tests and see them pass**

Run: `.venv/bin/python manage.py test web.tests.test_vote_contact web.tests.test_vote_integration web.tests.test_vote_carry -v 2`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add web templates
git commit -m "feat(vote): the thanks-screen list ask now confirms by email"
```

---

### Task 5: Placements and styles

**Files:**
- Modify: `templates/partials/now_showing.html`, `web/templates/web/movie_detail.html`
- Create: `static/css/ListSignup.css`; Modify: `frontend/styles/main.css`; rebuild `static/css/bundle.css`
- Test: `web/tests/test_list_signup_placement.py`

**Interfaces:**
- Consumes: `partials/list_signup.html` and its context names (Task 2).

- [ ] **Step 1: Write the failing tests** (reuse `movie()` from `web/tests/test_home_sections.py` and `MoviePageFixture` from `web/tests/test_movie_pages.py`, with the same `mock.patch` pair as `web/tests/test_ticket_info.py`)

```python
def signup_locations(html):
    return re.findall(r'name="location" value="([^"]+)"', html)

class HomePlacementTests(TestCase):
    # get_now_showing → [movie()]
    def test_under_the_showtimes(self):
        html = home_html
        self.assertEqual(signup_locations(html), ["home_showtimes"])
        self.assertLess(html.index('class="schedule-list"'), html.index('class="list-signup"'))
        self.assertIn("every Thursday", html)
    # get_now_showing → []
    def test_in_the_empty_state_before_the_links(self):
        self.assertEqual(signup_locations(html), ["home_empty"])
        self.assertIn("Get an email the moment new runs are booked.", html)
        self.assertLess(html.index('class="list-signup"'), html.index('class="no-showtimes__links"'))

class MoviePagePlacementTests(MoviePageFixture):
    def test_showing_film_after_the_prices(self):  # ["movie_page"], index(ticket-info) < index(list-signup)
    def test_archived_film_after_the_schedule_note(self):  # ["movie_page"], after "It isn't currently on our schedule."
```

- [ ] **Step 2: Run them and see them fail**

Run: `.venv/bin/python manage.py test web.tests.test_list_signup_placement -v 2`
Expected: FAIL (no form on the pages).

- [ ] **Step 3: Implement**

- Includes, as `{% include "partials/list_signup.html" with list_signup_location="…" %}` (and `list_signup_lead="Get an email the moment new runs are booked."` in the empty state, placed after `no-showtimes__body`, before the links list).
- `ListSignup.css`: one quiet row, lighter than `.ticket-info` (smaller/muted lead, outlined field, the site's existing button style); field and button stack full-width below 600px; `.list-signup__hp` positioned off-screen (not `display:none`); a `.visually-hidden` label if the site lacks that utility. Use `variables.css` custom properties only.
- `@import '../../static/css/ListSignup.css';` in group 4 of `frontend/styles/main.css`; run `npm run build`; commit the rebuilt bundle as the repo does.
- Check it renders at 375px and desktop on the home page and a film page (use the `run` skill or a browser screenshot).

- [ ] **Step 4: Run the full suite and lint**

Run: `.venv/bin/python manage.py test --parallel 4 && .venv/bin/flake8 && .venv/bin/black --check .`
Expected: all pass (existing count plus the new tests), no lint output.

- [ ] **Step 5: Commit**

```bash
git add templates web static frontend
git commit -m "feat(web): mailing-list signup under the showtimes and on film pages"
```
