# Online ticket pre-sale — buy a showtime on the site, see it in the dashboard — Design

**Date:** 2026-10-17
**Status:** Implemented on feat/online-tickets (see Amendments)
**Repo:** `www_fortkentcinema_com` (branch: `feat/online-tickets`)
**Builds on:** `2026-10-05-square-sync-design.md` (the `boxoffice` app, its
gateway, the per-run Square ticket items), `2026-10-09-square-membership-webhook-design.md`
(the payment webhook), `2026-10-12-home-visual-hierarchy-design.md` (the
Now Showing cards)

## Context

The home page lists every showtime, and none of them can be bought. The
only online ticket path the cinema has ever had is a hand-made Square
payment link for a special event (The Graduate, 2026-10-17), which sells a
flat-priced item with no cap, no door list and no way for the dashboard to
see who bought.

Meanwhile the Square sync already gives every confirmed run a Square item
with adult, senior and child variations, the nightly pull already attributes
any order line carrying one of those variation IDs to its run, and the
payment webhook already verifies Square's signature and fetches orders by
ID. The pieces for selling the real showtimes are mostly in place.

### Goal

A visitor taps a showtime, picks adult, senior and child tickets at the
door prices (matinee applied automatically), pays on Square's hosted
checkout, and gets an email with the order and a QR code. Staff see every
order per showtime in the dashboard, tick people off at the door, read
pre-sale demand across upcoming shows, and refund a cancelled show in one
click. Online sales flow into the existing nightly reports with no new
reporting code.

### Why (in order, decided with the owner 2026-10-17)

1. **Prove demand and commitment for special events.** A pre-sale shows a
   booking is worth making before the date.
2. **Let regulars skip the line.**
3. **Handle the occasional sell-out.** Stop selling online when the
   online share of the house is gone.

## Decisions (made with the owner, 2026-10-17)

- **Every showtime of every confirmed run sells online, no switch.** From
  the moment it is listed until 30 minutes before it starts.
- **Adult, senior and child only, at door prices, no fee.** Matinee (a
  show starting at or before 4 PM) is applied automatically. Senior and
  child stay honour-system, as at the door. The member rate stays at the
  door until member sign-in exists; the ticket page leaves a slot for it.
- **Square, hosted checkout.** Online sales land in the owner summary, the
  distributor ticket report and the run's admissions through the existing
  pull, because every order line points at a Django-issued variation ID.
  Stripe would have meant a second money system stitched into every
  report. Square's page on a `square.link` address is the accepted cost.
- **Buyer gives name, email and phone.** Phone so staff can reach people
  about a cancelled show. Square prefills email and phone on its page.
- **Buyer gets an email with a QR code and the dashboard gets a door
  list.** The list ships in this pass; a QR scanner is a later phase that
  reads the same token.
- **Per-showtime online allowance.** Default is a share of the screen's
  seat count (50 percent to start), editable per showtime. "Sold out
  online" when it is reached. Door sales are not tracked against the
  showtime.
- **Cancelling a showtime offers one-click refund of its online orders,**
  each with an email. No buyer-initiated refunds, no exchanges.
- **Dashboard gets all of:** per-showtime door list with tick-off,
  allowance control, upcoming pre-sale summary, order log with Retry,
  home-page alerts, CSV export.

### Explicitly out of scope

- **QR scanning at the door.** Phase 2. The QR encodes the order's token
  URL, so a scanner page is one view that marks the order arrived.
- **Member pricing online.** Phase 3, after member sign-in.
- **Door sales counted against the showtime.** The allowance is an online
  cap, not a house count.
- **Exchanges, buyer-initiated refunds, partial refunds.**
- **Refunds in the nightly pull.** The pull still sums completed orders;
  a refunded ticket inflates admissions by one until the pull learns about
  refunds. The pre-sale summary counts only PAID orders, so it is right.
- **Automatic notice when a showtime with orders is moved.** Staff are
  warned and email by hand.
- **Reserved seating.** General admission only.
- **Concessions, gift cards, donations at checkout.**

## Section 1: shape and purchase flow

### The `tickets` app

A new Django app, `tickets`, owns online orders. It sits beside
`boxoffice` the way `boxoffice` sits beside `cinema`: it reads showtimes
and the run's `SquareVariation` rows, talks to Square only through
`boxoffice.gateway`, and nothing in `cinema` or `boxoffice` imports it
(the webhook view calls into it by a one-line hook, see below). The
dashboard app gets `ticket_views.py` the way it has
`membership_sale_views.py`.

### Flow

1. **Pick.** On the home page every purchasable showtime chip links to
   `/tickets/<showtime pk>/`. That page shows the film, date and time, the
   three ticket types at their prices with matinee already applied, and
   quantity steppers; then name, email, phone. A showtime inside its
   30-minute cutoff, cancelled, sold out online, or on a run with no live
   Square item shows a sentence instead of the form.
2. **Reserve.** Submitting creates a `TicketOrder` (status PENDING) with
   its lines and buyer. A PENDING order counts against the allowance for
   20 minutes (`TICKET_HOLD_MINUTES`). The site then asks Square for a
   payment link (`checkout.payment_links.create`) whose order carries:
   - `location_id` from settings, `reference_id` = our order number,
     `metadata.showtime` = the showtime pk;
   - one line per ticket type with `catalog_object_id` = the run's
     variation for that tier, `quantity`, and an explicit
     `base_price_money` at the door price, so what we showed is what
     Square charges even if a catalog push lags;
   - for a matinee showtime, one `LINE_ITEM`-scoped `FIXED_AMOUNT`
     discount named "Matinee" per adult or senior line, amount
     `(tier price − matinee price) × quantity`, referenced from that
     line's `applied_discounts`. Child is already the matinee price and
     gets none. A per-line discount keeps the nightly report's
     `total_money` at the matinee price and keeps the register's wording;
   - no fulfillment (so the order completes on payment; see Section 2);
   - `checkout_options`: `redirect_url` = our confirmation URL with the
     order token, `ask_for_shipping_address` false, `allow_tipping`
     false, `merchant_support_email` = the cinema's address,
     `accepted_payment_methods` with Apple Pay and Google Pay on;
   - `pre_populated_data`: `buyer_email`, `buyer_phone_number`;
   - `idempotency_key` = the order token.
   The response's `order_id` and `url` are stored on the order and the
   buyer is redirected to the URL.
3. **Pay.** Square redirects back to `/tickets/order/<token>/`. The page
   reads our row only: "Payment received" with the ticket when PAID,
   "Confirming your payment" with a refresh otherwise. It never trusts
   the redirect alone.
4. **Confirm.** `boxoffice.views.square_webhook`, on a COMPLETED payment,
   calls `process_order` (memberships) as today and then
   `tickets.orders.confirm_payment(order_id, payment_id)`. The membership
   handler and the ticket handler never share an order; each returns
   quickly when the ID is not theirs. A PENDING (or EXPIRED, see 5)
   `TicketOrder` with that `square_order_id` becomes PAID with the payment
   ID and `paid_at`, and the ticket email is sent. A second event for a
   PAID order does nothing.
5. **Expire.** A PENDING order older than the hold stops counting against
   the allowance immediately (the count is a query, not a flag). The
   nightly `expire_ticket_orders` command marks stale PENDING orders
   EXPIRED, after the recovery fetch in Section 6. A payment arriving for
   an EXPIRED order still marks it PAID: the money was taken, and the
   allowance may go over by that order.

### Webhook return codes

The ticket handler records its own failures on the order row and never
asks for a Square retry; the 503 rule for never-fetched membership orders
is unchanged and does not apply to tickets, which carry their own order
ID from creation.

## Section 2: data model

### `cinema.Showtime.online_allowance`

`PositiveIntegerField(null=True, blank=True)`. Help text: "How many
tickets this showtime sells online. Blank uses the default: half the
screen's seats." The effective allowance is a property:

```
online_allowance if set, else floor(screen.capacity × TICKET_ONLINE_SHARE)
```

`TICKET_ONLINE_SHARE = 0.5` lives in `web/constants.py` beside
`TICKET_PRICES`. Changing it, or a screen's capacity, moves every unset
showtime. Both screens still carry the placeholder capacity of 100; the
real seat counts are confirmed in rollout.

Migration: the next `cinema` migration, `showtime_online_allowance`, adds the nullable
column, no data migration.

### `tickets.TicketOrder`

One row per checkout attempt.

| field | type | notes |
|---|---|---|
| `number` | `CharField(12, unique)` | public code `FK-` + 5 characters from an unambiguous alphabet (no 0/O/1/I); on the email and the door list |
| `token` | `CharField(43, unique)` | `secrets.token_urlsafe(32)`; the confirmation URL and the QR payload |
| `showtime` | `FK(cinema.Showtime, PROTECT, related_name="ticket_orders")` | a showtime with orders cannot be deleted |
| `name` | `CharField(200)` | as entered, stripped |
| `email` | `EmailField` | lowercased, stripped |
| `phone` | `CharField(40)` | as entered |
| `status` | `CharField` choices PENDING / PAID / EXPIRED / REFUNDED / FAILED | |
| `square_order_id` | `CharField(64, blank, default "")` with partial unique (non-blank) | the webhook's lookup key |
| `square_payment_id` | `CharField(64, blank, default "")` | needed for refunds |
| `square_checkout_url` | `URLField(blank)` | "Return to payment" on the pending page |
| `total_cents` | `PositiveIntegerField` | sum of lines after matinee |
| `error` | `TextField(blank)` | why FAILED; cleared on Retry success |
| `created_at` | `auto_now_add` | |
| `paid_at` | `DateTimeField(null)` | the payment event's time, else now |
| `refunded_at` | `DateTimeField(null)` | |
| `redeemed_at` | `DateTimeField(null)` | "Mark arrived" |
| `redeemed_by` | `FK(User, SET_NULL, null)` | who marked it |

Indexes: `(showtime, status)`, `(status, created_at)`.

`is_holding` property: PENDING and `created_at` within the hold window.
`is_valid_at_door`: PAID.

### `tickets.TicketLine`

| field | type | notes |
|---|---|---|
| `order` | `FK(TicketOrder, CASCADE, related_name="lines")` | |
| `tier` | `CharField(16)` | `adult`, `senior`, `child` (the `SQUARE_TIERS` names) |
| `quantity` | `PositiveIntegerField` | ≥ 1; zero-quantity tiers are not stored |
| `unit_cents` | `PositiveIntegerField` | the price charged, after matinee |
| `square_variation_id` | `CharField(64)` | the variation the Square line pointed at |

Unique on `(order, tier)`.

### Counting

```
sold(showtime) = Σ quantity over lines of orders where
    status == PAID
    or (status == PENDING and created_at > now − hold)
remaining(showtime) = max(effective_allowance − sold, 0)
```

REFUNDED, EXPIRED and FAILED orders hold nothing. A FAILED order that
carries a payment ID (email failed after payment) is counted as sold,
because the buyer has a ticket; implementation: a FAILED order with a
non-blank `square_payment_id` is treated as PAID for counting and for the
door list, and shows a "resend email" Retry.

### Status meanings

- **PENDING**: created, payment link made (or being made). Holds seats
  for the hold window.
- **PAID**: Square reported a completed payment. Email sent.
- **EXPIRED**: PENDING past the hold, recovery fetch found no payment.
- **REFUNDED**: refund issued through Square.
- **FAILED**: the payment-link call failed (no `square_order_id`), or
  the email after payment failed (`square_payment_id` set). The error
  text says which.

### What is untouched

`SaleLine`, `SalesPull`, `EmailReport`, `SquareItem`, `SquareVariation`.
The nightly pull attributes these sales by variation ID exactly as it
does register sales, so `Engagement.admissions` and both reports include
them with no change.

### The one thing to verify first

Payment-link orders made by hand with a shipping address stay OPEN until
staff mark the shipment done (membership webhook spec, Amendments). The
orders this spec creates carry no fulfillment, and Square's documented
behaviour is that a fulfillment-free order moves to COMPLETED when fully
paid, which is what the nightly pull's `state_filter` needs. The first
implementation task creates one such link in the sandbox, pays it with a
test card, and reads the order back. If it does not reach COMPLETED, the
pull's search gains a second query for OPEN orders carrying our
`reference_id` prefix, and this spec is amended before the rest is built.

## Section 3: public pages and the ticket email

### Home page

Each upcoming showtime chip in `movie_schedule_card.html` becomes an
`<a>` to the ticket page when the showtime is purchasable, keeping the
chip's look with a small "Buy" cue, so the card stays a schedule rather
than a store. The template comment that says there is no online ticket
path is replaced. States:

- purchasable: link;
- sold out online: plain chip with "Sold out online" in the note slot;
- inside the cutoff, cancelled, no live Square item, or Square disabled:
  the plain chip as today.

`web.views` computes `purchasable`, `sold_out` and `ticket_url` per
showtime through one `tickets.availability.for_showtimes(showtimes, now)`
call that does the counting in one query, not one per chip.

`home_jsonld.html`'s ScreeningEvent gains an `offers` block (price,
`priceCurrency`, `url`, `availability` InStock / SoldOut) when the
showtime is purchasable or sold out, which is what lets Google show a
Tickets link.

### Ticket page `/tickets/<showtime pk>/`

Name `tickets:buy`. One column on a phone, 16px gutters.

- Header: poster, title, rating, runtime, language label, date and time
  (Eastern), screen name, captions note.
- Three ticket rows: label, price (matinee price for a matinee showtime,
  with "Matinee" beside it), minus and plus steppers around a numeric
  input. The sum of quantities is capped at `remaining`; the cap is shown
  as "N left online" only when fewer than 10 remain.
- Name, email, phone fields, all required. Phone is validated loosely
  (digits, spaces, punctuation; 7 to 20 characters).
- Running total and one "Continue to payment" button, with a line under
  it: "You'll pay on Square's secure page. Members pay $4 at the door."
- Prices, the 4 PM rule, and the member line read `TICKET_PRICES` so the
  page, the phone line and the register agree.

Steppers are the only JavaScript; the form works without it. Validation
errors render inline in the mailing-list signup form's style. A POST that
fails the availability check (sold out between page load and submit,
cutoff passed) re-renders with the reason and no order is created.

The POST runs `tickets.orders.start(showtime, buyer, quantities, now)`:

1. `transaction.atomic()`; `select_for_update()` on the showtime row (a
   lock on Postgres, no-op on sqlite); recompute `remaining`; refuse if
   short.
2. Insert the PENDING order and its lines.
3. Commit, then call the gateway's `create_payment_link(spec)`.
4. Success: store `square_order_id` and `square_checkout_url`, redirect
   (303) to the checkout URL. `GatewayError`: mark FAILED with the text,
   render the page with "We couldn't start checkout. Please try again, or
   buy at the door."

The gateway call sits outside the transaction so a slow Square does not
hold the showtime lock.

### Confirmation page `/tickets/order/<token>/`

Name `tickets:order`. Looked up by token; unknown token is 404.

- PAID (or FAILED with a payment ID): the ticket. Order number, film,
  date and time, address, ticket breakdown, total, the QR image, and the
  two sentences from the email. Printable.
- PENDING inside the hold: "Confirming your payment…" with
  `<meta http-equiv="refresh" content="4">` for up to 2 minutes from
  `created_at` (the template compares), then: "Still waiting. Check your
  email for the ticket, or return to payment." with the stored checkout
  URL. Each load of this page for a PENDING order older than 60 seconds
  runs the recovery fetch (Section 6) once per load.
- EXPIRED: "This checkout expired before payment. Start again." with a
  link to the ticket page.
- REFUNDED: "This order was refunded on <date>."
- FAILED without a payment ID: "This checkout did not start. Start
  again."

### Ticket email

Sent by `tickets.mail.send_ticket(order)` through Django's mail backend
from `DEFAULT_FROM_EMAIL`, multipart plain text and HTML, the QR as an
inline image attachment (`cid:`) so it shows without remote images.

- Subject: `Your tickets: <film>, <Weekday Mon D> at <h:mm PM>`
- Body: order number, film, date and time, screen, ticket lines and
  total, the cinema's address, the QR, then: "Show this at the door, or
  just give your name. Tickets are non-refundable unless the show is
  cancelled." and the confirmation URL as a plain link.

The QR encodes the confirmation URL (token included) and is generated
locally with the `qrcode` package (PIL output); no outside service.

### Cancellation email

`tickets.mail.send_refund(order)`: subject `Refunded: <film>, <date>`;
body says the show was cancelled, the amount refunded, and that the card
will show it within a few days, plus the cinema's phone number.

## Section 4: dashboard

### Engagement page

`_showtime_list.html` rows gain "12 of 50 online", the number linking to
the door list. The showtime edit drawer (`_showtime_form.html`) gains the
`online_allowance` field with the computed default as placeholder text
and help "Blank uses the default". Moving a showtime that has PAID orders
shows a warning on save: "N online orders were emailed the old time. Let
them know." (no automatic notice; out of scope above).

### Door list `/dashboard/showtimes/<pk>/orders`

Name `dashboard:showtime_orders`, staff-only.

- Header: film, date and time, "sold / allowance online", inline
  allowance editor (HTMX form, same drawer-less pattern as the poll
  status control).
- Cancelled showtime: red banner with "Refund all N orders" (Section 5).
- Rows sorted by name: order number, name, phone, breakdown
  ("2 adult, 1 child"), total, status pill, and "Mark arrived". Arriving
  HTMX-swaps the row to "Arrived 6:52 PM · Brandon" with "Undo". Both
  are POSTs (`dashboard:ticket_order_arrive`, `..._unarrive`) that set
  or clear `redeemed_at` / `redeemed_by`. Refunded rows are greyed with no
  button. FAILED-with-payment rows show like PAID with a "Resend email"
  Retry.
- A search box filters rows by name or order number as you type (HTMX
  `hx-trigger="keyup changed delay:200ms"`, server-side filter).
- "Download CSV" → `dashboard:showtime_orders_export` through
  `csv_export.safe_csv_writer`: number, name, email, phone, adult,
  senior, child, total, status, paid at, arrived at.

### Pre-sale summary `/dashboard/tickets`

Name `dashboard:tickets`, sidebar entry "Online tickets" beside the box
office entries (alphabetical rule from the advertising-page memory).

- Top: tickets sold and gross for today and for the next seven days.
- "Upcoming" (default): showtimes from now, grouped by day: film, time,
  sold, gross, allowance, link to the door list. Showtimes with zero
  sales are listed too, so the demand picture is complete.
- "Past" filter: the same for showtimes that have started, newest first,
  paginated at 50.

Sold and gross count PAID orders (and FAILED-with-payment).

### Order log `/dashboard/tickets/orders`

Name `dashboard:ticket_orders`, staff-only, newest first, paginated at
50, filter by status, the `square_sales.html` shape:

- created, number, buyer name and email, show (film and time, linking to
  the door list), amount, status pill, error text.
- **Retry** on FAILED: with a payment ID, resends the email and marks
  PAID; without one, shows the error only (the buyer retries by buying
  again; there is no Square order to recover).
- **Refund** on PAID: confirmation step naming the amount, then the
  single-order refund (Section 5).
- "Download CSV" with the same columns as the door list plus film and
  showtime.

### Home page

`build_smart_alerts` gains:

- `ticket_failures: int` → warning "N online ticket order(s) need
  attention", linking to the order log.
- `nearly_sold_out: list[(showtime, sold, allowance)]` for showtimes in
  the next two days at ≥ 90 percent of allowance → info "<film> at
  <time> is nearly sold out online (45 of 50)", linking to the door list.
- `cancelled_with_orders: list[(showtime, count)]` → warning "<film> at
  <time> is cancelled with N unrefunded online orders", linking to the
  door list.

The today panel gains "N online" per showtime.

## Section 5: cancellation and refunds

Cancelling a showtime (the drawer's checkbox, or the run's status moving
to CANCELLED, which cascades in `Engagement.save`) does **not** issue
refunds. A save is the wrong place for a loop of Square calls with
partial failure to report. Instead:

1. A cancelled showtime with PAID orders raises the
   `cancelled_with_orders` alert and the red banner on its door list.
2. "Refund all N orders" → a confirmation naming the total → POST
   `dashboard:showtime_refund_all`.
3. `tickets.refunds.refund_showtime(showtime, reason="Showtime
   cancelled")` walks the PAID orders in pk order. For each:
   `gateway.refund_payment(payment_id=..., amount_cents=total_cents,
   idempotency_key=f"refund-{order.number}", reason=...)`. Success: status
   REFUNDED, `refunded_at` now, `send_refund(order)`. `GatewayError`: the
   order stays PAID with the error stored, the loop continues. The view
   reports "13 refunded, 1 failed"; a failed row keeps its own Refund
   button. The idempotency key makes a second click a no-op at Square.
4. The alert and banner clear when no PAID orders remain.

The order log's single Refund uses `refund_order(order, reason="Refunded
by staff")`, the same function for one order.

Un-cancelling a showtime does nothing to orders: unrefunded orders are
still PAID and still valid.

A refund email failure after a successful refund stores the error on the
order (status stays REFUNDED) and counts in `ticket_failures`; Retry
resends.

## Section 6: failures, settings, testing

### Failure cases

| case | behaviour |
|---|---|
| Square disabled (`get_gateway()` is None) | ticket page shows "Buy tickets at the door"; chips stay plain; nothing else visible changes |
| run has no live `SquareItem` with a Square ID | same as disabled for that run; the existing sync alert already flags the push failure |
| payment-link call fails | order FAILED with the error; buyer sees the retry sentence; `ticket_failures` counts it |
| webhook before redirect | pending page polls our row, finds PAID |
| webhook never arrives | pending-page loads after 60 s, and the nightly expiry command, run `gateway.retrieve_order(order_id)`; a tender with status COMPLETED marks the order PAID (payment ID from the tender) and sends the email; otherwise PENDING stays until expiry |
| two buyers race the last seats | count and insert under `select_for_update()` on the showtime, one transaction |
| ticket email fails after payment | order FAILED with the error, payment ID kept, counted as sold, Retry resends; webhook still returns 200 |
| allowance lowered below sold | allowed; page shows sold out; nothing refunded |
| showtime moved after orders exist | drawer warns; orders follow the showtime |
| buyer reloads the ticket page after redirect | a new PENDING order each submit; abandoned ones expire |
| token guessed | 43 random characters; 404 on miss |

`OrderData` gains `tenders: tuple[Tender, ...]` with `payment_id` and
`status`, read for the recovery fetch; `search_orders` fills it too.

### Gateway additions (`boxoffice/gateway.py`)

```
create_payment_link(spec: CheckoutSpec) -> CheckoutResult   # order_id, url
refund_payment(*, payment_id, amount_cents, idempotency_key, reason) -> str  # refund id
```

`CheckoutSpec` (in `tickets/spec.py`, mirroring `boxoffice/spec.py`)
holds the location, reference, lines (variation id, quantity, unit
cents, discount cents), redirect URL, buyer email and phone, support
email. The gateway maps it to the Square request; nothing else builds
Square payloads. The fake gateway in `boxoffice/tests/fakes.py` gains
both methods with scripted results and a way to raise `GatewayError`.

### Settings and constants

No new Square credentials. One new setting, `TICKETS_BASE_URL`
(default: blank, falling back to the host of `SQUARE_WEBHOOK_URL`), used
for the redirect and the QR URL because `build_absolute_uri()` is wrong
behind nginx. Constants in `web/constants.py`:

```
TICKET_ONLINE_SHARE = 0.5          # default allowance as a share of seats
TICKET_HOLD_MINUTES = 20           # how long a PENDING order holds seats
TICKET_CUTOFF_MINUTES = 30         # sales close this long before start
```

Dependencies: `qrcode[pil]`.

### Testing

Fake gateway as above. Cases:

- allowance: default from capacity and share; override; sold counts
  PAID and young PENDING, not old PENDING, EXPIRED, REFUNDED, or FAILED
  without payment; FAILED with payment counts.
- gating: cutoff (29 minutes before is closed, 31 is open, in Eastern
  across a DST change), cancelled, sold out, no Square item, disabled.
- pricing: evening adult/senior/child; matinee at 4:00 PM exactly is a
  matinee, 4:01 is not; matinee discount lines only on adult and senior;
  `total_cents` matches.
- start: PENDING order and lines written; payment link spec carries
  variation IDs, prices, discounts, reference, redirect, prefills;
  redirect 303; gateway error → FAILED and the page message; race
  (second start after the first filled the allowance) refuses.
- webhook: COMPLETED payment for a PENDING order → PAID, email sent once
  with QR attachment, `paid_at`; duplicate event → no second email; a
  membership order and a ticket order are each handled by their own
  module; unknown order ID → nothing; EXPIRED order paid late → PAID.
- recovery: pending page after 60 s fetches, a completed tender → PAID;
  expiry command marks stale PENDING EXPIRED only when the fetch finds no
  payment; a gateway error leaves PENDING.
- confirmation page: each status renders its state; refresh meta present
  inside 2 minutes and absent after; 404 on a bad token.
- refunds: refund-all walks PAID orders, partial failure leaves one PAID
  with error and the summary says so, idempotency key is the order
  number, emails sent per success; single refund; un-cancel leaves orders.
- dashboard: door list sorted, search filters, arrive/undo set and clear
  fields and user, CSV columns and formula neutralising, summary totals,
  order log filters and Retry paths, alerts for failures, nearly sold
  out at 90 percent, cancelled with orders; all views require staff.
- home page: chips link, sold out note, plain when closed; JSON-LD
  offers present with InStock / SoldOut.

Flake8 gate: no new findings on changed lines (repo baseline is dirty).

## Rollout

1. Sandbox: run the completion check from Section 2 with a test card.
2. Confirm both screens' real seat counts and set `Screen.capacity`.
3. Deploy with `TICKETS_BASE_URL` set; `migrate`. Square settings already
   present in production make the feature live on deploy; if a quiet
   launch is wanted, deploy with the token blank on the public workers
   first.
4. Schedule `manage.py expire_ticket_orders` nightly, in the same cron as
   `pull_square_sales`.
5. Buy one real ticket for a cheap showtime, check the email, the door
   list, the nightly report the next morning, and refund it from the
   order log.
6. Add the "Buy online" sentence to the hours-and-prices phone speech and
   the ticket info partial in a follow-up.

## Phases after this one

- **QR scanner.** A staff-only page that opens the camera, reads the
  token URL, and calls the arrive endpoint. No model change.
- **Member sign-in.** A member tier on the ticket page for a signed-in
  member, priced from `TICKET_PRICES["member"]`, which `TicketLine.tier`
  already allows.

## Amendments (implementation, 2026-10-18)

- `CheckoutSpec`, `CheckoutLine`, `CheckoutResult` and `Tender` live in
  `boxoffice/gateway.py`, so `boxoffice` never imports `tickets`;
  `tickets/spec.py` builds the spec.
- Square's tender card status when paid is `CAPTURED` (never `COMPLETED`).
  `recover_pending` treats `CAPTURED` as paid, and the fake gateway's `pay()`
  writes `CAPTURED`.
- `payment_link_body` raises `ValueError` if a line's discount does not divide
  evenly by its quantity.
- The paid confirmation page serves its QR from `tickets/order/<token>/qr.png`
  (`tickets:order_qr`), with a private cache, and returns 404 unless the order
  is paid.
- Page CSS is `static/css/TicketPage.css`, bundled through
  `frontend/styles/main.css`. The desktop `movie_card.html` and the schedule
  card share `partials/showtime_chip.html`; chip CSS lives in `MovieCard.css`.
- A sold-out showing keeps its ticket URL (the SoldOut offer points at the
  ticket page). `ticket_url` means "has a ticket page", not "purchasable".
- An all-zero order on an unbuyable show is refused with the availability
  reason, not "quantity"; the form rejects all-zero before `start` is reached.
- The moved-showtime warning is a warning toast on the drawer-save response,
  not an inline list, because the drawer closes on save.
- The summary's Upcoming/Past split is Eastern midnight today.
- `cancelled_with_orders` and the door list count orders that count as sold
  (PAID, or FAILED with a payment ID), not PAID only.
- Refund-all is refused server-side when the showtime is not cancelled.
- The sandbox completion check (Task 6 of the plan) was not run during
  implementation and is the first rollout step. If a fulfillment-free
  payment-link order does not reach COMPLETED on payment, `boxoffice/pull.py`
  needs an OPEN-order search by `reference_id` prefix `FK-` before the nightly
  report sees online sales.
- `TICKETS_BASE_URL` falls back to the scheme and host of `SQUARE_WEBHOOK_URL`.
  `support_email` falls back to `DEFAULT_FROM_EMAIL` because `SITE_CONFIG` has
  no cinema email.
- (2026-10-18, final review) Deleting a showtime or an engagement first
  looked at its online orders: any order that counted as sold, was
  REFUNDED, or was still holding seats refused the delete with "Has online
  orders. Cancel it instead.", before any Square call. Dead orders
  (EXPIRED, PENDING past the hold, FAILED without a payment) were deleted
  first, since `TicketOrder.showtime` is PROTECT.
- (2026-10-18, final review) The refund email chose its wording from
  `showtime.is_cancelled`: a staff refund on a running show said "has been
  refunded by the cinema" instead of claiming the show was cancelled.
- (2026-10-18, final review) The ticket page returned 404 on GET and POST for
  a draft or hidden run (availability's "not_listed"), whatever the Square
  setting, instead of showing its title, poster and time.
- (2026-10-18, final review) `tickets.spec.e164_phone` normalised the typed
  phone for Square's prefill (US numbers gained +1; anything unusable became
  blank), and the order kept the typed phone. `support_email` became the
  bare address of `DEFAULT_FROM_EMAIL`, or blank when unset or on
  `localhost`. `payment_link_body` left out `buyer_phone_number` and
  `merchant_support_email` when blank.
- (2026-10-18, final review) The ticket email's status write became
  conditional (only from PENDING, PAID or FAILED), so a staff refund made
  while the email was sending stayed REFUNDED.
- (2026-10-18, final review) The payment webhook skipped the membership
  handler's `process_order` for an order ID that belonged to a ticket order
  and went straight to `confirm_payment`.
- (2026-10-18, final review) The online allowance was capped at 10000 (same
  error message) and each ticket quantity at 20 (was 50).
- (2026-10-18, final review) The ticket info line under the showtimes read
  "Buy online from the showtimes above, or pay at the box office.", with the
  street as its own item, and Rollout gained the nightly
  `expire_ticket_orders` step.
- (2026-10-19, sandbox Part B) A paid payment-link order does **not** reach
  COMPLETED: Square adds a DIGITAL fulfillment (PROPOSED) and the order stays
  OPEN with its tender CAPTURED, so `search_orders` never returns it.
  Fixed 2026-10-20: `boxoffice/pull.py` also asks the gateway for OPEN orders
  updated in the day (`search_open_orders`; Square has no reference filter)
  and keeps the ones whose `reference_id` starts with `FK-` and that carry a
  tender. Such a line is dated by its payment time (`OrderData.paid_at`),
  so it does not move when staff close the order later, and its `closed_at`
  is null (`SaleLine.closed_at` became nullable, boxoffice 0009).
