# Thursday Email Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Every Thursday at 10 AM Eastern, each active mailing-list subscriber gets one HTML+text email with the weekend's showtimes and ticket links, can unsubscribe in one click, and the owner can see on the dashboard what went out.

**Architecture:** A new `newsletter` app holds two models (`Issue` per week, `Delivery` per recipient), a content builder that reuses the home page's services, two email templates, a resumable `send_weekly_email` command, and the public unsubscribe view. The dashboard gets a read-only Thursday Email page and one smart alert. The ticket-state helper moves out of `web/views.py` into a service so the chips and the email share it.

**Tech Stack:** Django 5.2, `EmailMultiAlternatives` over the configured SMTP backend (locmem in tests), `python manage.py test`, cron via the ansible `django_app` role (separate repo at `../ansible`).

**Spec:** `docs/superpowers/specs/2026-10-30-thursday-email-design.md`

## Global Constraints

- Branch `feat/thursday-email`. The owner commits on request: stop at each task's commit step and report unless the owner has said per-task commits are fine. Never merge or push unprompted.
- Run `.venv/bin/python manage.py test <app>` for the task's app and the full suite (`.venv/bin/python manage.py test --parallel`; record the baseline count from a fresh run on main first) before any commit.
- Lint gate: no new flake8 findings on added or changed lines (`.flake8`: max line 88). The repo baseline is dirty; do not fix lines the branch does not touch.
- Every `now`-dependent entry point takes `now: datetime | None = None` and defaults to `timezone.now()`. Tests pass `now` explicitly. No time-freezing library.
- Eastern time is `cinema.dates.CINEMA_TZ`. "Local date" means `dt.astimezone(CINEMA_TZ).date()`, the same rule as `web.services.cinema_data._local_date`.
- Window: local dates `today` through `today + 3 days`, showtimes with `starts_at > now`.
- Subject: `"This weekend at the Cinema: A, B"` for one or two titles, `"This weekend at the Cinema: A, B and more"` for three or more. Django adds `EMAIL_SUBJECT_PREFIX` itself only for `mail_admins`; set the subject exactly as given, no prefix.
- Unsubscribe placeholder in stored bodies is the literal string `{unsubscribe_url}`.
- Public unsubscribe route: `/unsubscribe/<uuid:token>`, URL name `list_unsubscribe`, `noindex, nofollow`, not in the sitemap.
- Dashboard permission: Django's default `newsletter.view_issue`. Add it to `SPEC_PERMISSIONS` in `dashboard/tests/helpers.py` under a `# newsletter` comment.
- Absolute URLs come from `boxoffice.site.base_url()`; tests use `override_settings(TICKETS_BASE_URL="https://www.fortkentcinema.com")`.
- Copy: unsubscribe GET page says "Unsubscribe **{masked email}** from the Thursday showtimes email?" with one button "Unsubscribe". Done page says "You're off the list." with a link "Changed your mind? Rejoin" to `/#coming-soon`.
- Email masking: first character of the local part, then `•••`, then `@domain`: `brandon@example.com` → `b•••@example.com`.

## Review Focus

1. A showtime at 10:15 AM on the Thursday of the send: it is after `now` (10:00) and must appear; one at 9:30 AM must not. Pinned in Task 3 (`test_thursday_morning_edge`).
2. A subscriber confirms between the 10:00 run and the 10:30 resume: the resume creates a Delivery for them and sends the already-rendered body, so they get the same email as everyone else. Pinned in Task 6 (`test_resume_picks_up_new_subscriber`).
3. A film whose only remaining showtime is sold out online: it must still be listed, with "Sold out online" and no link, not dropped. Pinned in Task 3 (`test_sold_out_film_is_listed`).
4. A mail client's one-click POST carries no CSRF token and no body fields: it must unsubscribe and return 200. Pinned in Task 5 (`test_one_click_post_without_csrf`).
5. An Issue stored as `sending` with every Delivery already `sent` (the process died after the last send, before closing): the resume must close it as `sent`, not send again. Pinned in Task 6 (`test_resume_closes_fully_sent_issue`).

---

### Task 1: App scaffold and models

**Files:**
- Create: `newsletter/__init__.py`, `newsletter/apps.py`, `newsletter/models.py`, `newsletter/migrations/0001_initial.py`, `newsletter/tests/__init__.py`
- Modify: `fortkentcinema/settings.py` (INSTALLED_APPS, after `"join.apps.JoinConfig",`), `dashboard/tests/helpers.py` (SPEC_PERMISSIONS)
- Test: `newsletter/tests/test_models.py`

**Interfaces:**
- Produces:
  - `class Issue(models.Model)` with `class Status(models.TextChoices)`: `SENDING = "sending"`, `SENT = "sent"`, `SKIPPED = "skipped"`, `FAILED = "failed"`; fields exactly as the spec's table (`week_of` DateField unique; `status` default SENDING; `subject` CharField(200) blank; `html`, `text` TextField blank; `started_at` DateTimeField default `timezone.now`; `finished_at` null; `recipient_count`, `sent_count`, `failed_count` PositiveIntegerField default 0; `skip_reason` CharField(200) blank). `Meta.ordering = ["-week_of"]`. `__str__` → `f"Thursday email {self.week_of:%Y-%m-%d}"`.
  - `Issue.is_done -> bool` property: status in (SENT, SKIPPED).
  - `Issue.preview_html -> str` property: `self.html.replace("{unsubscribe_url}", "#")`.
  - `class Delivery(models.Model)` with `class Status(models.TextChoices)`: `PENDING = "pending"`, `SENT = "sent"`, `FAILED = "failed"`; fields `issue` FK CASCADE related_name `deliveries`, `subscriber` FK `audience.Subscriber` CASCADE related_name `deliveries`, `status` default PENDING, `sent_at` null, `error` TextField blank. `Meta.constraints = [UniqueConstraint(fields=["issue", "subscriber"], name="newsletter_delivery_once_per_issue")]`, `ordering = ["pk"]`.

- [ ] **Step 1: Write the failing tests**

```python
# newsletter/tests/test_models.py
import datetime
from django.db import IntegrityError
from django.test import TestCase
from audience.models import Subscriber
from newsletter.models import Delivery, Issue


class IssueTests(TestCase):
    def test_defaults(self):
        issue = Issue.objects.create(week_of=datetime.date(2026, 11, 5))
        self.assertEqual(issue.status, Issue.Status.SENDING)
        self.assertFalse(issue.is_done)
        self.assertEqual((issue.recipient_count, issue.sent_count, issue.failed_count), (0, 0, 0))

    def test_is_done_for_sent_and_skipped(self):
        for status in (Issue.Status.SENT, Issue.Status.SKIPPED):
            self.assertTrue(Issue(week_of=datetime.date(2026, 11, 5), status=status).is_done)

    def test_week_of_unique(self):
        Issue.objects.create(week_of=datetime.date(2026, 11, 5))
        with self.assertRaises(IntegrityError):
            Issue.objects.create(week_of=datetime.date(2026, 11, 5))

    def test_preview_html_replaces_placeholder(self):
        issue = Issue(week_of=datetime.date(2026, 11, 5), html='<a href="{unsubscribe_url}">x</a>')
        self.assertEqual(issue.preview_html, '<a href="#">x</a>')


class DeliveryTests(TestCase):
    def test_one_delivery_per_subscriber_per_issue(self):
        issue = Issue.objects.create(week_of=datetime.date(2026, 11, 5))
        sub, _ = Subscriber.objects.record("a@example.com", source="site")
        Delivery.objects.create(issue=issue, subscriber=sub)
        with self.assertRaises(IntegrityError):
            Delivery.objects.create(issue=issue, subscriber=sub)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python manage.py test newsletter`
Expected: error importing `newsletter.models` (app does not exist yet).

- [ ] **Step 3: Create the app and models**

`newsletter/apps.py`: `class NewsletterConfig(AppConfig)` with `default_auto_field = "django.db.models.BigAutoField"`, `name = "newsletter"`, `verbose_name = "Thursday email"`. Add `"newsletter.apps.NewsletterConfig",` to INSTALLED_APPS after the `join` line. Write the models per the Interfaces block. Run `.venv/bin/python manage.py makemigrations newsletter` and check the file is named `0001_initial.py`.

- [ ] **Step 4: Register the permission in the dashboard helper**

In `dashboard/tests/helpers.py` `SPEC_PERMISSIONS`, after the `# blog` group, add:

```python
        # newsletter
        "newsletter.view_issue",
```

- [ ] **Step 5: Run the tests**

Run: `.venv/bin/python manage.py test newsletter dashboard.tests.test_permissions` (or whichever dashboard test module asserts the permission registry; find it with `grep -rl DASHBOARD_PERMISSIONS dashboard/tests`).
Expected: all PASS.

- [ ] **Step 6: Commit**

```bash
git add newsletter fortkentcinema/settings.py dashboard/tests/helpers.py
git commit -m "feat(newsletter): Issue and Delivery models for the Thursday email"
```

---

### Task 2: Move the ticket-state helper into a service

**Files:**
- Create: `web/services/ticket_state.py`
- Modify: `web/views.py` (remove `_add_ticket_state` at lines 174-200, import and call `add_ticket_state` in its two call sites), `web/tests/test_home_tickets.py` (if it imports `_add_ticket_state` by name; `grep -n _add_ticket_state web/tests`)
- Test: existing `web/tests/test_home_tickets.py` covers behaviour

**Interfaces:**
- Produces: `def add_ticket_state(times: list[dict], now: datetime.datetime | None = None) -> None` in `web/services/ticket_state.py`. Same body as today's `_add_ticket_state`, with `now` passed to `availability.for_showtimes` instead of `timezone.now()` inline. Mutates each dict: `ticket_url` (relative path or ""), `sold_out`, `in_person`.

- [ ] **Step 1: Confirm the existing tests cover the four states**

Run: `grep -n "sold_out\|in_person\|ticket_url" web/tests/test_home_tickets.py | wc -l`
Expected: a non-zero count. These tests are the safety net for the move.

- [ ] **Step 2: Create `web/services/ticket_state.py` and switch the callers**

Move the function verbatim, rename, add the `now` parameter. In `web/views.py` replace the definition with `from web.services.ticket_state import add_ticket_state` and update the two call sites (HomeView and CalendarMonthView). Keep the imports of `availability` and `square_enabled` in `web/views.py` only if something else still uses them; otherwise remove them.

- [ ] **Step 3: Run the web tests**

Run: `.venv/bin/python manage.py test web`
Expected: PASS, same count as before the move.

- [ ] **Step 4: Commit**

```bash
git add web/services/ticket_state.py web/views.py web/tests
git commit -m "refactor(web): ticket chip state lives in web.services.ticket_state"
```

---

### Task 3: Content builder and subject line

**Files:**
- Create: `newsletter/content.py`
- Test: `newsletter/tests/test_content.py`

**Interfaces:**
- Consumes: `web.services.cinema_data.get_hero_films(now)`, `get_coming_soon(now)`, `web.services.ticket_state.add_ticket_state(times, now)`, `boxoffice.site.base_url()`, `blog.models.BlogPost.objects.published()`, `web.constants.SITE_CONFIG`, `web.constants.TICKET_PRICES` (check the exact name with `grep -n "^TICKET_PRICES\|^ticket_prices" web/constants.py web/context_processors.py`).
- Produces:
  - `WINDOW_DAYS = 3`
  - `COMING_SOON_CAP = 3`
  - `POST_MAX_AGE_DAYS = 7`
  - `def window_for(now: datetime.datetime) -> tuple[datetime.date, datetime.date]`: local `today` and `today + WINDOW_DAYS`.
  - `def build_context(now: datetime.datetime | None = None) -> dict | None`. Returns `None` when no film has a remaining showtime in the window. Otherwise a dict with keys:
    - `films`: list of dicts `{"title", "poster", "rating", "runtime", "is_free_for_members", "days": [{"label": "Thursday, Nov 5", "times": [time dicts]}]}` where each time dict is the hero's entry plus `ticket_url` made absolute (`base_url() + path`, "" stays ""), `sold_out`, `in_person`. Days ordered by date, films in hero order.
    - `coming_soon`: up to `COMING_SOON_CAP` dicts `{"title", "poster", "opens": "Fri, Nov 14"}`; `coming_soon_url`: `base_url() + "/#coming-soon"`.
    - `post`: `{"title", "subtitle", "url"}` or `None`; `url` is `base_url() + post.get_absolute_url()`.
    - `site_url`: `base_url()`; `cinema`: `SITE_CONFIG["cinema"]`; `ticket_prices`: the constant; `unsubscribe_url`: the literal `"{unsubscribe_url}"`.
  - `def subject_for(films: list[dict]) -> str` per the Global Constraints rule.
  - `def day_label(d: datetime.date) -> str` → `"Thursday, Nov 5"` (`%A, %b %-d`).
  - `def opens_label(d: datetime.date) -> str` → `"Fri, Nov 14"`.

- [ ] **Step 1: Write the failing tests**

Use the helpers from `web/tests/test_cinema_data.py` (`make_screen`, `make_film`, `make_engagement`, `aware`) by importing them. Fix `now = aware(2026, 11, 5, 10, 0)` (a Thursday) in `setUp`, with an engagement running Nov 5 to Nov 11 on `self.screen`, and create showtimes with `Showtime.objects.create(engagement=..., screen=..., starts_at=aware(...))`.

```python
# newsletter/tests/test_content.py (assertions; one test method each)
# test_none_without_showtimes: no showtimes → build_context(now) is None
# test_window_edges: showtimes Wed Nov 4 23:59, Sun Nov 8 20:00, Mon Nov 9 19:00
#   → the film's days are exactly ["Sunday, Nov 8"]
# test_thursday_morning_edge: showtimes Thu Nov 5 9:30 and 10:15 with now = 10:00
#   → the Thursday day has exactly one time, "10:15 AM"
# test_cancelled_and_hidden_excluded: a cancelled showtime and a showtime on a show=False engagement are absent
# test_coming_soon_capped: four future engagements starting after the window → len(ctx["coming_soon"]) == 3, in start order
# test_post_recent_included_old_excluded: BlogPost published with post_date = Nov 1 → ctx["post"]["title"]; post_date = Oct 27 → ctx["post"] is None
# test_ticket_urls_absolute (override_settings TICKETS_BASE_URL): a purchasable showtime's ticket_url startswith "https://www.fortkentcinema.com/tickets/"
#   (set up a purchasable showtime the way web/tests/test_home_tickets.py does: see its SQUARE_ON settings and make_live_item in tickets/tests/factories.py)
# test_sold_out_film_is_listed: with the showtime's online allowance exhausted (see tickets.availability tests for how to sell it out), the film is still in ctx["films"], its time has sold_out True and ticket_url ""
# test_subject_lines: subject_for([{"title": "A"}]) == "This weekend at the Cinema: A";
#   two titles → "...: A, B"; three → "...: A, B and more"
```

Write each as a real method with `self.assertEqual` / `self.assertIsNone` / `self.assertTrue`.

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python manage.py test newsletter.tests.test_content`
Expected: FAIL with `ModuleNotFoundError: newsletter.content`.

- [ ] **Step 3: Implement `newsletter/content.py`**

Filter each hero film's `upcoming` rows to the window by their `key` (ISO date) and each time by its showtime's `starts_at > now`. The hero rows do not carry `starts_at`, so after `get_hero_films(now)` the filter by `now` is already applied (the service uses `starts_at__gte=now`); only the date window needs applying here. Call `add_ticket_state` once over every kept time dict, then prefix `ticket_url`.

- [ ] **Step 4: Run the tests**

Run: `.venv/bin/python manage.py test newsletter.tests.test_content`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add newsletter/content.py newsletter/tests/test_content.py
git commit -m "feat(newsletter): build the weekend email's content from the listing services"
```

---

### Task 4: Email templates and renderer

**Files:**
- Create: `newsletter/render.py`, `newsletter/templates/newsletter/email/issue.html`, `newsletter/templates/newsletter/email/issue.txt`
- Test: `newsletter/tests/test_render.py`

**Interfaces:**
- Consumes: `build_context` output shape from Task 3.
- Produces: `def render_issue(context: dict) -> tuple[str, str]` returning `(html, text)` via `render_to_string` of the two templates.

- [ ] **Step 1: Write the failing tests**

Build a context dict by hand (no database): two films, one with a Buy time (`ticket_url="https://www.fortkentcinema.com/tickets/7/"`), one sold out (`sold_out=True, ticket_url=""`), one in-person (`in_person=True`), one plain; two coming-soon entries; a post; `unsubscribe_url="{unsubscribe_url}"`.

```python
# test_html_has_every_buy_link_and_the_placeholder: html contains the ticket URL, "Sold out online", "In-person purchase only", "{unsubscribe_url}", both film titles, the post title, "Coming Soon"
# test_text_names_every_showtime_the_html_does: text contains "10:15 AM", the ticket URL on its own line (assertIn("\nhttps://www.fortkentcinema.com/tickets/7/\n", text)), and "{unsubscribe_url}"
# test_html_escapes_titles: a film title "Tom & Jerry" renders as "Tom &amp; Jerry" in html and "Tom & Jerry" in text
# test_no_post_section_without_post: context["post"] = None → "From the Booth" absent from both bodies
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python manage.py test newsletter.tests.test_render`
Expected: FAIL, module not found.

- [ ] **Step 3: Write the templates and `render_issue`**

`issue.html`: follow `tickets/templates/tickets/email/ticket.html` (doctype, inline styles, Arial stack). Wrap content in a centred table or div with `max-width: 600px`. Per film: `<img src="{{ film.poster }}" width="120" alt="{{ film.title }}">` only when `film.poster`, `<h2>` title, a muted line with rating and runtime when present, "Free for Members" when flagged, then per day a `<p>` with `<strong>{{ day.label }}</strong>` and the times: `<a href="{{ time.ticket_url }}">{{ time.time }} · Buy</a>` when `ticket_url`, else the time followed by `<span style="color:#666">Sold out online</span>` or `In-person purchase only`, else the bare time. Then `<h2>Coming Soon</h2>` with one line per entry ("{{ title }} · Opens {{ opens }}") linking to `coming_soon_url`, then `<h2>From the Booth</h2>` with the post link when `post`, then the footer: the price line copied from `templates/partials/ticket_info.html` wording, address, phone, and `<a href="{{ unsubscribe_url }}">Unsubscribe</a>`.

`issue.txt`: `{% autoescape off %}` like the other `.txt` emails. Same sections. Each Buy URL on its own line under its time.

- [ ] **Step 4: Run the tests**

Run: `.venv/bin/python manage.py test newsletter.tests.test_render`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add newsletter/render.py newsletter/templates
git commit -m "feat(newsletter): HTML and text templates for the Thursday email"
```

---

### Task 5: Public unsubscribe page

**Files:**
- Create: `newsletter/links.py`, `newsletter/views.py`, `newsletter/urls.py`, `newsletter/templates/newsletter/unsubscribe.html`
- Modify: `fortkentcinema/urls.py` (add `path("", include("newsletter.urls")),` before the `join` include)
- Test: `newsletter/tests/test_unsubscribe.py`

**Interfaces:**
- Produces:
  - `def unsubscribe_url(subscriber: Subscriber) -> str` in `newsletter/links.py`: `base_url() + reverse("list_unsubscribe", args=[subscriber.unsubscribe_token])`.
  - `def mask_email(email: str) -> str` in `newsletter/links.py` per the Global Constraints rule.
  - `class UnsubscribeView(View)` in `newsletter/views.py`, decorated `@method_decorator(csrf_exempt, name="dispatch")`. GET renders state `"ask"` with `masked` for a known active subscriber, else state `"done"`. POST calls `subscriber.unsubscribe()` when found, renders state `"done"`. Response header `X-Robots-Tag: noindex, nofollow` on every response.
  - `newsletter/urls.py`: `path("unsubscribe/<uuid:token>", UnsubscribeView.as_view(), name="list_unsubscribe")`. No `app_name`, so the name is global like `list_confirm`.

- [ ] **Step 1: Write the failing tests**

```python
# test_get_known_token_asks: record + confirm a subscriber; GET → 200, contains "b•••@example.com", a <form method="post">, and 'name="robots" content="noindex, nofollow"'
# test_post_unsubscribes: POST → 200, "You're off the list.", subscriber refreshed has status UNSUBSCRIBED and unsubscribed_at set, SubscriptionChange row count 1 (import from audience.models)
# test_unknown_token_get_and_post_show_done: uuid4() → both 200 with "You're off the list."
# test_one_click_post_without_csrf: Client(enforce_csrf_checks=True).post(url) → 200 and unsubscribed
# test_already_unsubscribed_post_is_noop: unsubscribe first, record unsubscribed_at, POST again → same unsubscribed_at, still one SubscriptionChange row
# test_done_page_links_to_rejoin: contains 'href="/#coming-soon"'
# test_mask_email: mask_email("brandon@example.com") == "b•••@example.com"; mask_email("a@b.co") == "a•••@b.co"
# test_unsubscribe_url_is_absolute (override_settings TICKETS_BASE_URL): startswith "https://www.fortkentcinema.com/unsubscribe/"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python manage.py test newsletter.tests.test_unsubscribe`
Expected: FAIL, module not found.

- [ ] **Step 3: Implement view, URL, template**

Template extends `base.html`, `{% block robots %}noindex, nofollow{% endblock %}`, same `thanks-page` / `thanks-container` / `thanks-cta` classes as `web/templates/web/list_confirm.html`. The `ask` state: the sentence from Global Constraints, a `<form method="post">{% csrf_token %}<button class="thanks-cta">Unsubscribe</button></form>`. The `done` state: `<p role="status">You're off the list.</p>` and `<a href="/#coming-soon">Changed your mind? Rejoin</a>`.

- [ ] **Step 4: Confirm the sitemap does not list it**

Run: `.venv/bin/python manage.py test web.tests.test_sitemaps` (find the module with `grep -rl sitemap web/tests`).
Expected: PASS. The static sitemap lists names explicitly, so nothing to change; this run proves it.

- [ ] **Step 5: Run the tests**

Run: `.venv/bin/python manage.py test newsletter.tests.test_unsubscribe`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add newsletter/links.py newsletter/views.py newsletter/urls.py newsletter/templates/newsletter/unsubscribe.html fortkentcinema/urls.py newsletter/tests/test_unsubscribe.py
git commit -m "feat(newsletter): one-click unsubscribe page"
```

---

### Task 6: Send pipeline and the `send_weekly_email` command

**Files:**
- Create: `newsletter/send.py`, `newsletter/management/__init__.py`, `newsletter/management/commands/__init__.py`, `newsletter/management/commands/send_weekly_email.py`
- Test: `newsletter/tests/test_send.py`, `newsletter/tests/test_command.py`

**Interfaces:**
- Consumes: `build_context`, `subject_for` (Task 3); `render_issue` (Task 4); `unsubscribe_url` (Task 5); `Issue`, `Delivery` (Task 1); `Subscriber.objects.active()`.
- Produces, in `newsletter/send.py`:
  - `SEND_HOUR = 10`
  - `class NotYet(Exception)` with a `reason: str` attribute (`"not Thursday"` or `"too early"`).
  - `def thursday_for(now: datetime.datetime) -> datetime.date`: raises `NotYet` unless the Eastern local datetime is a Thursday at or after `SEND_HOUR:00`; returns the local date.
  - `def send_issue(week_of: datetime.date, now: datetime.datetime | None = None, *, logger=log) -> Issue`: steps 1 to 6 of the spec. Returns the Issue in its final state. Raises nothing for recipient-level failures. Re-raises connection-level errors (`smtplib.SMTPException` other than `SMTPRecipientsRefused`/`SMTPDataError`, and `OSError`) after setting the Issue to `FAILED` when `sent_count == 0`, else leaving it `SENDING`.
  - `def render_for(issue: Issue) -> bool`: fills `subject/html/text` from `build_context(now)` when the Issue has none yet; returns False (and marks `SKIPPED`, `skip_reason="no showtimes"`, `finished_at`) when the context is None and the Issue has no deliveries.
  - `def message_for(issue: Issue, delivery: Delivery, connection) -> EmailMultiAlternatives`: substitutes the recipient's `unsubscribe_url` into both bodies, sets `to=[subscriber.email]`, `from_email=settings.DEFAULT_FROM_EMAIL`, `headers={"List-Unsubscribe": f"<{url}>", "List-Unsubscribe-Post": "List-Unsubscribe=One-Click"}`, attaches the HTML alternative.
  - Command `send_weekly_email` with `--week-of YYYY-MM-DD` and `--dry-run`. Without `--week-of`, `NotYet` logs its reason at INFO and exits 0. With `--week-of` not a Thursday → `CommandError`. `--dry-run` prints `Subject: ...` then the HTML to stdout, writes nothing, sends nothing. A connection-level error exits 1 (let `CommandError` carry the message).

- [ ] **Step 1: Write the failing tests for `send.py`**

Set up as in Task 3 (`now = aware(2026, 11, 5, 10, 0)`, one engagement with a Sunday showtime) plus three subscribers: two via `Subscriber.objects.record(...)` (active), one via `request_signup` (pending), one recorded then `.unsubscribe()`'d. Use `django.core.mail.outbox` (locmem backend is the test default).

```python
# test_thursday_for: aware(2026,11,5,10,0) → date(2026,11,5); aware(2026,11,5,9,59) raises NotYet(reason="too early"); aware(2026,11,6,10,0) raises NotYet(reason="not Thursday")
# test_sends_one_email_per_active_subscriber: send_issue(date(2026,11,5), now) → len(mail.outbox) == 2; recipients are the two active addresses; issue.status SENT; counts (2, 2, 0); every Delivery SENT with sent_at
# test_body_carries_recipients_own_token: outbox[0].alternatives[0][0] contains str(that subscriber.unsubscribe_token); the other does not
# test_headers: message.extra_headers["List-Unsubscribe"] == f"<{unsubscribe_url(sub)}>" and ["List-Unsubscribe-Post"] == "List-Unsubscribe=One-Click"
# test_second_run_is_noop: send twice → outbox still 2, one Issue row
# test_no_showtimes_skips: delete showtimes → issue.status SKIPPED, skip_reason "no showtimes", no Deliveries, outbox empty
# test_recipient_refusal_marks_failed_and_continues: patch the connection's send_messages (or EmailMultiAlternatives.send) to raise smtplib.SMTPRecipientsRefused for the first address → that Delivery FAILED with error text, the other SENT, issue SENT with failed_count 1
# test_connection_error_leaves_pending_and_resumes: first run raises OSError after the first send (patch to raise on the second call) → assertRaises(OSError); issue SENDING; one SENT, one PENDING; second run → outbox gains exactly one more, issue SENT
# test_connection_error_before_any_send_marks_failed: raise on the first send → issue FAILED, sent_count 0; a re-run completes it
# test_resume_picks_up_new_subscriber: after a run interrupted as above, record a new active subscriber, re-run → the new address gets a message whose subject equals the stored issue.subject
# test_resume_closes_fully_sent_issue: create Issue SENDING with html/text/subject set and every Delivery already SENT → send_issue → outbox empty, status SENT, counts right
# test_body_not_rerendered_on_resume: interrupt, add a showtime, resume → the late recipient's HTML equals the stored issue.html with their URL substituted (no new showtime)
```

- [ ] **Step 2: Write the failing tests for the command**

```python
# newsletter/tests/test_command.py, using django.core.management.call_command with StringIO stdout
# test_dry_run_prints_and_writes_nothing: call_command("send_weekly_email", "--dry-run", "--week-of", "2026-11-05") → stdout contains "Subject: This weekend at the Cinema" and "<!doctype html>"; Issue.objects.count() == 0; outbox empty
# test_non_thursday_week_of_is_an_error: "--week-of", "2026-11-06" → CommandError
# test_outside_window_exits_quietly: the command reads the clock once via `timezone.now()` imported as
#   `from django.utils import timezone`; patch `newsletter.management.commands.send_weekly_email.timezone.now`
#   to return aware(2026, 11, 6, 10, 0) → no Issue, no mail, and assertLogs("newsletter", "INFO") captures "not Thursday"
# test_sends_for_week_of: "--week-of", "2026-11-05" with the fixtures → 2 emails
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `.venv/bin/python manage.py test newsletter.tests.test_send newsletter.tests.test_command`
Expected: FAIL, modules not found.

- [ ] **Step 4: Implement `newsletter/send.py` and the command**

Open one connection with `mail.get_connection()` and pass it to each message. Catch `(smtplib.SMTPRecipientsRefused, smtplib.SMTPDataError)` per recipient; truncate `str(exc)` to 1000 chars into `delivery.error`. Any other `smtplib.SMTPException` or `OSError`: update counts, set `FAILED` if `sent_count == 0`, log at ERROR, re-raise. Close: recount from the Delivery rows, set `SENT`, `finished_at = now`; when `failed_count`, `log.error("Thursday email %s: %d of %d deliveries failed", week_of, failed, total)`.

- [ ] **Step 5: Run the tests**

Run: `.venv/bin/python manage.py test newsletter`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add newsletter/send.py newsletter/management newsletter/tests/test_send.py newsletter/tests/test_command.py
git commit -m "feat(newsletter): resumable Thursday send and the send_weekly_email command"
```

---

### Task 7: Dashboard page and preview

**Files:**
- Create: `dashboard/newsletter_views.py`, `dashboard/templates/dashboard/newsletter_issues.html`
- Modify: `dashboard/urls.py` (import `newsletter_views`; add two paths after the `subscribers_export` entry), `dashboard/templates/dashboard/_sidebar.html` (entry after Subscribers, before Voicemails, gated `{% if perms.newsletter.view_issue %}`)
- Test: `dashboard/tests/test_newsletter.py`

**Interfaces:**
- Consumes: `Issue` (Task 1), `StaffRequiredMixin` from `dashboard/mixins.py`.
- Produces:
  - `class IssueListView(StaffRequiredMixin, View)`, `permission_required = "newsletter.view_issue"`, GET renders `dashboard/newsletter_issues.html` with `issues` (all Issues, newest first, `prefetch_related("deliveries__subscriber")` for the failed expansions).
  - `class IssuePreviewView(StaffRequiredMixin, View)`, same permission, GET returns `HttpResponse(issue.preview_html, content_type="text/html")` with `response["Content-Security-Policy"] = "sandbox"`, 404 for an unknown pk.
  - URL names: `dashboard:newsletter_issues` at `thursday-email`, `dashboard:newsletter_issue_preview` at `thursday-email/<int:pk>/preview`.

- [ ] **Step 1: Write the failing tests**

```python
# test_requires_login: anonymous → 302
# test_requires_permission: make_staff(perms=permissions_except("newsletter.view_issue")) → 403 on both URLs
# test_lists_issues_with_status_and_counts: a SENT Issue (recipient 12, sent 11, failed 1) and a SKIPPED one → page contains "Nov 5, 2026", "Sent", "Skipped", "no showtimes", "12", "11", "1"
# test_failed_deliveries_expand: a FAILED Delivery for "x@example.com" with error "550 no such user" → both strings in the page inside a <details> element
# test_preview_serves_stored_html_sandboxed: Issue html '<p>hi</p><a href="{unsubscribe_url}">u</a>' → body == '<p>hi</p><a href="#">u</a>', header Content-Security-Policy == "sandbox", content type starts "text/html"
# test_preview_unknown_404
# test_sidebar_link: dashboard home contains reverse("dashboard:newsletter_issues")
# test_empty_state: no Issues → "empty-state" in page
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python manage.py test dashboard.tests.test_newsletter`
Expected: FAIL (NoReverseMatch).

- [ ] **Step 3: Implement views, URLs, template, sidebar entry**

Template extends `dashboard/base_dashboard.html`, title `Thursday Email · LeprinceOS`, same `page` / `page-header` / `tableWrapper` / `table` classes as `subscribers.html`. Columns: Week (`{{ issue.week_of|date:"M j, Y" }}`), Status (`<span class="status-pill status-{{ issue.status }}">{{ issue.get_status_display }}</span>`; reuse whatever pill class the subscribers page uses for "Pending confirmation"), Recipients, Sent, Failed, Preview (`<a href="{% url 'dashboard:newsletter_issue_preview' issue.pk %}" target="_blank">Preview</a>`, only when `issue.html`). A skipped row shows `skip_reason` in the Status cell. A row with `failed_count` adds a second `<tr>` with a `<details><summary>{{ issue.failed_count }} failed</summary>` listing `subscriber.email` and `error` per failed Delivery. Sidebar: copy the Subscribers block, change url name and label to "Thursday Email", keep the envelope icon.

- [ ] **Step 4: Run the tests**

Run: `.venv/bin/python manage.py test dashboard`
Expected: PASS (including the permission-registry test, since the view declares `newsletter.view_issue`).

- [ ] **Step 5: Commit**

```bash
git add dashboard/newsletter_views.py dashboard/urls.py dashboard/templates/dashboard/newsletter_issues.html dashboard/templates/dashboard/_sidebar.html dashboard/tests/test_newsletter.py
git commit -m "feat(dashboard): Thursday Email page with per-week status and preview"
```

---

### Task 8: Smart alert for a missed Thursday

**Files:**
- Modify: `dashboard/smart_alerts.py` (new keyword `thursday_email_missed: bool = False`), `dashboard/views.py` HomeView (compute and pass it)
- Create: `newsletter/alerts.py`
- Test: `newsletter/tests/test_alerts.py`, extend `dashboard/tests/test_smart_alerts.py` (find with `grep -rl build_smart_alerts dashboard/tests`)

**Interfaces:**
- Produces:
  - `def last_thursday(today: datetime.date) -> datetime.date | None` in `newsletter/alerts.py`: the Thursday of the current Monday-to-Sunday week (`today - timedelta(days=today.weekday() - 3)`) when `today.weekday() >= 4` (Friday, Saturday, Sunday), else `None`.
  - `def missed(today: datetime.date) -> bool`: `last_thursday(today)` is not None and no `Issue` with that `week_of` and status in (SENT, SKIPPED) exists.
  - In `build_smart_alerts`, when `thursday_email_missed`: append `{"id": "thursday-email-missed", "type": "warning", "perm": "newsletter.view_issue", "message": "Last Thursday's email did not go out", "url": reverse("dashboard:newsletter_issues")}`.

- [ ] **Step 1: Write the failing tests**

```python
# newsletter/tests/test_alerts.py
# test_last_thursday: Fri Nov 6 → Nov 5; Sun Nov 8 → Nov 5; Thu Nov 5 → None; Wed Nov 4 → None
# test_missed_true_without_issue: missed(date(2026,11,6)) is True
# test_missed_false_when_sent_or_skipped: Issue(week_of Nov 5, SENT) → False; SKIPPED → False; SENDING → True
# test_missed_false_midweek: missed(date(2026,11,4)) is False even with no Issue
# dashboard/tests/test_smart_alerts.py: build_smart_alerts([], 1, today, thursday_email_missed=True) contains an alert with id "thursday-email-missed" and perm "newsletter.view_issue"; False → absent
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python manage.py test newsletter.tests.test_alerts dashboard.tests.test_smart_alerts`
Expected: FAIL.

- [ ] **Step 3: Implement**

In HomeView pass `thursday_email_missed=(newsletter_alerts.missed(today) if user.has_perm("newsletter.view_issue") else False)` alongside the other counts.

- [ ] **Step 4: Run the tests**

Run: `.venv/bin/python manage.py test newsletter dashboard`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add newsletter/alerts.py newsletter/tests/test_alerts.py dashboard/smart_alerts.py dashboard/views.py dashboard/tests/test_smart_alerts.py
git commit -m "feat(dashboard): alert when last Thursday's email did not go out"
```

---

### Task 9: Deployment: cron, flag, deploy notes

**Files (separate repo, `../ansible`):**
- Modify: `roles/django_app/tasks/main.yml` (two cron tasks after the `delete_unverified_accounts` one; add `or (app.cron_weekly_email | default(false))` to the CRON_TZ task's `when:` list), `group_vars/webservers.yml` (`cron_weekly_email: true` after `cron_unverified_cleanup`), `deploy.md`
- Also check `cleanup_site.yml`'s `django_app_cron_job_names` list and add the two new job names.

**Interfaces:**
- Produces two crontab entries for `_run_user`, Thursday only (`weekday: "4"`), `hour: "10"` with `minute: "0"` and `minute: "30"`, names `{{ app.name }}_send_weekly_email` and `{{ app.name }}_send_weekly_email_resume`, job: `flock -n {{ _lock_dir }}/send_weekly_email.lock {{ _shared_venv }}/bin/python {{ _runtime_working_dir }}/manage.py send_weekly_email >> /var/log/{{ app.service_name }}/cron.log 2>&1`.

- [ ] **Step 1: Add the cron tasks and the flag**

Copy the `delete_unverified_accounts` task twice, change name, job, `hour`, `minute`, add `weekday: "4"`, `when: app.cron_weekly_email | default(false)`. Comment above them: the command itself refuses to send before 10 AM Eastern or on another weekday, so a crontab without CRON_TZ cannot send early.

- [ ] **Step 2: Syntax-check the playbook**

Run: `cd ../ansible && ansible-playbook site.yml --syntax-check`
Expected: `playbook: site.yml` with no errors.

- [ ] **Step 3: Write the deploy notes**

In `deploy.md`, a "Thursday email" section: run `manage.py migrate newsletter`; grant `newsletter | issue | Can view issue` to the owner's dashboard group in the admin; run `manage.py send_weekly_email --dry-run --week-of <next Thursday>` on the server and read the HTML; confirm the From address in the output of a test send to yourself (`--week-of` on a Thursday sends for real, so use `--dry-run` only); check `/var/log/<service>/cron.log` the first Thursday after 10:00.

- [ ] **Step 4: Report, do not commit**

The ansible repo is the owner's; stage nothing. Report the diff summary in the task report.

---

### Task 10: Full-suite verification and branch report

- [ ] **Step 1: Full test run**

Run: `.venv/bin/python manage.py test --parallel`
Expected: `OK`, count = baseline + the new tests. Record both numbers.

- [ ] **Step 2: Lint the changed lines**

Run: `git diff -U0 main...HEAD -- '*.py' | grep '^+++' ; .venv/bin/flake8 newsletter dashboard/newsletter_views.py dashboard/smart_alerts.py web/services/ticket_state.py`
Expected: no findings in new files; for modified files, no finding on an added or changed line.

- [ ] **Step 3: Dry run against the dev database**

Run: `.venv/bin/python manage.py send_weekly_email --dry-run --week-of <next Thursday>`
Expected: `Subject: This weekend at the Cinema: ...` and HTML, or `Skipped: no showtimes` if the dev DB has none in the window. Paste the HTML into a browser file and look at it once.

- [ ] **Step 4: Report**

Summarise: tests before/after, files added, the three owner steps from `deploy.md`, and stop for the owner's commit / merge instruction.
