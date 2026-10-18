# Online Ticket Pre-sale Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Sell adult, senior and child tickets for every upcoming showtime through Square's hosted checkout, email the buyer a QR ticket, and give staff a door list, a pre-sale summary, an order log, one-click refunds for a cancelled show, and home-page alerts.

**Architecture:** A new `tickets` Django app owns `TicketOrder`/`TicketLine` and the checkout, confirmation, mail and refund logic. It reads `cinema.Showtime` and the run's `boxoffice.SquareVariation` rows and talks to Square only through `boxoffice.gateway`, which gains `create_payment_link` and `refund_payment`. The existing Square payment webhook hands completed payments to `tickets.orders.confirm_payment`. Public pages live in `tickets/views.py`; staff pages live in `dashboard/ticket_views.py`. Online sales are attributed to runs by the nightly pull with no change, because every Square line points at a Django-issued variation ID.

**Tech Stack:** Django 5.2, squareup SDK 42.1, HTMX + Alpine in the dashboard, `qrcode[pil]` for the ticket QR, Django's mail backend, sqlite in tests / Postgres in production.

**Spec:** `docs/superpowers/specs/2026-10-17-online-ticket-presale-design.md`

## Global Constraints

- Test runner: `.venv/bin/python manage.py test <label>`; `-v 2` for names. Run the whole suite before each commit of a task that touches `boxoffice` or `web`.
- Lint gate: no new flake8 findings on changed lines (repo baseline is dirty). Black line length 88.
- Prices come from `web.constants.TICKET_PRICES` (adult 8, senior 7, child 6, matinee 6, `matinee_until` 16:00). Never hard-code a dollar figure elsewhere.
- Constants in `web/constants.py`: `TICKET_ONLINE_SHARE = 0.5`, `TICKET_HOLD_MINUTES = 20`, `TICKET_CUTOFF_MINUTES = 30`.
- Ticket tiers sold online: `boxoffice.spec.SQUARE_TIERS` = `("adult", "senior", "child")`, in that order.
- Order number: `FK-` + 5 characters from `ABCDEFGHJKLMNPQRSTUVWXYZ23456789`. Token: `secrets.token_urlsafe(32)`.
- Time zone: all cutoff, matinee and label logic in `America/New_York` (`web.services.cinema_data.CINEMA_TZ`).
- Nothing in `cinema` or `boxoffice` imports `tickets`, except the one-line webhook hook in `boxoffice/views.py`.
- Square calls never run inside a database transaction.
- Staff views use `dashboard.mixins.StaffRequiredMixin`. CSV goes through `dashboard.csv_export.safe_csv_writer`.
- Public pages that are reached by redirect or token are `noindex, nofollow` (`{% block robots %}`) and absent from the sitemap.
- Commit messages: conventional prefix, end with `Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>`.
- Do not merge or push; the owner does both.

## Review Focus

1. **All quantities zero** on the ticket form: the page must re-render with "Pick at least one ticket" and create no order. Test in Task 9.
2. **Showtime reachable by URL but not listed**: a showtime on a DRAFT or CANCELLED run, or a run hidden from main listings, must not be purchasable even though the URL resolves. Test in Task 4.
3. **Tampered quantities**: a POST whose total exceeds `remaining` (or a negative number) must be refused with the sold-out sentence and create no order. Test in Task 9.
4. **Payment lands after the showtime was cancelled**: the order still becomes PAID (money was taken) and the cancelled-with-orders alert counts it. Test in Task 8.
5. **Allowance lowered below sold**: saving must succeed, `remaining` becomes 0, the page shows sold out, nothing is refunded. Test in Task 12.

---

## File structure

| path | responsibility |
|---|---|
| `web/constants.py` | the three ticket constants beside `TICKET_PRICES` |
| `cinema/models/showtime.py`, `cinema/migrations/0029_showtime_online_allowance.py` | `online_allowance` and `effective_online_allowance` |
| `tickets/apps.py`, `tickets/models.py`, `tickets/migrations/0001_initial.py` | `TicketOrder`, `TicketLine`, number/token generation |
| `tickets/pricing.py` | matinee rule and per-tier unit price for a showtime |
| `tickets/availability.py` | sold / remaining / why-not-purchasable, single and bulk |
| `tickets/spec.py` | `CheckoutSpec` / `CheckoutLine` built from an order |
| `tickets/orders.py` | `start`, `confirm_payment`, `recover_pending`, `expire_stale` |
| `tickets/mail.py` | QR image, ticket email, refund email |
| `tickets/refunds.py` | `refund_order`, `refund_showtime` |
| `tickets/forms.py`, `tickets/views.py`, `tickets/urls.py`, `tickets/templates/tickets/*.html`, `tickets/templates/tickets/email/*` | public buy and order pages, email bodies |
| `tickets/management/commands/expire_ticket_orders.py` | nightly expiry |
| `boxoffice/gateway.py`, `boxoffice/tests/fakes.py` | `Tender`, `OrderData.tenders`, `create_payment_link`, `refund_payment` |
| `boxoffice/views.py` | webhook hands the order ID to tickets |
| `web/services/cinema_data.py`, `web/views.py`, `templates/partials/movie_schedule_card.html`, `templates/partials/home_jsonld.html` | chips link, sold-out note, JSON-LD offers |
| `dashboard/ticket_views.py`, `dashboard/urls.py`, `dashboard/templates/dashboard/showtime_orders.html`, `_ticket_order_row.html`, `tickets.html`, `ticket_orders.html`, `_allowance_form.html` | door list, summary, order log |
| `dashboard/views.py`, `dashboard/templates/dashboard/_showtime_form.html`, `_showtime_list.html`, `_sidebar.html`, `home.html`, `dashboard/smart_alerts.py` | allowance field, online counts, sidebar, alerts |
| `fortkentcinema/settings.py`, `fortkentcinema/urls.py`, `requirements.txt` | app registration, `TICKETS_BASE_URL`, `qrcode` |

---

### Task 1: Constants and the showtime allowance

**Files:**
- Modify: `web/constants.py` (after `TICKET_PRICES`)
- Modify: `cinema/models/showtime.py`
- Create: `cinema/migrations/0029_showtime_online_allowance.py`
- Test: `cinema/tests/test_showtime_allowance.py`

**Interfaces:**
- Produces: `web.constants.TICKET_ONLINE_SHARE: float`, `TICKET_HOLD_MINUTES: int`, `TICKET_CUTOFF_MINUTES: int`; `Showtime.online_allowance: int | None`; `Showtime.effective_online_allowance -> int` property.

- [ ] **Step 1: Write the failing tests**

```python
class EffectiveAllowanceTests(TestCase):
    def setUp(self):
        self.screen = Screen.objects.create(name="S1", capacity=101)
        eng = Engagement.objects.create(screen=self.screen, start_date=date(2026, 10, 20),
                                        end_date=date(2026, 10, 26), status="CONFIRMED")
        self.st = Showtime.objects.create(engagement=eng, starts_at=aware(2026, 10, 20, 19))

    def test_default_is_half_the_seats_rounded_down(self):
        self.assertEqual(self.st.effective_online_allowance, 50)

    def test_override_wins(self):
        self.st.online_allowance = 7
        self.assertEqual(self.st.effective_online_allowance, 7)

    def test_zero_override_means_none_online(self):
        self.st.online_allowance = 0
        self.assertEqual(self.st.effective_online_allowance, 0)

    def test_constants(self):
        self.assertEqual((TICKET_ONLINE_SHARE, TICKET_HOLD_MINUTES, TICKET_CUTOFF_MINUTES),
                         (0.5, 20, 30))
```

- [ ] **Step 2: Run to verify they fail**

Run: `.venv/bin/python manage.py test cinema.tests.test_showtime_allowance -v 2`
Expected: ImportError on the constants.

- [ ] **Step 3: Add the constants and the field**

In `web/constants.py` directly under `TICKET_PRICES`, with a comment that these govern online sales (`tickets` app):
```python
TICKET_ONLINE_SHARE = 0.5
TICKET_HOLD_MINUTES = 20
TICKET_CUTOFF_MINUTES = 30
```
In `Showtime`: `online_allowance = models.PositiveIntegerField(null=True, blank=True, help_text="How many tickets this showtime sells online. Blank uses the default: half the screen's seats.")` and the property using `math.floor(self.screen.capacity * TICKET_ONLINE_SHARE)`, importing the constant inside the property so `cinema` gains no module-level import of `web`.

- [ ] **Step 4: Make the migration and run the tests**

Run: `.venv/bin/python manage.py makemigrations cinema -n showtime_online_allowance && .venv/bin/python manage.py test cinema -v 1`
Expected: migration `0029_showtime_online_allowance.py` created; all cinema tests pass.

- [ ] **Step 5: Commit**

```bash
git add web/constants.py cinema/models/showtime.py cinema/migrations/0029_showtime_online_allowance.py cinema/tests/test_showtime_allowance.py
git commit -m "feat(cinema): per-showtime online allowance with a half-the-seats default"
```

---

### Task 2: The `tickets` app and its models

**Files:**
- Create: `tickets/__init__.py`, `tickets/apps.py`, `tickets/models.py`, `tickets/migrations/0001_initial.py`, `tickets/tests/__init__.py`
- Modify: `fortkentcinema/settings.py` (`INSTALLED_APPS`, after `boxoffice`)
- Test: `tickets/tests/test_models.py`

**Interfaces:**
- Produces: `TicketOrder` with fields exactly as the spec's Section 2 table, `TicketOrder.Status` (PENDING, PAID, EXPIRED, REFUNDED, FAILED), `TicketOrder.TIERS = SQUARE_TIERS`, `TicketOrder.is_holding(now) -> bool`, `TicketOrder.counts_as_sold -> bool` (PAID, or FAILED with a payment ID), `TicketOrder.total_dollars -> Decimal`, `TicketOrder.breakdown -> str` ("2 adult, 1 child"); `TicketLine` with `order`, `tier`, `quantity`, `unit_cents`, `square_variation_id`; `tickets.models.new_number() -> str`, `new_token() -> str`.
- Consumes: `boxoffice.spec.SQUARE_TIERS`, `web.constants.TICKET_HOLD_MINUTES`.

- [ ] **Step 1: Write the failing tests**

```python
class NumberAndTokenTests(SimpleTestCase):
    def test_number_shape(self):
        n = new_number()
        self.assertRegex(n, r"^FK-[ABCDEFGHJKLMNPQRSTUVWXYZ23456789]{5}$")

    def test_token_is_long_and_url_safe(self):
        self.assertRegex(new_token(), r"^[A-Za-z0-9_-]{43}$")


class OrderModelTests(TestCase):
    def test_defaults_on_create(self):
        order = make_order(self.st)              # helper in the test module
        self.assertEqual(order.status, "PENDING")
        self.assertTrue(order.number.startswith("FK-"))
        self.assertEqual(len(order.token), 43)

    def test_is_holding_inside_window_only(self):
        order = make_order(self.st)
        self.assertTrue(order.is_holding(order.created_at + timedelta(minutes=19)))
        self.assertFalse(order.is_holding(order.created_at + timedelta(minutes=21)))
        order.status = "PAID"
        self.assertFalse(order.is_holding(order.created_at))

    def test_counts_as_sold(self):
        self.assertTrue(make_order(self.st, status="PAID").counts_as_sold)
        self.assertTrue(make_order(self.st, status="FAILED", square_payment_id="P1").counts_as_sold)
        self.assertFalse(make_order(self.st, status="FAILED").counts_as_sold)
        self.assertFalse(make_order(self.st, status="REFUNDED").counts_as_sold)

    def test_breakdown_and_total(self):
        order = make_order(self.st, lines={"adult": 2, "child": 1})
        self.assertEqual(order.breakdown, "2 adult, 1 child")
        self.assertEqual(order.total_dollars, Decimal("22.00"))

    def test_showtime_with_orders_is_protected(self):
        make_order(self.st)
        with self.assertRaises(ProtectedError):
            self.st.delete()

    def test_square_order_id_unique_when_set_blank_allowed_twice(self):
        make_order(self.st, square_order_id="")
        make_order(self.st, square_order_id="")
        make_order(self.st, square_order_id="SQ1")
        with self.assertRaises(IntegrityError):
            make_order(self.st, square_order_id="SQ1")
```

`make_order(showtime, *, status="PENDING", lines=None, **over)` creates the order with name "Ann Lee", email "ann@example.com", phone "207-555-0100", and `TicketLine`s from `lines` (default `{"adult": 1}`) at `unit_cents` 800/700/600; `total_cents` is the sum. Put it in `tickets/tests/factories.py` so later tasks reuse it, along with `make_showtime(**over)` that builds screen (capacity 100), film, confirmed engagement and a showtime at 19:00 Eastern seven days out.

- [ ] **Step 2: Run to verify they fail**

Run: `.venv/bin/python manage.py test tickets -v 2`
Expected: "No module named tickets".

- [ ] **Step 3: Create the app, models, and register it**

`TicketsConfig(name="tickets", verbose_name="Online tickets", default_auto_field="django.db.models.BigAutoField")`. Models per the spec table: `number` `CharField(12, unique=True, default=new_number)`, `token` `CharField(43, unique=True, default=new_token)`, `square_order_id` `CharField(64, blank=True, default="")` with `UniqueConstraint(fields=["square_order_id"], condition=~Q(square_order_id=""), name="tickets_one_order_per_square_order")`, indexes `["showtime", "status"]` and `["status", "created_at"]`, `Meta.ordering = ["-created_at"]`. `TicketLine` with `UniqueConstraint(fields=["order", "tier"], name="tickets_one_line_per_tier")`. `breakdown` joins lines in `SQUARE_TIERS` order. Register the app and run `makemigrations tickets`.

- [ ] **Step 4: Run the tests**

Run: `.venv/bin/python manage.py test tickets -v 2`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add tickets fortkentcinema/settings.py
git commit -m "feat(tickets): TicketOrder and TicketLine models"
```

---

### Task 3: Pricing

**Files:**
- Create: `tickets/pricing.py`
- Test: `tickets/tests/test_pricing.py`

**Interfaces:**
- Produces: `is_matinee(starts_at: datetime) -> bool` (Eastern local time ≤ `TICKET_PRICES["matinee_until"]`); `unit_cents(tier: str, starts_at: datetime) -> int`; `discount_cents(tier, starts_at) -> int` (list price minus matinee price when matinee and positive, else 0); `price_table(starts_at) -> list[PriceRow]` where `PriceRow(tier, label, unit_cents, discount_cents)` in `SQUARE_TIERS` order with labels "Adult", "Senior", "Child".

- [ ] **Step 1: Write the failing tests**

```python
def test_four_pm_is_a_matinee_four_oh_one_is_not(self):
    self.assertTrue(is_matinee(eastern(2026, 10, 24, 16, 0)))
    self.assertFalse(is_matinee(eastern(2026, 10, 24, 16, 1)))

def test_evening_prices(self):
    self.assertEqual([r.unit_cents for r in price_table(eastern(2026, 10, 24, 19))], [800, 700, 600])
    self.assertEqual([r.discount_cents for r in price_table(eastern(2026, 10, 24, 19))], [0, 0, 0])

def test_matinee_prices_and_discounts(self):
    rows = price_table(eastern(2026, 10, 24, 13))
    self.assertEqual([r.unit_cents for r in rows], [600, 600, 600])
    self.assertEqual([r.discount_cents for r in rows], [200, 100, 0])

def test_utc_input_is_judged_in_eastern(self):
    # 20:30 UTC on 24 Oct is 16:30 Eastern: not a matinee.
    self.assertFalse(is_matinee(datetime(2026, 10, 24, 20, 30, tzinfo=timezone.utc)))
    # 19:30 UTC is 15:30 Eastern.
    self.assertTrue(is_matinee(datetime(2026, 10, 24, 19, 30, tzinfo=timezone.utc)))
```

- [ ] **Step 2: Run to verify they fail**

Run: `.venv/bin/python manage.py test tickets.tests.test_pricing -v 2`
Expected: ImportError.

- [ ] **Step 3: Implement `tickets/pricing.py`**

Convert with `starts_at.astimezone(CINEMA_TZ).time() <= TICKET_PRICES["matinee_until"]`. `unit_cents` is `min(list, matinee) * 100` when matinee.

- [ ] **Step 4: Run the tests** — expected PASS.

- [ ] **Step 5: Commit** — `git commit -m "feat(tickets): matinee-aware pricing table"`

---

### Task 4: Availability

**Files:**
- Create: `tickets/availability.py`
- Test: `tickets/tests/test_availability.py`

**Interfaces:**
- Produces:
  - `sold(showtime, now) -> int`: sum of line quantities over orders where `counts_as_sold` or `is_holding(now)`, one aggregate query.
  - `remaining(showtime, now) -> int`: `max(effective_online_allowance - sold, 0)`.
  - `Availability(purchasable: bool, reason: str, sold: int, remaining: int, allowance: int)`; `reason` is one of `""`, `"disabled"`, `"not_listed"`, `"cancelled"`, `"cutoff"`, `"no_item"`, `"sold_out"`.
  - `check(showtime, now, *, square_enabled: bool) -> Availability`, evaluated in that reason order. `not_listed` means engagement status not CONFIRMED or `show_in_main_listings` False. `cutoff` means `now >= starts_at - TICKET_CUTOFF_MINUTES`. `no_item` means no live `SquareItem` with a `square_id` for the engagement (use `boxoffice.sync.live_item`).
  - `for_showtimes(showtimes: Iterable[Showtime], now, *, square_enabled) -> dict[int, Availability]`: same result keyed by pk, with sold counts from one grouped query and live items from one query.
  - `variation_ids(engagement) -> dict[str, str]`: tier → `SquareVariation.square_id` from the live item.
- Consumes: Task 1 constants and property, Task 2 model helpers.

- [ ] **Step 1: Write the failing tests**

```python
def test_sold_counts_paid_and_young_pending_only(self):
    make_order(self.st, status="PAID", lines={"adult": 2})
    make_order(self.st, status="PENDING", lines={"child": 1})                       # young
    old = make_order(self.st, status="PENDING", lines={"senior": 5}); age(old, minutes=21)
    make_order(self.st, status="EXPIRED", lines={"adult": 5})
    make_order(self.st, status="REFUNDED", lines={"adult": 5})
    make_order(self.st, status="FAILED", lines={"adult": 5})
    make_order(self.st, status="FAILED", lines={"adult": 1}, square_payment_id="P9")
    self.assertEqual(sold(self.st, NOW), 4)

def test_remaining_never_negative(self):
    self.st.online_allowance = 1; self.st.save()
    make_order(self.st, status="PAID", lines={"adult": 3})
    self.assertEqual(remaining(self.st, NOW), 0)

def test_reason_order(self):
    # disabled beats everything
    self.assertEqual(check(self.st, NOW, square_enabled=False).reason, "disabled")
    # draft run, hidden run
    ...assert "not_listed" for status DRAFT and for show_in_main_listings False
    # cancelled showtime
    ...assert "cancelled"
    # 29 minutes before start is closed, 31 is open
    self.assertEqual(check(self.st, self.st.starts_at - timedelta(minutes=29), square_enabled=True).reason, "cutoff")
    self.assertEqual(check(self.st, self.st.starts_at - timedelta(minutes=31), square_enabled=True).reason, "no_item")
    # with a live item but a full allowance
    make_live_item(self.st.engagement)          # SquareItem with square_id + 3 variations
    self.st.online_allowance = 0; self.st.save()
    self.assertEqual(check(self.st, NOW, square_enabled=True).reason, "sold_out")
    self.st.online_allowance = None; self.st.save()
    self.assertTrue(check(self.st, NOW, square_enabled=True).purchasable)

def test_cutoff_across_dst_change(self):
    # 1 Nov 2026 1:30 AM EDT showtime; 1:05 AM EDT is inside the cutoff, 0:55 is outside.
    ...

def test_for_showtimes_matches_check_and_uses_few_queries(self):
    with self.assertNumQueries(3):   # showtimes already loaded: sold aggregate, live items, variations
        result = for_showtimes([self.st, other], NOW, square_enabled=True)
    self.assertEqual(result[self.st.pk], check(self.st, NOW, square_enabled=True))

def test_variation_ids(self):
    make_live_item(self.st.engagement)
    self.assertEqual(set(variation_ids(self.st.engagement)), {"adult", "senior", "child"})
```

Add `make_live_item(engagement)` to `tickets/tests/factories.py`: a `SquareItem(engagement=..., square_id="item-1", name=engagement.title)` with three `SquareVariation`s (`square_id="var-<tier>"`, sku `fkc-eng-<pk>-<tier>`, `price_cents` from `TICKET_PRICES`, ordinal 0..2). Add `age(order, minutes)` that rewinds `created_at` with `update()`.

- [ ] **Step 2: Run to verify they fail** — ImportError.

- [ ] **Step 3: Implement `tickets/availability.py`**

`sold` uses `TicketLine.objects.filter(order__showtime=...).filter(Q(order__status="PAID") | Q(order__status="FAILED", order__square_payment_id__gt="") | Q(order__status="PENDING", order__created_at__gt=now - hold)).aggregate(Sum("quantity"))`. `for_showtimes` does the same with `.values("order__showtime_id").annotate(...)`. The `assertNumQueries(3)` figure may need adjusting to what the implementation actually needs; keep it the minimum and record the number in the test.

- [ ] **Step 4: Run the tests** — expected PASS.

- [ ] **Step 5: Commit** — `git commit -m "feat(tickets): availability and online counts"`

---

### Task 5: Gateway: payment links, refunds, tenders

**Files:**
- Modify: `boxoffice/gateway.py`
- Modify: `boxoffice/tests/fakes.py`
- Test: `boxoffice/tests/test_gateway.py`

**Interfaces:**
- Produces, in `boxoffice/gateway.py`:
  - `@dataclass(frozen=True) class Tender: payment_id: str; status: str` (status as Square gives it, e.g. `"COMPLETED"`); `OrderData.tenders: tuple[Tender, ...] = ()` filled by `_order_data` from `order.tenders` (`id`, `card_details.status` when present, else `""`).
  - `@dataclass(frozen=True) class CheckoutLine: variation_id: str; name: str; quantity: int; unit_cents: int; discount_cents: int` (discount is the per-line total, 0 for none).
  - `@dataclass(frozen=True) class CheckoutSpec: reference: str; showtime_id: int; lines: tuple[CheckoutLine, ...]; redirect_url: str; buyer_email: str; buyer_phone: str; support_email: str; idempotency_key: str`.
  - `@dataclass(frozen=True) class CheckoutResult: order_id: str; url: str`.
  - `payment_link_body(spec, location_id) -> dict`: the request dict (pure, testable).
  - `SquareGateway.create_payment_link(spec) -> CheckoutResult` via `client.checkout.payment_links.create(**payment_link_body(...))`, wrapped in `_call`; result from `response.payment_link.order_id` and `.url`.
  - `SquareGateway.refund_payment(*, payment_id, amount_cents, idempotency_key, reason) -> str` via `client.refunds.refund_payment(...)`, returns `response.refund.id`.
- Fake gateway gains `create_payment_link` (records the call, returns `CheckoutResult(order_id=f"SQ-{n}", url=f"https://square.link/u/{n}")`, appends a matching OPEN `OrderData` with no tenders to `self.orders`), `refund_payment` (records, returns `f"R-{n}"`), and `pay(order_id, payment_id="P1")` which replaces that stored order with one whose `tenders=(Tender(payment_id, "COMPLETED"),)` and `paid_at=now`.

- [ ] **Step 1: Write the failing tests**

```python
def test_payment_link_body_matinee(self):
    spec = CheckoutSpec(reference="FK-ABCDE", showtime_id=5, lines=(
        CheckoutLine("var-adult", "Adult", 2, 600, 400),
        CheckoutLine("var-child", "Child", 1, 600, 0)),
        redirect_url="https://www.fortkentcinema.com/tickets/order/tok/",
        buyer_email="ann@example.com", buyer_phone="2075550100",
        support_email="info@fortkentcinema.com", idempotency_key="tok")
    body = payment_link_body(spec, "LOC1")
    order = body["order"]
    self.assertEqual(order["location_id"], "LOC1")
    self.assertEqual(order["reference_id"], "FK-ABCDE")
    self.assertEqual(order["metadata"], {"showtime": "5"})
    self.assertNotIn("fulfillments", order)
    adult, child = order["line_items"]
    self.assertEqual(adult["catalog_object_id"], "var-adult")
    self.assertEqual(adult["quantity"], "2")
    self.assertEqual(adult["base_price_money"], {"amount": 800, "currency": "USD"})
    self.assertEqual(adult["applied_discounts"], [{"discount_uid": "matinee-var-adult"}])
    self.assertNotIn("applied_discounts", child)
    self.assertEqual(order["discounts"], [{
        "uid": "matinee-var-adult", "name": "Matinee", "type": "FIXED_AMOUNT",
        "scope": "LINE_ITEM", "amount_money": {"amount": 400, "currency": "USD"}}])
    opts = body["checkout_options"]
    self.assertEqual(opts["redirect_url"], spec.redirect_url)
    self.assertFalse(opts["ask_for_shipping_address"]); self.assertFalse(opts["allow_tipping"])
    self.assertEqual(opts["accepted_payment_methods"], {"apple_pay": True, "google_pay": True})
    self.assertEqual(opts["merchant_support_email"], "info@fortkentcinema.com")
    self.assertEqual(body["pre_populated_data"], {"buyer_email": "ann@example.com", "buyer_phone_number": "2075550100"})
    self.assertEqual(body["idempotency_key"], "tok")

def test_evening_body_has_no_discounts_key(self): ...

def test_create_payment_link_maps_response_and_errors(self):
    client = mock.Mock(); client.checkout.payment_links.create.return_value = mock.Mock(
        payment_link=mock.Mock(order_id="SQ1", url="https://square.link/u/x"))
    gw = SquareGateway(client, "LOC1", "CAT1")
    self.assertEqual(gw.create_payment_link(spec), CheckoutResult("SQ1", "https://square.link/u/x"))
    client.checkout.payment_links.create.side_effect = httpx.ConnectError("down")
    with self.assertRaises(GatewayError): gw.create_payment_link(spec)

def test_refund_payment_sends_amount_and_key(self):
    client.refunds.refund_payment.return_value = mock.Mock(refund=mock.Mock(id="R1"))
    self.assertEqual(gw.refund_payment(payment_id="P1", amount_cents=2200,
                     idempotency_key="refund-FK-ABCDE", reason="Showtime cancelled"), "R1")
    client.refunds.refund_payment.assert_called_once_with(
        idempotency_key="refund-FK-ABCDE", payment_id="P1",
        amount_money={"amount": 2200, "currency": "USD"}, reason="Showtime cancelled")

def test_order_data_reads_tenders(self):
    order = mock.Mock(tenders=[mock.Mock(id="P1", created_at="2026-10-03T03:12:00Z",
                      card_details=mock.Mock(status="CAPTURED"))], ...)
    self.assertEqual(_order_data(order).tenders, (Tender("P1", "CAPTURED"),))

def test_fake_pay_marks_tender_completed(self):
    gw = FakeGateway(); res = gw.create_payment_link(spec)
    self.assertEqual(gw.retrieve_order(res.order_id).tenders, ())
    gw.pay(res.order_id, "P7")
    self.assertEqual(gw.retrieve_order(res.order_id).tenders, (Tender("P7", "COMPLETED"),))
```

Base price rule: `base_price_money.amount = unit_cents + discount_cents // quantity`; the discount line's `amount_money` is the per-line total `discount_cents`. Discount uid: `f"matinee-{variation_id}"`.

- [ ] **Step 2: Run to verify they fail** — ImportError on the new names.

- [ ] **Step 3: Implement the gateway additions and the fake**

Check the SDK's exact method paths with `.venv/bin/python -c "from square import Square; help(Square.checkout)"` style introspection before writing the calls; the spec's names (`client.checkout.payment_links.create`, `client.refunds.refund_payment`) are from SDK 42's layout and the test mocks must match what the code calls.

- [ ] **Step 4: Run the boxoffice suite**

Run: `.venv/bin/python manage.py test boxoffice -v 1`
Expected: pass, apart from the three pre-existing `test_sync` failures recorded in memory (`presale-banner-decisions`); confirm those are the same three.

- [ ] **Step 5: Commit** — `git commit -m "feat(boxoffice): gateway creates payment links, refunds payments, reads tenders"`

---

### Task 6: Sandbox check (manual, decides the pull)

**Files:**
- Create: `docs/superpowers/specs/2026-10-17-online-ticket-presale-design.md` → Amendments entry only

**Interfaces:**
- Consumes: Task 5 `create_payment_link`.

- [ ] **Step 1: Create one link in the sandbox**

With sandbox `SQUARE_*` settings in the shell environment, in `manage.py shell`: get the gateway, build a `CheckoutSpec` for any existing sandbox variation (or push a test engagement first via `boxoffice.sync.push`), one line, quantity 1, no discount, `redirect_url` `https://example.com/`, and call `create_payment_link`. Print the URL.

- [ ] **Step 2: Pay it with a Square sandbox test card** (4111 1111 1111 1111, any future date, CVV 111) in a browser.

- [ ] **Step 3: Read the order back**

`gateway.retrieve_order(order_id)` → print `closed_at`, `paid_at`, `tenders`. Then `gateway.search_orders(day_bounds(today))` and confirm the order is in the COMPLETED results.

- [ ] **Step 4: Record the outcome**

Append to the spec's Amendments: date, whether a fulfillment-free payment-link order reached COMPLETED on payment, and the tender status string seen. If it did **not** complete, stop and raise it with the owner: Tasks 8 and 9 proceed unchanged, but a follow-up task adds an OPEN-order search by `reference_id` prefix `FK-` to `boxoffice/pull.py`.

- [ ] **Step 5: Commit** — `git commit -m "docs: record the sandbox payment-link completion check"`

---

### Task 7: Checkout spec and `orders.start`

**Files:**
- Create: `tickets/spec.py`, `tickets/orders.py`
- Modify: `fortkentcinema/settings.py` (`TICKETS_BASE_URL`)
- Test: `tickets/tests/test_spec.py`, `tickets/tests/test_orders_start.py`

**Interfaces:**
- Produces:
  - `settings.TICKETS_BASE_URL = config("TICKETS_BASE_URL", default="")`.
  - `tickets.spec.base_url() -> str`: `TICKETS_BASE_URL`, else scheme+host of `SQUARE_WEBHOOK_URL`, else `""`; no trailing slash.
  - `tickets.spec.checkout_spec(order, variation_ids: dict[str, str]) -> CheckoutSpec`: lines in `SQUARE_TIERS` order from the order's `TicketLine`s with `discount_cents = pricing.discount_cents(tier, starts_at) * quantity`, `redirect_url = base_url() + reverse("tickets:order", args=[order.token])`, `support_email = SITE_CONFIG["cinema"]["email"]` (check the key in `web/constants.py`; if there is none, use `DEFAULT_FROM_EMAIL`), `idempotency_key = order.token`, `reference = order.number`.
  - `tickets.orders.Refused(Exception)` with `.reason` (an availability reason string).
  - `tickets.orders.start(showtime, *, name, email, phone, quantities: dict[str, int], now, gateway=None) -> TicketOrder`:
    1. `square_enabled = gateway is not None` where `gateway = gateway or get_gateway()`.
    2. `transaction.atomic()`: `Showtime.objects.select_for_update().get(pk=...)`, `check(...)`; refuse if not purchasable or `sum(quantities) > remaining` or `sum(quantities) == 0` (`reason="quantity"`); create the PENDING order and lines with `unit_cents` from pricing.
    3. After commit: `gateway.create_payment_link(checkout_spec(order, variation_ids(engagement)))`; success → store `square_order_id`, `square_checkout_url`; `GatewayError` → status FAILED, `error=str(exc)`; return the order either way.

- [ ] **Step 1: Write the failing tests**

```python
# test_spec.py
def test_spec_lines_prices_and_urls(self):
    with override_settings(TICKETS_BASE_URL="https://www.fortkentcinema.com"):
        order = make_order(self.matinee_st, lines={"adult": 2, "child": 1})   # 13:00 showtime
        spec = checkout_spec(order, {"adult": "va", "senior": "vs", "child": "vc"})
    self.assertEqual([(l.variation_id, l.quantity, l.unit_cents, l.discount_cents) for l in spec.lines],
                     [("va", 2, 600, 400), ("vc", 1, 600, 0)])
    self.assertEqual(spec.redirect_url, f"https://www.fortkentcinema.com/tickets/order/{order.token}/")
    self.assertEqual(spec.reference, order.number); self.assertEqual(spec.idempotency_key, order.token)

def test_base_url_falls_back_to_webhook_host(self):
    with override_settings(TICKETS_BASE_URL="", SQUARE_WEBHOOK_URL="https://www.fortkentcinema.com/boxoffice/square/webhook/"):
        self.assertEqual(base_url(), "https://www.fortkentcinema.com")

# test_orders_start.py
def test_start_creates_pending_order_and_link(self):
    gw = FakeGateway(); make_live_item(self.st.engagement)
    order = start(self.st, name="Ann Lee", email=" Ann@Example.com", phone="207-555-0100",
                  quantities={"adult": 2, "senior": 0, "child": 1}, now=NOW, gateway=gw)
    self.assertEqual(order.status, "PENDING"); self.assertEqual(order.email, "ann@example.com")
    self.assertEqual(order.total_cents, 2200); self.assertEqual(order.lines.count(), 2)   # no zero line
    self.assertEqual(order.square_order_id, "SQ-1"); self.assertTrue(order.square_checkout_url)
    self.assertEqual(gw.calls[0][0], "create_payment_link")

def test_gateway_error_marks_failed(self):
    gw = FakeGateway(fail_with=GatewayError("down")); make_live_item(self.st.engagement)
    order = start(..., gateway=gw)
    self.assertEqual((order.status, order.error, order.square_order_id), ("FAILED", "down", ""))

def test_refuses_when_short_or_zero(self):
    make_live_item(self.st.engagement); self.st.online_allowance = 2; self.st.save()
    with self.assertRaises(Refused) as cm: start(..., quantities={"adult": 3}, ...)
    self.assertEqual(cm.exception.reason, "sold_out")
    with self.assertRaises(Refused) as cm: start(..., quantities={"adult": 0, "senior": 0, "child": 0}, ...)
    self.assertEqual(cm.exception.reason, "quantity")
    self.assertEqual(TicketOrder.objects.count(), 0)

def test_refuses_when_not_purchasable(self):   # no live item → "no_item"; gateway None → "disabled"
```

- [ ] **Step 2: Run to verify they fail** — ImportError.

- [ ] **Step 3: Implement `tickets/spec.py`, `tickets/orders.py` (start only), and the setting.**

`tickets:order` URL name does not exist yet; define `tickets/urls.py` with `app_name = "tickets"` and the two paths from Task 9 now, pointing at placeholder views that return 404, and include it in `fortkentcinema/urls.py` under `tickets/` so `reverse` works. Task 9 replaces the placeholders.

- [ ] **Step 4: Run the tests** — expected PASS.

- [ ] **Step 5: Commit** — `git commit -m "feat(tickets): checkout spec and order start"`

---

### Task 8: Confirmation, recovery, expiry, webhook hook

**Files:**
- Create: `tickets/mail.py`, `tickets/templates/tickets/email/ticket.txt`, `ticket.html`, `refund.txt`, `tickets/management/__init__.py`, `tickets/management/commands/__init__.py`, `tickets/management/commands/expire_ticket_orders.py`
- Modify: `tickets/orders.py`, `boxoffice/views.py`, `requirements.txt` (`qrcode==8.2` under a "Online tickets" comment)
- Test: `tickets/tests/test_mail.py`, `tickets/tests/test_orders_confirm.py`, `boxoffice/tests/test_webhook.py`

**Interfaces:**
- Produces:
  - `tickets.mail.qr_png(url: str) -> bytes`.
  - `tickets.mail.send_ticket(order) -> None`: `EmailMultiAlternatives`, subject `f"Your tickets: {title}, {Weekday Mon D} at {h:mm PM}"` in Eastern, text body from `email/ticket.txt`, HTML alternative from `email/ticket.html` referencing `cid:ticket-qr`, the QR attached as `MIMEImage` with that Content-ID, `to=[order.email]`. Body contains order number, title, date and time, screen, each line "2 × Adult $16.00", total, the street address, "Show this at the door, or just give your name.", "Tickets are non-refundable unless the show is cancelled.", and the confirmation URL.
  - `tickets.mail.send_refund(order) -> None`: subject `f"Refunded: {title}, {Weekday Mon D}"`, body names the amount, "cancelled", "within a few days", and `SITE_CONFIG["cinema"]["phone"]`.
  - `tickets.orders.confirm_payment(order_id: str, payment_id: str, *, paid_at=None) -> TicketOrder | None`: `select_for_update` the order by `square_order_id`; None when no row; PAID or REFUNDED → return unchanged; PENDING, EXPIRED, or FAILED-without-payment → set `square_payment_id`, `paid_at = paid_at or now`, status PAID, save; then outside the transaction `send_ticket`; on any exception from mail, status FAILED with `error=f"Ticket email failed: {exc!r}"` and `logger.exception`.
  - `tickets.orders.recover_pending(order, gateway=None) -> TicketOrder`: for a PENDING order with a `square_order_id`, `retrieve_order`; a tender with status `"COMPLETED"` (or `"CAPTURED"`, both recorded as paid by Square) → `confirm_payment(order_id, tender.payment_id, paid_at=order_data.paid_at)`; `GatewayError` → log, return unchanged.
  - `tickets.orders.expire_stale(now, gateway=None) -> int`: for each PENDING order older than the hold, `recover_pending`; those still PENDING become EXPIRED; return the count expired.
  - `tickets.orders.resend(order) -> TicketOrder`: for FAILED with a payment ID, retry `send_ticket`, PAID on success.
  - `expire_ticket_orders` command: calls `expire_stale(timezone.now())`, prints the count.
  - In `boxoffice/views.py`, after `process_order`: `confirm_payment(order_id, payment["id"], paid_at=_timestamp(payment.get("created_at")))` — import `from tickets.orders import confirm_payment` at module top (the one allowed import).

- [ ] **Step 1: Write the failing tests**

```python
# test_mail.py
def test_ticket_email_contents_and_qr(self):
    order = make_order(self.st, status="PAID", lines={"adult": 2, "child": 1})
    with override_settings(TICKETS_BASE_URL="https://www.fortkentcinema.com"): send_ticket(order)
    msg = mail.outbox[0]
    self.assertEqual(msg.to, ["ann@example.com"])
    self.assertRegex(msg.subject, r"^Your tickets: Dune, \w{3} \w{3} \d{1,2} at \d{1,2}:\d{2} [AP]M$")
    for text in [order.number, "2 × Adult", "$16.00", "Total $22.00", "give your name", "non-refundable",
                 f"https://www.fortkentcinema.com/tickets/order/{order.token}/"]:
        self.assertIn(text, msg.body)
    html = [a for a in msg.alternatives if a[1] == "text/html"][0][0]
    self.assertIn('src="cid:ticket-qr"', html)
    qr = [a for a in msg.attachments if getattr(a, "get_content_type", lambda: "")() == "image/png"]
    self.assertEqual(len(qr), 1)

def test_qr_png_decodes_to_the_url(self):
    self.assertEqual(qr_png("https://x/y")[:8], b"\x89PNG\r\n\x1a\n")

def test_refund_email(self): ...asserts "cancelled", "$22.00", "within a few days", the phone number.

# test_orders_confirm.py
def test_confirm_marks_paid_and_emails_once(self):
    order = make_order(self.st, square_order_id="SQ1")
    confirm_payment("SQ1", "P1", paid_at=PAID_AT); confirm_payment("SQ1", "P1", paid_at=PAID_AT)
    order.refresh_from_db()
    self.assertEqual((order.status, order.square_payment_id, order.paid_at), ("PAID", "P1", PAID_AT))
    self.assertEqual(len(mail.outbox), 1)

def test_unknown_order_is_ignored(self): self.assertIsNone(confirm_payment("nope", "P1"))

def test_expired_and_cancelled_showtime_still_pay(self):
    self.st.is_cancelled = True; self.st.save()
    order = make_order(self.st, status="EXPIRED", square_order_id="SQ1")
    self.assertEqual(confirm_payment("SQ1", "P1").status, "PAID")      # Review Focus 4

def test_mail_failure_leaves_failed_with_payment_and_resend_fixes_it(self):
    order = make_order(self.st, square_order_id="SQ1")
    with mock.patch("tickets.orders.send_ticket", side_effect=OSError("smtp")):
        order = confirm_payment("SQ1", "P1")
    self.assertEqual((order.status, order.square_payment_id), ("FAILED", "P1"))
    self.assertIn("Ticket email failed", order.error)
    self.assertEqual(resend(order).status, "PAID"); self.assertEqual(len(mail.outbox), 1)

def test_recover_pending_finds_the_tender(self):
    gw = FakeGateway(); make_live_item(self.st.engagement)
    order = start(self.st, ..., gateway=gw); gw.pay(order.square_order_id, "P3")
    self.assertEqual(recover_pending(order, gateway=gw).status, "PAID")

def test_expire_stale(self):
    gw = FakeGateway(); make_live_item(self.st.engagement)
    paid_late = start(...); unpaid = start(...); young = start(...)
    age(paid_late, 25); age(unpaid, 25); gw.pay(paid_late.square_order_id)
    self.assertEqual(expire_stale(NOW, gateway=gw), 1)
    ...paid_late PAID, unpaid EXPIRED, young PENDING

def test_expire_leaves_pending_on_gateway_error(self): ...

def test_command_prints_count(self): call_command("expire_ticket_orders") → "Expired 1 order"

# boxoffice/tests/test_webhook.py (new test in the existing module, keeping its mocks)
def test_completed_payment_reaches_tickets(self):
    with mock.patch("boxoffice.views.confirm_payment") as cp:
        post(self.client, event(order_id="SQ1"))
    cp.assert_called_once()
    self.assertEqual(cp.call_args.args[:2], ("SQ1", "P1"))
```

- [ ] **Step 2: Run to verify they fail** — ImportError / `qrcode` missing.

- [ ] **Step 3: Install `qrcode`, implement mail, confirm, recover, expire, the command, and the hook.**

`pip install qrcode==8.2` into `.venv` and add to `requirements.txt`. The email templates render with `{% autoescape off %}` for the text body.

- [ ] **Step 4: Run tickets and boxoffice tests** — expected PASS (same three baseline sync failures).

- [ ] **Step 5: Commit** — `git commit -m "feat(tickets): payment confirmation, ticket email, recovery and expiry"`

---

### Task 9: Public buy and order pages

**Files:**
- Create: `tickets/forms.py`, `tickets/templates/tickets/buy.html`, `tickets/templates/tickets/order.html`, `tickets/templates/tickets/_closed.html`
- Modify: `tickets/views.py`, `tickets/urls.py`, `static/css/` (one new stylesheet `tickets.css` loaded by the two templates, or a block in the site stylesheet, whichever the existing pages do; check `templates/base.html`)
- Test: `tickets/tests/test_views.py`

**Interfaces:**
- Produces:
  - `tickets.forms.BuyForm(forms.Form)`: `adult`, `senior`, `child` (`IntegerField(min_value=0, max_value=50, initial=0)`), `name` (`CharField(max_length=200)`), `email` (`EmailField`), `phone` (`CharField(max_length=40)`, `clean_phone` requires 7–20 characters once stripped of spaces and punctuation and only digits plus `+`), `website` honeypot (`CharField(required=False)`, non-empty → `is_bot()` True, same as `web.forms.AdInquiryForm`). `clean()` adds a non-field error "Pick at least one ticket." when all three are zero. `quantities() -> dict[str, int]`.
  - URLs: `tickets/<int:pk>/` name `tickets:buy`; `tickets/order/<str:token>/` name `tickets:order`.
  - `BuyView(View)`: GET renders `buy.html` with `showtime`, `movie` (title, poster, rating, runtime via `_format_runtime`, language label, captions note), `rows = price_table(starts_at)`, `availability`, `form`, `ticket_prices`; when not purchasable renders the same template with `_closed.html` in place of the form and the sentence for the reason: disabled/no_item → "Online tickets aren't available for this show. Buy at the door.", not_listed/cancelled → "This showtime isn't on sale.", cutoff → "Online sales for this show have closed. Tickets are still available at the door.", sold_out → "Sold out online. Tickets may still be available at the door." POST: bot → 303 to `tickets:buy` with nothing created; invalid → re-render with errors; valid → `orders.start`; `Refused` → re-render with the reason sentence; FAILED result → re-render with "We couldn't start checkout. Please try again, or buy at the door."; else 303 to `square_checkout_url`. A pk whose showtime does not exist is 404.
  - `OrderView(View)`: GET by token, 404 on miss; context `order`, `state` in {paid, pending, waiting, expired, refunded, failed}; `pending` when PENDING and `created_at > now - 2 min` (meta refresh 4 s); `waiting` when PENDING and older (no refresh, shows the "Return to payment" link to `square_checkout_url` and the check-your-email sentence); a PENDING order older than 60 s runs `recover_pending` once before choosing the state. `paid` covers PAID and FAILED-with-payment. Both templates set `{% block robots %}noindex, nofollow{% endblock %}`.

- [ ] **Step 1: Write the failing tests**

```python
def test_buy_page_lists_prices_and_matinee(self):
    html = get(self.matinee_st)
    self.assertIn("Dune", html); self.assertIn("$6", html); self.assertIn("Matinee", html)
    self.assertIn("Members pay $4 at the door", html)

def test_closed_sentences(self):   # one assert per reason, including a hidden run and 404 for pk 999

def test_post_all_zero(self):      # Review Focus 1
    r = post(self.st, adult=0, senior=0, child=0)
    self.assertContains(r, "Pick at least one ticket."); self.assertEqual(TicketOrder.objects.count(), 0)

def test_post_bad_phone_and_email(self): ...assertContains errors, no order

def test_post_over_remaining_is_refused(self):   # Review Focus 3
    self.st.online_allowance = 1; self.st.save()
    r = post(self.st, adult=2)
    self.assertContains(r, "Sold out online"); self.assertEqual(TicketOrder.objects.count(), 0)

def test_post_negative_is_invalid(self): post(self.st, adult=-1) → form error, no order

def test_honeypot(self): post(self.st, website="x") → 303, no order

def test_post_redirects_to_square(self):
    r = post(self.st, adult=2, child=1)
    self.assertEqual(r.status_code, 303); self.assertTrue(r["Location"].startswith("https://square.link/"))
    order = TicketOrder.objects.get(); self.assertEqual(order.total_cents, 2200)

def test_post_gateway_failure_message(self): ...FakeGateway(fail_with=GatewayError("x")) → "couldn't start checkout"

def test_order_states(self):
    # paid renders the ticket with the QR and the number; pending has the refresh meta;
    # waiting (created 3 min ago) has "Return to payment" and no refresh; expired/refunded/failed sentences
    ...
def test_order_page_recovers_after_sixty_seconds(self): gw.pay(...); age(order, 2); get → "Payment received"

def test_bad_token_404_and_noindex(self):
    self.assertEqual(self.client.get(reverse("tickets:order", args=["nope"])).status_code, 404)
    self.assertIn("noindex", get(self.st))
```

Tests patch `tickets.views.get_gateway` to return a `FakeGateway` and call `make_live_item`.

- [ ] **Step 2: Run to verify they fail**.

- [ ] **Step 3: Implement the form, views, URLs and templates.**

Templates extend `base.html`. Steppers: minimal Alpine (`x-data` per row, buttons adjust the input's value, total recomputed from `data-price`), the input itself is the submitted field so the form works without JS. Phone-first single column, 16px gutters; reuse the site's existing form and button classes (look at `web/templates/web/rentals.html` inquiry form for class names). Follow the existing site styles; no new design direction.

- [ ] **Step 4: Run tickets tests** — expected PASS.

- [ ] **Step 5: Commit** — `git commit -m "feat(tickets): public buy and order pages"`

---

### Task 10: Home page chips and JSON-LD offers

**Files:**
- Modify: `web/services/cinema_data.py` (`get_now_showing`), `web/views.py` (`HomeView`), `templates/partials/movie_schedule_card.html`, `templates/partials/home_jsonld.html`
- Test: `web/tests/test_cinema_data.py`, `web/tests/test_home_tickets.py`

**Interfaces:**
- Consumes: `tickets.availability.for_showtimes`, `boxoffice.gateway.disabled_reason`.
- Produces: each time dict in `get_now_showing()` gains `"showtime_id": st.pk`; `HomeView` adds to each time dict `"ticket_url"` (reverse of `tickets:buy`, or `""`) and `"sold_out"` (bool) from one `for_showtimes` call over all listed showtimes with `square_enabled = disabled_reason() is None`; each `ns_events` entry carries `ticket_url` and `sold_out`.

- [ ] **Step 1: Write the failing tests**

```python
# test_cinema_data.py
def test_time_dict_carries_showtime_id(self): ...

# test_home_tickets.py (override SQUARE settings so disabled_reason() is None; make_live_item)
def test_purchasable_chip_is_a_link(self):
    html = self.client.get(reverse("home")).content.decode()
    self.assertIn(f'href="{reverse("tickets:buy", args=[self.st.pk])}"', html)
    self.assertIn("Buy", html)

def test_sold_out_chip_is_plain_with_note(self):
    self.st.online_allowance = 0; self.st.save()
    html = ...; self.assertNotIn(reverse("tickets:buy", args=[self.st.pk]), html); self.assertIn("Sold out online", html)

def test_disabled_square_leaves_plain_chips(self): override SQUARE_ACCESS_TOKEN="" → no link, no note

def test_jsonld_offers(self):
    block = jsonld(html, None)   # reuse web.tests.test_crawl_and_schema.jsonld, walking @graph
    ev = block["@graph"][0]
    self.assertEqual(ev["offers"]["url"], f"http://testserver{reverse('tickets:buy', args=[self.st.pk])}")
    self.assertEqual(ev["offers"]["availability"], "https://schema.org/InStock")
    # sold out → SoldOut; closed → the existing /#now-showing url and InStock
```

- [ ] **Step 2: Run to verify they fail**.

- [ ] **Step 3: Implement.**

In `movie_schedule_card.html` replace the "Spans, not buttons" comment with one explaining the three chip states; purchasable: `<a class="showtime showtime--buy" href="{{ time.ticket_url }}">{{ time.time }} <span class="showtime__buy">Buy</span>…</a>`; sold out: the span with `<span class="showtime__note">Sold out online</span>`; else unchanged. Keep the captions chip and note markup inside both forms. Add the `.showtime--buy` and `.showtime__buy` styles beside the existing `.showtime` rule.

- [ ] **Step 4: Run web tests** — expected PASS.

- [ ] **Step 5: Commit** — `git commit -m "feat(home): showtime chips link to online tickets; offers in the screening events"`

---

### Task 11: Refunds

**Files:**
- Create: `tickets/refunds.py`
- Test: `tickets/tests/test_refunds.py`

**Interfaces:**
- Produces:
  - `refund_order(order, *, reason: str, gateway=None) -> TicketOrder`: only PAID (or FAILED-with-payment) orders; `gateway.refund_payment(payment_id=order.square_payment_id, amount_cents=order.total_cents, idempotency_key=f"refund-{order.number}", reason=reason)`; success → REFUNDED, `refunded_at`, `error=""`, then `send_refund(order)` (a mail failure stores `error=f"Refund email failed: {exc!r}"` and leaves REFUNDED); `GatewayError` → stays PAID with `error=str(exc)`. Gateway None → stays PAID with `error="Square sync disabled: ..."`.
  - `RefundSummary(refunded: int, failed: int)`; `refund_showtime(showtime, *, reason="Showtime cancelled", gateway=None) -> RefundSummary`: walks the showtime's PAID orders by pk.

- [ ] **Step 1: Write the failing tests**

```python
def test_refund_order_success(self):
    gw = FakeGateway(); order = make_order(self.st, status="PAID", square_payment_id="P1", lines={"adult": 2, "child": 1})
    order = refund_order(order, reason="Showtime cancelled", gateway=gw)
    self.assertEqual(order.status, "REFUNDED"); self.assertIsNotNone(order.refunded_at)
    self.assertEqual(gw.calls[0], ("refund_payment", {"payment_id": "P1", "amount_cents": 2200,
                     "idempotency_key": f"refund-{order.number}", "reason": "Showtime cancelled"}))
    self.assertEqual(mail.outbox[0].subject[:9], "Refunded:")

def test_refund_showtime_partial_failure(self):
    gw = FakeGateway(); a, b = paid orders; gw.fail_on = {b.square_payment_id}   # add to fake: payment ids that raise
    self.assertEqual(refund_showtime(self.st, gateway=gw), RefundSummary(1, 1))
    ...a REFUNDED, b PAID with error "boom", one email

def test_second_click_is_a_no_op(self): refunding a REFUNDED order makes no gateway call
def test_refund_without_gateway_records_reason(self): ...
def test_refund_email_failure_keeps_refunded(self): ...
```

Add `fail_on: set[str]` to `FakeGateway.refund_payment`: raise `GatewayError("boom")` for those payment IDs.

- [ ] **Step 2: Run to verify they fail** — ImportError.

- [ ] **Step 3: Implement `tickets/refunds.py` and the fake's `fail_on`.**

- [ ] **Step 4: Run tickets tests** — PASS.

- [ ] **Step 5: Commit** — `git commit -m "feat(tickets): refund one order or every order on a cancelled showtime"`

---

### Task 12: Dashboard: allowance field and online counts on the engagement page

**Files:**
- Modify: `dashboard/views.py` (`_render_showtime_form`, `ShowtimeCreateView.post`, `ShowtimeEditView.post`, `EngagementDetailView.get_context_data`, `_showtime_list_response`), `dashboard/templates/dashboard/_showtime_form.html`, `dashboard/templates/dashboard/_showtime_list.html`
- Test: `dashboard/tests/test_showtime_allowance.py`

**Interfaces:**
- Consumes: `tickets.availability.for_showtimes`.
- Produces: `online_allowance` input (number, optional, placeholder = the default) in both showtime forms; the list's new "Online" column "12 / 50" linking to `dashboard:showtime_orders` (Task 13 defines the URL; add the name to `dashboard/urls.py` now with the Task 13 view stubbed as a `TemplateView` that Task 13 replaces); a `warnings` context list rendered by `_form_alert.html` style for "N online orders were emailed the old time. Let them know." when the edit moves `starts_at` and PAID orders exist. Showtime context helper `showtime_rows(engagement, now) -> list[dict]` in `dashboard/views.py` returning `{"st", "sold", "allowance"}` for the list template.

- [ ] **Step 1: Write the failing tests**

```python
def test_edit_saves_allowance_and_blank_means_default(self):
    post edit with online_allowance="7" → st.online_allowance == 7; post with "" → None
def test_allowance_below_sold_is_allowed(self):             # Review Focus 5
    make_order(st, status="PAID", lines={"adult": 5}); post edit online_allowance="2"
    self.assertEqual(st.online_allowance, 2); self.assertEqual(remaining(st, now), 0)
def test_list_shows_online_count_with_link(self): "5 / 50" and the showtime_orders URL in the engagement page
def test_moving_a_showtime_with_orders_warns(self): toast/alert text "online orders were emailed the old time"
def test_create_form_accepts_allowance(self): ...
```

- [ ] **Step 2: Run to verify they fail**.

- [ ] **Step 3: Implement.**

Parse `online_allowance` with `int()` and reject negatives or non-numbers with "Online allowance must be a whole number." in the existing `errors` list.

- [ ] **Step 4: Run dashboard tests** — PASS.

- [ ] **Step 5: Commit** — `git commit -m "feat(dashboard): online allowance on showtimes, online counts on the engagement page"`

---

### Task 13: Dashboard: door list

**Files:**
- Create: `dashboard/ticket_views.py`, `dashboard/templates/dashboard/showtime_orders.html`, `dashboard/templates/dashboard/_ticket_order_row.html`, `dashboard/templates/dashboard/_ticket_order_rows.html`, `dashboard/templates/dashboard/_allowance_form.html`
- Modify: `dashboard/urls.py`
- Test: `dashboard/tests/test_showtime_orders.py`

**Interfaces:**
- Consumes: Task 4 `check`, Task 11 `refund_showtime`, `refund_order`, Task 8 `resend`.
- Produces URL names, all under `StaffRequiredMixin`:
  - `showtimes/<int:pk>/orders` → `dashboard:showtime_orders` (`ShowtimeOrdersView`, GET; `?q=` filters by name or number, case-insensitive; an HTMX request returns only `_ticket_order_rows.html`).
  - `showtimes/<int:pk>/orders.csv` → `dashboard:showtime_orders_export` (columns: number, name, email, phone, adult, senior, child, total, status, paid at, arrived at).
  - `showtimes/<int:pk>/allowance` → `dashboard:showtime_allowance` (POST `online_allowance`, blank = default; HTMX-swaps the header's count block, id `online-count`).
  - `showtimes/<int:pk>/refund-all` → `dashboard:showtime_refund_all` (POST; redirects back with a toast "13 refunded, 1 failed" via the existing `dashboard-toast` HX-Trigger or Django messages, whichever `_showtime_list_response` already uses — it uses HX-Trigger).
  - `tickets/orders/<int:pk>/arrive`, `.../unarrive` → `dashboard:ticket_order_arrive`, `dashboard:ticket_order_unarrive` (POST; set/clear `redeemed_at`, `redeemed_by`; HTMX returns `_ticket_order_row.html`).
  - `tickets/orders/<int:pk>/retry` → `dashboard:ticket_order_retry` (POST; `resend` for FAILED-with-payment; otherwise toast with the error).
  - `tickets/orders/<int:pk>/refund` → `dashboard:ticket_order_refund` (POST; `refund_order(reason="Refunded by staff")`; row swap).
- Rows: PAID, REFUNDED and FAILED-with-payment orders sorted by `name`, columns number, name, phone, breakdown, total, status pill (`status-active` PAID, `status-draft` REFUNDED, `status-cancelled` FAILED), arrive button or "Arrived 6:52 PM · <first name or username>" with Undo. Cancelled showtime: red banner `alert alertWarning` with the Refund-all form carrying `data-dashboard-confirm` naming the count and total.

- [ ] **Step 1: Write the failing tests**

```python
def test_requires_staff_everywhere(self): each URL 302 anonymous, 403 non-staff
def test_rows_sorted_by_name_and_only_valid_statuses(self): PAID Zed, PAID Ann, PENDING Bob, REFUNDED Cy → order Ann, Cy, Zed; Bob absent
def test_search_filters_by_name_or_number(self): ?q=ann and ?q=<number>
def test_arrive_and_undo(self): POST arrive → "Arrived", redeemed_by == staff user; unarrive clears
def test_allowance_inline_edit(self): POST "7" → 7; "" → None; "x" → 400 with message
def test_csv_columns_and_formula_neutralising(self): name "=HYPERLINK()" comes out prefixed with "'"
def test_refund_all_banner_only_when_cancelled_with_paid_orders(self): ...
def test_refund_all_summary_toast(self): FakeGateway with fail_on → "1 refunded, 1 failed"
def test_retry_resends_and_refund_single(self): ...
```

Patch `dashboard.ticket_views.get_gateway` to the fake.

- [ ] **Step 2: Run to verify they fail** — 404s/ImportError.

- [ ] **Step 3: Implement the views and templates**, following `square_sales.html` and `_square_sale_row.html` for markup and `membership_sale_views.py` for the HTMX/toast pattern. Replace the Task 12 stub.

- [ ] **Step 4: Run dashboard tests** — PASS.

- [ ] **Step 5: Commit** — `git commit -m "feat(dashboard): per-showtime door list with arrivals, allowance, refund-all and CSV"`

---

### Task 14: Dashboard: pre-sale summary and order log

**Files:**
- Create: `dashboard/templates/dashboard/tickets.html`, `dashboard/templates/dashboard/ticket_orders.html`
- Modify: `dashboard/ticket_views.py`, `dashboard/urls.py`, `dashboard/templates/dashboard/_sidebar.html`
- Test: `dashboard/tests/test_ticket_pages.py`

**Interfaces:**
- Produces:
  - `tickets` → `dashboard:tickets` (`TicketSummaryView`): `?tab=upcoming` (default) or `past`; context `totals = {"today": {"tickets", "gross_dollars"}, "week": {...}}`, `days = [{"date", "label", "rows": [{"st", "sold", "gross_dollars", "allowance"}]}]`; past tab paginated 50 by `Paginator`. Uses one grouped aggregate over `TicketLine` for PAID and FAILED-with-payment orders: `tickets.availability.sold_and_gross(showtimes) -> dict[int, tuple[int, int]]` (add it to `availability.py` here).
  - `tickets/orders` → `dashboard:ticket_orders` (`TicketOrderListView`): `?status=` filter, paginated 50, newest first; row shows created, number, buyer, show link to the door list, amount, pill, error, Retry (FAILED) and Refund (PAID) buttons reusing Task 13 endpoints; `tickets/orders.csv` → `dashboard:ticket_orders_export` with the door-list columns plus film and showtime.
  - Sidebar entry "Online tickets" placed alphabetically (between "Memberships" and "Polls"), with a ticket icon SVG in the sidebar's 20×20 stroke style; `nav_active` for `dashboard:tickets`.

- [ ] **Step 1: Write the failing tests**

```python
def test_summary_totals_and_grouping(self): two showtimes today and one in 3 days; today totals count only today; week counts all three; zero-sales showtime listed
def test_summary_past_tab(self): a showtime that started yesterday appears under past, not upcoming
def test_order_log_filter_and_pagination(self): ?status=FAILED shows only failed; 51 orders → 2 pages
def test_order_log_csv_has_film_and_showtime(self): ...
def test_sidebar_link_and_staff_only(self): ...
```

- [ ] **Step 2: Run to verify they fail**.

- [ ] **Step 3: Implement.**

- [ ] **Step 4: Run dashboard tests** — PASS.

- [ ] **Step 5: Commit** — `git commit -m "feat(dashboard): online ticket summary and order log"`

---

### Task 15: Alerts and the home panel

**Files:**
- Modify: `dashboard/smart_alerts.py`, `dashboard/views.py` (`HomeView`), `dashboard/templates/dashboard/home.html`
- Create: `tickets/alerts.py`
- Test: `dashboard/tests/test_smart_alerts.py`, `dashboard/tests/test_home.py`

**Interfaces:**
- Produces:
  - `tickets.alerts.failures_count() -> int` (FAILED orders, with or without payment).
  - `tickets.alerts.nearly_sold_out(now) -> list[tuple[Showtime, int, int]]`: non-cancelled showtimes starting within 2 days with allowance > 0 and `sold >= ceil(allowance * 0.9)`.
  - `tickets.alerts.cancelled_with_orders() -> list[tuple[Showtime, int]]`: cancelled showtimes with ≥ 1 PAID order, future or past (unrefunded money is unrefunded).
  - `build_smart_alerts(..., ticket_failures: int = 0, nearly_sold_out=(), cancelled_with_orders=())` appends: warning `ticket-failures` "N online ticket order(s) need attention" url `dashboard:ticket_orders?status=FAILED`; info `nearly-sold-out-<pk>` "<title> at <g:i A> is nearly sold out online (45 of 50)" url door list; warning `cancelled-orders-<pk>` "<title> at <g:i A> is cancelled with N unrefunded online order(s)" url door list.
  - `HomeView` passes the three; `today_showtimes` rows gain an "Online" cell from `for_showtimes`.

- [ ] **Step 1: Write the failing tests**

```python
def test_ticket_failures_alert_singular_and_plural(self): ...
def test_nearly_sold_out_at_ninety_percent(self): allowance 50, sold 45 → alert; sold 44 → none; 3 days out → none
def test_cancelled_with_orders(self): ...
def test_home_today_panel_shows_online_count(self): "3 online" in the row
```

- [ ] **Step 2: Run to verify they fail**.

- [ ] **Step 3: Implement.**

- [ ] **Step 4: Run dashboard tests** — PASS.

- [ ] **Step 5: Commit** — `git commit -m "feat(dashboard): online ticket alerts and today's online counts"`

---

### Task 16: Admin, docs, full-suite run

**Files:**
- Create: `tickets/admin.py` (read-mostly `TicketOrder` admin with `TicketLine` inline, list filter on status, search on number/name/email)
- Modify: `README.md` (one paragraph: the `expire_ticket_orders` nightly command beside the pull command; `TICKETS_BASE_URL`), the spec's Amendments section for anything that diverged during implementation.
- Test: whole suite.

- [ ] **Step 1: Add the admin and docs.**

- [ ] **Step 2: Run everything**

Run: `.venv/bin/python manage.py test -v 1 2>&1 | tail -5` and `.venv/bin/flake8 tickets dashboard/ticket_views.py boxoffice/gateway.py web/services/cinema_data.py`
Expected: only the three baseline `test_sync` failures; no new flake8 findings on changed lines.

- [ ] **Step 3: Commit** — `git commit -m "chore(tickets): admin, docs, amendments"`

Then stop. Merge, push and the sandbox-to-production rollout (Section "Rollout" in the spec: seat counts, `TICKETS_BASE_URL`, first real ticket) are the owner's.
