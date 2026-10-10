# Square membership webhook — paid in Square, entered in Django — Design

**Date:** 2026-10-09
**Status:** Implemented on feat/square-membership-webhook (see Amendments)
**Repo:** `www_fortkentcinema_com` (branch: `feat/square-membership-webhook`)
**Builds on:** `2026-10-05-square-sync-design.md` (the `boxoffice` app and
its gateway), `2026-09-11-membership-records-design.md` (members and terms)

## Context

Memberships are sold through five Square payment links, one per tier. When
someone pays, Square has the sale and the buyer's details, and Django has
nothing until staff notice the Square email and retype the person into the
roster. The Square sync spec deferred real-time events; this is the one
event it named as worth having.

A reading of the live account (2026-10-09) found:

- Five hand-made membership items, each with one `Annual` variation, no
  category and no SKU. The variation IDs are stable; the names are not
  guaranteed to be.
- Payment-link orders have `source.name = "Payment Links"`, no
  `customer_id`, and a `SHIPMENT` fulfillment whose recipient carries
  `display_name`, `email_address` and `phone_number`. That is where the
  buyer lives.
- Nine membership orders since June, all one line of quantity one.
- Square's `order.updated` event payload is a stub: order ID, location,
  state, version, timestamps. No line items, no buyer.

The site already has one webhook pattern, the Twilio phone line: a
decorator that verifies the signature, a base-URL setting for the public
address, 403 on anything unsigned, and no side effects before the check.
The Square SDK ships `square.utils.webhooks_helper.verify_signature`, so
the same shape carries over.

## Goal

When a membership is paid for through a Square payment link, the member
and their term appear in the roster within seconds, with the right tier,
dates and price, and nobody retypes anything. When the site cannot do
that, staff see why on the dashboard and can retry.

## Decisions (made with the owner, 2026-10-09)

- **Register sales are skipped.** A membership rung up at the counter has
  no buyer email. It is recorded as SKIPPED, raises no alert, and is
  entered by hand as today.
- **A known email is a renewal, dated like the Renew button.** The new
  term starts the day after current cover ends for an active member, or
  on the purchase date for a lapsed one, via the existing `latest_term`
  and `renewal_start` helpers.
- **Every membership event is recorded; failures alert and can be
  retried** from the dashboard, the same shape as the Square sync pill.
- **Fetch, don't trust.** The view acts on the order it fetches from
  Square by ID, never on the payload's contents beyond the ID and state.
- **Act in the request.** No queue. Square allows ten seconds; the
  gateway client already has a ten-second timeout. Five sales a week do
  not justify a worker.

### Explicitly out of scope

- Generating payment links or membership items from tiers (Phase 2 of the
  Square sync spec; still designed, still not built).
- Refunds. A refunded membership keeps its term until staff remove it.
- Verifying the payment behind `/thanks`. The page keeps trusting the
  redirect.
- Backfilling the payment-link sales already in Square. Same call as the
  term backfill and the ticket backfill: no importer for a one-time job.
- Updating an existing member's name from what the buyer typed.
- Subscribing to any event other than `order.updated`.

## Section 1: endpoint and flow

### Route

`POST /boxoffice/square/webhook/`, name `boxoffice:square_webhook`. The
`boxoffice` app gets its first `urls.py`, included from the project
`urls.py` under `boxoffice/`.

### Signature

A `square_webhook` decorator in `boxoffice/decorators.py` mirrors
`phone.decorators.twilio_webhook`:

- `csrf_exempt` and `require_POST`.
- Reads `settings.SQUARE_WEBHOOK_SIGNATURE_KEY` and
  `settings.SQUARE_WEBHOOK_URL`. Either blank: log an error, return 403.
- Verifies `X-Square-HmacSha256-Signature` with
  `verify_signature(request_body=request.body.decode(), signature_header=...,
  signature_key=..., notification_url=settings.SQUARE_WEBHOOK_URL)`.
  Mismatch: log a warning, return 403.
- The wrapped view runs only after the check, so a rejected request has
  no side effects.

`SQUARE_WEBHOOK_URL` is the exact notification URL registered in Square,
because the signature is computed over it. It is a setting rather than
`build_absolute_uri()` for the same reason `TWILIO_WEBHOOK_BASE_URL`
exists: behind nginx the rebuilt URL is wrong without proxy headers.

### View

`boxoffice/views.py::square_webhook`:

1. Parse the JSON body. Unparseable: 400. (Square will retry; a 400 on a
   malformed body is correct and visible in Square's webhook log.)
2. `type != "order.updated"`: 200, nothing recorded.
3. `data.object.order_updated.state != "COMPLETED"`: 200, nothing
   recorded. Other states are open or cancelled orders.
4. `order_id = data.object.order_updated.order_id`. Call
   `boxoffice.memberships.process_order(order_id)`. Return 200 whatever
   the outcome, except 503 when the order was never fetched (see
   Amendments): the outcome lives on the `MembershipSale` row, and a
   non-2xx would only make Square retry something the dashboard already
   shows.

### Gateway

`SquareGateway.retrieve_order(order_id) -> OrderData` via
`client.orders.get`. `OrderData` gains an optional `recipient:
Recipient | None` (`display_name`, `email_address`, `phone_number`, each
`""` when absent), read from the first fulfillment that has one.
`search_orders` keeps setting it too, so the type has one shape. The fake
gateway in `boxoffice/tests/fakes.py` gains `retrieve_order` and a way to
raise `GatewayError`.

### Processing — `boxoffice/memberships.py::process_order`

```
def process_order(order_id, gateway=None) -> MembershipSale | None
```

- Existing `MembershipSale` for `order_id` with status OK or SKIPPED:
  return it, do nothing. Square sends `order.updated` more than once per
  order (version bumps, fulfillment changes); the row is the idempotency
  key. FAILED: fall through and retry.
- Gateway disabled (`get_gateway()` is None): record FAILED with
  `error="Square sync disabled: <disabled_reason()>"`. The sale is not
  dropped; Retry works once the token is set.
- Fetch the order. `GatewayError`: record FAILED with the error text and
  only `order_id` filled. Retry re-fetches.
- No line whose `catalog_object_id` matches a tier's
  `square_variation_id`: return None, record nothing. Tickets and
  popcorn pass through here many times a day.
- Record or update the row with tier, quantity, gross, buyer fields and
  `closed_at`, then run attribution (Section 3) inside
  `transaction.atomic()` together with setting status OK and `term`. Any
  exception leaves status FAILED with `repr(exc)` and a
  `logger.exception` so the traceback reaches the server log.

## Section 2: data model

### `audience.MembershipTier.square_variation_id`

`CharField(max_length=64, blank=True, default="")` with a partial unique
constraint (unique where not blank). Help text: "The ID of this tier's
'Annual' variation in Square (Items → the item → the variation's ID in
the URL). Sales of that variation create terms for this tier." Shown in
the admin and the dashboard tier form. Blank means the tier is not sold
online and the webhook never attributes to it.

Matching on the variation ID rather than the item name means a renamed
item still attributes, and a new tier is wired up by pasting one ID. The
IDs differ between sandbox and production, so they are data, not code.

### `boxoffice.MembershipSale`

One row per Square order that contained a membership line.

| field | type | notes |
|---|---|---|
| `order_id` | `CharField(64, unique=True)` | the idempotency key |
| `closed_at` | `DateTimeField(null=True)` | from the order; null when the fetch failed |
| `tier` | `FK(MembershipTier, null=True, PROTECT)` | null when the fetch failed |
| `quantity` | `PositiveIntegerField(default=0)` | total membership quantity across lines |
| `gross_cents` | `IntegerField(default=0)` | sum of membership lines' `total_money` |
| `display_name` | `CharField(200, blank=True)` | as received |
| `email` | `EmailField(blank=True)` | lowercased, stripped |
| `phone` | `CharField(40, blank=True)` | as received |
| `status` | `CharField` choices OK / SKIPPED / FAILED | |
| `error` | `TextField(blank=True)` | why FAILED or SKIPPED |
| `term` | `OneToOneField(MembershipTerm, null=True, SET_NULL)` | the term this sale created |
| `created_at` | `auto_now_add` | first event seen |
| `processed_at` | `DateTimeField(null=True)` | last attempt |

`MembershipTerm` gets no new field. The sale points at the term, so
`audience` stays ignorant of `boxoffice`, as `cinema` does. Deleting the
term from the roster nulls the link and leaves the sale row as the record
that money changed hands; the sale list shows "term removed".

`SaleLine` is untouched. The nightly pull still stores the same order's
line as an unattributed line; the two tables answer different questions
(what sold vs. who is a member) and are not reconciled in this pass.

## Section 3: attribution

- **Tier.** The first line whose `catalog_object_id` matches a tier.
  A retired tier (`show_on_membership_page` off) still creates the term:
  the money was taken, and old terms on retired tiers already exist.
- **Quantity.** One term per sale. Quantity above one, or more than one
  membership line in the order: FAILED, `error="Ordered N memberships;
  enter by hand"`. The buyer fields are still stored so staff can see who.
- **Buyer.** From the fulfillment recipient. Email stripped and
  lowercased exactly as `Member.save` does. Blank email: SKIPPED,
  `error="No buyer email (register sale)"`. The display name is split on
  its last space into `first_name` / `last_name`; one word is all first
  name; blank stays blank.
- **Price.** `price_paid = gross_cents / 100` as a Decimal, not the
  tier's list price, so a discounted or repriced sale stays truthful.
- **Purchase date.** `closed_at` converted to Eastern via
  `boxoffice.pull.business_date`. It is `purchased_at`, and the start of
  a new or lapsed member's term.
- **New member** (no `Member` with that email): create with name, email,
  phone. Term: `started_on = purchase date`, `expires_on =
  MembershipTerm.default_expiry(started_on, tier.duration_months)`,
  `notes = "Square order <order_id>"`.
- **Existing member:** name left alone; phone filled only if blank.
  `latest = latest_term(member.terms.all())`. No terms: as a new member.
  Otherwise `started_on = renewal_start(latest, purchase date)`; a None
  (term runs to `date.max`) is FAILED with "Current term never expires".
  `expires_on` from `default_expiry`; an `OverflowError` is FAILED with
  the same wording the term form uses.
- **Atomicity.** Member, term, and the sale's OK status are one
  transaction. Any failure leaves the sale FAILED and nothing else
  written.
- **Retry** re-runs `process_order`. A buyer whose email staff have since
  entered by hand becomes a renewal, which is correct.

## Section 4: dashboard and settings

- **Alert.** `build_smart_alerts` gains `square_membership_failures: int`.
  Non-zero: a `warning` alert "N Square membership sale(s) need attention"
  linking to the sales list.
- **Sales list.** Staff-only `/dashboard/memberships/square-sales/`
  (`dashboard:square_membership_sales`), newest first: close date, tier,
  buyer name and email, amount, status pill, linked member (link to the
  roster row) or "term removed", error text, and a Retry button on FAILED
  rows. Retry is `POST /dashboard/memberships/square-sales/<pk>/retry/`,
  HTMX-swapping the row, following the Square sync Retry pattern.
- **Tier form and admin** gain `square_variation_id`.
- **Settings**, both blank by default:
  - `SQUARE_WEBHOOK_SIGNATURE_KEY` — from the subscription in the Square
    developer dashboard. Blank: every call is 403.
  - `SQUARE_WEBHOOK_URL` — the exact notification URL registered there.
- `disabled_reason()` and `get_gateway()` are unchanged. The webhook
  reuses them to fetch the order.
- Deploying with both settings blank changes nothing visible.

## Section 5: testing

Fake gateway: `retrieve_order` returning a scripted `OrderData`, or
raising `GatewayError`.

Signed requests in tests compute the HMAC with the same helper, as the
phone tests do with Twilio's validator.

Cases:

- Missing, forged, or tampered signature: 403, no `MembershipSale`.
- Blank key or blank URL setting: 403.
- Event type other than `order.updated`, or state not COMPLETED: 200,
  nothing recorded.
- Order with only ticket lines: 200, nothing recorded.
- New buyer: member created, term dated from `closed_at` in Eastern
  (a UTC timestamp after 8 pm Eastern lands on the right day), expiry
  from the tier's duration, `price_paid` from the gross, notes carry the
  order ID, sale OK and linked.
- Active member: term starts the day after `covered_through`.
- Lapsed member: term starts on the purchase date.
- Existing member with blank phone gets the phone; one with a phone and
  a different name keeps both.
- Quantity two, or two membership lines: FAILED with the message, buyer
  stored, no member or term.
- No recipient email: SKIPPED, no alert counted.
- Duplicate event for an OK order: 200, still one term.
- Gateway error: FAILED with the text; a second event, or Retry,
  succeeds and links the term.
- Gateway disabled: FAILED with the disabled reason.
- `build_smart_alerts` counts only FAILED; the list and Retry views
  require staff.

## Rollout

1. Deploy with both webhook settings blank; `migrate`.
2. In the dashboard tier form, paste each tier's variation ID. Read
   from the production catalog on 2026-10-09:

   | tier slug | Square item | variation ID |
   |---|---|---|
   | `silver-screen` | Silver Screen Membership (Seniors) | `WWROZFMDYT63NSYSQTIHONL4` |
   | `individual` | Individual Membership | `LUXWXSDRQGNENE7XDBXPNYXY` |
   | `cinema-supporter` | Cinema Supporter Membership | `KWL3ATNY4VC4MPKGQWZBZTUR` |
   | `family` | Family Membership | `KO4GD2VPETBG3KH7Q7LL4L43` |
   | `family-plus` | Family Plus Membership | `YJEGADIF7G23EQX67DK744LO` |

   The sandbox has its own IDs; a sandbox tier is wired the same way.
   The sales list lives at `/dashboard/memberships/square-sales/` and is
   linked from the Memberships page.
3. In the Square developer dashboard, add a webhook subscription for the
   production application: URL `https://www.fortkentcinema.com/boxoffice/square/webhook/`,
   API version matching the SDK, event `order.updated` only. Copy its
   signature key.
4. Set `SQUARE_WEBHOOK_SIGNATURE_KEY` and `SQUARE_WEBHOOK_URL` in
   `webservers.yml`; deploy.
5. Use Square's "Send test event" and confirm a 200 in its log and no
   row created (the test order has no membership line).
6. Watch the first real sale land in the roster.

## Amendments (implementation, 2026-10-09)

- `process_order` creates a placeholder `MembershipSale` row (FAILED, "Processing
  did not finish") before fetching the order, so a request killed mid-way still
  raises the dashboard alert. An order with no membership line deletes the
  placeholder again, so every completed register order costs one insert and
  one delete.
- After the fetch the row is re-read under `select_for_update()` inside
  `transaction.atomic()` and left untouched if another request already
  finished it (OK or SKIPPED). The early failure writes (gateway disabled,
  gateway error) use the same guard. This closes a two-events-for-one-order
  race the spec did not name. The lock is real on Postgres and a no-op on
  sqlite.
- An order with no `closed_at` is recorded FAILED with "Order has no closed_at".
- A term that would run past 31 December 9999 is FAILED with
  `A {months}-month term from {YYYY-MM-DD} runs past 31 December 9999. Enter
  the term by hand.`
- The webhook decodes the body strictly; a body that is not valid UTF-8 is a
  403, so the verified text is exactly the bytes Square signed.
- The home-page alert links to the sales list (an optional `url` key on the
  alert, rendered by `_alerts.html`); other alerts are unchanged.
- The webhook returns 400 for malformed JSON, a non-object body, or an
  `order.updated` event missing its order keys. Every other event type and
  every non-COMPLETED state is a 200 with nothing recorded.
- The webhook returns 503 when the order was never fetched (the sale is FAILED
  with no `closed_at`: gateway disabled, gateway error, or a placeholder left
  behind; `order_never_fetched()`). Square retries a non-2xx, and a retry that
  fetches resolves the event without a staff click: a non-membership order
  drops its placeholder, a membership is attributed. The FAILED row stays as
  the backstop alert if Square gives up. Gateway errors read "Could not fetch
  the order from Square: {error}". Every other outcome is still a 200.
- Buyer fields are cut to their columns before they are stored: display name
  to 200 characters, phone to 40, and the split first and last names to 100
  each. Square allows longer, and Postgres would refuse them. The final OK
  save sits inside the savepoint and `try`, so any failure there is recorded
  FAILED with `repr(exc)` and the member and term roll back.
