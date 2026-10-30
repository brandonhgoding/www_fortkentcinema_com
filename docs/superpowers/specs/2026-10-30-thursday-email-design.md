# Thursday Email — Design

Date: 2026-10-30
Status: approved in conversation, awaiting implementation plan

## Purpose

The mailing-list signup (templates/partials/list_signup.html) promises "the
weekend's showtimes, in your inbox every Thursday" and "one email a week".
Subscribers confirm through the double opt-in and then hear nothing: no code
sends the email. This spec adds the email, the Thursday send, a public
unsubscribe page, a record of every send, and a dashboard view of it.

Success: a confirmed subscriber gets one email every Thursday at 10 AM
Eastern with that weekend's showtimes and ticket links, can leave in one
click, and the owner can see from the dashboard that it went out.

## Decisions (owner, 2026-10-30)

- **Automatic.** Cron sends with no human step. No send button.
- **Content.** Thursday-through-Sunday showtimes, up to three Coming Soon
  runs, and the newest blog post if published in the last seven days.
  No film-vote block.
- **Format.** HTML with a plain-text alternative, following the ticket
  email's inline-style pattern (tickets/templates/tickets/email/ticket.html).
- **Dark weekend.** No showtimes in the window means the week is recorded
  as skipped and nothing is sent.
- **Send time.** 10:00 AM Eastern on Thursday, resumed at 10:30.
- **Scale.** Under 300 subscribers in the first year. Proton SMTP from the
  web server, one message per recipient, no third-party sender.
- **Thursday's own showtimes** are in the email when they have not started
  by send time.

## Architecture

A new Django app, `newsletter`, beside `audience` (which owns Subscriber)
the way `join` sits beside the membership models. It contains the models,
the content builder, the send command, the unsubscribe view and the email
templates. The dashboard app gets a view and a sidebar entry for it.

Data flow on a Thursday:

```
cron 10:00 ET ──► manage.py send_weekly_email
                    │
                    ├─ Issue.for_week(thursday)       create or load
                    ├─ build_context(now)             web.services.cinema_data
                    │     no showtimes ──► Issue.skipped("no showtimes") ──► exit
                    ├─ render issue.html + issue.txt  stored on the Issue
                    ├─ Delivery rows for Subscriber.objects.active()
                    ├─ send each pending Delivery     EmailMultiAlternatives
                    └─ Issue.sent(counts)             failures logged at ERROR
```

## Models (`newsletter/models.py`)

### Issue

One row per Thursday.

| field | type | notes |
|---|---|---|
| week_of | DateField, unique | the Thursday, Eastern |
| status | CharField choices | `sending`, `sent`, `skipped`, `failed` |
| subject | CharField(200) | |
| html | TextField | rendered body with `{unsubscribe_url}` placeholder |
| text | TextField | plain-text body with the same placeholder |
| started_at | DateTimeField | set on create |
| finished_at | DateTimeField, null | set on sent/skipped/failed |
| recipient_count | PositiveIntegerField | Delivery rows created |
| sent_count | PositiveIntegerField | |
| failed_count | PositiveIntegerField | |
| skip_reason | CharField(200), blank | `no showtimes` today; room for more |

Status meanings:

- `sending`: a run is in progress or died mid-run. A new run resumes it.
- `sent`: every Delivery is sent or failed. A new run exits at once.
- `skipped`: nothing to send. A new run exits at once.
- `failed`: the run could not connect to SMTP at all (zero sends). A new
  run resumes it like `sending`; the status is for the dashboard's benefit.

The body is stored once on the Issue, not per Delivery. The unsubscribe
link differs per recipient, so both bodies carry a literal
`{unsubscribe_url}` token that the sender substitutes at send time. The
dashboard preview substitutes a `#` so the stored copy renders cleanly.

### Delivery

One row per recipient per Issue.

| field | type | notes |
|---|---|---|
| issue | FK Issue, CASCADE | |
| subscriber | FK Subscriber, CASCADE | |
| status | CharField choices | `pending`, `sent`, `failed` |
| sent_at | DateTimeField, null | |
| error | TextField, blank | exception text, truncated to 1000 chars |

`unique_together = (issue, subscriber)`. This is what makes a re-run safe:
Delivery rows are created with `ignore_conflicts`, and only `pending` rows
are sent.

### Permissions

Django's default `newsletter.view_issue` gates the dashboard page. No
custom permissions; nothing writes from the dashboard.

## Content (`newsletter/content.py`)

`build_context(now) -> dict | None` assembles everything from existing
services. It never queries Showtime directly.

- **Window.** `today` is the Eastern local date of `now`. The window is
  `today` through `today + 3 days` (Thursday through Sunday when run on a
  Thursday; the command only runs then, but the builder takes any date so
  `--week-of` and tests work). A showtime is in the window when its local
  date is inside it and its `starts_at` is after `now`.
- **Films.** `web.services.cinema_data.get_hero_films(now)`, each film's
  `upcoming` rows filtered to the window, films with no remaining rows
  dropped. Order is the hero's order: by next showing.
- **Ticket state.** `web.views._add_ticket_state` is moved to
  `web/services/ticket_state.py` as `add_ticket_state(times)` and imported
  by both HomeView and the builder, so the chips and the email cannot
  drift. Each time ends up with `ticket_url` (relative), `sold_out`,
  `in_person`. The builder makes `ticket_url` absolute with
  `boxoffice.site.base_url()`.
- **Coming Soon.** `get_coming_soon(now)[:3]`, each as title, poster URL,
  opening date text. Links to `base_url() + "/#coming-soon"`.
- **Latest post.** `BlogPost.objects.published()` ordered by `post_date`
  descending, first row, included only when its `post_date` is within the
  last seven days of `today`. Title, `subtitle`, and the absolute URL from
  `get_absolute_url()`. No image.
- **Footer.** `ticket_prices` and `site_config.cinema` from web.constants,
  plus the literal `{unsubscribe_url}` placeholder.
- **Returns None** when no film has a remaining showtime in the window.
  Coming Soon and the post alone do not make an email (owner: skip).

`subject_for(films) -> str`: "This weekend at the Cinema: A, B" for one or
two titles; "This weekend at the Cinema: A, B and more" for three or more.
Titles come from the film's listing title. No subject prefix: Django applies
EMAIL_SUBJECT_PREFIX only to admin mail, and the ticket and welcome emails
set their subjects bare, so this one does too.

## Templates

- `newsletter/templates/newsletter/email/issue.html`: single column,
  inline styles, Arial stack, max width 600px. Per film: poster (from the
  existing poster URL, width 120, with alt text of the title), title as a
  heading, rating/runtime line if the film carries them, then one line per
  day: day name, and each time as a Buy link, or the time followed by
  "Sold out online" or "In-person purchase only" in muted text, or the bare
  time. Then Coming Soon (title and "Opens Fri, Nov 14"), then the post,
  then the footer: price line, address, phone, and "Unsubscribe" as a link
  to `{unsubscribe_url}`. No images other than posters. No tracking pixel,
  no redirecting links.
- `newsletter/templates/newsletter/email/issue.txt`: the same content as
  plain text. Each Buy link on its own line under the time so the URL does
  not break the line.
- Both templates are wrapped in `{% autoescape off %}` only where the
  existing text emails do it (the .txt), and the .html escapes normally.

## Send command (`newsletter/management/commands/send_weekly_email.py`)

Options:

- `--week-of YYYY-MM-DD`: the Thursday to send for. Default: today,
  Eastern. Without `--week-of`, the command logs "not Thursday" or "too
  early" at INFO and exits 0 when it is not Thursday 10:00 AM Eastern or
  later (so the extra UTC cron firings are quiet). An explicit `--week-of`
  skips both checks, and a date that is not a Thursday is an error
  (exit 1).
- `--dry-run`: build and render, print subject and HTML to stdout, write
  nothing, send nothing.

Steps:

1. `Issue.objects.get_or_create(week_of=thursday, defaults=...)`. A
   `sent` or `skipped` Issue logs "already done" at INFO and exits 0.
2. `build_context(now)`. `None` → `status=skipped`, `skip_reason="no
   showtimes"`, `finished_at=now`, exit 0. (Only when the Issue has no
   Deliveries yet; an Issue mid-send is never flipped to skipped.)
3. Render both templates, store `subject`, `html`, `text` on the Issue.
   On a resumed run the stored body is reused, not re-rendered, so every
   recipient of one Issue gets the same email even if showtimes changed
   between 10:00 and 10:30.
4. `Delivery.objects.bulk_create([... for s in Subscriber.objects.active()],
   ignore_conflicts=True)`. `recipient_count` = Delivery rows for the Issue.
5. Open one SMTP connection (`mail.get_connection()`). For each `pending`
   Delivery, ordered by pk: build the unsubscribe URL from the subscriber's
   token, substitute into both bodies, build `EmailMultiAlternatives` with
   `to=[email]`, `from_email=DEFAULT_FROM_EMAIL`, headers
   `List-Unsubscribe: <url>` and `List-Unsubscribe-Post: List-Unsubscribe=One-Click`,
   attach the HTML alternative, send. Success → `sent`, `sent_at`.
   `smtplib.SMTPRecipientsRefused` or `SMTPDataError` → `failed` with
   the error text, continue. Any other `SMTPException` or `OSError`
   (connection-level) → log at ERROR, leave the Issue `sending`
   (or `failed` if `sent_count` is still 0), exit 1. Cron's 10:30 firing
   resumes.
6. Close: `sent_count`, `failed_count` from the Deliveries, `status=sent`,
   `finished_at`. If `failed_count > 0`, one ERROR log line naming the
   count and the week, which the ADMINS mail route delivers.

A re-run after `sent` is a no-op. A re-run during `sending` sends only
pending rows. Two simultaneous runs are prevented by the cron `flock`.

## Unsubscribe (`newsletter/views.py`, routed in `web/urls.py` or `newsletter/urls.py`)

Route: `/unsubscribe/<uuid:token>`, name `list_unsubscribe`. Token is
`Subscriber.unsubscribe_token`.

- **GET**: page with the address (masked to `b•••@example.com`) and one
  button, "Unsubscribe". Unknown token → the done page (never reveals
  whether an address is on the list).
- **POST** (form or mail-client one-click): `subscriber.unsubscribe()`
  (the model method; it writes the SubscriptionChange row), then the done
  page: "You're off the list" with "Changed your mind? Rejoin" linking to
  `/#coming-soon` where the signup form is. Unknown token → done page.
  Already unsubscribed → done page. The one-click POST from a mail client
  carries no CSRF token, so the view is `csrf_exempt`; the token in the
  URL is the authorisation, as it is for the confirm link.
- `noindex`, not in the sitemap, same as `/thanks`.
- Template `newsletter/templates/newsletter/unsubscribe.html`, extending
  base.html, same look as list_confirm.html.

## Dashboard

- **Sidebar**: "Thursday Email" under the existing Subscribers entry,
  shown to users with `newsletter.view_issue`.
- **List** `/dashboard/thursday-email` (`dashboard:newsletter_issues`):
  one row per Issue, newest first: week, status pill, recipients, sent,
  failed, duration, Preview link. A row with failures expands (details
  element) to the failed addresses and errors. Nothing is editable.
- **Preview** `/dashboard/thursday-email/<pk>/preview`: the stored HTML
  with `{unsubscribe_url}` replaced by `#`, served as `text/html` inside
  an iframe on the list page. `Content-Security-Policy: sandbox` on the
  response so the stored HTML cannot script the dashboard.
- **Smart alert** on the dashboard home: "Last Thursday's email did not go
  out" when today is Friday or later in the week and the most recent
  Thursday has no Issue with status `sent` or `skipped`. Links to the list.
  Added to `dashboard/smart_alerts.py` with a new keyword argument, same
  as the inquiry counts.

## Deployment (ansible, separate repo)

- New flag `cron_weekly_email: true` in `group_vars/webservers.yml` next to
  `cron_ticket_expire`.
- Two cron entries in `roles/django_app/tasks/main.yml`, same flock and
  log pattern as `pull_square_sales`: Thursday at 10:00 and 10:30. The
  role already sets `CRON_TZ=America/New_York` in that crontab for the
  Square jobs, so the hours are Eastern wall-clock; the new flag joins the
  `when:` list on that CRON_TZ task. The command's own Thursday / 10 AM
  check stays as a safety net should the crontab ever lose CRON_TZ.
- `deploy.md`: run migrate for `newsletter`, grant `newsletter.view_issue`
  to the owner group, confirm the From address, and send one `--dry-run`
  before the first Thursday.

## Testing

Unit tests, all under `newsletter/tests/`, Django TestCase with the
locmem email backend. No time-freezing library is installed and none is
added: every builder and command entry point takes `now` as a keyword
argument, defaulting to `timezone.now()`, and tests pass it explicitly.

- **content**: window edges (Wednesday 11:59 PM out, Thursday 10:01 AM
  show in, Thursday 9:00 AM show out, Monday out); a cancelled showtime
  out; a run not in main listings out; no showtimes → None; Coming Soon
  capped at three; post included at six days, excluded at eight; ticket
  URLs absolute; sold-out and in-person flags carried.
- **subject**: one, two, three titles.
- **command**: creates Issue and one email per active subscriber;
  unsubscribed and unconfirmed subscribers get nothing; second run sends
  nothing more; a recipient refusal marks that Delivery failed and the
  rest still send; a connection error mid-run leaves pending rows and a
  re-run finishes them without re-sending the sent ones; `--dry-run`
  writes no rows and sends nothing; non-Thursday `--week-of` is refused;
  no showtimes → skipped Issue, no Deliveries; List-Unsubscribe headers
  present; the unsubscribe URL in the body contains the recipient's own
  token.
- **templates**: both bodies contain every Buy URL and the unsubscribe
  placeholder; the text body names every showtime the HTML does.
- **unsubscribe view**: GET known token shows the address and button; POST
  calls unsubscribe (status, unsubscribed_at, SubscriptionChange row);
  unknown token GET and POST show the done page with 200; one-click POST
  without CSRF works; already-unsubscribed POST is a no-op.
- **dashboard**: anonymous → login; staff without the permission → 403;
  with permission sees the list and preview; preview response has the
  sandbox header and no raw placeholder.
- **smart alert**: present on Friday with no Issue; absent when the Issue
  is sent or skipped; absent on Wednesday.

Lint gate per the repo rule: no new flake8 findings on changed lines.

## Out of scope

- Open and click tracking.
- A staff-written note or edited copy in the email.
- Film-vote block (declined).
- Poll results email for voters (separate promise, separate spec).
- Per-subscriber preferences or frequency.
- Any third-party sending service.
