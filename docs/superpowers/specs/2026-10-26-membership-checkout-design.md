# Membership checkout — join or renew on the site, pay on Square — Design

**Date:** 2026-10-26
**Status:** Implemented on feat/membership-checkout (see Amendments)
**Repo:** `www_fortkentcinema_com` (branch: `feat/membership-checkout`)
**Builds on:** `2026-10-17-online-ticket-presale-design.md` (the `tickets`
app: pending order, hosted checkout, order page, webhook handler),
`2026-10-09-square-membership-webhook-design.md` (`process_order`, the
`MembershipSale` row, the Square Sales list), `2026-09-13-membership-tier-catalogue-design.md`
(tiers, `square_variation_id`), `2026-10-24-member-registration-design.md`
(member accounts and the member home)

## Context

`/membership/` lists the tiers and sends people to the box office. The
Join buttons were removed on 2026-10-24 because memberships were sold in
person; this work reverses that decision. Each tier still carries a Square
payment link (`checkout_url`) and the Square variation ID of its item.
Sales through those links reach the roster through the payment webhook,
which fetches the order from Square and reads the buyer from the shipment
recipient that Square's payment-link checkout collects.

Online tickets already do what memberships need: a public form, a PENDING
order row, a Square hosted checkout built from our own line items with an
explicit price, a redirect back to an order page that trusts only our row,
a registered webhook handler that claims its own orders, and an email on
payment. Members can sign in, and the member home shows the roster row
whose email matches the account.

## Goal

A visitor picks a tier on the membership page, types their name and
email, pays on Square's hosted checkout, and their member row and term
appear in the roster correctly dated, with no staff typing. A signed-in
member renews from their member home the same way. The buyer gets a
welcome email. Staff see website sales beside payment-link sales on the
existing Square Sales list, with the same Retry.

## Decisions (made with the owner, 2026-10-26)

- **New joiners and renewals.** Anyone can join from `/membership/`. A
  signed-in member also gets a Renew button on the member home that
  prefills their details. A returning email renews correctly either way,
  through the webhook's existing rule.
- **Name and email only.** First name, last name, email, plus the tier.
  Matches the roster exactly (phone was dropped in the PII reduction).
  Square's checkout collects the card and billing details itself.
- **No account is created by a purchase.** The order page and the welcome
  email invite the buyer to register at `/register` with the same email.
  Registration stays the one way accounts are made.
- **One shared entry path.** The website order is handed to the existing
  `process_order`, which already fetches the order, matches the tier,
  dates a renewal and writes the `MembershipSale` row. The website path
  supplies the buyer through a hook; `boxoffice` never imports the new
  app.
- **No hold, no nightly expiry.** A membership has no stock, so a PENDING
  row blocks nobody. A payment arriving on a stale link still counts.

### Explicitly out of scope

- Creating accounts at purchase, or signing the buyer in.
- Gift memberships (buying for a different email than your own is
  possible but not designed for: the term lands on whoever's email is
  typed).
- Household names for family tiers. Family cover stays honour-system.
- Refunds of memberships, by buyer or staff. A refunded membership keeps
  its term until staff remove it, as today.
- Removing the legacy payment links or `checkout_url`. They keep working
  through the unchanged webhook path and are simply no longer linked.
- Member ticket pricing online (still Phase 3 of the ticket spec).
- Per-order GA4 deduplication. The order page fires the purchase event on
  each PAID render, like `/thanks` did on each visit.

## Section 1: shape and purchase flow

### The `join` app

A new Django app, `join`, listed after `tickets` in `INSTALLED_APPS`. It
holds the order model, the form, two public views, the checkout spec, the
welcome email, and an `apps.ready` that registers itself with `boxoffice`.
It imports `audience` (tiers, members, terms) and `boxoffice` (gateway,
customers, `process_order`, `MembershipSale`); nothing imports it.

### Flow

1. **Pick.** Every tier card on `/membership/` gets a "Join" button to
   `/membership/join/<slug>/`. A listed tier with a blank
   `square_variation_id` shows "Join at the box office" in place of the
   button and its join page answers 404.
2. **Fill in.** The join page shows the tier (eyebrow, name, price,
   length, perks, family note) beside a form: first name, last name,
   email, and the hidden `website` honeypot used by the ticket form. For
   a signed-in user, email is prefilled from the account and the names
   from the matching roster row when there is one; all three stay
   editable.
3. **Reserve.** Submitting creates a `MembershipOrder` (PENDING) with the
   tier's price as `total_cents`, looks up or creates the buyer's Square
   customer (`boxoffice.customers.ensure_customer`, see Section 3), then
   asks Square for a payment link (`checkout.payment_links.create`) whose
   order carries:
   - `location_id` from settings, `reference_id` = our order number, no
     `metadata` (the `showtime` key is a ticket thing);
   - one line: `catalog_object_id` = the tier's `square_variation_id`,
     name = the tier's name, quantity 1, explicit `base_price_money` =
     `tier.price × 100`, no discount;
   - no fulfillment, so Square's recipient stays empty and the order
     completes on payment;
   - `checkout_options`: `redirect_url` = our order page with the token,
     shipping address off, tipping off, support email, Apple Pay and
     Google Pay on, exactly as tickets;
   - `pre_populated_data.buyer_email`; no phone;
   - `idempotency_key` = the order token.
   The response's `order_id` and `url` are stored and the buyer is sent to
   the URL with a 303. A gateway failure leaves the order ABANDONED with
   the error recorded and shows "We couldn't start checkout. Please try
   again, or join at the box office."
4. **Pay and return.** Square redirects to `/membership/order/<token>/`.
   The page reads our row only. PAID: the welcome (Section 4). PENDING
   inside two minutes of creation: "Confirming your payment" with a
   refresh. PENDING after 60 seconds: the view asks Square for the order
   first (`recover_pending`, below), then renders what it finds. FAILED:
   "Payment received. We're finishing your membership and will email
   you." ABANDONED: "This checkout didn't start. Try again." with a link
   to the join page.
5. **Confirm.** `boxoffice.views.square_webhook` offers the COMPLETED
   payment to the registered handlers. The `join` handler claims it when
   a `MembershipOrder` carries that `square_order_id`, and calls
   `process_order(order_id)`. The existing code fetches the order from
   Square, finds the membership line by variation ID, takes the buyer
   from the registered order source (Section 3), creates or renews the
   member, dates the term (the day after current cover ends for an active
   member, the purchase date for a lapsed one), and writes the
   `MembershipSale` row. `process_order` then calls the source's
   `record`, which sets the `join` row PAID and sends the welcome email.
   The handler returns True; a repeated event for a finished sale does
   nothing and returns True.

### Recovery

`recover_pending(order)` mirrors `tickets.orders.recover_pending`: fetch
the Square order; if any tender is paid, call `process_order` the same
way the webhook would (the paid payment ID and time are on the order the
hook records). Square unreachable: log a warning, leave the row as it
is. Only the order page calls it; there is no nightly command.

### Webhook return codes

Unchanged. `process_order` records its own failures on the sale row, and
the 503 rule for a never-fetched order applies to website orders too, so
a Square outage during the fetch gets Square's retry.

## Section 2: data model

### `join.MembershipOrder`

One row per checkout attempt.

| field | type | notes |
|---|---|---|
| `number` | `CharField(12, unique)` | `FKM-` + 5 characters from the ticket alphabet (no 0/O/1/I); on the Square order as `reference_id` and in the email |
| `token` | `CharField(43, unique)` | `secrets.token_urlsafe(32)`; the order URL |
| `tier` | `FK(audience.MembershipTier, PROTECT, related_name="orders")` | |
| `first_name`, `last_name` | `CharField(100)` | as typed, stripped; the roster's widths |
| `email` | `EmailField` | lowercased, stripped |
| `status` | choices PENDING / PAID / FAILED / ABANDONED | FAILED = paid, term not entered (staff Retry); ABANDONED = Square refused the link |
| `square_order_id` | `CharField(64, blank, default "")`, partial unique on non-blank | the handler's lookup key |
| `square_payment_id` | `CharField(64, blank, default "")` | from the webhook event or the recovered tender |
| `square_checkout_url` | `URLField(blank)` | "Return to payment" on the pending page |
| `square_customer_id` | `CharField(64, blank, default "")` | |
| `total_cents` | `PositiveIntegerField` | the tier's price at checkout |
| `error` | `TextField(blank)` | why FAILED or ABANDONED; cleared when PAID |
| `created_at` | `auto_now_add` | |
| `paid_at` | `DateTimeField(null)` | from the sale |
| `term` | `FK(audience.MembershipTerm, SET_NULL, null)` | the term the sale created |
| `sale` | `FK(boxoffice.MembershipSale, SET_NULL, null)` | the ledger row |

Indexes: `(status, created_at)`. The email is normalised in `save()` as
`TicketOrder` does.

### `audience.MembershipTier`

`clean()` no longer requires `checkout_url` on a listed tier. The field
and its help text stay ("The legacy Square payment link; no longer
linked from the site"). No schema change.

### `boxoffice.MembershipSale.source`

`CharField(8, choices LINK / WEBSITE, default LINK)`. Migration
`boxoffice.0014` adds it; existing rows read LINK.
`process_order` sets WEBSITE when the buyer came from an order source.

## Section 3: the shared entry point

Three changes in `boxoffice`, none of which alter the payment-link path's
behaviour.

### `CheckoutSpec` without a showtime

`CheckoutSpec.showtime_id` becomes `int | None = None`, and
`payment_link_body` writes `metadata.showtime` only when it is set.
`tickets.spec.checkout_spec` is unchanged in effect. `OrderData.showtime_id`
already allows None.

### `boxoffice.customers`

`tickets.customers.ensure_customer(gateway, order)` moves to
`boxoffice/customers.py` as
`ensure_customer(gateway, *, first_name, last_name, email, phone, key, label)`:
`phone` is already E.164 or "", `key` seeds the idempotency keys
(`customer-<key>`, `customer-<key>-nophone`), `label` is the order number
for the log line. `tickets.customers` becomes a two-line wrapper, or the
ticket call site is updated and the module deleted. `e164_phone` stays in
`tickets.spec`; `join` never sends a phone. Same behaviour, same tests
moved with it.

### Order sources in `boxoffice.memberships`

```
class OrderSource(Protocol):
    def buyer_for(self, order_id: str) -> Buyer | None: ...
    def record(self, order_id: str, sale: MembershipSale) -> None: ...

def register_order_source(source: OrderSource) -> None: ...
```

`_Buyer` is renamed `Buyer` and exported. `process_order`, after the
fetch and the membership-line check:

1. Builds the buyer from Square's recipient as today.
2. If the recipient is empty, asks each registered source in turn for
   `buyer_for(order_id)`; the first non-None answer is the buyer and the
   sale's `source` becomes WEBSITE. The register-sale skip ("No buyer
   email") applies only when no source answers either.
3. After `_attribute` returns, calls `record(order_id, sale)` on the
   source that answered, outside the sale's transaction, inside a
   `try`/`except` that logs and swallows, so a broken `record` cannot
   undo an entered term or turn a 200 into a 500. The early failures
   (gateway disabled, fetch failed) happen before any source has been
   asked, so they offer `record` to every registered source with the
   FAILED sale; a source ignores an order it does not hold. The website
   order then reads FAILED until Square's retry of the 503 enters it.

The `join` source: `buyer_for` returns the order's typed name (as
`display_name`, since `split_name` is what `_member` uses; the row keeps
the two fields) and email for a PENDING, FAILED or PAID order with that
`square_order_id`, else None. `record` locks the row and:

- sale OK: set `term`, `sale`, `paid_at` = `sale.paid_at`,
  `square_payment_id` from the event when the caller passed one (the
  handler stores it on the row before calling `process_order`), status
  PAID, error cleared. Send the welcome email only when the status
  changed to PAID in this call.
- sale FAILED: status FAILED, `error` = `sale.error`, `sale` set. No
  email.
- sale SKIPPED cannot happen for a sourced order; treated as FAILED with
  the sale's error.

Because `record` runs from `process_order`, the dashboard's Retry button
needs no change: retrying a website sale updates the order and sends the
email the same way.

### The `join` handler

`join.orders.handle_square_payment(order_id, payment_id, paid_at, amount_cents)`:
True when a `MembershipOrder` has that `square_order_id`, after storing
`payment_id` on it and calling `process_order(order_id)`. Everything
else is False. Registered in `join.apps.ready` with
`register_payment_handler`; no refund or dispute handlers (out of scope,
as for payment-link sales). `amount_cents` is logged when it differs
from `total_cents`, nothing more: `process_order` records what Square's
order says was paid, as it does for link sales, and Square charges the
line we set.

## Section 4: pages and copy

### `/membership/`

- `partials/tier_card.html` gains, after the perks, a Join button
  (`btn btn-primary`, labelled "Join") linking
  to `join:start` with the slug, or the sentence "Join at the box
  office" when the tier has no variation ID. The home page's membership
  band includes the same partial through `home_membership.html`; the
  button appears there too, which is the point.
- The note under the grid: "Regular admission is $X ($Y for matinees);
  members pay $Z. Join online below, or at the box office before any
  show. There's no card to carry: after that, your name is all we need."
- The closing block: "Ready to join?" / "Pick a tier above and you'll be
  a member in a minute. Or stop by the box office before any show." with
  the button "Choose a tier" → `#tiers`.
- `MEMBERSHIP_FAQ`, first answer: "The length shown on your tier,
  counted from the day you join. Your welcome email and your member page
  show the exact end date." The FAQ JSON-LD follows automatically.

### Join page `/membership/join/<slug>/`

`join/templates/join/start.html`, in the ticket page's layout and
classes: the tier card on one side, the form on the other, "Pay $35 on
Square" as the submit. Beneath the form: "You'll pay on Square's secure
checkout and come straight back here." Errors shown inline. A GET for a
tier that is not listed or has no variation ID is a 404. The page is
`noindex`.

### Order page `/membership/order/<token>/`

`join/templates/join/order.html`. PAID: heading "Welcome, <first
name>" for a first term, or "You're renewed" when the member had an
earlier term (the sale's member has more than one term); the tier
name; "Your membership runs <started_on> through <expires_on>"; "There's
no card to carry. Give your name at the box office."; and "Want to see
your membership online? Create an account with <email>." linking to
`/register`. For a signed-in user whose email matches, that last line
instead links to `/dashboard/` as "See your membership". It fires the
GA4 `purchase` event with the tier's price and slug, the same call
`web/thanks.html` makes, now behind a verified payment. PENDING, FAILED
and ABANDONED as in Section 1. `noindex`, `never_cache`.

### Welcome email

`join/mail.py::send_welcome(order)`, text and HTML
(`join/templates/join/email/welcome.{txt,html}`), subject "Welcome to
Fort Kent Cinema" or "Your Fort Kent Cinema membership is renewed". Body:
tier, dates, "give your name at the box office", the register invite with
the `/register` link, and the order number. Sent through the same
`EmailMultiAlternatives` pattern as the ticket email, no QR. A failed
send leaves the order PAID (the term exists) and logs an error for
`ADMINS`; there is no resend button in this pass.

### Member home

`dashboard/member_home.html` gets a "Renew" button linking to
`join:start` for the latest term's tier when the member's status is
active, expiring or lapsed, with "or choose a different tier" linking to
`/membership/#tiers`. Hidden when the status is "Not started yet" or
when that tier is no longer listed or has no variation ID (then only the
"choose a tier" link shows). The join page prefills from the account and
roster as in Section 1.

## Section 5: dashboard

The Square Sales list (`dashboard/square_sales.html` and
`_square_sale_row.html`) gains a Source column reading "Website" or
"Payment link", and its empty-state copy becomes "They'll show up here
when someone joins on the website or pays through a membership link."
The page title stays. Retry is unchanged and now also updates the
website order and sends the email (Section 3).

Pending and abandoned website orders are listed nowhere: they block
nothing and need no action. The admin registers `MembershipOrder` read-
mostly (list, search by number and email, no add) for the rare
investigation.

## Section 6: edge cases and errors

- **Email already on the roster.** The existing rule: the term is added
  to that member, the typed name stays on the sale row for staff to
  compare, and the member's names are never overwritten. The order page
  says "You're renewed" because the member now has more than one term.
- **Email already on the roster with an unexpiring term.** `_create_term`
  refuses ("Current term never expires"); the sale is FAILED, the order
  FAILED, staff see it on the list. Same as a link sale.
- **Two tabs, two orders.** Each is its own Square order; paying both
  makes two terms, the second dated after the first. Same as paying a
  link twice. Not guarded.
- **Webhook before the row stores the Square order ID.** Not possible:
  the ID is written before the buyer is redirected, and the payment
  cannot happen before that.
- **Repeated events.** The sale row's idempotency and locks are
  unchanged. `record` is idempotent; the email is sent once, on the
  transition to PAID.
- **Short payment.** `process_order` records what Square's order says
  was paid, so a term's `price_paid` is always the truth. A mismatch
  with `total_cents` is logged by the handler.
- **Tier changed between form and payment.** The line carries an
  explicit price, so the buyer pays what the page showed. The term's
  tier is matched by variation ID from Square's order, not from the row,
  so the two agree.
- **Square sync disabled.** The join page shows "Online membership
  sign-up isn't available right now. Join at the box office before any
  show." instead of the form, the same test the ticket page makes
  (`get_gateway() is None`), and the tier cards show the box-office
  sentence.

## Section 7: testing and rollout

TDD throughout, the test baseline green before and after.

- `join/tests`: `start()` (row, customer, link body with one line and an
  explicit price, ABANDONED on gateway failure), `handle_square_payment`
  (claims own order only, calls `process_order`), the order source
  (`buyer_for` by status, `record` for OK / FAILED, email once),
  `recover_pending`, the start view (prefill, honeypot, 404s, disabled
  gateway), the order page states, the welcome email content.
- `boxoffice/tests`: `process_order` with a registered source (buyer
  taken, source WEBSITE, `record` called after OK and after early
  failures, a raising `record` is swallowed), no source (register skip
  unchanged), `CheckoutSpec` without showtime, `ensure_customer` moved.
- `web/tests`: tier card with and without the button, the copy changes.
- `dashboard/tests`: member home Renew button by status, Source column.
- `boxoffice.tests.fakes.FakeGateway`: already records `create_payment_link`
  and serves `retrieve_order`; extended only if the membership line
  needs it.

Rollout: the five live tiers already carry their variation IDs
(webhook spec, step 2). Run one real checkout in the sandbox and watch
the roster, the Square Sales row (Source: Website) and the email. No new
settings, cron or webhook events: `payment.updated` is already
subscribed. Deploy runs `migrate` for `join.0001` and `boxoffice.0014`.

## Amendments (planning, 2026-10-26)

- **No `join` payment handler.** The webhook already calls `process_order`
  for any completed payment no handler claims, and the ticket handler
  claims only its own orders. The order-source hook does everything the
  handler would have: `buyer_for` supplies the buyer, `record` updates the
  join row. Dropping the handler keeps the existing 503 rule (a
  never-fetched order gets Square's retry) without extra code, and
  `recover_pending` on the order page calls `process_order` the same way.
  Section 1 step 5, "Recovery", and "The `join` handler" in Section 3 read
  accordingly; `join.apps.ready` registers only the order source.
- **`record(order_id, sale, order)`.** The callback also receives the
  fetched `OrderData` (None on the early failures), so the join row can
  store `square_payment_id` from the first paid tender.
- **`Buyer` carries the split name.** `Buyer(display_name, email, phone,
  first_name="", last_name="")`; `_member` uses the two fields when either
  is set and `split_name(display_name)` otherwise, so "Ann van Dyke" typed
  as two fields is stored as typed.
- **The home page band does not include the tier card.** Only
  `/membership/` shows the Join buttons; the band's one button still
  links to `/membership/`.
- **Note copy.** "Join online from any tier above, or at the box office
  before any show." (the note sits under the cards, not above them).
- **`base_url()` and `support_email()` move to `boxoffice/site.py`**
  beside the moved `ensure_customer`, so `join` never imports `tickets`.
  `tickets.spec` imports them from there.
