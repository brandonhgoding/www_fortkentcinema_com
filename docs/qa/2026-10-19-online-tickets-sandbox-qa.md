# Online tickets: sandbox setup and manual QA checklist

Branch `feat/online-tickets` at `da0fbd2`. Spec:
`docs/superpowers/specs/2026-10-17-online-ticket-presale-design.md`.
Written 2026-10-19 from the code on the branch; constants quoted here come from
`web/constants.py`, `tickets/views.py` and `tickets/spec.py`.

Work through Part A first. It is the only check whose outcome changes code.
Everything after it can be done in any order. Tick boxes as you go and write
anything surprising in the "Findings" table at the end.

---

## Part A: sandbox setup

### A1. Square Developer dashboard (sandbox)

- [ ] Open https://developer.squareup.com/apps, pick the Fort Kent Cinema
      application, switch the toggle at the top to **Sandbox**.
- [ ] **Credentials tab:** copy the *Sandbox Access Token*.
- [ ] **Locations tab:** copy the sandbox *Location ID* (the default sandbox
      location is fine).
- [ ] Open the **sandbox Seller Dashboard** (Developer dashboard → Sandbox
      test accounts → Open). This is where you will later see the orders,
      payments and refunds the way the owner sees them in Square.
- [ ] In the sandbox Seller Dashboard create a category called **Movies**
      (Items → Categories). Then get its ID: Developer dashboard → API
      Explorer → Catalog → `ListCatalog`, `types=CATEGORY`, sandbox token.
      Copy the `id` of the Movies category.
- [ ] Note the test card values. Success: `4111 1111 1111 1111`, any future
      expiry, CVV `111`, any US postal code. For decline paths Square's
      sandbox uses special values (CVV `911` fails CVV, postal code `99999`
      fails address verification); confirm the current list at
      https://developer.squareup.com/docs/devtools/sandbox/payments before
      relying on them.

### A2. Tunnel

The redirect back from Square and the webhook both need a public URL.

- [ ] `ngrok http 8000` and copy the `https://….ngrok-free.app` host.
      Keep this terminal open; the host changes every time ngrok restarts and
      three settings below depend on it.

### A3. Webhook subscription (sandbox)

- [ ] Developer dashboard → **Webhooks** → Subscriptions, Sandbox toggle on →
      Add subscription. URL
      `https://<ngrok-host>/boxoffice/square/webhook/`. API version: the one
      the SDK in `requirements` uses. Events: tick **`payment.updated`** and
      **`payment.created`**. Do **not** tick `order.updated`.
- [ ] Copy the subscription's *Signature key*.

### A4. Local `.env`

Add or change these. Leave `DEBUG=True` so every email the app sends is
printed to the `runserver` console instead of being delivered.

```
SQUARE_ENVIRONMENT=sandbox
SQUARE_ACCESS_TOKEN=<sandbox access token>
SQUARE_LOCATION_ID=<sandbox location id>
SQUARE_TICKET_CATEGORY_ID=<sandbox Movies category id>
SQUARE_WEBHOOK_SIGNATURE_KEY=<subscription signature key>
SQUARE_WEBHOOK_URL=https://<ngrok-host>/boxoffice/square/webhook/
TICKETS_BASE_URL=https://<ngrok-host>
DEFAULT_FROM_EMAIL=Fort Kent Cinema <tickets@fortkentcinema.com>
ALLOWED_HOSTS=localhost,127.0.0.1,<ngrok-host>
CSRF_TRUSTED_ORIGINS=https://<ngrok-host>
```

Why each matters:

- All three `SQUARE_*` IDs must be present or the Buy button never appears
  (`boxoffice.gateway.disabled_reason`).
- `SQUARE_WEBHOOK_URL` must match the registered URL byte for byte; the
  signature is computed over it. Wrong value = every webhook is a 403.
- `TICKETS_BASE_URL` is what Square sends the buyer back to. Blank or
  `localhost` here means the buyer lands nowhere after paying.
- `DEFAULT_FROM_EMAIL` on a `localhost` domain makes `support_email()` return
  blank, so the Square checkout page shows no support address. Use a real
  looking domain to test the page as buyers will see it.
- `CSRF_TRUSTED_ORIGINS` is needed because you will submit the ticket form
  over the ngrok https origin.

- [ ] `.env` updated.
- [ ] `python manage.py migrate` (adds `tickets` tables and
      `Showtime.online_allowance`).
- [ ] `python manage.py runserver` and open `https://<ngrok-host>/`. The home
      page loads with no CSRF or host error.

### A5. Test data

- [ ] Both screens have a **real** capacity in the dashboard, not the 100
      placeholder. Default online allowance is half of capacity
      (`TICKET_ONLINE_SHARE = 0.5`), so a wrong capacity makes every
      sold-out test meaningless.
- [ ] One **confirmed** engagement with "show in main listings" on, ending
      in the future, with at least:
  - one **matinee** showtime starting at or before 4:00 PM, two or more
    days out;
  - one **evening** showtime starting after 4:00 PM, two or more days out;
  - one showtime starting **within the next 30 minutes** (for the cutoff
    test; create this one right before you need it).
- [ ] The engagement has a live Square item. Saving it in the dashboard
      pushes one; or run `python manage.py sync_square_catalog --dry-run`
      then without `--dry-run`. The Square pill on the engagement is green,
      and the item appears in the sandbox Seller Dashboard under Movies with
      Adult $8, Senior $7, Child $6 variations.
- [ ] A second confirmed engagement with **no** Square item (don't save it
      after the Square settings went in, or delete its item in Square and
      skip the nightly reconcile). Used in B10.
- [ ] Admin → Box Office → Email reports has at least one recipient, so the
      nightly pull has someone to report to (it will print to the console).

---

## Part B: the decisive check (spec Section 2, plan Task 6)

This settles whether a fulfillment-free payment-link order reaches
`COMPLETED` on payment. The nightly pull filters on that state. If it does
not, online sales silently vanish from the sales reports until
`boxoffice/pull.py` gains an OPEN-order search by the `FK-` reference prefix.

- [ ] **B1.** Buy one adult ticket for the evening showtime through the site
      (steps in C1 below) and pay with the success card.
- [ ] **B2.** In `python manage.py shell`:

```python
from boxoffice.gateway import get_gateway
from boxoffice.pull import day_bounds
from tickets.models import TicketOrder
import datetime
g = get_gateway()
o = TicketOrder.objects.latest("created_at")
od = g.retrieve_order(o.square_order_id)
# closed_at is set only once Square considers the order COMPLETED.
print("closed_at:", od.closed_at, "paid_at:", od.paid_at)
print("tenders:", od.tenders)
found = [x for x in g.search_orders(*day_bounds(datetime.date.today()))
         if x.order_id == o.square_order_id]
print("in COMPLETED search:", bool(found))
```

- [ ] **B3.** Record in the Findings table: whether `closed_at` was set, the
      tender `status` string, and whether the order was in the
      `search_orders` results.
- [ ] **B4.** Open the order in the sandbox Seller Dashboard (Orders) and
      confirm it shows as completed/paid with no fulfillment to mark.

**Outcome:**

- In the search results → the pull works as designed. Add an Amendments
  entry to the spec with the date and the tender status string.
- Not in the search results → stop here, report it. The pull needs the
  second query before launch. Everything else in this document is still
  worth running.

---

## Part C: public purchase flow

Pages: ticket page `/tickets/<showtime pk>/`, confirmation page
`/tickets/order/<token>/`, QR `/tickets/order/<token>/qr.png`.

### C1. Evening happy path

- [ ] Home page: the evening showtime chip shows as purchasable (links to
      `/tickets/<pk>/`). Non-purchasable chips are plain text.
- [ ] Ticket page shows the film title, date and time, and three tiers with
      prices **Adult $8, Senior $7, Child $6**. No "left online" note unless
      remaining is small.
- [ ] Set Adult 1, Senior 1, fill name, email, a phone typed as
      `(207) 555-0100`. Submit.
- [ ] You are redirected to Square's hosted checkout. On that page: the two
      lines read "Adult" and "Senior" at $8 and $7, no tipping prompt, no
      shipping address, email and phone are pre-filled, the support email
      is shown, Apple Pay / Google Pay buttons are present where the browser
      supports them.
- [ ] Pay with the success card.
- [ ] You land on `/tickets/order/<token>/`. Within a few seconds (the page
      refreshes every 4 s while "Confirming your payment") it switches to the
      paid view with the order number, film, showtime, ticket lines, the
      cinema address and the QR image.
- [ ] The QR image URL `…/qr.png` loads directly.
- [ ] `runserver` console shows **one** ticket email to the buyer with the
      order number, showtime, lines, total, and a QR attachment.
- [ ] Dashboard → Tickets → Orders: the order is **PAID** with a Square
      payment ID and `paid_at`.
- [ ] Sandbox Seller Dashboard → Transactions: the payment is there with
      the `FK-…` reference.

### C2. Matinee pricing

- [ ] Ticket page for the matinee showtime shows every tier at **$6**.
- [ ] Buy Adult 2. On Square's page each line is still named by tier, the
      per-line discount brings the line to $6 each, total $12.
- [ ] Pay. Order is PAID; the email total reads $12.

### C3. Form validation (each submit stays on the ticket page with a message)

- [ ] All quantities 0 → refused.
- [ ] Adult 21 → refused (max 20 per tier).
- [ ] Phone `12345` → refused. Phone `+1 207 555 0100` → accepted.
- [ ] Missing name or email → refused.
- [ ] Fill the hidden `website` field (browser dev tools) → honeypot:
      submission is swallowed without creating an order.

### C4. Confirmation page states

- [ ] Reload the paid page from C1: still paid, no second email in the
      console, no change in the order log.
- [ ] Guess a token (edit a character in the URL) → 404.
- [ ] Start a checkout and **close the Square tab without paying**. Open the
      confirmation URL (it is in the order log, or build it from the token
      in the admin). For the first 2 minutes it shows "Confirming your
      payment" with the refresh meta; after 2 minutes it shows the waiting
      message with no refresh meta.

### C5. Payment confirmation when the webhook is missing

Tests the recovery path (`RECOVER_AFTER = 60 s`).

- [ ] Developer dashboard → Webhooks → **disable** the sandbox subscription.
- [ ] Buy one adult, pay. The confirmation page stays on "Confirming your
      payment".
- [ ] After 60 seconds, reload. The page fetches the order from Square, finds
      the completed tender, flips to **paid**, and the email is sent once.
- [ ] Re-enable the subscription. Buy again and confirm the webhook path
      works again (paid within seconds, no reload needed).
- [ ] Developer dashboard → Webhooks → Logs: each event to your URL got a
      **200**. A 403 means the signature key or `SQUARE_WEBHOOK_URL` is
      wrong.

### C6. Hold and expiry (`TICKET_HOLD_MINUTES = 20`)

- [ ] Dashboard → the evening showtime → set the online allowance to **3**.
- [ ] Start a checkout for 2 tickets and do not pay. The ticket page now
      shows "1 left online". The engagement page's sold figure counts the
      hold.
- [ ] Run `python manage.py expire_ticket_orders` **before** 20 minutes have
      passed. Output "Expired 0 order(s)"; order is still PENDING.
- [ ] Wait until the order is 20 minutes old (or edit `created_at` back in
      the admin). The ticket page shows "3 left online" again even before
      the command runs.
- [ ] Run the command again: "Expired 1 order(s)". Order log shows
      **EXPIRED**. Its confirmation page reads "Checkout expired" with a
      "Start again" link to the ticket page.
- [ ] **Late payment:** open the Square checkout URL for that expired order
      (`square_checkout_url` on the order row in the admin) and pay it. The order flips to
      **PAID** and the email goes out. This is the known gap recorded in the
      follow-ups (links are not deleted on expiry); note whether it
      happened as described.

### C7. Availability rules (reason strings in `tickets/availability.py`)

- [ ] **Sold out:** allowance 1, buy and pay 1. Home chip is plain text; the
      ticket page says sold out and has no form.
- [ ] **Allowance lowered below sold:** allowance 3, sell 2, set allowance to
      1. Page shows sold out; both orders remain PAID; nothing is refunded.
- [ ] **Race:** allowance 1 (0 sold). Open the ticket page in two browser
      tabs, submit 1 adult in both. First redirects to Square; second is
      refused with a message. Only one PENDING order exists.
- [ ] **Cutoff (`TICKET_CUTOFF_MINUTES = 30`):** a showtime starting in 25
      minutes shows no Buy link and `/tickets/<pk>/` has no form.
- [ ] **Cancelled:** cancel a showtime in the dashboard. Its chip and page
      stop selling.
- [ ] **Not listed:** uncheck "show in main listings" on the engagement, or
      set its status to anything but confirmed. `/tickets/<pk>/` is a **404**
      and the home chip is plain text.
- [ ] **No Square item:** the second engagement from A5 shows no Buy link
      even though it is confirmed and listed.
- [ ] **Square off:** blank `SQUARE_ACCESS_TOKEN`, restart. No Buy links
      anywhere; the rest of the site is unchanged. Restore the token.

### C8. Gateway failure on checkout

- [ ] Set `SQUARE_ACCESS_TOKEN` to a garbage value, restart. Submit the
      ticket form. Page shows the retry sentence; order log has a **FAILED**
      order with the Square error text and no payment ID; the dashboard home
      shows a ticket-failures alert. Restore the token.

---

## Part D: dashboard

URLs: door list `/dashboard/showtimes/<pk>/orders` (+ `.csv`), summary
`/dashboard/tickets`, order log `/dashboard/tickets/orders` (+ `.csv`).

### D1. Door list

- [ ] Lists every PAID order for the showtime: buyer name, tier quantities,
      order number. PENDING, EXPIRED, FAILED-before-payment and REFUNDED
      orders are not on it.
- [ ] **Arrive** on a row marks it arrived; **Unarrive** reverses it. Reload
      keeps the state.
- [ ] CSV export opens in a spreadsheet with the same rows.
- [ ] Allowance control on the same page: change the number, save, the
      ticket page's remaining count follows.

### D2. Pre-sale summary and order log

- [ ] Summary shows per-showtime sold / allowance / gross for upcoming
      showtimes. Gross matches what Square shows.
- [ ] Order log lists every order with status, number, buyer, showtime,
      totals; filters or sorting work as the page offers them.
- [ ] CSV export of the log matches the page.
- [ ] Engagement page shows the online sold figure per showtime (paid plus
      holds).

### D3. Retry a failed ticket email

Optional; needs the email path to fail. Run once with `DEBUG=False`,
`EMAIL_HOST=127.0.0.1`, `EMAIL_PORT=1`, `runserver --insecure`.

- [ ] Buy and pay. Order becomes **FAILED** with "Ticket email failed" and a
      payment ID; it still counts as sold on the door list and summary.
- [ ] Home shows the ticket-failures alert.
- [ ] Restore email settings, restart, click **Retry** on the order. It
      becomes PAID and one email prints to the console.

### D4. Single refund

- [ ] Order log → **Refund** on a PAID order (confirm dialog). Order becomes
      **REFUNDED**; a cancellation/refund email prints; Seller Dashboard
      shows the refund; door list no longer lists it; summary gross drops.
- [ ] Clicking Refund again on the same order is not offered or does
      nothing.

### D5. Cancel a showtime with orders, refund all

- [ ] Sell 2 orders for a showtime, then cancel the showtime. Dashboard home
      shows the "cancelled with orders" alert. The door list shows the red
      "This showtime is cancelled. 2 online orders still need refunding."
      with a **Refund all** button.
- [ ] Click Refund all, confirm the dialog (it quotes the count and dollar
      total). Both orders become REFUNDED; two refund emails print; both
      refunds appear in the Seller Dashboard; the alert clears.
- [ ] Un-cancel the showtime: refunded orders stay REFUNDED, nothing is
      resold.

### D6. Home alerts

- [ ] **Nearly sold out:** a showtime within 2 days at 90%+ of allowance
      (allowance 10, sell 9) appears in the home alert with sold/allowance.
- [ ] Ticket-failures alert appears after C8 and clears when the FAILED
      order is dealt with (Retry, or as the page offers).

---

## Part E: reporting (nightly pull)

Only meaningful if Part B passed.

- [ ] `python manage.py pull_square_sales --days 1`. Output reports the
      orders and lines pulled; no errors.
- [ ] Dashboard home sales panel: yesterday/today tickets and gross include
      the online sales. Matinee lines total **$6** each, not $8.
- [ ] Admin → Box Office → the pull's stored lines carry the `FK-` reference
      and the ticket variation IDs. Engagement admissions were recomputed.
- [ ] The daily report email printed to the console lists the online sales
      with the rest.
- [ ] Known limitation to confirm, not fix: a refunded order from D4 is still
      counted in the pull's admissions (spec, out of scope).

---

## Part F: on a phone

Open the ngrok URL on a real phone.

- [ ] Home page chips: purchasable chip is distinguishable, tappable, and
      does not wrap badly.
- [ ] Ticket page: tier steppers usable with a thumb, number inputs show a
      numeric keyboard, no horizontal scroll, submit button reachable.
- [ ] Square checkout: Apple Pay / Google Pay offered where available.
- [ ] Confirmation page: QR is large enough to scan from another phone's
      camera; the address line reads correctly.
- [ ] Ticket email on a phone mail client: QR attachment opens.

---

## Part G: wrap up

- [ ] Add a spec Amendments entry with the Part B result (date, order state,
      tender status string).
- [ ] Reset the sandbox allowances you changed, un-cancel test showtimes, and
      delete or leave the test engagement.
- [ ] Decide the production rollout order (spec Rollout, steps 2 to 6).

### Findings

| # | Step | What happened | Expected | Severity (blocks launch / fix soon / note) |
|---|------|---------------|----------|---------------------------------------------|
| 1 | B3 | closed_at: not set; tender status: CAPTURED; in search: no. The order stays OPEN with a Square-added DIGITAL fulfillment (PROPOSED). | In the COMPLETED search | blocks launch; fixed 2026-10-20 (`search_open_orders` + `FK-` filter in `boxoffice/pull.py`, spec Amendments) |
| | | | | |
