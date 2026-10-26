# Membership Checkout Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A visitor joins or renews a membership from `/membership/` (or the member home), pays on Square's hosted checkout, and lands in the roster with a dated term and a welcome email, with no staff typing.

**Architecture:** A new `join` app mirrors `tickets`: a PENDING `MembershipOrder`, a Square payment link with one explicit-priced line, an order page that trusts only our row. On payment the existing `boxoffice.memberships.process_order` enters the member and term; a registered "order source" hook supplies the buyer from the join row and gets a `record` callback to mark it PAID and email. Nothing in `boxoffice` or `audience` imports `join`.

**Tech Stack:** Django 5.2, Square Python SDK through `boxoffice.gateway`, `FakeGateway` in tests, `python manage.py test`, esbuild CSS bundle (`cd frontend && npm run build:css`).

**Spec:** `docs/superpowers/specs/2026-10-26-membership-checkout-design.md` (read its Amendments section: it supersedes the handler in Section 1 step 5 and Section 3).

## Global Constraints

- Branch `feat/membership-checkout`. The owner commits on request: stop at each task's commit step and report unless the owner has said per-task commits are fine.
- Run `python manage.py test <app>` for the task's app, and the full suite (`python manage.py test --parallel`, baseline 2621 tests OK) before any commit.
- Lint gate: no new flake8 findings on changed lines (the repo baseline is dirty).
- Copy is exact where the spec quotes it; dates render as `M j, Y` ("Oct 26, 2026") everywhere a date is shown to a buyer.
- Settings names: `SQUARE_ACCESS_TOKEN`, `SQUARE_LOCATION_ID`, `SQUARE_TICKET_CATEGORY_ID`, `SQUARE_ENVIRONMENT`, `TICKETS_BASE_URL`, `SQUARE_WEBHOOK_URL`. `boxoffice.gateway.square_enabled()` is the one "is Square on" answer.
- Order numbers: prefix `FKM-` + 5 characters from `ABCDEFGHJKLMNPQRSTUVWXYZ23456789`.
- Every public join/order page is `noindex, nofollow`; the order page is `never_cache`.
- Tests patch `join.views.get_gateway` (views) and pass `gateway=` explicitly (orders), the way `tickets` tests do; tier variation IDs are set in `setUp` with `MembershipTier.objects.filter(slug=...).update(square_variation_id=...)`.

## Review Focus

1. A buyer types an email that already belongs to a roster member with a term that never expires (`expires_on = date.max`): the sale is FAILED, the join row is FAILED, the page says "Payment received. We're finishing your membership", no email. Pinned in Task 7.
2. Square's retry delivers the same `payment.updated` twice, seconds apart: one term, one email. Pinned in Task 7 (`record` idempotent) and Task 10 (end to end).
3. The buyer pays, closes the tab, and opens the link an hour later with the webhook lost: the order page's recovery enters the membership. Pinned in Task 8.
4. The buyer's typed first name has a space ("Mary Ann") and the last name two words ("van Dyke"): stored as typed on the member row, not re-split. Pinned in Task 4.
5. Square is turned off (`SQUARE_ACCESS_TOKEN` blank) after links were issued: tier cards and the join page show the box-office sentence, the member home shows no Renew button, and an order page still renders. Pinned in Tasks 9, 12 and 13.

---

### Task 1: `CheckoutSpec` without a showtime

**Files:**
- Modify: `boxoffice/gateway.py` (`CheckoutSpec`, `payment_link_body`)
- Test: `boxoffice/tests/test_gateway.py`

**Interfaces:**
- Produces: `CheckoutSpec(reference, lines, redirect_url, buyer_email, buyer_phone, support_email, idempotency_key, customer_id="", showtime_id: int | None = None)`. `payment_link_body` writes `order["metadata"] = {"showtime": str(id)}` only when `showtime_id` is not None.

- [ ] **Step 1: Write the failing test** in `boxoffice/tests/test_gateway.py`, next to `test_payment_link_body_matinee`:

```python
def test_payment_link_body_without_showtime_has_no_metadata(self) -> None:
    spec = dataclasses.replace(MATINEE_SPEC, showtime_id=None)
    self.assertNotIn("metadata", payment_link_body(spec, "LOC1")["order"])

def test_payment_link_body_with_showtime_keeps_metadata(self) -> None:
    body = payment_link_body(MATINEE_SPEC, "LOC1")
    self.assertEqual(body["order"]["metadata"], {"showtime": str(MATINEE_SPEC.showtime_id)})
```

- [ ] **Step 2: Run** `python manage.py test boxoffice.tests.test_gateway` — expected FAIL (metadata always written).
- [ ] **Step 3: Implement**: move `showtime_id` to the end of `CheckoutSpec` with default `None`; in `payment_link_body` add the `metadata` key only when it is not None. `tickets/spec.py` keeps passing `showtime_id=order.showtime_id` by keyword (check it already does; fix if positional).
- [ ] **Step 4: Run** `python manage.py test boxoffice tickets` — expected OK.
- [ ] **Step 5: Commit** `refactor(boxoffice): CheckoutSpec no longer needs a showtime`.

### Task 2: Share the customer and site helpers through `boxoffice`

**Files:**
- Create: `boxoffice/customers.py`, `boxoffice/site.py`
- Modify: `tickets/customers.py` (delete), `tickets/orders.py:~90`, `tickets/spec.py` (`base_url`, `support_email` become imports)
- Test: existing `tickets/tests/test_orders_start.py`, `tickets/tests/test_spec.py`

**Interfaces:**
- Produces: `boxoffice.customers.ensure_customer(gateway, *, first_name, last_name, email, phone, key, label) -> str` (phone is E.164 or ""; idempotency keys `customer-{key}` and `customer-{key}-nophone`; `label` names the order in the warning log; "" on any `GatewayError`).
- Produces: `boxoffice.site.base_url() -> str`, `boxoffice.site.support_email() -> str`, moved verbatim from `tickets/spec.py`.

- [ ] **Step 1:** Create `boxoffice/site.py` with the two functions and their docstrings moved from `tickets/spec.py`; in `tickets/spec.py` replace them with `from boxoffice.site import base_url, support_email` (keep the names importable from `tickets.spec`: `tickets.views` and `tickets.mail` use them).
- [ ] **Step 2:** Create `boxoffice/customers.py` from `tickets/customers.py` with the new signature; `_create` takes the same keyword fields. Delete `tickets/customers.py`. In `tickets/orders.py` call `ensure_customer(gateway, first_name=order.first_name, last_name=order.last_name, email=order.email, phone=e164_phone(order.phone), key=order.token, label=order.number)`.
- [ ] **Step 3: Run** `python manage.py test tickets boxoffice` — expected OK with no test changes (the existing start tests assert the customer calls and keys).
- [ ] **Step 4: Commit** `refactor(boxoffice): share the Square customer and site-URL helpers with other apps`.

### Task 3: `MembershipSale.source`

**Files:**
- Modify: `boxoffice/models/membership_sale.py`
- Create: `boxoffice/migrations/0014_membershipsale_source.py` (makemigrations)
- Test: `boxoffice/tests/test_models.py`

**Interfaces:**
- Produces: `MembershipSale.Source` TextChoices `LINK = "LINK", "Payment link"`, `WEBSITE = "WEBSITE", "Website"`; field `source = CharField(max_length=8, choices=Source.choices, default=Source.LINK)`.

- [ ] **Step 1: Write the failing test**:

```python
def test_sale_source_defaults_to_payment_link(self):
    sale = MembershipSale.objects.create(order_id="O1", status="FAILED")
    self.assertEqual((sale.source, sale.get_source_display()), ("LINK", "Payment link"))
```

- [ ] **Step 2: Run** `python manage.py test boxoffice.tests.test_models` — expected FAIL (no `source`).
- [ ] **Step 3: Implement** the field; `python manage.py makemigrations boxoffice -n membershipsale_source`.
- [ ] **Step 4: Run** `python manage.py test boxoffice` — expected OK.
- [ ] **Step 5: Commit** `feat(boxoffice): record whether a membership sale came from a link or the website`.

### Task 4: Order sources in `boxoffice.memberships`

**Files:**
- Modify: `boxoffice/memberships.py`
- Test: `boxoffice/tests/test_memberships.py`

**Interfaces:**
- Produces:

```python
@dataclasses.dataclass(frozen=True)
class Buyer:
    display_name: str
    email: str
    phone: str
    first_name: str = ""
    last_name: str = ""

class OrderSource(Protocol):
    def buyer_for(self, order_id: str) -> Buyer | None: ...
    def record(self, order_id: str, sale: MembershipSale, order: OrderData | None) -> None: ...

def register_order_source(source: OrderSource) -> None  # no duplicates, like register_payment_handler
def order_sources() -> list[OrderSource]  # a copy, for tests and checks
def clear_order_sources() -> None  # tests only
```

- `_Buyer` is renamed `Buyer` (update the two internal uses). `_member` uses `(buyer.first_name[:100], buyer.last_name[:100])` when either is non-empty, else `split_name(display_name)`.
- `process_order` flow, after `membership_lines` is non-empty: `buyer = _buyer(order.recipient)`; if `order.recipient is None` (or its email is blank), ask each registered source `buyer_for(order_id)` in order; the first non-None is the buyer and `answered = that source`. `_Facts` gains `source: str` (`WEBSITE` when answered, else `LINK`); `_attribute` writes `sale.source = facts.source`. After `_attribute` returns, `_notify([answered] if answered else [], order_id, sale, order)`.
- Early failures (`gateway is None`, `GatewayError` on fetch) call `_notify(all sources, order_id, sale, None)` after `_fail_unless_finished`.
- `_notify(sources, order_id, sale, order)`: for each source call `record` inside `try`/`except Exception: logger.exception(...)`. Outside any transaction.
- The register-sale skip ("No buyer email (register sale)") happens only when no source answered.

- [ ] **Step 1: Write the failing tests** (add a `FakeSource` to the test module: `buyer_for` returns `self.buyer` when `order_id in self.orders`, `record` appends `(order_id, sale.status, order)` to `self.recorded`; a `BrokenSource` whose `record` raises). In `setUp` call `clear_order_sources()` and `self.addCleanup(clear_order_sources)`.

```python
class OrderSourceTests(MembershipOrderTestCase):
    def setUp(self):
        super().setUp()
        clear_order_sources()
        self.addCleanup(clear_order_sources)
        self.source = FakeSource({"O1"}, Buyer("Mary Ann van Dyke", "mav@example.com", "",
                                              first_name="Mary Ann", last_name="van Dyke"))
        register_order_source(self.source)

    def test_source_supplies_the_buyer_when_square_has_no_recipient(self):
        self.membership_order(recipient=None)
        sale = process_order("O1", self.gw)
        member = Member.objects.get(email="mav@example.com")
        self.assertEqual((member.first_name, member.last_name), ("Mary Ann", "van Dyke"))
        self.assertEqual((sale.status, sale.source, sale.display_name),
                         ("OK", "WEBSITE", "Mary Ann van Dyke"))

    def test_source_is_told_the_outcome_with_the_fetched_order(self):
        order = self.membership_order(recipient=None)
        sale = process_order("O1", self.gw)
        self.assertEqual(self.source.recorded, [("O1", "OK", order)])

    def test_recipient_wins_over_the_source(self):
        self.membership_order()  # ANN as recipient
        sale = process_order("O1", self.gw)
        self.assertEqual((sale.source, sale.email), ("LINK", "ann@example.com"))
        self.assertEqual(self.source.recorded, [])

    def test_order_no_source_knows_is_still_a_register_sale(self):
        self.membership_order(order_id="O2", recipient=None)
        sale = process_order("O2", self.gw)
        self.assertEqual((sale.status, sale.source), ("SKIPPED", "LINK"))

    def test_fetch_failure_is_recorded_to_every_source_without_an_order(self):
        sale = process_order("O1", FakeGateway(fail_with=GatewayError("boom")))
        self.assertEqual(self.source.recorded, [("O1", "FAILED", None)])

    def test_attribution_failure_is_recorded(self):
        self.membership_order(recipient=None, quantity=2)
        sale = process_order("O1", self.gw)
        self.assertEqual(self.source.recorded[0][:2], ("O1", "FAILED"))

    def test_a_broken_record_does_not_undo_the_term(self):
        register_order_source(BrokenSource())
        self.membership_order(recipient=None)
        with self.assertLogs("boxoffice.memberships", "ERROR"):
            sale = process_order("O1", self.gw)
        self.assertEqual((sale.status, MembershipTerm.objects.count()), ("OK", 1))
```

- [ ] **Step 2: Run** `python manage.py test boxoffice.tests.test_memberships` — expected FAIL (ImportError on `Buyer`, `register_order_source`).
- [ ] **Step 3: Implement** as in Interfaces. Keep `_facts`' signature change internal; `_buyer()` still builds from the recipient.
- [ ] **Step 4: Run** `python manage.py test boxoffice` — expected OK, including every existing `test_memberships` case unchanged.
- [ ] **Step 5: Commit** `feat(boxoffice): membership orders can name their buyer through a registered order source`.

### Task 5: The `join` app, model and admin

**Files:**
- Create: `join/__init__.py`, `join/apps.py`, `join/models.py`, `join/admin.py`, `join/urls.py` (empty `urlpatterns`, `app_name = "join"`), `join/migrations/0001_initial.py`, `join/tests/__init__.py`, `join/tests/factories.py`, `join/tests/test_models.py`
- Modify: `fortkentcinema/settings.py:55` (add `"join.apps.JoinConfig"` after tickets), `fortkentcinema/urls.py:114` (add `path("", include("join.urls"))` before the `web.urls` include)

**Interfaces:**
- Produces `join.models.MembershipOrder` per the spec's Section 2 table, with `Status` TextChoices `PENDING`/`PAID`/`FAILED` ("Needs attention")/`ABANDONED` ("Never started"); `new_number()` (`FKM-` + 5 from `NUMBER_ALPHABET`, copied from tickets, not imported); `new_token()`; properties `name` (first + last stripped) and `total_dollars`; `save()` lowercases and strips `email`. `Meta`: ordering `-created_at`; partial unique on non-blank `square_order_id` named `join_one_order_per_square_order`; index `(status, created_at)`.
- Produces `join.tests.factories.make_order(tier_slug="individual", *, status="PENDING", **over) -> MembershipOrder` (defaults: Ann Lee, `ann@example.com`, `total_cents` = tier price × 100, `square_order_id` "SQ-1" when status is not ABANDONED) and `set_variation(slug="individual", variation_id="VAR-IND") -> MembershipTier`.
- `JoinConfig.ready()` is empty for now (Task 7 fills it).
- Admin: `list_display = ("number", "created_at", "status", "tier", "first_name", "last_name", "email", "total_dollars")`, `list_filter = ("status", "tier")`, `search_fields = ("number", "email", "first_name", "last_name", "square_order_id")`, every Square field and date read-only, `has_add_permission` returns False.

- [ ] **Step 1: Write the failing tests** in `join/tests/test_models.py`:

```python
class MembershipOrderTests(TestCase):
    def test_defaults(self):
        order = make_order()
        self.assertRegex(order.number, r"^FKM-[ABCDEFGHJKLMNPQRSTUVWXYZ23456789]{5}$")
        self.assertEqual(len(order.token), 43)
        self.assertEqual((order.status, order.total_cents, order.name), ("PENDING", 6000, "Ann Lee"))

    def test_email_is_normalised(self):
        order = make_order(email=" Ann@Example.com ")
        self.assertEqual(order.email, "ann@example.com")

    def test_one_order_per_square_order(self):
        make_order(square_order_id="SQ-9")
        with self.assertRaises(IntegrityError):
            make_order(square_order_id="SQ-9")

    def test_blank_square_order_ids_may_repeat(self):
        make_order(status="ABANDONED"); make_order(status="ABANDONED")
```

- [ ] **Step 2: Run** `python manage.py test join` — expected FAIL (no app).
- [ ] **Step 3: Implement** the app, model, admin, settings and URL include; `python manage.py makemigrations join`.
- [ ] **Step 4: Run** `python manage.py test join` then `python manage.py check` — expected OK.
- [ ] **Step 5: Commit** `feat(join): the membership order model`.

### Task 6: Checkout spec and `start()`

**Files:**
- Create: `join/spec.py`, `join/orders.py`, `join/tests/test_spec.py`, `join/tests/test_orders_start.py`

**Interfaces:**
- Produces `join.spec.checkout_spec(order: MembershipOrder) -> CheckoutSpec`: `reference=order.number`, `lines=(CheckoutLine(variation_id=order.tier.square_variation_id, name=order.tier.name, quantity=1, unit_cents=order.total_cents, discount_cents=0),)`, `redirect_url=base_url() + reverse("join:order", args=[order.token])`, `buyer_email=order.email`, `buyer_phone=""`, `support_email=support_email()`, `idempotency_key=order.token`, `customer_id=order.square_customer_id`, no `showtime_id`.
- Produces `join.orders.NotSoldOnline(Exception)` and `join.orders.start(tier: MembershipTier, *, first_name: str, last_name: str, email: str, gateway: Gateway) -> MembershipOrder`: raises `NotSoldOnline` before saving when `tier.square_variation_id` is blank or `tier.show_on_membership_page` is False; else creates the PENDING row (`total_cents = tier.price * 100`), calls `ensure_customer(gateway, first_name=..., last_name=..., email=order.email, phone="", key=order.token, label=order.number)`, saves `square_customer_id`, then `gateway.create_payment_link(checkout_spec(order))`; `GatewayError` → status ABANDONED with `error = str(exc)`; success stores `square_order_id` and `square_checkout_url`. No `InvalidPhone` retry (no phone is sent).
- The `join:order` URL arrives in Task 9. Until then this task's spec test patches `join.spec.reverse` (see the test); Task 9 removes the patch.

- [ ] **Step 1: Write the failing tests**:

```python
# test_spec.py
@override_settings(TICKETS_BASE_URL="https://www.fortkentcinema.com/", DEFAULT_FROM_EMAIL="Fort Kent Cinema <hello@fortkentcinema.com>")
def test_spec_has_one_explicitly_priced_line_and_no_showtime(self):
    set_variation(); order = make_order(square_customer_id="C-3")
    with mock.patch("join.spec.reverse", return_value=f"/membership/order/{order.token}/"):
        spec = checkout_spec(order)
    line = spec.lines[0]
    self.assertEqual((len(spec.lines), line.variation_id, line.name, line.quantity, line.unit_cents, line.discount_cents),
                     (1, "VAR-IND", "Individual", 1, 6000, 0))
    self.assertEqual((spec.reference, spec.buyer_email, spec.buyer_phone, spec.customer_id, spec.showtime_id, spec.idempotency_key),
                     (order.number, "ann@example.com", "", "C-3", None, order.token))
    self.assertEqual(spec.redirect_url, f"https://www.fortkentcinema.com/membership/order/{order.token}/")
    self.assertEqual(spec.support_email, "hello@fortkentcinema.com")

# test_orders_start.py
BUYER = {"first_name": "Ann", "last_name": "Lee", "email": " Ann@Example.com"}

def test_start_creates_pending_order_customer_and_link(self):
    gw = FakeGateway(); tier = set_variation()
    order = start(tier, gateway=gw, **BUYER); order.refresh_from_db()
    self.assertEqual((order.status, order.email, order.total_cents, order.tier, order.square_order_id, order.square_checkout_url, order.square_customer_id),
                     ("PENDING", "ann@example.com", 6000, tier, "SQ-1", "https://square.link/u/1", "C-1"))
    self.assertEqual([c[0] for c in gw.calls], ["find_customer", "create_customer", "create_payment_link"])
    self.assertEqual(gw.customers["C-1"], {"given_name": "Ann", "family_name": "Lee", "email": "ann@example.com", "phone": ""})
    spec = gw.calls[-1][1]["spec"]
    self.assertEqual((spec.reference, spec.lines[0].variation_id, spec.lines[0].unit_cents), (order.number, "VAR-IND", 6000))

def test_gateway_failure_abandons_the_order(self):
    tier = set_variation()
    order = start(tier, gateway=FakeGateway(fail_with=GatewayError("boom")), **BUYER)
    self.assertEqual((order.status, order.error, order.square_order_id), ("ABANDONED", "boom", ""))

def test_tier_without_a_variation_is_refused_before_saving(self):
    tier = MembershipTier.objects.get(slug="individual")
    with self.assertRaises(NotSoldOnline):
        start(tier, gateway=FakeGateway(), **BUYER)
    self.assertEqual(MembershipOrder.objects.count(), 0)

def test_unlisted_tier_is_refused(self):
    tier = set_variation(); tier.show_on_membership_page = False; tier.save()
    with self.assertRaises(NotSoldOnline):
        start(tier, gateway=FakeGateway(), **BUYER)
```

(`fail_with` makes `find_customer` raise too; `ensure_customer` swallows that and `create_payment_link` then raises, so the second test holds.)

- [ ] **Step 2: Run** `python manage.py test join` — expected FAIL (no `join.spec`, `join.orders`).
- [ ] **Step 3: Implement** both modules.
- [ ] **Step 4: Run** `python manage.py test join` — expected OK.
- [ ] **Step 5: Commit** `feat(join): start a membership checkout on Square`.

### Task 7: The order source and the welcome email

**Files:**
- Create: `join/source.py`, `join/mail.py`, `join/templates/join/email/welcome.txt`, `join/templates/join/email/welcome.html`, `join/tests/test_source.py`, `join/tests/test_mail.py`
- Modify: `join/apps.py` (`ready()` registers the source)

**Interfaces:**
- Produces `join.source.MembershipOrderSource` with `buyer_for(order_id) -> Buyer | None` (a row with that `square_order_id` whose status is PENDING, FAILED or PAID: `Buyer(display_name=order.name, email=order.email, phone="", first_name=order.first_name, last_name=order.last_name)`; ABANDONED or unknown → None) and `record(order_id, sale, order)`:
  - lock the row (`select_for_update`) inside `transaction.atomic()`; unknown → return;
  - `sale.status == OK`: `was_paid = row.status == PAID`; set `status=PAID`, `term=sale.term`, `sale=sale`, `paid_at=sale.paid_at`, `error=""`, and `square_payment_id` = the first tender with `.paid` from `order.tenders` when `order` is given and the field is blank; save; after the transaction, if not `was_paid`, `send_welcome(row)` in `try`/`except Exception: logger.exception("Welcome email failed for order %s", row.number)`;
  - any other sale status: if row is PAID, leave it; else `status=FAILED`, `error=sale.error`, `sale=sale`; save; no email.
- Produces module-level `SOURCE = MembershipOrderSource()`; `JoinConfig.ready()` does `register_order_source(SOURCE)`.
- Produces `join.mail.welcome_context(order) -> dict` with keys `order`, `tier_name`, `started_on`, `expires_on` (strings `M j, Y` via `date_format`/`strftime("%b %-d, %Y")`), `renewal: bool` (the term's member has more than one term), `register_url` (`base_url() + reverse("register")`), `url` (the order page), `cinema` (`SITE_CONFIG["cinema"]`); and `send_welcome(order) -> None` with subject "Welcome to Fort Kent Cinema" or "Your Fort Kent Cinema membership is renewed", `to=[order.email]`, text body + HTML alternative.
- Welcome text body (exact):

```
Hi {{ order.first_name }},

{% if renewal %}Thanks for renewing your Fort Kent Cinema membership.{% else %}Welcome to the Fort Kent Cinema. You're a member.{% endif %}

Order {{ order.number }}
{{ tier_name }} membership
Good from {{ started_on }} through {{ expires_on }}

There's no card to carry. Give your name at the box office.

See your membership online: create an account with this email at {{ register_url }}
Your order: {{ url }}

Fort Kent Cinema
{{ cinema.address.street }}, {{ cinema.address.city }}, {{ cinema.address.state }} {{ cinema.address.zip }}
{{ cinema.phone }}
```

- [ ] **Step 1: Write the failing tests** (`test_source.py` builds a term with `MembershipTerm.objects.create` and a sale with `MembershipSale.objects.create(order_id="SQ-1", status="OK", term=term, paid_at=...)`; `order` data via `OrderData(order_id="SQ-1", closed_at=None, lines=(), tenders=(Tender("P7", "CAPTURED", "CARD", 6000),))`):

```python
def test_buyer_for_pending_order_carries_the_typed_names(self):
    make_order(first_name="Mary Ann", last_name="van Dyke", square_order_id="SQ-1")
    buyer = SOURCE.buyer_for("SQ-1")
    self.assertEqual((buyer.display_name, buyer.first_name, buyer.last_name, buyer.email, buyer.phone),
                     ("Mary Ann van Dyke", "Mary Ann", "van Dyke", "ann@example.com", ""))

def test_buyer_for_unknown_or_abandoned_is_none(self):
    make_order(status="ABANDONED")
    self.assertIsNone(SOURCE.buyer_for("SQ-1")); self.assertIsNone(SOURCE.buyer_for("nope"))

def test_ok_sale_marks_paid_stores_payment_and_emails_once(self):
    order = make_order(square_order_id="SQ-1"); sale, data = self.ok_sale()
    SOURCE.record("SQ-1", sale, data); SOURCE.record("SQ-1", sale, data)
    order.refresh_from_db()
    self.assertEqual((order.status, order.term, order.sale, order.paid_at, order.square_payment_id, order.error),
                     ("PAID", sale.term, sale, sale.paid_at, "P7", ""))
    self.assertEqual(len(mail.outbox), 1)

def test_failed_sale_marks_failed_without_email(self):
    order = make_order(square_order_id="SQ-1")
    sale = MembershipSale.objects.create(order_id="SQ-1", status="FAILED", error="Current term never expires")
    SOURCE.record("SQ-1", sale, None); order.refresh_from_db()
    self.assertEqual((order.status, order.error, order.sale), ("FAILED", "Current term never expires", sale))
    self.assertEqual(mail.outbox, [])

def test_failed_after_paid_never_downgrades(self): ...  # PAID row stays PAID, error untouched

def test_failed_email_leaves_the_order_paid(self):
    with mock.patch("join.source.send_welcome", side_effect=RuntimeError("smtp")), self.assertLogs("join.source", "ERROR"):
        SOURCE.record("SQ-1", *self.ok_sale())
    self.assertEqual(MembershipOrder.objects.get().status, "PAID")

def test_source_is_registered_at_startup(self):
    self.assertIn(SOURCE, order_sources())

# test_mail.py
@override_settings(TICKETS_BASE_URL="https://www.fortkentcinema.com")
def test_welcome_email_for_a_first_term(self):
    order = self.paid_order()  # helper: member with one term, order PAID with that term
    send_welcome(order); msg = mail.outbox[0]
    self.assertEqual((msg.to, msg.subject), (["ann@example.com"], "Welcome to Fort Kent Cinema"))
    for text in ["Hi Ann,", "You're a member.", order.number, "Individual membership",
                 "Good from Oct 26, 2026 through Oct 25, 2027", "Give your name at the box office.",
                 "https://www.fortkentcinema.com/register", f"https://www.fortkentcinema.com/membership/order/{order.token}/",
                 "13 Hall Street"]:
        self.assertIn(text, msg.body)
    self.assertNotIn("&amp;", msg.body)
    html = [a for a in msg.alternatives if a[1] == "text/html"][0][0]
    self.assertIn(order.number, html)

def test_welcome_email_for_a_renewal(self):
    order = self.paid_order(earlier_term=True); send_welcome(order)
    self.assertEqual(mail.outbox[0].subject, "Your Fort Kent Cinema membership is renewed")
    self.assertIn("Thanks for renewing", mail.outbox[0].body)
```

Until Task 9 adds the `join:order` URL, both test modules patch `join.mail.reverse` with `side_effect=lambda name, args=(): {"register": "/register", "join:order": f"/membership/order/{args[0]}/"}[name]`; Task 9 removes the patch.

- [ ] **Step 2: Run** `python manage.py test join` — expected FAIL.
- [ ] **Step 3: Implement** `join/source.py`, `join/mail.py`, the two templates (HTML mirrors the ticket HTML email's structure), and `ready()`.
- [ ] **Step 4: Run** `python manage.py test join boxoffice` — expected OK.
- [ ] **Step 5: Commit** `feat(join): enter the membership and send the welcome email when Square pays`.

### Task 8: Recovery when the webhook is lost

**Files:**
- Modify: `join/orders.py`
- Test: `join/tests/test_orders_recover.py`

**Interfaces:**
- Produces `join.orders.recover_pending(order: MembershipOrder, gateway: Gateway | None = None) -> MembershipOrder`: returns at once unless status is PENDING with a `square_order_id`; `gateway or get_gateway()`; None → return; `retrieve_order` (`GatewayError` → `logger.warning`, return); if any tender `.paid`, call `process_order(order.square_order_id, gateway)` (the source's `record` marks the row); `order.refresh_from_db()`; return.

- [ ] **Step 1: Write the failing tests** (gateway: `FakeGateway()`, `set_variation()`, `start()` an order through it, then `gw.pay("SQ-1", "P2", paid_at=...)`):

```python
def test_paid_order_is_entered_by_recovery(self):
    order = self.started(); self.gw.pay(order.square_order_id, "P2")
    recover_pending(order, self.gw)
    self.assertEqual((order.status, order.square_payment_id), ("PAID", "P2"))
    self.assertTrue(Member.objects.filter(email="ann@example.com").exists())
    self.assertEqual(len(mail.outbox), 1)

def test_unpaid_order_stays_pending(self):
    order = self.started(); recover_pending(order, self.gw)
    self.assertEqual((order.status, MembershipSale.objects.count()), ("PENDING", 0))

def test_square_unreachable_is_logged_and_harmless(self):
    order = self.started()
    with self.assertLogs("join.orders", "WARNING"):
        recover_pending(order, FakeGateway(fail_with=GatewayError("down")))
    self.assertEqual(order.status, "PENDING")

def test_only_pending_orders_ask_square(self):
    order = make_order(status="PAID"); gw = FakeGateway(); recover_pending(order, gw)
    self.assertEqual(gw.calls, [])
```

`self.started()`: `set_variation()`, `start(tier, gateway=self.gw, **BUYER)`; `process_order` needs the sale's tier match, which the fake order's line carries (`catalog_object_id="VAR-IND"`).

- [ ] **Step 2: Run** `python manage.py test join.tests.test_orders_recover` — expected FAIL.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run** `python manage.py test join` — expected OK.
- [ ] **Step 5: Commit** `feat(join): the order page recovers a payment whose webhook was lost`.

### Task 9: Public views, templates and URLs

**Files:**
- Create: `join/views.py`, `join/templates/join/start.html`, `join/templates/join/order.html`, `join/forms.py`, `join/tests/test_views.py`
- Modify: `join/urls.py`, `join/tests/test_mail.py` and `test_spec.py` (drop the `reverse` patches)

**Interfaces:**
- URLs (`app_name = "join"`): `path("membership/join/<slug:slug>/", views.JoinView.as_view(), name="start")`, `path("membership/order/<str:token>/", views.OrderView.as_view(), name="order")`.
- `join.forms.JoinForm`: `first_name`, `last_name` (`CharField(max_length=100)`, autocomplete given-name/family-name), `email` (`EmailField`, autocomplete email), `website` hidden honeypot with `is_bot` property, copied from `BuyForm` without phone or quantities.
- `JoinView.get`: tier by slug with `show_on_membership_page=True` else 404; context `tier`, `form` (initial: `email=request.user.email` when authenticated; names from `Member.objects.filter(email=...)` when found), `online` (`square_enabled()` and `tier.square_variation_id`), `closed_sentence`, `error`, `price` ("$60"). Sentences: no Square → "Online membership sign-up isn't available right now. Join at the box office before any show."; tier with no variation → "This tier isn't sold online. Join at the box office before any show."
- `JoinView.post`: bot → 303 back to the page; `get_gateway()` None or invalid form → re-render (same `closed_sentence` rule); `orders.start(...)` with `NotSoldOnline` → re-render with the tier sentence; ABANDONED → re-render with `CHECKOUT_FAILED = "We couldn't start checkout. Please try again, or join at the box office."`; else 303 to `square_checkout_url`.
- `join.views.order_state(order, now) -> str`: PAID → `"paid"`; PENDING → `"pending"` within `CONFIRMING_FOR = 2 min` of `created_at` else `"waiting"`; FAILED → `"failed"`; ABANDONED → `"abandoned"`.
- `OrderView.get` (`never_cache`): 404 on a bad token; PENDING older than `RECOVER_AFTER = 60 s` → `recover_pending(order, gateway=get_gateway())`; context `order`, `state`, `tier_name`, `started_on`, `expires_on` (from `order.term`, `M j, Y`), `renewal` (term's member has >1 term), `mine` (authenticated user's email equals `order.email`), `register_url` (`reverse("register")`), `tier` (for the GA4 block).
- `start.html`: extends base; `{% block robots %}noindex, nofollow{% endblock %}`; `ticket-page` layout: the tier card (`{% include "partials/tier_card.html" with tier=tier join_button=False %}`, see Task 12 for the flag) then the form with `ticket-page__contact` fields, submit "Pay {{ price }} on Square", below it "You'll pay on Square's secure checkout and come straight back here." When `online` is False, show `closed_sentence` in place of the form.
- `order.html`: extends base; noindex; keeps the base `analytics` block (unlike tickets: the token grants nothing redeemable; the owner accepts the page URL in GA4). `state == "paid"`: `<p class="ticket-page__label">Payment received</p>`, `<h1>` "Welcome, {{ order.first_name }}" or "You're renewed" when `renewal`, "{{ tier_name }} membership", "Your membership runs {{ started_on }} through {{ expires_on }}.", "There's no card to carry. Give your name at the box office.", then `{% if mine %}<a href="/dashboard/">See your membership</a>{% else %}Want to see your membership online? <a href="{{ register_url }}">Create an account with {{ order.email }}</a>.{% endif %}`; and in `extra_head` the `gtag('event', 'purchase', ...)` block copied from `web/thanks.html` with `tier`. `pending`: "Confirming your payment…" + `<meta http-equiv="refresh" content="4">`. `waiting`: "Still waiting" + "Return to payment" button when `square_checkout_url`. `failed`: "Payment received. We're finishing your membership and will email you." `abandoned`: "This checkout didn't start." + link to `join:start` for `order.tier.slug` "Try again."

- [ ] **Step 1: Write the failing tests** in `join/tests/test_views.py` (base class patches `join.views.get_gateway` to a `FakeGateway`, calls `set_variation()`; `text()` helper unescapes):

```python
def test_join_page_shows_tier_and_form(self):
    html = self.get("individual")
    for s in ["Individual", "$60", 'name="first_name"', 'name="last_name"', 'name="email"', "Pay $60 on Square",
              "come straight back here", 'content="noindex, nofollow"']:
        self.assertIn(s, html)
    self.assertNotIn('name="phone"', html)

def test_unlisted_or_unknown_tier_404(self): ...  # show_on_membership_page False → 404; "nope" → 404

def test_tier_without_variation_shows_box_office_sentence(self):
    MembershipTier.objects.filter(slug="individual").update(square_variation_id="")
    html = self.get("individual")
    self.assertIn("This tier isn't sold online. Join at the box office before any show.", html)
    self.assertNotIn('name="email"', html)

def test_square_off_shows_unavailable_sentence(self):
    self.get_gateway.return_value = None
    with mock.patch("join.views.square_enabled", return_value=False):
        html = self.get("individual")
    self.assertIn("Online membership sign-up isn't available right now.", html)

def test_signed_in_member_is_prefilled(self):
    Member.objects.create(first_name="Marguerite", last_name="Ouellette", email="m.o@example.com")
    self.client.force_login(make_user("m.o@example.com", "pw12345", is_staff=False))
    html = self.get("individual")
    for s in ['value="Marguerite"', 'value="Ouellette"', 'value="m.o@example.com"']:
        self.assertIn(s, html)

def test_post_redirects_to_square(self):
    resp = self.post("individual")
    self.assertEqual((resp.status_code, resp["Location"]), (303, "https://square.link/u/1"))
    self.assertEqual(MembershipOrder.objects.get().status, "PENDING")

def test_post_invalid_email_rerenders(self): ...  # 200, "Enter a valid email address.", no order
def test_honeypot(self): ...  # 303 back to the page, no order, no gateway call
def test_post_gateway_failure_message(self):
    self.gw.fail_with = GatewayError("boom")
    self.assertIn("We couldn't start checkout. Please try again, or join at the box office.", text(self.post("individual")))

def test_order_states(self):  # one assertion per state on rendered copy
    ...  # paid: "Payment received", "Welcome, Ann", "Individual membership", "runs Oct 26, 2026 through Oct 25, 2027", "Create an account with ann@example.com", "'purchase'", "value: 60"
    ...  # renewal: "You're renewed"; mine (signed in as ann@example.com): 'href="/dashboard/"'
    ...  # pending (fresh): "Confirming your payment", 'http-equiv="refresh"'
    ...  # waiting (created_at 3 min ago): "Still waiting", "Return to payment"
    ...  # failed: "Payment received. We're finishing your membership and will email you."
    ...  # abandoned: "This checkout didn't start.", href to join:start

def test_order_page_is_noindex_and_never_cached(self): ...  # "noindex, nofollow"; "no-cache" in Cache-Control
def test_bad_token_404(self): ...
def test_order_page_renders_with_square_off(self):
    self.get_gateway.return_value = None
    order = make_order(status="PAID")  # with a term, as the paid-state helper builds it
    self.assertEqual(self.client.get(reverse("join:order", args=[order.token])).status_code, 200)
def test_order_page_recovers_after_sixty_seconds(self):
    order = make_order(); MembershipOrder.objects.filter(pk=order.pk).update(created_at=timezone.now() - datetime.timedelta(seconds=61))
    with mock.patch("join.views.recover_pending") as recover:
        self.client.get(reverse("join:order", args=[order.token]))
    recover.assert_called_once()
def test_young_pending_does_not_ask_square(self): ...  # recover_pending not called
```

- [ ] **Step 2: Run** `python manage.py test join.tests.test_views` — expected FAIL (no views).
- [ ] **Step 3: Implement** forms, views, templates, URLs; remove the `reverse` patches from Task 6/7 tests.
- [ ] **Step 4: Run** `python manage.py test join` — expected OK. Then `python manage.py runserver` and open `/membership/join/individual/` and an order page for a `make_order`'d row via the shell, to eyeball the layout (no screenshot needed).
- [ ] **Step 5: Commit** `feat(join): the join page and the order page`.

### Task 10: End to end through the signed webhook

**Files:**
- Create: `join/tests/test_webhook.py`

**Interfaces:** consumes `boxoffice.tests.test_webhook.post`, `event`, `KEY`, `URL`, `PAID_AT`.

- [ ] **Step 1: Write the test**:

```python
@override_settings(SQUARE_WEBHOOK_SIGNATURE_KEY=KEY, SQUARE_WEBHOOK_URL=URL)
class JoinWebhookTests(TestCase):
    def test_signed_event_enters_the_membership_once(self):
        gw = FakeGateway(); set_variation()
        order = start(MembershipTier.objects.get(slug="individual"), gateway=gw, **BUYER)
        gw.pay(order.square_order_id, "P1", paid_at=PAID_AT)
        with mock.patch("boxoffice.memberships.get_gateway", return_value=gw):
            first = post(self.client, event(order.square_order_id))
            second = post(self.client, event(order.square_order_id))
        self.assertEqual((first.status_code, second.status_code), (200, 200))
        order.refresh_from_db()
        self.assertEqual((order.status, order.square_payment_id), ("PAID", "P1"))
        member = Member.objects.get(email="ann@example.com")
        self.assertEqual((member.terms.count(), order.term, order.sale.source), (1, member.terms.get(), "WEBSITE"))
        self.assertEqual(order.term.started_on, datetime.date(2026, 10, 2))
        self.assertEqual(len(mail.outbox), 1)

    def test_fetch_failure_is_a_503_and_the_order_shows_failed(self):
        set_variation(); order = make_order(square_order_id="SQ-1")
        with mock.patch("boxoffice.memberships.get_gateway", return_value=FakeGateway(fail_with=GatewayError("down"))):
            resp = post(self.client, event("SQ-1"))
        order.refresh_from_db()
        self.assertEqual((resp.status_code, order.status), (503, "FAILED"))
```

- [ ] **Step 2: Run** `python manage.py test join.tests.test_webhook` — expected OK on the first run if Tasks 4–9 are right; if it fails, the failure is a bug in those tasks, not in this test.
- [ ] **Step 3: Run** the full suite — expected OK.
- [ ] **Step 4: Commit** `test(join): a signed Square event enters a website membership once`.

### Task 11: A listed tier no longer needs a payment link

**Files:**
- Modify: `audience/models/membership_tier.py` (`clean()`, `checkout_url` help text → "The legacy Square payment link. No longer linked from the site."), `dashboard/tier_views.py:145-152` (drop the restore guard), `dashboard/forms.py:244` label → "Square payment link (legacy)"
- Test: `audience/tests/test_membership_tier.py` (`CheckoutLinkTests`), `audience/tests/test_admin.py` (`test_a_listed_tier_needs_a_checkout_link`, `test_a_retired_tier_saves_without_one`), `dashboard/tests/test_tiers.py` (`test_a_listed_tier_needs_a_payment_link`, `test_an_unlisted_tier_can_wait_for_its_payment_link`, `test_a_tier_without_a_payment_link_cannot_be_restored`)

- [ ] **Step 1: Flip the tests**: replace the five with `test_a_listed_tier_saves_without_a_payment_link` (model `full_clean()` passes with blank `checkout_url`), `test_a_listed_tier_saves_without_a_link` (admin add succeeds, tier exists), `test_a_listed_tier_saves_without_a_payment_link` (dashboard create succeeds), and `test_a_tier_without_a_payment_link_can_be_restored` (listing toggle flips to True, toast kind success).
- [ ] **Step 2: Run** `python manage.py test audience dashboard.tests.test_tiers` — expected FAIL.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run** `python manage.py test audience dashboard` — expected OK.
- [ ] **Step 5: Commit** `feat(audience): a listed tier no longer needs a Square payment link`.

### Task 12: Join buttons and copy on `/membership/`

**Files:**
- Modify: `templates/partials/tier_card.html`, `web/templates/web/membership.html`, `web/views.py` (`MembershipView.get_context_data`), `web/constants.py` (`MEMBERSHIP_FAQ[0]`), `static/css/TierCard.css`, `static/css/bundle.css` (rebuilt)
- Test: `web/tests/test_membership_catalogue.py`, `web/tests/test_membership_wording.py`, `web/tests/test_analytics.py`

**Interfaces:**
- `MembershipView` context gains `online_join = square_enabled()` (import from `boxoffice.gateway`).
- `tier_card.html`, after the perks: `{% if join_button|default:True %}{% if online_join and tier.square_variation_id %}<a href="{% url 'join:start' tier.slug %}" class="btn btn-secondary tier-card__cta" data-track="membership_join_click" data-track-tier="{{ tier.slug }}">Join</a>{% else %}<p class="tier-card__box-office">Join at the box office</p>{% endif %}{% endif %}`. The join page passes `join_button=False`.
- `TierCard.css`: restore the `.tier-card__cta` and `.tier-card--featured .tier-card__cta` rules and the perks list's bottom rule/margin exactly as removed in commit `a120368` (`git show a120368 -- static/css/TierCard.css`); add `.tier-card__box-office { margin-top: auto; font-size: 0.85rem; opacity: 0.8; }`.
- Copy (exact): note → "Regular admission is ${{ ticket_prices.adult }} (${{ ticket_prices.matinee }} for matinees); members pay ${{ ticket_prices.member }}. Join online from any tier above, or at the box office before any show. There's no card to carry: after that, your name is all we need."; final section → `<h2>Ready to join?</h2><p>Pick a tier above and you'll be a member in a minute. Or stop by the box office before any show.</p><a href="#tiers" class="btn btn-primary">Choose a tier</a>`; FAQ answer 1 → "The length shown on your tier, counted from the day you join. Your welcome email and your member page show the exact end date."
- Rebuild: `cd frontend && npm run build:css`.

- [ ] **Step 1: Flip and add tests.** In `test_membership_catalogue.py`: `test_no_join_buttons` → `test_join_buttons_link_to_the_join_page` (patch `web.views.square_enabled` to True, set a variation ID on every seeded tier, assert each card has `href="/membership/join/<slug>/"` and `>Join<`, and no `square.link` URL). `MissingCheckoutLinkTests` → a tier with no variation renders "Join at the box office" and no `href=""`. Add `test_square_off_shows_box_office_on_every_card` (no patch: the test settings have no token). In `test_membership_wording.py`: delete `JoinAtTheBoxOfficeTests.test_no_checkout_promised`; rewrite `test_note_and_final_section_point_to_the_box_office` to assert the new note sentence, "Choose a tier" and `href="#tiers"` in the final section, and "box office" in both; `test_duration_answer_does_not_hedge` asserts "welcome email". In `test_analytics.py` add `test_join_click_is_tracked_without_a_value` (patch `square_enabled`, set variations; `tracked(html, "membership_join_click")` has 5 entries, none containing `value`).
- [ ] **Step 2: Run** `python manage.py test web` — expected FAIL.
- [ ] **Step 3: Implement** template, view, constants, CSS, bundle.
- [ ] **Step 4: Run** `python manage.py test web join` — expected OK. `git diff --stat static/css/bundle.css` shows one changed line.
- [ ] **Step 5: Commit** `feat(membership): Join buttons return, pointing at the site's own checkout`.

### Task 13: Renew from the member home

**Files:**
- Modify: `dashboard/member_home.py`, `dashboard/templates/dashboard/member_home.html`
- Test: `dashboard/tests/test_member_home.py`

**Interfaces:**
- Context gains `renew_tier`: the latest term's tier when `member.status in (ACTIVE, EXPIRING, LAPSED)` and that tier is listed with a variation ID and `square_enabled()`, else None; and `can_renew`: True for those three statuses regardless of the tier.
- Template, inside the member card after the fields: `{% if renew_tier %}<a class="btn btn-primary" href="{% url 'join:start' renew_tier.slug %}">Renew</a> <a href="/membership/#tiers">or choose a different tier</a>{% elif can_renew %}<a href="/membership/#tiers">Choose a tier to renew</a>{% endif %}`. The no-member sentence becomes "No membership on file for this email. You can join on the membership page, or at the box office before any show."

- [ ] **Step 1: Write the failing tests** (patch `dashboard.member_home.square_enabled` to True; set the variation ID):

```python
def test_active_member_gets_renew_for_their_tier(self): ...  # give_term → 'href="/membership/join/cinema-supporter/"', ">Renew<", "or choose a different tier"
def test_lapsed_member_gets_renew(self): ...  # give_expired_term(family-plus) → join link for family-plus
def test_upcoming_member_gets_no_renew(self): ...  # term starting in 10 days → no "Renew", no "Choose a tier"
def test_tier_not_sold_online_offers_the_tier_list_only(self): ...  # variation blank → "Choose a tier to renew", no join link
def test_square_off_offers_the_tier_list_only(self): ...  # square_enabled False
def test_member_without_match_sees_join_prompt(self): ...  # flip the sentence
```

- [ ] **Step 2: Run** `python manage.py test dashboard.tests.test_member_home` — expected FAIL.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run** `python manage.py test dashboard` — expected OK.
- [ ] **Step 5: Commit** `feat(dashboard): members renew from their member home`.

### Task 14: Source column on the Square Sales list

**Files:**
- Modify: `dashboard/templates/dashboard/square_sales.html`, `dashboard/templates/dashboard/_square_sale_row.html`
- Test: `dashboard/tests/test_square_sales.py`

- [ ] **Step 1: Write the failing tests**: `test_source_column_says_website_or_payment_link` (two sales, one `source="WEBSITE"`; the row for it contains "Website", the other "Payment link"; the header has `<th>Source</th>` after Buyer) and update `test_empty_state` to assert "They'll show up here when someone joins on the website or pays through a membership link."
- [ ] **Step 2: Run** — expected FAIL.
- [ ] **Step 3: Implement**: `<th>Source</th>` after `<th>Buyer</th>`; `<td>{{ sale.get_source_display }}</td>` in the row at the same position.
- [ ] **Step 4: Run** `python manage.py test dashboard` — expected OK.
- [ ] **Step 5: Commit** `feat(dashboard): the Square sales list says where each sale came from`.

### Task 15: Docs and final verification

**Files:**
- Modify: `README.md` (after "Online tickets"), spec `Status:` line

- [ ] **Step 1:** README section "Membership checkout": memberships are sold at `/membership/join/<slug>/` through the same Square payment-link flow as tickets; a tier sells online when it is listed and has a Square variation ID; website sales appear on the dashboard's Square Sales list as "Website" and use the same Retry; no new settings, cron or webhook events; legacy payment links keep working. Spec status → "Implemented on feat/membership-checkout".
- [ ] **Step 2: Run** the full suite with `--parallel` — expected OK, count ≥ 2621 + the new tests. Run `flake8` on the changed files and compare with `main` for new findings on changed lines.
- [ ] **Step 3: Commit** `docs: membership checkout`.
- [ ] **Step 4:** Report to the owner: branch state, the sandbox rollout check still to do (one real checkout: roster row, Square Sales "Website" row, welcome email), and the two migrations the deploy runs (`join 0001`, `boxoffice 0014`).
