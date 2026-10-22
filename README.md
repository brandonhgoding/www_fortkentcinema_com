API FILES GO HERE
Does this effect the othe

# api_fortkentcinema_com
##


https://django-tailwind.readthedocs.io/en/latest/installation.html


npx @tailwindcss/cli -i theme/static/src/input.css -o theme/static/src/output.css --watch

## Python

The site runs on Python 3.12 (the black and mypy targets in `pyproject.toml`
and `mypy.ini`); 3.11 is the floor, because `boxoffice.gateway.parse_timestamp`
relies on `fromisoformat` reading Square's trailing `Z`. The deploy's
interpreter must match; `.python-version` is gitignored here, so set it locally.

## Online tickets

Online ticket sales (the `tickets` app) need one nightly job beside the Square
sales pull (`python manage.py pull_square_sales`): `python manage.py
expire_ticket_orders`, which asks Square about every order still pending past the
hold and expires the unpaid ones (an order Square could not be asked about stays
pending for the next run). Set `TICKETS_BASE_URL` (for example
`https://www.fortkentcinema.com`) so Square's checkout returns buyers to this
site; when it is empty the scheme and host of `SQUARE_WEBHOOK_URL` are used. The
confirmation page and ticket email draw a QR code with the `qrcode` package,
which is in `requirements.txt`.

## Phone line

The cinema's number is a Twilio number (the `phone` app). Twilio POSTs to
`/phone/voice/` when a call comes in and the app answers with TwiML: a greeting
and a three-key menu (today's showtimes, hours and prices, leave a message).
Showtimes come from the same rule as Now Showing, prices from `TICKET_PRICES` in
`web/constants.py`. Voicemails are recorded at Twilio and reach staff through
the dashboard's Voicemails page and its badge; nothing is emailed. Two toggles
live at the top of `phone/views.py`: `TRANSCRIBE` (off, it was most of a
voicemail's cost) and `VOICE`. A recording under `MIN_VOICEMAIL_SECONDS` is a
hang-up at the beep, not a message, and is discarded.

Every webhook is checked against `X-Twilio-Signature`, which Twilio computes
over the exact public URL it called, query string included. Three settings:

- `TWILIO_AUTH_TOKEN`: the signing token. Empty means every webhook answers
  403, so a missing variable fails closed.
- `TWILIO_ACCOUNT_SID`: only for calls *to* Twilio. Empty means the dashboard
  can't stream or delete recordings (it falls back to linking Twilio directly).
- `TWILIO_WEBHOOK_BASE_URL`: the scheme and host signatures are checked
  against (`https://www.fortkentcinema.com` in production). Leave it empty only
  where Django can rebuild the public URL itself, which behind nginx needs
  `USE_PROXY_HEADERS=True`.

**Twilio console.** The number's Voice URL must be exactly
`https://www.fortkentcinema.com/phone/voice/` with HTTP POST. Any other form
(`http://`, no `www`, no trailing slash) is answered by this site but fails the
signature. Set the Voice *Fallback URL* to a TwiML Bin with a static message
("We can't take your call right now. Showtimes and tickets are at
fortkentcinema.com"): without one, a deploy restart or a 5xx plays Twilio's
"an application error has occurred" to the caller. Turn on alert emails under
Monitor → Alerts so a run of failed webhooks reaches someone; a bad signature is
logged here only as a WARNING, on purpose, because bots probe the URL. Under
Account → General settings turn on *Enforce HTTP Auth on Media URLs*: nothing
on the site links to Twilio media directly, so recordings should not be open to
anyone who learns a URL.

**Rotating the token.** Rotating in place kills the line until the next deploy.
Instead create a *secondary* auth token in the console, put it in the Ansible
vault as `TWILIO_AUTH_TOKEN`, deploy, then promote it to primary.

**Local development.** Run `ngrok http 8000`, set `TWILIO_WEBHOOK_BASE_URL` to
the ngrok URL, and point a number's Voice URL at `https://<ngrok>/phone/voice/`.
Use a separate dev number: the URL on the real number is what customers reach.

**When every call gets a 403**, check in this order: the console URL against
`TWILIO_WEBHOOK_BASE_URL` (scheme, host, trailing slash), the token, then the
proxy headers. The WARNING log line names the URL the signature was checked
against. **When a voicemail is missing**, the recording is still at Twilio
(Monitor → Logs → Recordings); its webhooks are retried, and if they still
failed the error email to `ADMINS` carries the `RecordingSid` and caller.
`docs/qa/phone-line.md` is the manual checklist for a real call.

## Granting dashboard access

A dashboard user needs **Staff status** and the Django permissions for what they
should see and do. The sidebar shows only the sections the user holds a `view`
permission for; Edit, Delete, and action buttons appear only with the matching
`change`, `delete`, or `add` permission. Manage users, groups, and permissions
in Django admin at `/admin/`. Superusers see everything.

Five wrong passwords for one username from one address lock that pair out of
`/login` for fifteen minutes (django-axes; the numbers are the `AXES_*` settings).
A locked-out person sees a wait message, not which username was tried. To clear
a lockout early, run `python manage.py axes_reset_username <username>` or delete
the row under **Axes → Access attempts** in Django admin. Deploying this needs
`pip install -r requirements.txt` and `migrate` (the `axes` tables).

When this change is first deployed, every existing staff account that is not a
superuser holds no permissions, so it sees only the home header and no sidebar
links until an administrator assigns permissions or groups in Django admin. Do
that before or right after deploying.

Permissions that go together:

- Creating or editing an engagement, and adding a poll option, needs
  `cinema.view_film` for the film search; adding films from TMDB needs
  `cinema.add_film`.
- The home page's Today's Showtimes needs `cinema.view_showtime`; Yesterday's
  Sales needs `boxoffice.view_salespull`.
- The blog page's Authors and Categories panels need `blog.view_blogauthor` and
  `blog.view_blogcategory`.
- Writing blog posts needs `blog.add_blogpost` and `blog.change_blogpost`
  together (saving opens the editor).
- Door lists on an engagement's showtimes need `tickets.view_ticketorder`; the
  back link from a door list needs `cinema.view_engagement`.
