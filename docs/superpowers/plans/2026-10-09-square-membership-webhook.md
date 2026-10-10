# Square Membership Webhook Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A membership paid for through a Square payment link appears in the roster as a member and a term within seconds, and a sale the site could not place shows on the dashboard with a Retry button.

**Architecture:** Square posts `order.updated` to a new signed endpoint in the `boxoffice` app. The view fetches the full order through the existing gateway, and `boxoffice/memberships.py` attributes it: a `MembershipSale` row per membership order (the idempotency key and the audit record), a `Member` found or created by email, and a `MembershipTerm` dated like the dashboard's Renew button. Tiers are matched by a new `square_variation_id` field. The dashboard gains one alert, one list page and one Retry endpoint.

**Tech Stack:** Django 5.2.3, `squareup==42.1.0.20250521` (its `square.utils.webhooks_helper.verify_signature`), htmx + Alpine dashboard, `manage.py test` + `flake8`.

**Spec:** `docs/superpowers/specs/2026-10-09-square-membership-webhook-design.md`

## Global Constraints

- **Tests:** `.venv/bin/python manage.py test <label> -v 2`. Full suite: `.venv/bin/python manage.py test --parallel 4` (1879 tests pass at the start of this branch).
- **Lint:** `.venv/bin/python -m flake8 <paths>`; `max-line-length = 88`, migrations excluded. `dashboard/views.py`, `dashboard/urls.py`, `dashboard/forms.py` carry pre-existing flake8 debt; lint only the paths each task names and never fix lines you did not write.
- **Git identity:** the machine's hostname changed, so git cannot auto-detect an author. Commit with `git -c user.name="Brandon Goding" -c user.email="brandongoding@pop-os.lan" commit ...` unless the user has since set a global identity. End every commit message with the attribution trailer the session provides.
- **Import direction.** `boxoffice` imports `audience` (it already imports `cinema`). `audience` never imports `boxoffice`. `dashboard` imports both.
- **Only `boxoffice/gateway.py` and `boxoffice/decorators.py` import `square`.** Everything else takes a gateway object; tests use `boxoffice.tests.fakes.FakeGateway`.
- **Processing resolves the gateway through `boxoffice.gateway.get_gateway()`** when none is passed, exactly as `boxoffice.sync` does. Tests patch `boxoffice.memberships.get_gateway`.
- **Database:** production is Postgres (`USE_POSTGRES`), local and tests are sqlite. `select_for_update()` is a real row lock in production and a no-op on sqlite; the plan relies on it only to serialise two events for one order, and tests prove the re-check logic rather than real concurrency.
- **Business day** is the Eastern calendar day of `closed_at`, via the existing `boxoffice.pull.business_date`.
- **Email normalisation** is `(value or "").strip().lower()`, the rule in `Member.save`.
- **Status words** are `MembershipSale.Status.OK = "OK"`, `SKIPPED = "SKIPPED"`, `FAILED = "FAILED"`, labels "Entered", "Skipped", "Needs attention".
- **Exact copy** (tests assert on it):
  - FAILED quantity: `Ordered {n} memberships; enter by hand`
  - SKIPPED no email: `No buyer email (register sale)`
  - FAILED gateway off: `Square sync disabled: {disabled_reason()}`
  - FAILED never-expiring term: `Current term never expires`
  - FAILED overflow: `A {months}-month term from {date} runs past 31 December 9999. Enter the term by hand.`
  - FAILED no payment time: `Order has no payment time`
  - Term notes: `Square order {order_id}`
  - Alert: `{n} Square membership sale needs attention` / `{n} Square membership sales need attention`
- **Every dashboard view is staff-only** via `StaffRequiredMixin` from `dashboard/mixins.py`.
- **Migrations:** `audience.0013_membershiptier_square_variation_id` (Task 1), `boxoffice.0006_membershipsale` (Task 2). Both generated with `makemigrations`, then renamed to those names.
- **Settings** added after the `SQUARE_ENVIRONMENT` line in `fortkentcinema/settings.py`: `SQUARE_WEBHOOK_SIGNATURE_KEY = config("SQUARE_WEBHOOK_SIGNATURE_KEY", default="")` and `SQUARE_WEBHOOK_URL = config("SQUARE_WEBHOOK_URL", default="")`, with a comment in the style of the Twilio block.
- **Commit after each task** with a conventional-commit subject (`feat(boxoffice): …`, `feat(dashboard): …`, `feat(audience): …`).

## Review Focus

Inputs the spec implies but does not name. Each has a test in the task that owns the code.

1. **A membership order with a ticket line too** (someone buys a membership and tickets in one checkout) must still create the term from the membership line and ignore the ticket line. → Task 4.
2. **A recipient email in mixed case or with spaces** must match the existing member stored in lower case, not create a duplicate that trips the unique index. → Task 4.
3. **A display name with a middle name or a suffix** ("Mary Ann Smith Jr.") is split on the last space only; the implementer must not split on the first. → Task 4.
4. **A second `order.updated` arriving while the first is still fetching the order** must not create two terms: after the fetch, the sale row is locked with `select_for_update()` and its status re-read before anything is written, so the slower request finds OK and stops. → Task 4 (`test_event_arriving_mid_fetch_does_not_create_a_second_term`).
5. **Retry on a sale whose linked term staff have since deleted** must not create a second term: a sale with `status=OK` is never reprocessed, even if `term` is null. → Task 4.

---

### Task 1: `MembershipTier.square_variation_id`

**Files:**
- Modify: `audience/models/membership_tier.py` (add the field after `checkout_url`)
- Create: `audience/migrations/0013_membershiptier_square_variation_id.py` (generated)
- Modify: `dashboard/forms.py:194-230` (`MembershipTierForm.Meta.fields` and `widgets`)
- Modify: `dashboard/templates/dashboard/_tier_form.html` (one `{% field %}` after `checkout_url`)
- Modify: `audience/admin.py:43-56` (`MembershipTierAdmin.list_display`)
- Test: `audience/tests/test_membership_tier.py`, `dashboard/tests/test_tiers.py`

**Interfaces:**
- Produces: `MembershipTier.square_variation_id: CharField(max_length=64, blank=True, default="")` with `UniqueConstraint(fields=["square_variation_id"], condition=~Q(square_variation_id=""), name="audience_membershiptier_square_variation_id_unique")`. Help text: `"The ID of this tier's 'Annual' variation in Square (Items → the item → the variation's ID in the URL). Sales of that variation create terms for this tier."`
- Later tasks look tiers up with `MembershipTier.objects.filter(square_variation_id__in=ids)`.

- [ ] **Step 1: Write the failing model tests** in `audience/tests/test_membership_tier.py`

```python
class SquareVariationIdTests(TestCase):
    def test_defaults_blank_and_two_blanks_coexist(self) -> None:
        a = MembershipTier.objects.create(slug="a", name="A", price=1, checkout_url="https://square.link/u/a")
        b = MembershipTier.objects.create(slug="b", name="B", price=1, checkout_url="https://square.link/u/b")
        self.assertEqual((a.square_variation_id, b.square_variation_id), ("", ""))

    def test_set_ids_are_unique(self) -> None:
        MembershipTier.objects.create(slug="a", name="A", price=1, square_variation_id="VAR1")
        with self.assertRaises(IntegrityError):
            MembershipTier.objects.create(slug="b", name="B", price=1, square_variation_id="VAR1")
```

- [ ] **Step 2: Run them to verify they fail**

Run: `.venv/bin/python manage.py test audience.tests.test_membership_tier.SquareVariationIdTests -v 2`
Expected: FAIL with `TypeError: ... unexpected keyword argument 'square_variation_id'`

- [ ] **Step 3: Add the field and constraint** to `MembershipTier`, then `.venv/bin/python manage.py makemigrations audience -n membershiptier_square_variation_id`

- [ ] **Step 4: Run the model tests to verify they pass**

Run: `.venv/bin/python manage.py test audience.tests.test_membership_tier -v 2`
Expected: PASS

- [ ] **Step 5: Write the failing dashboard form test** in `dashboard/tests/test_tiers.py`, inside `TierCreateTests`

```python
def test_square_variation_id_is_saved(self) -> None:
    self.client.post(reverse("dashboard:tier_create"), tier_payload(square_variation_id="VARXYZ"))
    self.assertTrue(MembershipTier.objects.filter(square_variation_id="VARXYZ").exists())
```

(`tier_payload` is the existing helper at the top of that file; add `"square_variation_id": ""` to its defaults.)

- [ ] **Step 6: Run it to verify it fails**

Run: `.venv/bin/python manage.py test dashboard.tests.test_tiers -v 2`
Expected: the new test FAILS with `'' != 'VARXYZ'`; everything else passes.

- [ ] **Step 7: Add the field to the form, the template and the admin.** Form: append `"square_variation_id"` after `"checkout_url"` in `fields`, widget `forms.TextInput(attrs={"class": "input", "placeholder": "e.g. LUXWXSDRQGNENE7XDBXPNYXY"})`. Template: `{% field form.square_variation_id label="Square variation ID" hint="Sales of this variation create terms for this tier. Blank means not sold online." %}` directly after the `checkout_url` field. Admin: add `"square_variation_id"` to `list_display`.

- [ ] **Step 8: Run the tier tests and flake8**

Run: `.venv/bin/python manage.py test dashboard.tests.test_tiers audience.tests -v 1 && .venv/bin/python -m flake8 audience/models/membership_tier.py audience/admin.py`
Expected: PASS, no flake8 output

- [ ] **Step 9: Commit**

```bash
git add audience/models/membership_tier.py audience/migrations/0013_membershiptier_square_variation_id.py audience/admin.py audience/tests/test_membership_tier.py dashboard/forms.py dashboard/templates/dashboard/_tier_form.html dashboard/tests/test_tiers.py
git commit -m "feat(audience): link each membership tier to its Square variation"
```

---

### Task 2: The `MembershipSale` model and admin

**Files:**
- Create: `boxoffice/models/membership_sale.py`
- Modify: `boxoffice/models/__init__.py` (export `MembershipSale`)
- Create: `boxoffice/migrations/0006_membershipsale.py` (generated)
- Modify: `boxoffice/admin.py` (read-only admin like `SalesPullAdmin`)
- Test: `boxoffice/tests/test_models.py`

**Interfaces:**
- Produces `boxoffice.models.MembershipSale` exactly as the spec's table:
  - `order_id = CharField(max_length=64, unique=True)`
  - `closed_at = DateTimeField(null=True, blank=True)`
  - `tier = ForeignKey("audience.MembershipTier", null=True, blank=True, on_delete=PROTECT, related_name="square_sales")`
  - `quantity = PositiveIntegerField(default=0)`, `gross_cents = IntegerField(default=0)`
  - `display_name = CharField(max_length=200, blank=True)`, `email = EmailField(blank=True)`, `phone = CharField(max_length=40, blank=True)`
  - `status = CharField(max_length=8, choices=Status.choices)`, `error = TextField(blank=True)`
  - `term = OneToOneField("audience.MembershipTerm", null=True, blank=True, on_delete=SET_NULL, related_name="square_sale")`
  - `created_at = DateTimeField(auto_now_add=True)`, `processed_at = DateTimeField(null=True, blank=True)`
  - `class Status(TextChoices)`: `OK`, `SKIPPED`, `FAILED` with the labels in Global Constraints.
  - `Meta.ordering = ["-closed_at", "-created_at"]`; `__str__` returns `order_id`.
  - `purchase_date` property: `business_date(self.closed_at)` or `None` when `closed_at` is null.

- [ ] **Step 1: Write the failing tests** in `boxoffice/tests/test_models.py`

```python
class MembershipSaleTests(TestCase):
    def test_order_id_is_unique(self) -> None:
        MembershipSale.objects.create(order_id="O1", status=MembershipSale.Status.FAILED)
        with self.assertRaises(IntegrityError):
            MembershipSale.objects.create(order_id="O1", status=MembershipSale.Status.FAILED)

    def test_deleting_the_term_keeps_the_sale(self) -> None:
        tier = MembershipTier.objects.get(slug="individual")
        member = Member.objects.create(first_name="A", last_name="B", email="a@b.c")
        term = MembershipTerm.objects.create(member=member, tier=tier, started_on=date(2026, 10, 2), expires_on=date(2027, 10, 1), price_paid=60)
        sale = MembershipSale.objects.create(order_id="O1", tier=tier, term=term, status=MembershipSale.Status.OK)
        term.delete()
        sale.refresh_from_db()
        self.assertIsNone(sale.term)

    def test_purchase_date_is_the_eastern_day(self) -> None:
        sale = MembershipSale(order_id="O1", closed_at=datetime(2026, 10, 3, 3, 12, tzinfo=timezone.utc))
        self.assertEqual(sale.purchase_date, date(2026, 10, 2))
        self.assertIsNone(MembershipSale(order_id="O2").purchase_date)
```

(The membership catalogue is seeded by migration `audience.0004`, so `slug="individual"` exists in every test database.)

- [ ] **Step 2: Run them to verify they fail**

Run: `.venv/bin/python manage.py test boxoffice.tests.test_models.MembershipSaleTests -v 2`
Expected: FAIL with `ImportError: cannot import name 'MembershipSale'`

- [ ] **Step 3: Write the model**, export it, run `.venv/bin/python manage.py makemigrations boxoffice -n membershipsale`, and register `MembershipSaleAdmin` with `list_display = ("order_id", "closed_at", "tier", "email", "status")`, `list_filter = ("status",)`, `search_fields = ("order_id", "email", "display_name")`, every field read-only, and no add permission (change stays allowed so a stuck row can be deleted from the admin).

- [ ] **Step 4: Run the tests and flake8**

Run: `.venv/bin/python manage.py test boxoffice.tests.test_models -v 2 && .venv/bin/python -m flake8 boxoffice/models boxoffice/admin.py boxoffice/tests/test_models.py`
Expected: PASS, no flake8 output

- [ ] **Step 5: Commit**

```bash
git add boxoffice/models boxoffice/migrations/0006_membershipsale.py boxoffice/admin.py boxoffice/tests/test_models.py
git commit -m "feat(boxoffice): record every Square membership sale"
```

---

### Task 3: Gateway `retrieve_order` and the fulfillment recipient

**Files:**
- Modify: `boxoffice/gateway.py` (`OrderData`, `_order_data`, new `Recipient`, new `SquareGateway.retrieve_order`)
- Modify: `boxoffice/tests/fakes.py` (`FakeGateway.retrieve_order`)
- Test: `boxoffice/tests/test_gateway.py`

**Interfaces:**
- Produces `boxoffice.gateway.Recipient` (frozen dataclass): `display_name: str`, `email_address: str`, `phone_number: str`, each `""` when Square omits it.
- `OrderData` gains `recipient: Recipient | None = None` as its last field, so every existing constructor call still works.
- `_order_data` fills `recipient` from the first fulfillment that has `pickup_details`, `shipment_details` or `delivery_details` with a `recipient`; `None` when there is no fulfillment or none carries a recipient.
- `SquareGateway.retrieve_order(order_id: str) -> OrderData` via `_call(self.client.orders.get, order_id)` reading `response.order`. Errors surface as `GatewayError` like every other call.
- `FakeGateway.retrieve_order(order_id)` records the call, returns the matching entry from `self.orders` by `order_id`, or raises `GatewayError(f"Unknown order {order_id}")`.

- [ ] **Step 1: Write the failing gateway tests** in `boxoffice/tests/test_gateway.py` (follow the file's `mock.Mock` style; a fulfillment mock is `mock.Mock(shipment_details=mock.Mock(recipient=mock.Mock(display_name="Ann Lee", email_address="Ann@Example.com", phone_number="+12075550100")), pickup_details=None, delivery_details=None)`)

```python
class RetrieveOrderTests(SimpleTestCase):
    def test_reads_lines_and_shipment_recipient(self) -> None:
        # client.orders.get.return_value = mock.Mock(order=_order("O1", "2026-10-02T23:12:33.034Z", [_line()]) with fulfillments=[shipment mock])
        data = gw.retrieve_order("O1")
        self.assertEqual(data.order_id, "O1")
        self.assertEqual(data.lines[0].catalog_object_id, "V0")
        self.assertEqual(data.recipient, Recipient("Ann Lee", "Ann@Example.com", "+12075550100"))
        client.orders.get.assert_called_once_with("O1")

    def test_no_fulfillment_means_no_recipient(self) -> None:
        # order mock with fulfillments=None
        self.assertIsNone(gw.retrieve_order("O1").recipient)

    def test_recipient_fields_default_to_empty_strings(self) -> None:
        # recipient mock with email_address=None, phone_number=None
        self.assertEqual(data.recipient, Recipient("Ann Lee", "", ""))

    def test_api_error_becomes_gateway_error(self) -> None:
        # client.orders.get.side_effect = ApiError(status_code=404, body={"errors": [{"code": "NOT_FOUND"}]}) — copy the file's existing ApiError construction
        with self.assertRaises(GatewayError):
            gw.retrieve_order("O1")
```

Also add to the existing `FakeGateway` test class (or a new one) that `FakeGateway().retrieve_order("nope")` raises `GatewayError` and that an order placed in `fake.orders` is returned by ID.

- [ ] **Step 2: Run to verify they fail**

Run: `.venv/bin/python manage.py test boxoffice.tests.test_gateway -v 2`
Expected: FAIL with `ImportError: cannot import name 'Recipient'`

- [ ] **Step 3: Implement** `Recipient`, the `OrderData` field, the `_order_data` change (mocks: use `getattr(fulfillment, kind, None)` per kind and `getattr(recipient, field, None) or ""` per field), `retrieve_order`, and the fake.

- [ ] **Step 4: Run the whole boxoffice suite** (the `_order_data` change touches `search_orders`) and flake8

Run: `.venv/bin/python manage.py test boxoffice -v 1 && .venv/bin/python -m flake8 boxoffice/gateway.py boxoffice/tests/fakes.py boxoffice/tests/test_gateway.py`
Expected: PASS, no flake8 output

- [ ] **Step 5: Commit**

```bash
git add boxoffice/gateway.py boxoffice/tests/fakes.py boxoffice/tests/test_gateway.py
git commit -m "feat(boxoffice): fetch one order with its buyer from Square"
```

---

### Task 4: `process_order` — attribution

**Files:**
- Create: `boxoffice/memberships.py`
- Test: `boxoffice/tests/test_memberships.py`

**Interfaces:**
- Consumes: Task 1's `square_variation_id`, Task 2's `MembershipSale`, Task 3's `retrieve_order` / `Recipient`, `boxoffice.gateway.get_gateway` / `disabled_reason` / `GatewayError`, `boxoffice.pull.business_date`, `audience.terms.latest_term` / `renewal_start`, `MembershipTerm.default_expiry`.
- Produces:
  - `process_order(order_id: str, gateway: SquareGateway | None = None) -> MembershipSale | None` — the spec's Section 1 "Processing" and Section 3 rules. Returns `None` when the order has no membership line (nothing recorded).
  - `split_name(display_name: str) -> tuple[str, str]` — `rsplit(" ", 1)` after `strip()`; one word → `(word, "")`; blank → `("", "")`.
  - `membership_lines(order: OrderData, tiers_by_variation: dict[str, MembershipTier]) -> list[tuple[OrderLine, MembershipTier]]`.
- Order of checks inside `process_order`, each recorded on the row with `processed_at = timezone.now()`:
  1. Existing sale with status OK or SKIPPED → return it untouched.
  2. `gateway or get_gateway()` is None → FAILED `Square sync disabled: {disabled_reason()}` (row created with only `order_id` if new).
  3. `retrieve_order` raises `GatewayError` → FAILED with `str(exc)`.
  4. No membership line → return `None`; if a FAILED row already exists for this order (from an earlier step 2/3 failure), delete it, since the order turned out not to be a membership.
  5. Fill `closed_at`, `tier` (first membership line's), `quantity` (sum), `gross_cents` (sum), buyer fields from `order.recipient` (email normalised).
  6. `quantity != 1` or more than one membership line → FAILED `Ordered {quantity} memberships; enter by hand`.
  7. Blank email → SKIPPED `No buyer email (register sale)`.
  8. In `transaction.atomic()`: re-read the row with `MembershipSale.objects.select_for_update().get(pk=sale.pk)`; if its status is now OK or SKIPPED (another request finished while this one was fetching), return it untouched. Otherwise find or create the member, build the term, set `term`, status OK, save. Exceptions → FAILED `repr(exc)` + `logger.exception`.
- Term rules (step 8): member lookup `Member.objects.filter(email=email).first()`; new member gets `first_name, last_name = split_name(display_name)` and `phone`; existing member gets `phone` only if blank (saved with `update_fields=["phone"]`). `purchase = business_date(order.closed_at)`. `latest = latest_term(member.terms.all())`; `started_on = purchase` if `latest is None` else `renewal_start(latest, purchase)`; `None` → FAILED `Current term never expires`. `expires_on = MembershipTerm.default_expiry(started_on, tier.duration_months)`; `OverflowError` → FAILED with the overflow copy. `price_paid = Decimal(gross_cents) / 100`, `purchased_at = purchase`, `notes = f"Square order {order_id}"`. A `closed_at` of `None` → FAILED `Order has no closed_at`.

- [ ] **Step 1: Write the failing tests** in `boxoffice/tests/test_memberships.py`. Helpers at module top: `INDIVIDUAL = "LUXWXSDRQGNENE7XDBXPNYXY"`; `setUp` sets `MembershipTier.objects.filter(slug="individual").update(square_variation_id=INDIVIDUAL)` and builds `self.gw = FakeGateway()`; `membership_order(order_id="O1", closed_at=at_eastern(2026, 10, 2, 19, 12), quantity=1, recipient=Recipient("Ann Lee", "Ann@Example.com ", "+12075550100"), extra_lines=())` builds an `OrderData` with one line `OrderLine(uid="L1", name="Individual Membership", variation_name="Annual", catalog_object_id=INDIVIDUAL, quantity=quantity, gross_cents=6000 * quantity)` plus `extra_lines`, appends it to `self.gw.orders`, and returns it. Every test calls `process_order("O1", self.gw)` unless it says otherwise.

```python
class NewMemberTests(TestCase):
    def test_creates_member_and_term(self):
        sale = process_order("O1", self.gw)
        member = Member.objects.get(email="ann@example.com")
        self.assertEqual((member.first_name, member.last_name, member.phone), ("Ann", "Lee", "+12075550100"))
        term = member.terms.get()
        self.assertEqual((term.tier.slug, term.started_on, term.expires_on), ("individual", date(2026, 10, 2), date(2027, 10, 1)))
        self.assertEqual((term.price_paid, term.purchased_at, term.notes), (Decimal("60.00"), date(2026, 10, 2), "Square order O1"))
        self.assertEqual((sale.status, sale.term, sale.tier.slug, sale.quantity, sale.gross_cents), ("OK", term, "individual", 1, 6000))
        self.assertEqual((sale.display_name, sale.email, sale.phone), ("Ann Lee", "ann@example.com", "+12075550100"))
        self.assertIsNotNone(sale.processed_at)

    def test_late_evening_utc_lands_on_the_eastern_day(self):
        # closed_at=datetime(2026, 10, 3, 3, 12, tzinfo=timezone.utc) is 23:12 Eastern on Oct 2
        self.assertEqual(term.started_on, date(2026, 10, 2))

    def test_price_paid_is_the_gross_not_the_list_price(self):
        # line gross_cents=4500 → price_paid == Decimal("45.00")

    def test_name_splits_on_the_last_space(self):
        # recipient display_name="Mary Ann Smith Jr." → ("Mary Ann Smith", "Jr.")
        # display_name="Cher" → ("Cher", "")

    def test_membership_with_tickets_in_the_same_order(self):
        # extra_lines=(OrderLine(uid="L2", name="Dune", variation_name="Adult", catalog_object_id="TICKET-VAR", quantity=2, gross_cents=1600),)
        # → sale OK, quantity 1, gross_cents 6000, one term


class ExistingMemberTests(TestCase):
    # setUp also creates member Ann (email "ann@example.com", phone "") with a term
    def test_active_member_renews_after_cover_ends(self):
        # existing term 2026-01-15 .. 2027-01-14 → new term 2027-01-15 .. 2028-01-14
    def test_lapsed_member_renews_on_the_purchase_date(self):
        # existing term 2024-01-15 .. 2025-01-14 → new term 2026-10-02 .. 2027-10-01
    def test_mixed_case_email_matches(self):
        # recipient email "ANN@example.com" → Member.objects.count() == 1, two terms
    def test_name_kept_phone_filled_only_when_blank(self):
        # member "Ann Lee" phone "" + recipient "A. Lee" "+1207..." → name unchanged, phone set
        # member with phone "555" + recipient phone "+1207..." → phone stays "555"
    def test_member_with_no_terms_starts_on_the_purchase_date(self):
    def test_never_expiring_term_fails(self):
        # existing term expires_on=date.max → FAILED "Current term never expires", no new term


class FailureTests(TestCase):
    def test_quantity_two_fails_with_buyer_kept(self):
        # quantity=2 → status FAILED, error "Ordered 2 memberships; enter by hand", email stored, Member.objects.count() == 0, MembershipTerm.objects.count() == 0
    def test_two_membership_lines_fail(self):
        # extra_lines with a second membership line (family tier wired to "VAR-FAMILY") → FAILED "Ordered 2 memberships; enter by hand"
    def test_no_email_is_skipped(self):
        # recipient=None → SKIPPED "No buyer email (register sale)", no member
    def test_ticket_only_order_records_nothing(self):
        # order with only "TICKET-VAR" line → returns None, MembershipSale.objects.count() == 0
    def test_gateway_error_fails_with_only_order_id(self):
        # self.gw = FakeGateway(fail_with=GatewayError("boom")) → FAILED "boom", tier None, closed_at None
    def test_gateway_disabled_fails(self):
        # with mock.patch("boxoffice.memberships.get_gateway", return_value=None), override_settings(SQUARE_ACCESS_TOKEN=""): process_order("O1") → FAILED "Square sync disabled: no SQUARE_ACCESS_TOKEN"
    def test_failed_row_for_a_non_membership_order_is_removed(self):
        # first a GatewayError FAILED row for "O1"; then the fake can serve O1 as a ticket-only order → process_order returns None and the row is gone
    def test_missing_closed_at_fails(self):
        # closed_at=None → FAILED "Order has no closed_at"
    def test_unexpected_exception_fails_and_logs(self):
        # mock.patch("boxoffice.memberships.MembershipTerm.default_expiry", side_effect=RuntimeError("x")) with self.assertLogs("boxoffice.memberships", "ERROR") → FAILED "RuntimeError('x')", no member


class IdempotencyTests(TestCase):
    def test_second_call_for_an_ok_sale_does_nothing(self):
        # process twice → one term, gw.calls has one retrieve_order
    def test_ok_sale_with_deleted_term_is_not_reprocessed(self):
        # process, delete the term, process again → MembershipTerm.objects.count() == 0, sale.status "OK"
    def test_skipped_sale_is_not_reprocessed(self):
    def test_failed_sale_is_retried(self):
        # FakeGateway(fail_with=GatewayError("boom")) then a fresh FakeGateway with the order → OK, one row
    def test_pre_existing_failed_row_is_reused(self):
        # MembershipSale.objects.create(order_id="O1", status="FAILED") first, then process → the same pk, status OK
    def test_event_arriving_mid_fetch_does_not_create_a_second_term(self):
        # A FakeGateway subclass whose retrieve_order first calls process_order("O1", FakeGateway with the same order)
        # and then returns the order. The nested call (the "second event") finishes first; the outer one must find
        # the row OK after its fetch and stop: MembershipTerm.objects.count() == 1, one Member, sale.status "OK".
```

- [ ] **Step 2: Run to verify they fail**

Run: `.venv/bin/python manage.py test boxoffice.tests.test_memberships -v 2`
Expected: FAIL with `ModuleNotFoundError: No module named 'boxoffice.memberships'`

- [ ] **Step 3: Implement `boxoffice/memberships.py`** per the Interfaces block. Module docstring: one paragraph on what it does and that `MembershipSale.order_id` is the idempotency key. Use `MembershipSale.objects.get_or_create(order_id=order_id, defaults={"status": FAILED, "error": "Processing did not finish"})` before fetching, so a request killed mid-way still shows on the dashboard (the same pattern as `SalesPull`).

- [ ] **Step 4: Run to verify they pass, then flake8**

Run: `.venv/bin/python manage.py test boxoffice.tests.test_memberships -v 2 && .venv/bin/python -m flake8 boxoffice/memberships.py boxoffice/tests/test_memberships.py`
Expected: PASS, no flake8 output

- [ ] **Step 5: Commit**

```bash
git add boxoffice/memberships.py boxoffice/tests/test_memberships.py
git commit -m "feat(boxoffice): turn a Square membership order into a member and a term"
```

---

### Task 5: Signed webhook endpoint

**Files:**
- Create: `boxoffice/decorators.py`, `boxoffice/views.py`, `boxoffice/urls.py`
- Modify: `fortkentcinema/urls.py` (add `path("boxoffice/", include("boxoffice.urls"))` after the `phone/` line)
- Modify: `fortkentcinema/settings.py` (the two settings from Global Constraints)
- Test: `boxoffice/tests/test_webhook.py`

**Interfaces:**
- Consumes: Task 4's `process_order`.
- Produces:
  - `boxoffice.decorators.square_webhook(view)` — `csrf_exempt(require_POST(wrapped))`, same shape as `phone.decorators.twilio_webhook`. Blank `SQUARE_WEBHOOK_SIGNATURE_KEY` or `SQUARE_WEBHOOK_URL`: `logger.error`, 403. Verification: `verify_signature(request_body=request.body.decode("utf-8"), signature_header=request.META.get("HTTP_X_SQUARE_HMACSHA256_SIGNATURE", ""), signature_key=..., notification_url=settings.SQUARE_WEBHOOK_URL)`; False → `logger.warning`, 403.
  - `boxoffice.views.square_webhook(request)` — parse JSON (`json.JSONDecodeError`/non-dict → 400); `type != "order.updated"` → 200; `state != "COMPLETED"` → 200; else `process_order(order_id)` and 200. Order ID and state read from `data["data"]["object"]["order_updated"]`; a payload missing those keys → 400. Response body is empty.
  - URL name `boxoffice:square_webhook` at `/boxoffice/square/webhook/`.
- Test helper in `boxoffice/tests/test_webhook.py`: `KEY = "test-signature-key"`, `URL = "https://www.fortkentcinema.com/boxoffice/square/webhook/"`, `sign(body: str) -> str` returning `base64.b64encode(hmac.new(KEY.encode(), (URL + body).encode(), hashlib.sha256).digest()).decode()`, and `post(client, payload: dict, *, signature: str | None = "valid") -> HttpResponse` that serialises the payload, signs it unless told otherwise, and posts with `content_type="application/json"` and `HTTP_X_SQUARE_HMACSHA256_SIGNATURE`. `event(order_id="O1", state="COMPLETED", type="order.updated") -> dict` builds `{"type": type, "event_id": "E1", "data": {"type": "order_updated", "id": order_id, "object": {"order_updated": {"order_id": order_id, "state": state, "version": 2, "location_id": "LOC"}}}}`.

- [ ] **Step 1: Write the failing tests** (class decorated `@override_settings(SQUARE_WEBHOOK_SIGNATURE_KEY=KEY, SQUARE_WEBHOOK_URL=URL)`; `setUp` patches `boxoffice.views.process_order` as `self.process` unless the test says otherwise, and silences `boxoffice.decorators.logger`)

```python
class SignatureTests(TestCase):
    def test_missing_signature_is_403_with_no_side_effects(self):
        resp = post(self.client, event(), signature=None)
        self.assertEqual(resp.status_code, 403); self.process.assert_not_called()
    def test_forged_signature_is_403(self):          # signature="forged"
    def test_tampered_body_is_403(self):             # sign(json of event("O1")) sent with body of event("O2")
    @override_settings(SQUARE_WEBHOOK_SIGNATURE_KEY="")
    def test_blank_key_is_403(self):
    @override_settings(SQUARE_WEBHOOK_URL="")
    def test_blank_url_is_403(self):
    def test_get_is_405(self):
    def test_signature_is_over_the_registered_url_not_the_request_host(self):
        # a signature computed over "http://testserver/boxoffice/square/webhook/" + body is 403; over URL + body is 200

class DispatchTests(TestCase):
    def test_completed_order_is_processed(self):
        self.assertEqual(post(self.client, event("O9")).status_code, 200); self.process.assert_called_once_with("O9")
    def test_other_event_types_are_ignored(self):    # type="payment.updated" → 200, not called
    def test_open_order_is_ignored(self):            # state="OPEN" → 200, not called
    def test_malformed_json_is_400(self):            # body "{not json" signed → 400
    def test_payload_without_order_is_400(self):     # {"type": "order.updated", "data": {}} → 400
    def test_failed_outcome_still_returns_200(self):
        # self.process.return_value = MembershipSale(order_id="O9", status="FAILED", error="boom") → 200
        # (process_order never raises: Task 4 records every exception on the row)

class EndToEndTests(TestCase):
    def test_signed_event_creates_the_member(self):
        # no process patch; tier "individual" wired to INDIVIDUAL; mock.patch("boxoffice.memberships.get_gateway", return_value=FakeGateway with a membership order "O1")
        # post(event("O1")) → 200, Member.objects.filter(email="ann@example.com").exists(), MembershipSale.objects.get(order_id="O1").status == "OK"
```

- [ ] **Step 2: Run to verify they fail**

Run: `.venv/bin/python manage.py test boxoffice.tests.test_webhook -v 2`
Expected: FAIL with `NoReverseMatch` (or `ModuleNotFoundError` for `boxoffice.views`)

- [ ] **Step 3: Implement** the decorator, view, `boxoffice/urls.py` (`app_name = "boxoffice"`), the project URL include, and the two settings.

- [ ] **Step 4: Run to verify they pass, then flake8**

Run: `.venv/bin/python manage.py test boxoffice.tests.test_webhook phone.tests.test_signature -v 1 && .venv/bin/python -m flake8 boxoffice/decorators.py boxoffice/views.py boxoffice/urls.py boxoffice/tests/test_webhook.py fortkentcinema/urls.py`
Expected: PASS, no flake8 output

- [ ] **Step 5: Commit**

```bash
git add boxoffice/decorators.py boxoffice/views.py boxoffice/urls.py boxoffice/tests/test_webhook.py fortkentcinema/urls.py fortkentcinema/settings.py
git commit -m "feat(boxoffice): signed Square webhook for completed orders"
```

---

### Task 6: Dashboard alert, sales list and Retry

**Files:**
- Modify: `dashboard/smart_alerts.py` (new keyword `square_membership_failures: int = 0`)
- Modify: `dashboard/views.py:91-108` (`HomeView.get_context_data` passes the count)
- Create: `dashboard/membership_sale_views.py`
- Create: `dashboard/templates/dashboard/square_sales.html`, `dashboard/templates/dashboard/_square_sale_row.html`
- Modify: `dashboard/urls.py` (two routes, after the `memberships/benefits/...` entries)
- Modify: `dashboard/templates/dashboard/tiers.html` (a link to the sales list in the page header, text "Square sales")
- Test: `dashboard/tests/test_smart_alerts.py`, `dashboard/tests/test_home.py`, `dashboard/tests/test_square_sales.py`

**Interfaces:**
- Consumes: Task 2's `MembershipSale`, Task 4's `process_order`.
- Produces:
  - Alert id `square-membership-failed`, type `warning`, message per Global Constraints, appended after the `square-sync-failed` block.
  - `HomeView` passes `square_membership_failures=MembershipSale.objects.filter(status=MembershipSale.Status.FAILED).count()`.
  - `dashboard.membership_sale_views.SquareSaleListView(StaffRequiredMixin, View)` — GET renders `square_sales.html` with `sales = MembershipSale.objects.select_related("tier", "term__member")` (model ordering) and `failed_count`.
  - `dashboard.membership_sale_views.SquareSaleRetryView(StaffRequiredMixin, View)` — POST: `sale = get_object_or_404(MembershipSale, pk=pk)`; `process_order(sale.order_id)`; re-fetch the row; render `_square_sale_row.html` for it and return it with an `HX-Trigger` toast (`{"dashboard-toast": {"kind": "success" if OK else "error", "message": "Entered: <name>" / "Skipped" / sale.error}}`) — same header shape as `_showtime_list_response` in `dashboard/views.py`. A non-htmx POST redirects to the list.
  - URLs: `memberships/square-sales` → `dashboard:square_sales`; `memberships/square-sales/<int:pk>/retry` → `dashboard:square_sale_retry`.
  - `MembershipSale.gross_dollars` property (added in this task): `Decimal(self.gross_cents) / 100`.
  - Row template: `<tr id="square-sale-{{ sale.pk }}">` with cells: purchase date (`sale.purchase_date|date:"M j, Y"` or "—"), tier name or "—", buyer (`display_name` and `email`, each "—" when blank), amount (`${{ sale.gross_dollars|floatformat:2 }}`), status pill (`status-active` for OK, `status-draft` for SKIPPED, `status-cancelled` for FAILED, using the status label), member column (link to `dashboard:member_detail` for `sale.term.member`; "term removed" when OK and `term` is null; "—" otherwise), error text in a `fieldHint`, and for FAILED rows a Retry form `hx-post="{% url 'dashboard:square_sale_retry' sale.pk %}" hx-target="#square-sale-{{ sale.pk }}" hx-swap="outerHTML"` with the CSRF token and a `btn btn-secondary btn-sm` button.
  - Page template extends `dashboard/base_dashboard.html` like `voicemails.html`: title "Square membership sales · LeprinceOS", subtitle `{{ failed_count }} need{{ failed_count|pluralize:"s," }} attention` (render exactly: 1 → "1 needs attention", 2 → "2 need attention"), the table with headers Purchased / Tier / Buyer / Amount / Status / Member, rows via `{% include "dashboard/_square_sale_row.html" %}`, and an empty state "No Square membership sales yet" / "They'll show up here when someone pays through a membership link."

- [ ] **Step 1: Write the failing alert tests** in `dashboard/tests/test_smart_alerts.py`

```python
def test_square_membership_failed_pluralises(self) -> None:
    one = build_smart_alerts([], 1, self.today, square_membership_failures=1)
    self.assertIn("1 Square membership sale needs attention", [a["message"] for a in one])
    two = build_smart_alerts([], 1, self.today, square_membership_failures=2)
    self.assertIn("2 Square membership sales need attention", [a["message"] for a in two])
    self.assertNotIn("square-membership-failed", self._square_ids())
```

and in `dashboard/tests/test_home.py`, in `HomeRenderTests` next to `test_sales_panel_with_sales_and_failed_pull_alert`:

```python
def test_failed_membership_sale_alert(self) -> None:
    MembershipSale.objects.create(order_id="O1", status="FAILED", error="boom")
    MembershipSale.objects.create(order_id="O2", status="SKIPPED")
    html = self.client.get(reverse("dashboard:home")).content.decode()
    self.assertIn("1 Square membership sale needs attention", html)
```

- [ ] **Step 2: Run to verify they fail**

Run: `.venv/bin/python manage.py test dashboard.tests.test_smart_alerts dashboard.tests.test_home -v 1`
Expected: the two new tests FAIL (`TypeError: unexpected keyword argument` / assertion); the rest pass.

- [ ] **Step 3: Add the alert and the HomeView count.** Run the same command; expected PASS.

- [ ] **Step 4: Write the failing view tests** in `dashboard/tests/test_square_sales.py` (reuse the `StaffTestCase` pattern from `test_square_views.py`; a helper `make_sale(**over)` creating a FAILED `MembershipSale` with `order_id="O1"`, `email="ann@example.com"`, `display_name="Ann Lee"`, `error="boom"`)

```python
class StaffOnlyTests(TestCase):
    def test_list_and_retry_require_staff(self):
        # anonymous GET list → 302 to login; anonymous POST retry → 302; logged-in non-staff → 403 on both

class ListTests(StaffTestCase):
    def test_lists_sales_newest_first_with_status_and_member(self):
        # one OK sale linked to a term for member Ann (closed_at Oct 2), one FAILED (closed_at Oct 3) → FAILED row first; html contains "Needs attention", "Entered", "Ann Lee", reverse("dashboard:member_detail", args=[member.pk]), "boom", "$60.00"
    def test_ok_sale_whose_term_was_deleted_says_so(self):     # "term removed"
    def test_retry_only_on_failed_rows(self):                  # retry URL present for FAILED, absent for OK and SKIPPED
    def test_empty_state(self):                                # "No Square membership sales yet"
    def test_subtitle_counts_failed(self):                     # "1 needs attention" / "2 need attention"

class RetryTests(StaffTestCase):
    def test_retry_runs_process_order_and_swaps_the_row(self):
        # mock.patch("dashboard.membership_sale_views.process_order") that flips the row to OK with a term → resp 200, 'id="square-sale-<pk>"' in html, "Entered" in html, json.loads(resp["HX-Trigger"])["dashboard-toast"]["kind"] == "success"; called with "O1"
    def test_retry_that_fails_again_toasts_the_error(self):    # process leaves FAILED error "still boom" → toast kind "error", message "still boom", Retry button still in html
    def test_non_htmx_post_redirects_to_the_list(self):        # no HX-Request header → 302 to reverse("dashboard:square_sales")
    def test_unknown_sale_is_404(self):
```

- [ ] **Step 5: Run to verify they fail**

Run: `.venv/bin/python manage.py test dashboard.tests.test_square_sales -v 2`
Expected: FAIL with `NoReverseMatch: 'square_sales'`

- [ ] **Step 6: Implement** the views module, the two templates, the URL entries, the `gross_dollars` property on `MembershipSale`, and the "Square sales" link in `tiers.html`'s `.actions` div before "Terms sold" (`<a class="btn btn-secondary" href="{% url 'dashboard:square_sales' %}">Square sales</a>`).

- [ ] **Step 7: Run the dashboard suite and flake8**

Run: `.venv/bin/python manage.py test dashboard boxoffice -v 1 && .venv/bin/python -m flake8 dashboard/membership_sale_views.py dashboard/smart_alerts.py dashboard/tests/test_square_sales.py boxoffice/models/membership_sale.py`
Expected: PASS, no flake8 output

- [ ] **Step 8: Commit**

```bash
git add dashboard/smart_alerts.py dashboard/views.py dashboard/membership_sale_views.py dashboard/urls.py dashboard/templates/dashboard/square_sales.html dashboard/templates/dashboard/_square_sale_row.html dashboard/templates/dashboard/tiers.html dashboard/tests/test_smart_alerts.py dashboard/tests/test_home.py dashboard/tests/test_square_sales.py boxoffice/models/membership_sale.py
git commit -m "feat(dashboard): Square membership sales list with alert and Retry"
```

---

### Task 7: Rollout notes and full-suite check

**Files:**
- Modify: `docs/superpowers/specs/2026-10-09-square-membership-webhook-design.md` (set `**Status:** Implemented on feat/square-membership-webhook`; add an "Amendments" section if any task deviated from the spec — at minimum note the `Processing did not finish` placeholder row and the `Order has no closed_at` failure, which the spec did not name)
- Modify: `CLAUDE.md` only if it exists and documents settings (it does not at the time of writing; skip otherwise)

- [ ] **Step 1: Run the full suite in parallel**

Run: `.venv/bin/python manage.py test --parallel 4 2>&1 | grep -E '^(Ran|OK|FAILED)'`
Expected: `Ran <N> tests` with N ≥ 1879 + the tests added above, then `OK`

- [ ] **Step 2: Run `makemigrations --check`** to confirm no migration is missing

Run: `.venv/bin/python manage.py makemigrations --check --dry-run`
Expected: `No changes detected`

- [ ] **Step 3: Smoke the signature against the real helper** with the settings pointed at a local URL

Run (one shell command):
```bash
SQUARE_WEBHOOK_SIGNATURE_KEY=k SQUARE_WEBHOOK_URL=http://testserver/boxoffice/square/webhook/ .venv/bin/python -c "
import django, os; os.environ.setdefault('DJANGO_SETTINGS_MODULE','fortkentcinema.settings'); django.setup()
import base64, hashlib, hmac, json
from django.test import Client
body = json.dumps({'type': 'order.updated', 'data': {'object': {'order_updated': {'order_id': 'X', 'state': 'OPEN'}}}})
sig = base64.b64encode(hmac.new(b'k', ('http://testserver/boxoffice/square/webhook/' + body).encode(), hashlib.sha256).digest()).decode()
print(Client().post('/boxoffice/square/webhook/', body, content_type='application/json', HTTP_X_SQUARE_HMACSHA256_SIGNATURE=sig).status_code)
"
```
Expected: `200` (an OPEN order is ignored, but the signature passed). This uses the real sqlite database read-only; nothing is written for an OPEN order.

- [ ] **Step 4: Update the spec status and amendments; commit**

```bash
git add docs/superpowers/specs/2026-10-09-square-membership-webhook-design.md
git commit -m "docs: mark the Square membership webhook spec implemented"
```

---

### Task 8: Trigger on the payment, not the order's completion (added after the final review, 2026-10-09)

**Why:** The nine live payment-link orders were all created at checkout but reached `COMPLETED` days later, in bursts seconds apart, when staff marked their shipments done in Square. `order.updated` with `COMPLETED` therefore fires on that click, not on payment, and an order fetched at payment time is `OPEN` with no `closed_at`, which the current code records as FAILED. Square's `payment.created` arrives as `APPROVED`; `payment.updated` fires when the payment completes. The payment moment on the fetched order is its first tender's `created_at` (one to two minutes after the order's `created_at` on every live sale).

**Files:**
- Modify: `boxoffice/gateway.py` (`OrderData` gains `paid_at: datetime | None = None` set from the first tender's `created_at`, else the order's `created_at`, else `None`; both `_order_data` paths)
- Modify: `boxoffice/tests/fakes.py` only if a helper needs it; `boxoffice/tests/test_gateway.py` (tender parsing)
- Modify: `boxoffice/models/membership_sale.py` + `boxoffice/migrations/0007_membershipsale_paid_at.py` (generated `RenameField` `closed_at` → `paid_at`; `purchase_date` reads `paid_at`; the ordering comment follows)
- Modify: `boxoffice/memberships.py` (`paid_at` replaces `closed_at` everywhere; the FAILED copy becomes `Order has no payment time`; `order_never_fetched` tests `paid_at is None`)
- Modify: `boxoffice/views.py` (accept `type in {"payment.created", "payment.updated"}`; require `data.object.payment.status == "COMPLETED"`; `order_id = data.object.payment.order_id`; a payment with no `order_id` → 200, nothing recorded; `order.updated` and every other type → 200, nothing recorded; missing `payment` object or keys → 400)
- Modify: `boxoffice/admin.py`, `dashboard/membership_sale_views.py`, `dashboard/templates/dashboard/_square_sale_row.html` (field rename only)
- Modify: tests `boxoffice/tests/test_memberships.py`, `boxoffice/tests/test_webhook.py`, `boxoffice/tests/test_models.py`, `dashboard/tests/test_square_sales.py`, `dashboard/tests/test_home.py` (rename; the webhook `event()` helper builds a payment event: `{"type": "payment.updated", "event_id": "E1", "data": {"type": "payment", "id": "<payment id>", "object": {"payment": {"id": "<payment id>", "order_id": order_id, "status": status, "created_at": "..."}}}}`)
- Modify: spec `docs/superpowers/specs/2026-10-09-square-membership-webhook-design.md` (Section 1 event name and view steps, Section 3 purchase date, Rollout step 3 ticks `payment.updated` only, an Amendments bullet explaining the finding), and the plan's Global Constraints copy line.

**Interfaces:**
- `OrderData.paid_at` — aware datetime or `None`; `closed_at` stays for the nightly pull.
- `MembershipSale.paid_at` — same meaning as the old `closed_at` column, correctly sourced.
- View contract: `payment.updated` or `payment.created` with `status == "COMPLETED"` → `process_order(order_id)`; 503 when `order_never_fetched`; otherwise 200.

- [ ] **Step 1: Gateway tests** — a tender mock `mock.Mock(created_at="2026-09-29T15:11:16Z", payment_id="P1")` on `tenders=[...]` yields `paid_at` equal to that instant; `tenders=None` falls back to the order's `created_at`; both `None` → `paid_at is None`. Run `boxoffice.tests.test_gateway`; expect failures on the missing field; implement; expect pass.
- [ ] **Step 2: Rename and memberships** — `makemigrations boxoffice -n membershipsale_paid_at` must produce a `RenameField`. Update `memberships.py` and its tests (`membership_order` helper takes `paid_at=`; the Eastern-day test uses a late-evening UTC `paid_at`; the `closed_at=None` test becomes `test_missing_payment_time_fails` with the new copy). Run `boxoffice.tests.test_memberships boxoffice.tests.test_models`; expect pass.
- [ ] **Step 3: Webhook** — rewrite the `event()` helper and dispatch tests: `payment.updated` COMPLETED → processed; `payment.created` COMPLETED → processed; `payment.updated` APPROVED → 200 not called; `order.updated` COMPLETED → 200 not called; payment without `order_id` → 200 not called; missing `payment` object → 400. End-to-end test unchanged in substance. Run `boxoffice.tests.test_webhook`; expect pass.
- [ ] **Step 4: Dashboard rename** — admin, views, row template, tests. Run `dashboard`; expect pass.
- [ ] **Step 5: Docs** — spec and plan edits above.
- [ ] **Step 6: Full suite, `makemigrations --check`, flake8 on touched files; commit** `feat(boxoffice): trigger membership entry on the payment, not the order's completion`.
