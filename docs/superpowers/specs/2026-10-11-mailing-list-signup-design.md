# Mailing-list signup — confirmed opt-in under the showtimes — Design

**Date:** 2026-10-11
**Status:** Approved design, not yet implemented
**Repo:** `www_fortkentcinema_com` (branch: `feat/mailing-list-signup`)
**Builds on:** `2026-08-20-film-vote-design.md` (the `Subscriber` model and
the vote thanks-screen ask)
**Followed by:** the Thursday "This weekend at the Cinema" email (separate
spec, not yet written)

## Context

A site review found no newsletter signup anywhere. The Facebook page
reaches whoever Facebook chooses; an email list belongs to the cinema. The
recommendation was a Thursday "This weekend at the Cinema" email, with one
signup line under the showtimes and another on each `/movies/` page.

What exists today:

- `audience.Subscriber`: unique lowercased email, `ACTIVE`/`UNSUBSCRIBED`
  status, `source` label, `consent_at`/`consent_ip`, an `unsubscribe_token`
  on every row, and a `SubscriptionChange` log of every status change.
- One way onto the list: the "Yes, add me" button on the vote thanks
  screen (`VoteSubscribeView`), which adds the voting address as `ACTIVE`
  immediately.
- A dashboard Subscribers page and an active-only CSV export.
- No mail to subscribers, no unsubscribe page. SMTP is configured for the
  nightly box-office reports (`EMAIL_*`, `DEFAULT_FROM_EMAIL`).

The work splits in two. This spec is the first half: collecting confirmed
addresses. The weekly email (composition, sending, unsubscribe page,
schedule) is the second half and gets its own spec.

## Goal

A visitor reading showtimes on the home page or a film page can enter an
email address, confirm it from their inbox, and be on the list for the
Thursday email. Nobody can put someone else's address on the list.

## Decisions

- **Signups first.** Ship the forms now so the list grows while the
  Thursday email is designed.
- **Double opt-in.** Every new address confirms by clicking a link in an
  email before it becomes `ACTIVE`.
- **The copy promises the Thursday email.** "Get the weekend's showtimes
  by email every Thursday." The confirmation email says the first one is on
  its way soon.
- **Former opt-outs may rejoin by confirming.** Clicking the confirmation
  link is fresh, explicit consent. The earlier opt-out stays in
  `SubscriptionChange`. The rule "never *silently* re-add an opt-out" is
  unchanged.
- **The vote thanks-screen button confirms too.** Vote addresses are
  unverified, so one rule applies to every way onto the list.

## Data model

`audience.models.subscriber`:

- `SubscriberStatus` gains `PENDING = "PENDING", "Pending confirmation"`.
- New `Subscriber.confirmed_at` (nullable `DateTimeField`): when the
  address became active by consent. This is the CAN-SPAM consent record;
  `consent_at` remains the time the row was created.
- New `Subscriber.confirmation_sent_at` (nullable `DateTimeField`): when
  the last confirmation email went out. Used only for the resend limit.
- Migration: add the status choice and both fields; data-migrate existing
  `ACTIVE` rows to `confirmed_at = consent_at`. Rows with `UNSUBSCRIBED`
  status keep `confirmed_at = consent_at` too (they were active once).
- `Subscriber.save()` keeps its status/`unsubscribed_at` agreement. A
  `PENDING` row has `unsubscribed_at = None`. Its `_log_change()` already
  writes a `SubscriptionChange` on every status change, so `PENDING` →
  `ACTIVE` is logged without new code; the `at` for a change to `ACTIVE`
  is `confirmed_at`.
- `SubscriberManager.active()` is unchanged (`ACTIVE` only). The CSV
  export and any future send therefore never include pending addresses.

### Manager methods

`SubscriberManager.request_signup(email, source, ip) -> Subscriber | None`
normalises the address the way `record()` does, then:

| Existing row  | Effect                                                   | Returns          |
|---------------|----------------------------------------------------------|------------------|
| none          | create `PENDING` with `source`, `consent_ip`             | the row          |
| `PENDING`     | none (row is unchanged; `source` is not overwritten)     | the row, unless a confirmation went out under an hour ago, then `None` |
| `ACTIVE`      | none                                                     | `None`           |
| `UNSUBSCRIBED`| none until confirmed (status stays `UNSUBSCRIBED`)       | the row, same hourly limit as `PENDING` |

A returned row means "send a confirmation email now"; `None` means send
nothing. The caller sends the email, then sets `confirmation_sent_at`. The
create uses `get_or_create`, as `record()` does, for the same race reason.

`Subscriber.confirm()` sets `status = ACTIVE` and `confirmed_at = now`, and
saves. Calling it on an already-`ACTIVE` row does nothing.

`record()` stays for admin and test use. `VoteSubscribeView` stops calling
it (see below).

## Signup flow

### `POST /subscribe` (`web.views.ListSignupView`, name `list_signup`)

Fields: `email`, `location` (one of `home_showtimes`, `home_empty`,
`movie_page`; anything else becomes `site`), and a honeypot field
`website` that is hidden from people and left empty by them.

1. If the honeypot is filled, respond exactly as for success and do
   nothing.
2. Validate `email` with Django's `EmailField` (max length
   `Subscriber.EMAIL_MAX_LENGTH`). On failure, re-render the form with
   "That doesn't look like an email address." and the value kept.
3. Call `request_signup(email, source=location, ip=client_ip)`. If it
   returns a row, send the confirmation email and set
   `confirmation_sent_at`.
4. Respond with the same "check your inbox" reply whatever happened in
   step 3, so the form never reveals whether an address is on the list.

htmx requests (`HX-Request`) get `partials/list_signup.html` in its done
state, swapped over the form. Plain posts get `web/list_signup.html`, a
small page extending `base.html` with the same message and a link back to
the referring page (or home).

If sending the email raises (SMTP down), log the exception, leave
`confirmation_sent_at` unset so the next try sends again, and still show
the same reply. The pending row stays.

### Confirmation email

Plain text, from `DEFAULT_FROM_EMAIL`, sent with Django's
`EmailMessage`. Subject: "Confirm your Fort Kent Cinema emails". Body, in
substance:

> Click below to confirm you'd like the weekend's showtimes from Fort Kent
> Cinema by email every Thursday. The first one is on its way soon.
>
> {confirm link}
>
> Didn't ask for this? Ignore this email and you won't hear from us.
>
> Fort Kent Cinema · {street address} · {phone}

The link is an absolute URL to `/subscribe/confirm/<token>`, where
`token = signing.dumps(subscriber.pk, salt="list-confirm")`. It is valid
for 7 days (`max_age`). Nothing new is stored for it. The absolute URL
uses `request.build_absolute_uri`.

### `GET`/`POST /subscribe/confirm/<token>` (`ListConfirmView`, name `list_confirm`)

- `GET` with a valid token for a `PENDING` or `UNSUBSCRIBED` row: a page
  with the address and one "Confirm" button that POSTs back to the same
  URL. GET never changes state, because mail scanners open every link.
- `POST` with a valid token: `subscriber.confirm()`, then "You're on the
  list. The first Thursday email is on its way soon."
- Valid token for an `ACTIVE` row (GET or POST): "You're already on the
  list."
- Bad, tampered or expired token, or a deleted row: a friendly "That link
  has expired" page with the signup form (`location=site`) so they can
  request a new one. Status 200, never 400 or 404.

Both pages extend `base.html` in the style of `web/thanks.html`, and are
`noindex`.

## Vote thanks screen

`VoteSubscribeView` keeps its signed vote token and "Yes, add me" button,
but calls `request_signup(vote.email, source="poll_vote", ip=…)` and sends
the confirmation email instead of `record()`. Its done state changes from
"You're on the list — thanks." to "Almost there: check your inbox for a
link to confirm."

`offer_subscribe` is unchanged: the ask appears only when no `Subscriber`
row exists for the address. A pending row therefore hides it, as does an
opt-out.

The comment in `partials/vote_subscribe.html` saying nothing sends mail is
updated: the ask still makes no newsletter promise of its own.

## Placement and copy

One partial, `templates/partials/list_signup.html`, takes `location` and
renders either the form or the done state. Included in four places:

1. **Home, Now Showing** (`partials/now_showing.html`): inside the
   `{% if ns_dates %}` branch, after the schedule list.
   `location=home_showtimes`.
2. **Home, no showtimes** (same file, empty-state branch): above the
   links list, with the lead "Get an email the moment new runs are
   booked." `location=home_empty`.
3. **Film page, now showing** (`web/movie_detail.html`): after
   `partials/ticket_info.html` in the showtimes section.
   `location=movie_page`.
4. **Film page, archive state**: after "It isn't currently on our
   schedule." `location=movie_page`.

Default copy:

> **This weekend at the Cinema**: get the weekend's showtimes by email
> every Thursday.
> `[ your@email ]` `[ Sign me up ]`

Done: "Almost there: check your inbox for a link to confirm."
Error: "That doesn't look like an email address."

The field has a visible label (or `aria-label`), `type="email"`,
`autocomplete="email"` and `required`. The button carries
`data-track="list_signup"` and `data-track-location="{{ location }}"`.

**Look:** a quiet inline row in the site's existing type and colours,
visually lighter than the ticket-price line above it, not a CTA banner.
On narrow screens the field and button stack at full width. Styles go in a
new `static/css/ListSignup.css`, included where the partial is used.

## Dashboard

The Subscribers page shows status with the new "Pending confirmation"
label. Its headline count stays `active().count()`. The CSV export stays
active-only. No new dashboard actions.

## Out of scope

- The Thursday email: composing showtimes and reviews, sending, schedule.
- The unsubscribe page and `List-Unsubscribe` header (needed before the
  first Thursday send; they belong with it).
- Purging stale pending rows.
- Signup forms anywhere other than the four placements above.

## Testing

Django `TestCase`, `mail.outbox` for email.

- `request_signup`: each row of the table above, including the hourly
  limit on both `PENDING` and `UNSUBSCRIBED`, and case/space
  normalisation.
- `confirm()`: `PENDING` → `ACTIVE` and `UNSUBSCRIBED` → `ACTIVE` set
  `confirmed_at` and log a `SubscriptionChange`; on `ACTIVE`, it does
  nothing.
- Migration: existing rows get `confirmed_at = consent_at`.
- `active()` and the CSV export exclude `PENDING`.
- `POST /subscribe`: new address sends one email with a working link;
  active address sends none but gives the same reply; honeypot sends none
  and gives the same reply; bad address re-renders with the error; htmx
  vs plain responses; unknown `location` becomes `site`; an SMTP failure
  still replies and leaves `confirmation_sent_at` unset.
- Confirm view: GET shows a button and changes nothing; POST activates;
  already-active message; tampered and expired tokens give the friendly
  page with status 200.
- Vote: "Yes, add me" now creates a `PENDING` row and sends the email;
  the done copy changed; the ask is hidden for a pending address.
- Templates: the form renders in each of the four placements with the
  right `location`, exactly once per page.
